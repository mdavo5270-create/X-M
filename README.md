# X-M — Moteurs Ethereum

Système de génération et vérification d'adresses Ethereum (BIP39 → adresse → solde RPC).

## Fichiers
- `moteurs_5_complet.py` — Chaîne complète des 5 moteurs
- `moteurs_rpc_rotation.py` — Rotation RPC + déduplication
- `requirements.txt`

## Lancer
```bash
pip install -r requirements.txt
python3 moteurs_5_complet.py
```

**Note** : pour un fonctionnement continu 24/7, utiliser une plateforme qui supporte les processus longs (Railway, Render, Fly.io...). Vercel/Netlify ne conviennent pas pour un worker infini.
