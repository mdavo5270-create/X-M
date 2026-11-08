#!/usr/bin/env python3
import hashlib, hmac, secrets, time, os, requests, threading
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from web3 import Web3

PORT = int(os.getenv("PORT", "10000"))
UPSTASH_URL = os.getenv("UPSTASH_REDIS_REST_URL", "")
UPSTASH_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN", "")
SEUIL = 0.00000001

WORDLIST = ["abandon","ability","able","about","above","absent","absorb","abstract","absurd","abuse"] * 205

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"ok")
    def log_message(self, *args): pass

def health_server():
    HTTPServer(("0.0.0.0", PORT), HealthHandler).serve_forever()

def redis(cmd):
    if not UPSTASH_URL: return None
    try:
        r = requests.post(UPSTASH_URL, headers={"Authorization": f"Bearer {UPSTASH_TOKEN}"}, json=cmd, timeout=4)
        return r.json().get("result")
    except:
        return None

def deja_teste(addr: str) -> bool:
    return redis(["SISMEMBER", "tested", addr.lower()]) == 1

def marquer_teste(addr: str):
    redis(["SADD", "tested", addr.lower()])
    redis(["INCR", "tested_count"])

def generer_mnemonic() -> str:
    entropy = secrets.token_bytes(16)
    checksum = hashlib.sha256(entropy).digest()[0] >> 4
    bits = int.from_bytes(entropy, "big")
    bits = (bits << 4) | checksum
    return " ".join(WORDLIST[(bits >> (11 * (11 - i))) & 0x7FF] for i in range(12))

def derive(mnemonic: str) -> str:
    seed = hashlib.pbkdf2_hmac("sha512", mnemonic.encode(), b"mnemonic", 2048)
    I = hmac.new(b"Bitcoin seed", seed, hashlib.sha512).digest()
    return Web3().eth.account.from_key(I[:32]).address

def main():
    print("Moteur démarré (dédup + compteur)")
    threading.Thread(target=health_server, daemon=True).start()
    w3 = Web3(Web3.HTTPProvider("https://ethereum.publicnode.com"))
    n = 0
    while True:
        n += 1
        mnemonic = generer_mnemonic()
        try:
            addr = derive(mnemonic)
            if deja_teste(addr):
                if n % 50 == 0:
                    print("skip doublon")
                continue
            marquer_teste(addr)
            wei = w3.eth.get_balance(addr)
            eth = float(w3.from_wei(wei, "ether"))
            if eth > SEUIL:
                payload = f"{datetime.utcnow().isoformat()}|{addr}|{mnemonic}|{eth}"
                redis(["SET", f"hit:{addr.lower()}", payload])
                redis(["LPUSH", "hits", addr.lower()])
                print(f"HIT {addr} {eth}")
        except Exception as e:
            print("err", e)
        if n % 30 == 0:
            count = redis(["GET", "tested_count"]) or 0
            print(f"cycle {n} | testés: {count}")
        time.sleep(0.15)

if __name__ == "__main__":
    main()
