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

def mnemonic_to_seed(mnemonic: str, passphrase: str = "") -> bytes:
    return hashlib.pbkdf2_hmac("sha512", mnemonic.encode(), ("mnemonic" + passphrase).encode(), 2048)

def derive_eth_address(mnemonic: str) -> str:
    seed = mnemonic_to_seed(mnemonic)
    I = hmac.new(b"Bitcoin seed", seed, hashlib.sha512).digest()
    key = I[:32]
    acct = Web3().eth.account.from_key(key)
    return acct.address

def generer_mnemonic() -> str:
    entropy = secrets.token_bytes(16)
    checksum = hashlib.sha256(entropy).digest()[0] >> 4
    bits = int.from_bytes(entropy, "big")
    bits = (bits << 4) | checksum
    words = [WORDLIST[(bits >> (11 * (11 - i))) & 0x7FF] for i in range(12)]
    return " ".join(words)

def main():
    print("Moteur BIP39 démarré")
    threading.Thread(target=health_server, daemon=True).start()
    w3 = Web3(Web3.HTTPProvider("https://ethereum.publicnode.com"))
    headers = {"Authorization": f"Bearer {UPSTASH_TOKEN}"}
    n = 0
    while True:
        n += 1
        mnemonic = generer_mnemonic()
        try:
            addr = derive_eth_address(mnemonic)
            wei = w3.eth.get_balance(addr)
            eth = float(w3.from_wei(wei, "ether"))
            if eth > SEUIL and UPSTASH_URL:
                payload = f"{datetime.utcnow().isoformat()}|{addr}|{mnemonic}|{eth}"
                requests.post(UPSTASH_URL, headers=headers, json=["SET", f"hit:{addr.lower()}", payload], timeout=4)
                print(f"HIT {addr} {eth}")
        except Exception as e:
            print("err", e)
        if n % 20 == 0:
            print(f"cycle {n}")
        time.sleep(0.2)

if __name__ == "__main__":
    main()
