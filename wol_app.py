#!/usr/bin/env python3
"""
Application Flask pour Wake-on-LAN via API Freebox
"""

from flask import Flask, render_template, request, jsonify, redirect
import requests
import json
import hmac
import hashlib
import subprocess
import platform
import os
from dotenv import load_dotenv

# Définir explicitement les dossiers de templates et de fichiers statiques
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, 'templates')
STATIC_DIR = os.path.join(BASE_DIR, 'static')


load_dotenv(os.path.join(BASE_DIR, '.env'))

# Crée l'application Flask en précisant les chemins (évite TemplateNotFound si le CWD change)
app = Flask(__name__, template_folder=TEMPLATE_DIR, static_folder=STATIC_DIR)

# Utiliser la clé secrète depuis la variable d'environnement `SECRET_KEY` (ou `FLASK_SECRET`), sinon fallback
app_secret = os.environ.get('SECRET_KEY') or os.environ.get('FLASK_SECRET') or 'your-secret-key-change-this'
app.secret_key = app_secret  # changez via .env ou variable d'environnement

# Configuration
FREEBOX_URL = "http://mafreebox.freebox.fr"
CONFIG_FILE = os.path.join(BASE_DIR, ".freebox_token")  # Chemin absolu pour le token
GAMEARENA_URL = "http://philippe.mourey.com:60001"
GAMEARENA_HOST_IP = "192.168.1.100"  # IP de la machine GameArena
MAX_WAIT_TIME = 120  # Temps d'attente max en secondes

# Liste des machines configurées
MACHINES = {
    "windows-pc": {
        "name": "PC Windows (192.168.1.100)",
        "mac": "00:23:24:F2:63:4D",  # À remplacer
        "ip": "192.168.1.100"
    },
    # Ajoutez d'autres machines ici
}

def load_config():
    """Charger la configuration Freebox"""
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return None

def get_challenge():
    """Obtenir le challenge pour l'authentification"""
    url = f"{FREEBOX_URL}/api/v8/login/"
    response = requests.get(url)
    data = response.json()
    
    if data.get("success"):
        return data["result"]["challenge"]
    return None

def login_freebox(config):
    """Se connecter à la Freebox et obtenir un session_token"""
    challenge = get_challenge()
    if not challenge:
        return None
    
    # Calculer le mot de passe (HMAC-SHA1)
    password = hmac.new(
        config["app_token"].encode(),
        challenge.encode(),
        hashlib.sha1
    ).hexdigest()
    
    # Login
    url = f"{FREEBOX_URL}/api/v8/login/session/"
    payload = {
        "app_id": config["app_id"],
        "password": password
    }
    
    response = requests.post(url, json=payload)
    data = response.json()
    
    if data.get("success"):
        return data["result"]["session_token"]
    return None

def send_wol(session_token, mac_address):
    """Envoyer un paquet Wake-on-LAN"""
    url = f"{FREEBOX_URL}/api/v8/lan/wol/pub/"
    headers = {"X-Fbx-App-Auth": session_token}
    payload = {"mac": mac_address}
    
    response = requests.post(url, json=payload, headers=headers)
    data = response.json()
    
    return data.get("success", False)

def ping_host(host, timeout=1):
    """Vérifier si l'hôte répond au ping"""
    param = "-n" if platform.system().lower() == "windows" else "-c"
    command = ["ping", param, "1", "-W" if platform.system().lower() != "darwin" else "-t", str(timeout), host]
    
    try:
        subprocess.check_output(command, stderr=subprocess.STDOUT)
        return True
    except subprocess.CalledProcessError:
        return False

@app.route('/api/wol', methods=['POST'])
def api_wol():
    """API pour envoyer un paquet WOL"""
    data = request.json
    mac = data.get('mac')
    ip = data.get('ip')
    
    if not mac:
        return jsonify({"success": False, "error": "MAC address required"}), 400
    
    # Charger config
    config = load_config()
    if not config:
        return jsonify({"success": False, "error": "Configuration not found"}), 500
    
    # Login Freebox
    try:
        session_token = login_freebox(config)
        if not session_token:
            return jsonify({"success": False, "error": "Freebox login failed"}), 500
        
        # Envoyer WOL
        success = send_wol(session_token, mac)
        
        if success:
            return jsonify({
                "success": True,
                "message": "WOL packet sent",
                "mac": mac,
                "ip": ip
            })
        else:
            return jsonify({"success": False, "error": "Failed to send WOL packet"}), 500
            
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/ping/<ip>')
def api_ping(ip):
    """API pour vérifier si une machine est en ligne"""
    online = ping_host(ip)
    return jsonify({"ip": ip, "online": online})

@app.route('/api/machines')
def api_machines():
    """Lister les machines configurées"""
    machines_with_status = {}
    
    for machine_id, machine in MACHINES.items():
        machines_with_status[machine_id] = {
            **machine,
            "online": ping_host(machine["ip"])
        }
    
    return jsonify(machines_with_status)

@app.route('/')
def gamearena_redirect():
    """
    Route pour accéder à GameArena
    - Vérifie si la machine est en ligne
    - Si hors ligne, envoie un WOL et attend le démarrage
    - Redirige vers GameArena une fois la machine accessible
    """
    # Vérifier si la machine est déjà en ligne
    if ping_host(GAMEARENA_HOST_IP):
        return redirect(GAMEARENA_URL)
    
    # Machine hors ligne, essayer de la réveiller
    config = load_config()
    if not config:
        return render_template('error.html',
                             title="Configuration manquante",
                             message="Le token Freebox n'est pas configuré.",
                             details="Exécutez d'abord: python3 freebox_auth.py")
    
    # Récupérer la MAC address de la machine GameArena
    gamearena_mac = None
    for machine in MACHINES.values():
        if machine["ip"] == GAMEARENA_HOST_IP:
            gamearena_mac = machine["mac"]
            break
    
    if not gamearena_mac:
        return render_template('error.html',
                             title="Machine non configurée",
                             message=f"L'adresse IP {GAMEARENA_HOST_IP} n'est pas configurée dans MACHINES.")
    
    # Page d'attente avec réveil automatique
    return render_template('gamearena_waiting.html',
                         mac=gamearena_mac,
                         ip=GAMEARENA_HOST_IP,
                         url=GAMEARENA_URL,
                         max_wait=MAX_WAIT_TIME)

# if __name__ == '__main__':
#     print("🏠 Wake-on-LAN Web Interface")
#     print("="*60)
#     print("📝 Configuration:")
#     # Afficher les chemins utilisés pour les templates et static pour faciliter le debug
#     print(f"Templates dir: {TEMPLATE_DIR}")
#     print(f"Static dir: {STATIC_DIR}")
#
#     config = load_config()
#     if config:
#         print(f"   ✅ Freebox token: {config['app_token'][:20]}...")
#     else:
#         print("   ❌ Pas de token trouvé. Exécutez: python3 freebox_auth.py")
#
#     print(f"\n📡 Machines configurées: {len(MACHINES)}")
#     for machine_id, machine in MACHINES.items():
#         print(f"   - {machine['name']}")
#         print(f"     MAC: {machine['mac']}")
#         print(f"     IP: {machine['ip']}")
#
#     secret_key_status = "✅" if app_secret != 'your-secret-key-change-this' else "❌"
#     print(f"\n🔑 Clé secrète chargée: {secret_key_status} (modifiez via .env ou variable d'environnement)")
#
#     print("\n🌐 Interface web disponible sur:")
#     print("   http://localhost:5001")
#     print("   http://127.0.0.1:5001")
#     print("\n⚠️  IMPORTANT: Modifiez les adresses MAC dans MACHINES en haut du fichier")
#     print("\nAppuyez sur Ctrl+C pour arrêter")
#     print("="*60)
#
#     app.run(host='0.0.0.0', port=5001, debug=True)
