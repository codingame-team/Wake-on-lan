#!/usr/bin/env python3
"""
Vérifier les permissions actuelles du token Freebox
"""
import requests
import json
import hmac
import hashlib

FREEBOX_URL = "http://mafreebox.freebox.fr"
CONFIG_FILE = "../.freebox_token"

# Charger config
with open(CONFIG_FILE, "r") as f:
    config = json.load(f)

print("🔍 Vérification des permissions Freebox\n")
print(f"App ID: {config['app_id']}")
print(f"Token: {config['app_token'][:30]}...\n")

# Login
challenge_resp = requests.get(f"{FREEBOX_URL}/api/v8/login/")
challenge = challenge_resp.json()["result"]["challenge"]

password = hmac.new(
    config["app_token"].encode(),
    challenge.encode(),
    hashlib.sha1
).hexdigest()

login_resp = requests.post(f"{FREEBOX_URL}/api/v8/login/session/", json={
    "app_id": config["app_id"],
    "password": password
})

session_data = login_resp.json()

if not session_data.get("success"):
    print(f"❌ Login échoué: {session_data}")
    exit(1)

session_token = session_data["result"]["session_token"]
print(f"✅ Login réussi: {session_token[:30]}...\n")

# Récupérer les permissions
perms_resp = requests.get(
    f"{FREEBOX_URL}/api/v8/login/session/",
    headers={"X-Fbx-App-Auth": session_token}
)

perms_data = perms_resp.json()

if not perms_data.get("success"):
    print(f"❌ Erreur récupération permissions: {perms_data}")
    exit(1)

print("📋 PERMISSIONS ACCORDÉES:\n")
permissions = perms_data["result"].get("permissions", {})

for perm, value in sorted(permissions.items()):
    status = "✅ OUI" if value else "❌ NON"
    print(f"   {status}  {perm}")

print("\n" + "="*60)
if permissions.get("settings"):
    print("✅ Permission 'settings' ACCORDÉE - WOL devrait fonctionner!")
else:
    print("❌ Permission 'settings' NON ACCORDÉE - WOL ne fonctionnera pas!")
    print("\n💡 SOLUTION:")
    print("   1. Allez dans les paramètres de votre Freebox")
    print("   2. Paramètres > Gestion des accès")
    print("   3. Trouvez l'application 'GameArena WOL'")
    print("   4. Cochez la permission 'Modification des réglages'")
    print("   OU")
    print("   5. Supprimez l'application et relancez test_freebox_perms.py")
print("="*60)
