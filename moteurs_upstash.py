#!/usr/bin/env python3
import hashlib, secrets, time, os, requests, threading
from datetime import datetime
from typing import Optional, Dict, Any
from http.server import HTTPServer, BaseHTTPRequestHandler
from web3 import Web3
from bip_utils import Bip39SeedGenerator, Bip44, Bip44Coins, Bip44Changes

try:
    with open("bip39_english.txt") as f:
        BIP39_WORDLIST = [line.strip() for line in f if line.strip()]
except:
    BIP39_WORDLIST = ["abandon"] * 2048

SEUIL_ETH = 0.00000001
UPSTASH_URL = os.getenv("UPSTASH_REDIS_REST_URL", "")
UPSTASH_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN", "")
PORT = int(os.getenv("PORT", "10000"))

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/health", "/healthz"):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"ok")
        else:
            self.send_response(404)
            self.end_headers()
    def log_message(self, format, *args):
        pass

def start_health_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    print(f"Health endpoint on :{PORT}/health")
    server.serve_forever()

class Generateur:
    def generer(self) -> str:
        entropy = secrets.token_bytes(16)
        checksum = hashlib.sha256(entropy).digest()[0] >> 4
        bits = int.from_bytes(entropy, "big")
        bits = (bits << 4) | checksum
        return " ".join(BIP39_WORDLIST[(bits >> (11 * (11 - i))) & 0x7FF] for i in range(12))

class Convertisseur:
    def convertir(self, mnemonic: str) -> Optional[str]:
        try:
            seed = Bip39SeedGenerator(mnemonic).Generate()
            bip = Bip44.FromSeed(seed, Bip44Coins.ETHEREUM)
            acc = bip.Purpose().Coin().Account(0).Change(Bip44Changes.CHAIN_EXT).AddressIndex(0)
            return acc.PublicKey().ToAddress()
        except:
            return None

class Verificateur:
    def __init__(self):
        self.w3 = Web3(Web3.HTTPProvider("https://ethereum.publicnode.com"))
    def verifier(self, adresse: str) -> Dict[str, Any]:
        try:
            checksum = Web3.to_checksum_address(adresse)
            wei = self.w3.eth.get_balance(checksum)
            return {"ok": True, "solde_eth": float(self.w3.from_wei(wei, "ether")), "solde_wei": wei}
        except Exception as e:
            return {"ok": False, "erreur": str(e)}

class SignaleurRedis:
    def __init__(self):
        self.headers = {"Authorization": f"Bearer {UPSTASH_TOKEN}"}
    def _redis(self, cmd):
        if not UPSTASH_URL: return
        try:
            requests.post(UPSTASH_URL, headers=self.headers, json=cmd, timeout=5)
        except:
            pass
    def traiter(self, mnemonic, adresse, info):
        if not info.get("ok") or info.get("solde_eth", 0) <= SEUIL_ETH:
            return False
        key = f"hit:{adresse.lower()}"
        data = f"{datetime.utcnow().isoformat()}|{adresse}|{mnemonic}|{info['solde_eth']}"
        self._redis(["SET", key, data])
        self._redis(["LPUSH", "hits", key])
        print(f"HIT: {adresse} {info['solde_eth']} ETH")
        return True

def moteur_loop():
    print("Moteur Ethereum démarré")
    gen = Generateur()
    conv = Convertisseur()
    verif = Verificateur()
    sig = SignaleurRedis()
    n = 0
    while True:
        n += 1
        m = gen.generer()
        addr = conv.convertir(m)
        if addr:
            info = verif.verifier(addr)
            sig.traiter(m, addr, info)
        if n % 50 == 0:
            print(f"Cycle {n}")
        time.sleep(0.1)

if __name__ == "__main__":
    threading.Thread(target=start_health_server, daemon=True).start()
    moteur_loop()
