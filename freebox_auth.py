import requests
import json
import time
import sys

FREEBOX_URL = "http://mafreebox.freebox.fr"
APP_ID = "fr.gamearena.deploy"

def request_authorization():
    """Demander l'autorisation à la Freebox"""
    url = f"{FREEBOX_URL}/api/v8/login/authorize/"
    
    app_info = {
        "app_id": APP_ID,
        "app_name": "GameArena Deploy",
        "app_version": "1.0.0",
        "device_name": "MacBook Display",
        "app_permissions": {
            "settings": {
                "value": True,
                "desc": "Modification des réglages de la Freebox (requis pour Wake-on-LAN)"
            }
        }
    }
    
    print("📡 Demande d'autorisation à la Freebox...")
    response = requests.post(url, json=app_info)
    data = response.json()
    
    if not data.get("success"):
        print(f"❌ Erreur: {data}")
        sys.exit(1)
    
    result = data["result"]
    app_token = result["app_token"]
    track_id = result["track_id"]
    
    print("\n" + "="*60)
    print("✅ DEMANDE D'AUTORISATION ENVOYÉE")
    print("="*60)
    print(f"\n🔑 App Token: {app_token}")
    print(f"📝 Track ID: {track_id}")
    print("\n⚠️  IMPORTANT:")
    print("1. Allez sur l'ÉCRAN DE VOTRE FREEBOX")
    print("2. Vous devriez voir une notification demandant d'autoriser l'application")
    print("3. Utilisez les FLÈCHES pour sélectionner 'OUI' et appuyez sur OK")
    print("\n⏳ En attente de validation (60 secondes)...\n")
    
    return app_token, track_id

def check_authorization_status(track_id):
    """Vérifier si l'autorisation a été accordée"""
    url = f"{FREEBOX_URL}/api/v8/login/authorize/{track_id}"
    
    for i in range(60):  # 60 tentatives = 60 secondes
        time.sleep(1)
        
        try:
            response = requests.get(url)
            data = response.json()
            
            if not data.get("success"):
                continue
            
            status = data["result"]["status"]
            
            if status == "granted":
                print("\n✅ AUTORISATION ACCORDÉE!")
                return True
            elif status == "pending":
                print(f"⏳ En attente... ({i+1}/60s)", end="\r")
            elif status == "denied":
                print("\n❌ AUTORISATION REFUSÉE sur la Freebox")
                return False
            elif status == "timeout":
                print("\n⏱️  TIMEOUT - L'autorisation a expiré")
                return False
                
        except Exception as e:
            print(f"\n❌ Erreur: {e}")
            continue
    
    print("\n⏱️  TIMEOUT - Pas de réponse après 60 secondes")
    return False

def save_token(app_token):
    """Sauvegarder le token dans un fichier"""
    config = {
        "app_id": "fr.gamearena.deploy",
        "app_token": app_token,
        "freebox_url": FREEBOX_URL
    }
    
    with open(".freebox_token", "w") as f:
        json.dump(config, f, indent=2)
    
    print(f"\n💾 Token sauvegardé dans .freebox_token")
    print("\n⚠️  IMPORTANT: Ajoutez .freebox_token au .gitignore!")

if __name__ == "__main__":
    print("🏠 Configuration API Freebox pour Wake-on-LAN")
    print("="*60)
    
    # Étape 1: Demander l'autorisation
    app_token, track_id = request_authorization()
    
    # Étape 2: Attendre la validation
    if check_authorization_status(track_id):
        save_token(app_token)
        
        print("\n" + "="*60)
        print("✅ CONFIGURATION TERMINÉE")
        print("="*60)
        print("\nVous pouvez maintenant utiliser wake_remote.py")
        print("pour réveiller votre PC à distance via WOL")
    else:
        print("\n❌ Configuration échouée")
        print("Relancez le script et validez sur la Freebox")
        sys.exit(1)