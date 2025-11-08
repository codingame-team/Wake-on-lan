#!/usr/bin/env python3
"""
Script pour tester et réautoriser l'application Freebox avec les bonnes permissions
"""
import requests
import json
import hmac
import hashlib
import time
import sys

FREEBOX_URL = "http://mafreebox.freebox.fr"
APP_ID = "fr.gamearena.wol"  # Changement d'ID pour forcer nouvelle autorisation
CONFIG_FILE = "../.freebox_token"

print("🔍 Test des permissions Freebox actuelles\n")

# Vérifier le token actuel
try:
    with open(CONFIG_FILE, "r") as f:
        config = json.load(f)
    print(f"✅ Token trouvé: {config['app_token'][:20]}...")
    print(f"📝 App ID: {config['app_id']}\n")
except FileNotFoundError:
    print("❌ Pas de token trouvé\n")
    config = None

if config:
    # Tester l'accès WOL avec le token actuel
    print("🧪 Test d'accès à l'API WOL...")
    
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
    if session_data.get("success"):
        session_token = session_data["result"]["session_token"]
        print(f"✅ Login OK: {session_token[:20]}...")
        
        # Test permissions
        perms_resp = requests.get(
            f"{FREEBOX_URL}/api/v8/login/session/",
            headers={"X-Fbx-App-Auth": session_token}
        )
        perms = perms_resp.json()
        
        if perms.get("success"):
            print("\n📋 Permissions actuelles:")
            permissions = perms["result"].get("permissions", {})
            for perm, value in permissions.items():
                status = "✅" if value else "❌"
                print(f"   {status} {perm}: {value}")
            
            # Vérifier si settings est disponible
            if permissions.get("settings"):
                print("\n✅ Permission 'settings' ACCORDÉE - WOL devrait fonctionner!")
            else:
                print("\n❌ Permission 'settings' MANQUANTE - WOL ne fonctionnera pas!")
                print("\n💡 Solution: Réautoriser l'application")
        else:
            print(f"\n❌ Erreur permissions: {perms}")
    else:
        print(f"❌ Login échoué: {session_data}")

print("\n" + "="*60)
print("🔄 RÉAUTORISATION AVEC NOUVELLES PERMISSIONS")
print("="*60)
response = input("\nVoulez-vous réautoriser l'application avec les bonnes permissions? (o/n): ")

if response.lower() != 'o':
    print("❌ Annulé")
    sys.exit(0)

# Nouvelle autorisation
print("\n📡 Demande d'autorisation avec permissions 'settings'...")

app_info = {
    "app_id": APP_ID,
    "app_name": "GameArena WOL",
    "app_version": "2.0.0",
    "device_name": "MacBook Display",
    "app_permissions": {
        "settings": {
            "value": True,
            "desc": "Accès aux réglages pour Wake-on-LAN"
        }
    }
}

auth_resp = requests.post(f"{FREEBOX_URL}/api/v8/login/authorize/", json=app_info)
auth_data = auth_resp.json()

if not auth_data.get("success"):
    print(f"❌ Erreur autorisation: {auth_data}")
    sys.exit(1)

app_token = auth_data["result"]["app_token"]
track_id = auth_data["result"]["track_id"]

print("\n" + "="*60)
print("✅ DEMANDE ENVOYÉE")
print("="*60)
print(f"\n🔑 Nouveau Token: {app_token}")
print(f"📝 Track ID: {track_id}")
print("\n⚠️  IMPORTANT:")
print("1. Allez sur l'ÉCRAN DE VOTRE FREEBOX")
print("2. Utilisez les FLÈCHES pour sélectionner 'OUI'")
print("3. Appuyez sur OK")
print("\n⏳ Attente de validation (60 secondes)...\n")

# Attendre la validation
for i in range(60):
    time.sleep(1)
    
    status_resp = requests.get(f"{FREEBOX_URL}/api/v8/login/authorize/{track_id}")
    status_data = status_resp.json()
    
    if not status_data.get("success"):
        print(f"❌ Erreur: {status_data}")
        sys.exit(1)
    
    status = status_data["result"]["status"]
    
    if status == "granted":
        print(f"\n✅ AUTORISATION ACCORDÉE après {i+1} secondes!")
        
        # Sauvegarder le nouveau token
        new_config = {
            "app_id": APP_ID,
            "app_token": app_token,
            "freebox_url": FREEBOX_URL
        }
        
        with open(CONFIG_FILE, "w") as f:
            json.dump(new_config, f, indent=2)
        
        print(f"💾 Token sauvegardé dans {CONFIG_FILE}")
        print("\n🎉 SUCCÈS! Vous pouvez maintenant utiliser le WOL")
        print("\n⚠️  Redémarrez wol_app.py pour utiliser le nouveau token")
        sys.exit(0)
        
    elif status == "denied":
        print("\n❌ AUTORISATION REFUSÉE")
        sys.exit(1)
        
    elif status == "timeout":
        print("\n⏱️ TIMEOUT - Temps écoulé")
        sys.exit(1)
    
    # Afficher progression
    if (i + 1) % 10 == 0:
        print(f"   ... {i+1}s écoulées (status: {status})")

print("\n⏱️ TIMEOUT - Aucune réponse après 60 secondes")
sys.exit(1)
