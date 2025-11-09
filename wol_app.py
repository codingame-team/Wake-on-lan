# python
#!/usr/bin/env python3
"""
Application Flask pour Wake-on-LAN via API Freebox (durcie)
"""

from flask import Flask, render_template, request, jsonify, redirect
import requests
import json
import hmac
import hashlib
import subprocess
import platform
import os
import socket
from urllib.parse import urlparse
from dotenv import load_dotenv
from requests.exceptions import RequestException

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, 'templates')
STATIC_DIR = os.path.join(BASE_DIR, 'static')

load_dotenv(os.path.join(BASE_DIR, '.env'))

app = Flask(__name__, template_folder=TEMPLATE_DIR, static_folder=STATIC_DIR)

app_secret = os.environ.get('SECRET_KEY') or os.environ.get('FLASK_SECRET') or 'your-secret-key-change-this'
app.secret_key = app_secret

# Par défaut; sera remplacé par la valeur du fichier .freebox_token si présente
DEFAULT_FREEBOX_URL = "http://mafreebox.freebox.fr"
TIMEOUT = 10  # timeout pour requests en secondes

CONFIG_FILE = os.path.join(BASE_DIR, ".freebox_token")
GAMEARENA_URL = "http://philippe.mourey.com:60001"
GAMEARENA_HOST_IP = "192.168.1.100"
MAX_WAIT_TIME = 120

MACHINES = {
    "windows-pc": {
        "name": "PC Windows (192.168.1.100)",
        "mac": "00:23:24:F2:63:4D",
        "ip": "192.168.1.100"
    },
}

def load_config():
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except Exception:
        return None

def get_freebox_base(config):
    # Prend la valeur dans la config si fournie, sinon fallback
    if config:
        url = config.get("freebox_url")
        if url:
            return url.rstrip('/')
    return DEFAULT_FREEBOX_URL

def safe_json(resp):
    """Retourne un tuple (data, error). data est dict ou None."""
    try:
        data = resp.json()
        return data, None
    except Exception:
        # Réponse non-JSON ou vide : renvoyer l'extrait pour debug
        snippet = (resp.text or "")[:2000]
        return None, f"Non-JSON response (status {resp.status_code}): {snippet}"

def get_challenge(base_url):
    url = f"{base_url}/api/v8/login/"
    try:
        resp = requests.get(url, timeout=TIMEOUT)
    except RequestException as e:
        return None, f"Network error getting challenge: {e}"
    data, err = safe_json(resp)
    if err:
        return None, err
    if not data.get("success"):
        return None, f"Freebox returned error for challenge: {data}"
    return data["result"]["challenge"], None

def login_freebox(config):
    base_url = get_freebox_base(config)
    challenge, err = get_challenge(base_url)
    if err:
        return None, err
    if not challenge:
        return None, "No challenge received"

    try:
        password = hmac.new(
            config["app_token"].encode(),
            challenge.encode(),
            hashlib.sha1
        ).hexdigest()
    except Exception as e:
        return None, f"Error computing HMAC: {e}"

    url = f"{base_url}/api/v8/login/session/"
    payload = {"app_id": config["app_id"], "password": password}
    try:
        resp = requests.post(url, json=payload, timeout=TIMEOUT)
    except RequestException as e:
        return None, f"Network error during login: {e}"

    data, err = safe_json(resp)
    if err:
        return None, err
    if not data.get("success"):
        return None, f"Freebox login failed: {data}"
    session_token = data.get("result", {}).get("session_token")
    if not session_token:
        return None, f"Login success but no session_token in response: {data}"
    return session_token, None

def send_wol(session_token, mac_address, config):
    base_url = get_freebox_base(config)
    url = f"{base_url}/api/v8/lan/wol/pub/"
    headers = {"X-Fbx-App-Auth": session_token}
    payload = {"mac": mac_address}

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=TIMEOUT)
    except RequestException as e:
        return False, f"Network error sending WOL: {e}"

    data, err = safe_json(resp)
    if err:
        return False, err
    if not data.get("success"):
        return False, f"Freebox returned failure for WOL: {data}"
    return True, None

def ping_host(host, timeout=1):
    param = "-n" if platform.system().lower() == "windows" else "-c"
    # macOS and Linux differ on timeout flags; keep a minimal portable ping invocation
    command = ["ping", param, "1", host]
    try:
        subprocess.check_output(command, stderr=subprocess.STDOUT)
        return True
    except subprocess.CalledProcessError:
        return False
    except FileNotFoundError:
        return False

def is_service_up(host, port, timeout=1):
    """Vérifie qu'un service TCP est joignable sur (host, port).
    Retourne True si une connexion TCP a réussi, False sinon.
    """
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except Exception:
        return False

def parse_host_port_from_url(url):
    parsed = urlparse(url)
    host = parsed.hostname
    port = parsed.port
    # si pas de port, choisir 80/443 en fonction du scheme
    if port is None:
        if parsed.scheme == 'https':
            port = 443
        else:
            port = 80
    return host, port

@app.route('/api/wol', methods=['POST'])
def api_wol():
    data = request.get_json(silent=True) or {}
    mac = data.get('mac')
    ip = data.get('ip')

    if not mac:
        return jsonify({"success": False, "error": "MAC address required"}), 400

    config = load_config()
    if not config:
        return jsonify({"success": False, "error": "Configuration not found"}), 500

    session_token, err = login_freebox(config)
    if err:
        return jsonify({"success": False, "error": "Freebox login failed", "details": err}), 500

    success, err = send_wol(session_token, mac, config)
    if success:
        return jsonify({"success": True, "message": "WOL packet sent", "mac": mac, "ip": ip})
    else:
        return jsonify({"success": False, "error": "Failed to send WOL packet", "details": err}), 500

@app.route('/api/ping/<ip>')
def api_ping(ip):
    online = ping_host(ip)
    return jsonify({"ip": ip, "online": online})

@app.route('/api/machines')
def api_machines():
    machines_with_status = {}
    for machine_id, machine in MACHINES.items():
        machines_with_status[machine_id] = {
            **machine,
            "online": ping_host(machine["ip"])
        }
    return jsonify(machines_with_status)

@app.route('/')
def gamearena_redirect():
    # Prefer TCP check on the game server port; fallback to ICMP ping if socket unavailable
    host, port = parse_host_port_from_url(GAMEARENA_URL)
    # if GAMEARENA_HOST_IP is set and different, prefer the explicit IP for local network checks
    check_host = GAMEARENA_HOST_IP or host

    if is_service_up(check_host, port, timeout=1):
        return redirect(GAMEARENA_URL)

    config = load_config()
    if not config:
        return render_template('error.html',
                             title="Configuration manquante",
                             message="Le token Freebox n'est pas configuré.",
                             details="Exécutez d'abord: python3 freebox_auth.py")

    gamearena_mac = None
    for machine in MACHINES.values():
        if machine["ip"] == GAMEARENA_HOST_IP:
            gamearena_mac = machine["mac"]
            break

    if not gamearena_mac:
        return render_template('error.html',
                             title="Machine non configurée",
                             message=f"L'adresse IP {GAMEARENA_HOST_IP} n'est pas configurée dans MACHINES.")

    return render_template('gamearena_waiting.html',
                         mac=gamearena_mac,
                         ip=GAMEARENA_HOST_IP,
                         url=GAMEARENA_URL,
                         max_wait=MAX_WAIT_TIME)

@app.route('/debug')
def debug_info():
    debug_data = {
        "base_dir": BASE_DIR,
        "config_file_path": CONFIG_FILE,
        "config_file_exists": os.path.exists(CONFIG_FILE),
        "working_directory": os.getcwd()
    }
    config_content = "File not found or could not be read."
    if debug_data["config_file_exists"]:
        try:
            with open(CONFIG_FILE, "r") as f:
                config_content = f.read()
        except Exception as e:
            config_content = f"Error reading file: {str(e)}"
    debug_data["config_content"] = config_content
    return jsonify(debug_data)

if __name__ == '__main__':
    print("🏠 Wake-on-LAN Web Interface")
    print("="*60)
    print(f"Templates dir: {TEMPLATE_DIR}")
    print(f"Static dir: {STATIC_DIR}")

    config = load_config()
    if config:
        print(f"   ✅ Freebox token: {config.get('app_token','')[:20]}...")
        print(f"   ✅ freebox_url: {config.get('freebox_url', DEFAULT_FREEBOX_URL)}")
    else:
        print("   ❌ Pas de token trouvé. Exécutez: python3 freebox_auth.py")

    print(f"\n📡 Machines configurées: {len(MACHINES)}")
    for machine_id, machine in MACHINES.items():
        print(f"   - {machine['name']}")
        print(f"     MAC: {machine['mac']}")
        print(f"     IP: {machine['ip']}")

    secret_key_status = "✅" if app_secret != 'your-secret-key-change-this' else "❌"
    print(f"\n🔑 Clé secrète chargée: {secret_key_status}")

    print("\n🌐 Interface web disponible sur:")
    print("   http://localhost:5001")
    print("\nAppuyez sur Ctrl+C pour arrêter")
    print("="*60)

    app.run(host='0.0.0.0', port=5001, debug=True)
