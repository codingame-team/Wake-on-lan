import requests
import json
import sys
import time

def load_config():
    """Charger la configuration Freebox"""
    try:
        with open("../.freebox_token", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        print("❌ Fichier .freebox_token non trouvé")
        print("Exécutez d'abord: python3 freebox_auth.py")
        sys.exit(1)

def get_challenge(freebox_url):
    """Obtenir le challenge pour l'authentification"""
    url = f"{freebox_url}/api/v8/login/"
    response = requests.get(url)
    data = response.json()
    
    if data.get("success"):
        return data["result"]["challenge"]
    else:
        raise Exception(f"Erreur challenge: {data}")

def login_freebox(freebox_url, app_id, app_token):
    """Se connecter à la Freebox et obtenir un session_token"""
    import hmac
    import hashlib
    
    # Obtenir le challenge
    challenge = get_challenge(freebox_url)
    
    # Calculer le mot de passe (HMAC-SHA1)
    password = hmac.new(
        app_token.encode(),
        challenge.encode(),
        hashlib.sha1
    ).hexdigest()
    
    # Login
    url = f"{freebox_url}/api/v8/login/session/"
    payload = {
        "app_id": app_id,
        "password": password
    }
    
    response = requests.post(url, json=payload)
    data = response.json()
    
    if data.get("success"):
        return data["result"]["session_token"]
    else:
        raise Exception(f"Login échoué: {data}")

def send_wol(freebox_url, session_token, mac_address):
    """Envoyer un paquet Wake-on-LAN"""
    url = f"{freebox_url}/api/v8/lan/wol/pub/"
    headers = {"X-Fbx-App-Auth": session_token}
    payload = {"mac": mac_address}
    
    response = requests.post(url, json=payload, headers=headers)
    data = response.json()
    
    return data.get("success", False)

def ping_host(host, timeout=1):
    """Vérifier si l'hôte répond au ping"""
    import subprocess
    import platform
    
    param = "-n" if platform.system().lower() == "windows" else "-c"
    command = ["ping", param, "1", "-W" if platform.system().lower() != "darwin" else "-t", str(timeout), host]
    
    try:
        subprocess.check_output(command, stderr=subprocess.STDOUT)
        return True
    except subprocess.CalledProcessError:
        return False

def wait_for_host(host, max_wait=120):
    """Attendre que l'hôte soit accessible"""
    print(f"\n⏳ Attente du démarrage de {host}...")
    
    for i in range(max_wait):
        if ping_host(host):
            print(f"\n✅ Hôte {host} accessible après {i} secondes")
            return True
        
        print(f"⏳ Attente... ({i+1}/{max_wait}s)", end="\r")
        time.sleep(1)
    
    print(f"\n⏱️  Timeout après {max_wait} secondes")
    return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 wake_remote.py <mac_address> [host_ip]")
        print("Exemple: python3 wake_remote.py AA:BB:CC:DD:EE:FF 192.168.1.100")
        sys.exit(1)
    
    mac_address = sys.argv[1]
    host_ip = sys.argv[2] if len(sys.argv) > 2 else None
    
    print("🏠 Wake-on-LAN via Freebox API")
    print("="*60)
    
    # Charger config
    config = load_config()
    
    # Login
    print("🔐 Connexion à la Freebox...")
    try:
        session_token = login_freebox(
            config["freebox_url"],
            config["app_id"],
            config["app_token"]
        )
        print("✅ Connecté")
    except Exception as e:
        print(f"❌ Erreur de connexion: {e}")
        sys.exit(1)
    
    # Envoyer WOL
    print(f"📡 Envoi du paquet WOL vers {mac_address}...")
    if send_wol(config["freebox_url"], session_token, mac_address):
        print("✅ Paquet WOL envoyé")
        
        # Attendre que l'hôte démarre
        if host_ip:
            if wait_for_host(host_ip):
                print("\n🎉 PC démarré et accessible!")
            else:
                print("\n⚠️  PC non accessible (vérifiez la configuration)")
        else:
            print("\n⏳ Attendez environ 30-60 secondes que le PC démarre")
    else:
        print("❌ Échec de l'envoi du paquet WOL")
        sys.exit(1)