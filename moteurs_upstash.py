#!/usr/bin/env python3
import hashlib, hmac, secrets, time, os, requests, threading, json
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from web3 import Web3
from urllib.parse import urlparse

PORT = int(os.getenv("PORT", "10000"))
UPSTASH_URL = os.getenv("UPSTASH_REDIS_REST_URL", "")
UPSTASH_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN", "")
SEUIL = 0.00001
INSTANCE = os.getenv("INSTANCE_NAME", "xm-1")
INSTANCE_SEED = int(hashlib.sha256(INSTANCE.encode()).hexdigest()[:8], 16)

RPC_POOL = [
    "https://ethereum.publicnode.com",
    "https://rpc.ankr.com/eth",
    "https://eth.llamarpc.com",
    "https://cloudflare-eth.com",
    "https://eth.drpc.org",
    "https://1rpc.io/eth",
    "https://eth.merkle.io",
    "https://rpc.flashbots.net",
    "https://eth-mainnet.public.blastapi.io",
    "https://ethereum.blockpi.network/v1/rpc/public"
]

WORDLIST = ["abandon","ability","able","about","above","absent","absorb","abstract","absurd","abuse"] * 205

def log(msg):
    print(f"[{INSTANCE}] {datetime.utcnow().isoformat()} | {msg}", flush=True)

def redis(cmd):
    if not UPSTASH_URL: return None
    try:
        r = requests.post(UPSTASH_URL, headers={"Authorization": f"Bearer {UPSTASH_TOKEN}"}, json=cmd, timeout=4)
        return r.json().get("result")
    except Exception as e:
        log(f"REDIS ERR: {e}")
        return None

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/health", "/healthz"):
            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"ok")
        elif path in ("/dashboard", "/dashboard_global.html"):
            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            try:
                with open("dashboard_global.html", "rb") as f:
                    self.wfile.write(f.read())
            except:
                self.wfile.write(b"<h1>Dashboard not found</h1>")
        elif path == "/api/stats":
            count = redis(["GET", "tested_count"]) or "0"
            set_size = redis(["SCARD", "tested"]) or 0
            hits_len = redis(["LLEN", "hits"]) or 0
            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "tested": int(count),
                "set_size": int(set_size),
                "hits": hits_len,
                "rpc_pool": len(RPC_POOL),
                "instance": INSTANCE,
                "seed": INSTANCE_SEED
            }).encode())
        elif path == "/api/hits":
            hits = redis(["LRANGE", "hits", "0", "49"]) or []
            data = []
            for h in hits:
                raw = redis(["GET", f"hit:{h}"]) or ""
                try:
                    obj = json.loads(raw)
                except:
                    obj = {"raw": raw}
                data.append(obj)
            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(data).encode())
        else:
            self.send_response(404)
            self.end_headers()
    def log_message(self, *args): pass

def health_server():
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()

def deja_teste(addr: str) -> bool:
    return redis(["SISMEMBER", "tested", addr.lower()]) == 1

def marquer_teste(addr: str):
    redis(["SADD", "tested", addr.lower()])
    redis(["INCR", "tested_count"])

def generer_mnemonic(counter: int) -> str:
    entropy = hashlib.sha256(f"{INSTANCE_SEED}:{counter}".encode()).digest()[:16]
    checksum = hashlib.sha256(entropy).digest()[0] >> 4
    bits = int.from_bytes(entropy, "big")
    bits = (bits << 4) | checksum
    return " ".join(WORDLIST[(bits >> (11 * (11 - i))) & 0x7FF] for i in range(12))

def derive(mnemonic: str):
    seed = hashlib.pbkdf2_hmac("sha512", mnemonic.encode(), b"mnemonic", 2048)
    I = hmac.new(b"Bitcoin seed", seed, hashlib.sha512).digest()
    priv = I[:32].hex()
    acct = Web3().eth.account.from_key(priv)
    return acct.address, priv, mnemonic

def get_balance_rotated(addr: str, rpc_index: int):
    url = RPC_POOL[rpc_index % len(RPC_POOL)]
    try:
        w3 = Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": 5}))
        wei = w3.eth.get_balance(addr)
        return float(w3.from_wei(wei, "ether")), url
    except Exception as e:
        log(f"RPC fail {url}: {e}")
        return None, url

def main():
    log(f"=== Moteur démarré | seed: {INSTANCE_SEED} ===")
    log(f"Pool size: {len(RPC_POOL)} | Seuil: {SEUIL}")
    threading.Thread(target=health_server, daemon=True).start()
    n = 0
    rpc_idx = 0
    skips = 0
    while True:
        n += 1
        try:
            addr, priv, mnemonic = derive(generer_mnemonic(n))
            if deja_teste(addr):
                skips += 1
                if skips % 200 == 0:
                    log(f"skips cumulés: {skips}")
                continue
            marquer_teste(addr)
            eth, rpc_used = get_balance_rotated(addr, rpc_idx)
            rpc_idx += 1
            if eth is not None and eth > SEUIL:
                hit = {
                    "date": datetime.utcnow().isoformat(),
                    "address": addr,
                    "private_key": priv,
                    "mnemonic": mnemonic,
                    "balance": eth,
                    "rpc": rpc_used,
                    "instance": INSTANCE
                }
                redis(["SET", f"hit:{addr.lower()}", json.dumps(hit)])
                redis(["LPUSH", "hits", addr.lower()])
                log(f"HIT {addr} | {eth} ETH | priv:{priv[:10]}... | via {rpc_used}")
        except Exception as e:
            log(f"LOOP ERR: {e}")
        if n % 50 == 0:
            count = redis(["GET", "tested_count"]) or 0
            set_size = redis(["SCARD", "tested"]) or 0
            log(f"cycle {n} | testés: {count} | set: {set_size} | skips: {skips}")
        time.sleep(0.15)

if __name__ == "__main__":
    main()
