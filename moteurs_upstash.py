#!/usr/bin/env python3
import hashlib, hmac, secrets, time, os, requests, threading, json
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from web3 import Web3
from urllib.parse import urlparse

PORT = int(os.getenv("PORT", "10000"))
UPSTASH_URL = os.getenv("UPSTASH_REDIS_REST_URL", "")
UPSTASH_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN", "")
SEUIL = 0.00000001
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
    print(f"[{INSTANCE}] {msg}", flush=True)

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
            hits_len = redis(["LLEN", "hits"]) or 0
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"tested": int(count), "hits": hits_len, "rpc_pool": len(RPC_POOL), "instance": INSTANCE}).encode())
        elif path == "/api/hits":
            hits = redis(["LRANGE", "hits", "0", "99"]) or []
            data = []
            for h in hits:
                raw = redis(["GET", f"hit:{h}"]) or ""
                parts = raw.split("|")
                data.append({
                    "date": parts[0] if len(parts)>0 else "",
                    "address": parts[1] if len(parts)>1 else h,
                    "mnemonic": parts[2] if len(parts)>2 else "",
                    "balance": float(parts[3]) if len(parts)>3 else 0
                })
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
table{width:100%;border-collapse:collapse}
th,td{padding:8px;text-align:left;border-bottom:1px solid #334155}
th{cursor:pointer;color:#94a3b8}
.hit{color:#4ade80}
</style>
</head>
<body>
<h1>X-M Ethereum Scanner</h1>
<div class=\"card\">
  <h2>Statistiques</h2>
  <p>Adresses testées : <strong id=\"tested\">...</strong></p>
  <p>Hits : <strong id=\"hits\">...</strong></p>
  <p>RPC dans le pool : <strong id=\"rpc\">...</strong></p>
  <p>Instance : <strong id=\"instance\">...</strong></p>
  <button onclick=\"load()\">Actualiser</button>
</div>
<div class=\"card\">
  <h2>Résultats (hits)</h2>
  <table id=\"table\">
    <thead>
      <tr>
        <th onclick=\"sort('date')\">Date</th>
        <th>Adresse</th>
        <th>12 mots</th>
        <th onclick=\"sort('balance')\">Solde ETH</th>
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
  document.getElementById('hits').textContent = s.hits;
  document.getElementById('rpc').textContent = s.rpc_pool || '-';
  document.getElementById('instance').textContent = s.instance || '-';
  data = await fetch('/api/hits').then(r=>r.json());
  render();
}
function render(){
  const tb = document.getElementById('tbody');
  tb.innerHTML = data.map(d=>`<tr class=\"hit\">
    <td>${d.date}</td>
    <td>${d.address}</td>
    <td style=\"font-size:0.8em\">${d.mnemonic}</td>
    <td>${d.balance}</td>
  </tr>`).join('') || '<tr><td colspan=\"4\">Aucun hit pour le moment</td></tr>';
}
function sort(key){
  data.sort((a,b)=> key==='balance' ? b.balance-a.balance : a.date.localeCompare(b.date));
  render();
}
load();
setInterval(load, 8000);
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

def derive(mnemonic: str) -> str:
    seed = hashlib.pbkdf2_hmac("sha512", mnemonic.encode(), b"mnemonic", 2048)
    I = hmac.new(b"Bitcoin seed", seed, hashlib.sha512).digest()
    return Web3().eth.account.from_key(I[:32]).address

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
    log("=== Moteur démarré (partagé) ===")
    log(f"Pool size: {len(RPC_POOL)}")
    threading.Thread(target=health_server, daemon=True).start()
    n = 0
    rpc_idx = 0
    while True:
        n += 1
        try:
            mnemonic = generer_mnemonic()
            addr = derive(mnemonic)
            if deja_teste(addr):
                if n % 50 == 0:
                    log(f"cycle {n} skip")
                continue
            marquer_teste(addr)
            eth, rpc_used = get_balance_rotated(addr, rpc_idx)
            rpc_idx += 1
            if eth is not None and eth > SEUIL:
                payload = f"{datetime.utcnow().isoformat()}|{addr}|{mnemonic}|{eth}|{INSTANCE}"
                redis(["SET", f"hit:{addr.lower()}", payload])
                redis(["LPUSH", "hits", addr.lower()])
                log(f"HIT {addr} {eth} via {rpc_used}")
        except Exception as e:
            log(f"LOOP ERR: {e}")
        if n % 30 == 0:
            count = redis(["GET", "tested_count"]) or 0
            log(f"cycle {n} | testés: {count}")
        time.sleep(0.15)

if __name__ == "__main__":
    main()
