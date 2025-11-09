#!/usr/bin/env python3
"""
Script universel pour vérifier les permissions Freebox du token courant
"""
import json
import requests
import hmac
import hashlib
import os

CONFIG_FILE = ".freebox_token"
FREEBOX_URL = "http://mafreebox.freebox.fr"

# Charger la config
if not os.path.exists(CONFIG_FILE):
    print("❌ Fichier .freebox_token introuvable")
    exit(1)
with open(CONFIG_FILE, "r") as f:
    config = json.load(f)

app_id = config.get("app_id")
app_token = config.get("app_token")
freebox_url = config.get("freebox_url", FREEBOX_URL)

print("🔍 Vérification des permissions Freebox")
print(f"App ID: {app_id}")
print(f"Token: {app_token[:20]}...")

# 1. Obtenir le challenge
resp = requests.get(freebox_url + "/api/v8/login/")
data = resp.json()
if not data.get("success"):
    print("❌ Erreur challenge Freebox", data)
    exit(1)
challenge = data["result"]["challenge"]

# 2. Calculer le mot de passe
password = hmac.new(app_token.encode(), challenge.encode(), hashlib.sha1).hexdigest()

# 3. Login
payload = {"app_id": app_id, "password": password}
resp = requests.post(freebox_url + "/api/v8/login/session/", json=payload)
data = resp.json()
if not data.get("success"):
    print("❌ Erreur login Freebox", data)
    exit(1)
session_token = data["result"]["session_token"]
perms = data["result"].get("permissions", {})

print(f"✅ Login réussi: {session_token[:20]}...")
print("\n📋 Permissions accordées:")
if perms:
    for k, v in perms.items():
        print(f"   {'✅' if v else '❌'} {k}: {v}")
else:
    print("   ⚠️ Permissions non retournées par la Freebox (API trop ancienne ?)")
    print("   Essayez de mettre à jour Freebox OS ou vérifiez manuellement dans l'interface.")
