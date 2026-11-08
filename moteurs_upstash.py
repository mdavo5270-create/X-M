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
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"ok")
        elif path == "/dashboard":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(DASHBOARD_HTML.encode())
        elif path == "/api/stats":
            count = redis(["GET", "tested_count"]) or "0"
            set_size = redis(["SCARD", "tested"]) or 0
            hits_len = redis(["LLEN", "hits"]) or 0
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "tested": int(count),
                "set_size": int(set_size),
                "hits": hits_len,
                "rpc_pool": len(RPC_POOL),
                "instance": INSTANCE
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
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(data).encode())
        else:
            self.send_response(404)
            self.end_headers()
    def log_message(self, *args): pass

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang=\"fr\">
<head>
<meta charset=\"UTF-8\">
<title>X-M Dashboard</title>
<style>
body{font-family:system-ui;background:#0f172a;color:#e2e8f0;padding:20px}
.card{background:#1e293b;border-radius:12px;padding:16px;margin:10px 0}
h1{color:#38bdf8}
table{width:100%;border-collapse:collapse;font-size:0.85em}
th,td{padding:6px;text-align:left;border-bottom:1px solid #334155}
th{cursor:pointer;color:#94a3b8}
.hit{color:#4ade80}
</style>
</head>
<body>
<h1>X-M Ethereum Scanner</h1>
<div class=\"card\">
  <h2>Statistiques</h2>
  <p>Adresses testées : <strong id=\"tested\">...</strong></p>
  <p>Taille du set : <strong id=\"set_size\">...</strong></p>
  <p>Hits : <strong id=\"hits\">...</strong></p>
  <p>Instance : <strong id=\"instance\">...</strong></p>
  <button onclick=\"load()\">Actualiser</button>
</div>
<div class=\"card\">
  <h2>Hits (clé privée + publique + solde)</h2>
  <table id=\"table\">
    <thead>
      <tr>
        <th>Date</th>
        <th>Adresse</th>
        <th>Clé privée</th>
        <th>Solde ETH</th>
        <th>Instance</th>
      </tr>
    </thead>
    <tbody id=\"tbody\"></tbody>
  </table>
</div>
<script>
let data = [];
async function load(){
  const s = await fetch('/api/stats').then(r=>r.json());
  document.getElementById('tested').textContent = s.tested;
  document.getElementById('set_size').textContent = s.set_size;
  document.getElementById('hits').textContent = s.hits;
  document.getElementById('instance').textContent = s.instance || '-';
  data = await fetch('/api/hits').then(r=>r.json());
  render();
}
function render(){
  const tb = document.getElementById('tbody');
  tb.innerHTML = data.map(d=>`<tr class=\"hit\">
    <td>${d.date||''}</td>
    <td>${d.address||''}</td>
    <td style=\"font-size:0.7em\">${d.private_key||''}</td>
    <td>${d.balance||0}</td>
    <td>${d.instance||''}</td>
  </tr>`).join('') || '<tr><td colspan=\"5\">Aucun hit pour le moment</td></tr>';
}
load();
setInterval(load, 10000);
</script>
</body>
</html>
"""

def health_server():
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()

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
    log("=== Moteur démarré (hits complets) ===")
    log(f"Pool size: {len(RPC_POOL)} | Seuil: {SEUIL}")
    threading.Thread(target=health_server, daemon=True).start()
    n = 0
    rpc_idx = 0
    skips = 0
    while True:
        n += 1
        try:
            addr, priv, mnemonic = derive(generer_mnemonic())
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
