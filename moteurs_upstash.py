#!/usr/bin/env python3
import hashlib, secrets, time, os, requests, threading
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from web3 import Web3

PORT = int(os.getenv("PORT", "10000"))
UPSTASH_URL = os.getenv("UPSTASH_REDIS_REST_URL", "")
UPSTASH_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN", "")
SEUIL = 0.00000001

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"ok")
    def log_message(self, *args): pass

def health_server():
    HTTPServer(("0.0.0.0", PORT), HealthHandler).serve_forever()

def main():
    print("Moteur simplifié démarré")
    threading.Thread(target=health_server, daemon=True).start()
    w3 = Web3(Web3.HTTPProvider("https://ethereum.publicnode.com"))
    headers = {"Authorization": f"Bearer {UPSTASH_TOKEN}"}
    n = 0
    while True:
        n += 1
        acct = w3.eth.account.create()
        addr = acct.address
        try:
            wei = w3.eth.get_balance(addr)
            eth = float(w3.from_wei(wei, "ether"))
            if eth > SEUIL and UPSTASH_URL:
                requests.post(UPSTASH_URL, headers=headers, json=["SET", f"hit:{addr.lower()}", f"{datetime.utcnow().isoformat()}|{addr}|{eth}"], timeout=4)
                print(f"HIT {addr} {eth}")
        except Exception as e:
            print("err", e)
        if n % 20 == 0:
            print(f"cycle {n}")
        time.sleep(0.2)

if __name__ == "__main__":
    main()
