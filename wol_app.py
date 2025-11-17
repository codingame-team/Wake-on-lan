# python
#!/usr/bin/env python3
"""
Application Flask pour Wake-on-LAN via API Freebox (durcie)
"""

from flask import Flask, render_template, request, jsonify, redirect, abort
from werkzeug.middleware.proxy_fix import ProxyFix
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
ENV_PATH = os.path.join(BASE_DIR, '.env')

# Charger .env s'il existe
load_dotenv(ENV_PATH)

app = Flask(__name__, template_folder=TEMPLATE_DIR, static_folder=STATIC_DIR)

# Configuration pour proxy nginx - ESSENTIEL pour que les redirections fonctionnent
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=0)

# Ensure SECRET_KEY is loaded; if absent, generate one and persist it to .env (permissions 600)
def ensure_secret_key(env_path):
    key = os.environ.get('SECRET_KEY') or os.environ.get('FLASK_SECRET')
    if key:
        return key, False

    # Générer une clé sécurisée
    import secrets
    newkey = secrets.token_urlsafe(32)
    try:
        # Créer le fichier .env s'il n'existe pas et ajouter SECRET_KEY
        # On évite d'écraser des variables existantes
        if os.path.exists(env_path):
            with open(env_path, 'a', encoding='utf-8') as f:
                f.write(f"\nSECRET_KEY={newkey}\n")
        else:
            with open(env_path, 'w', encoding='utf-8') as f:
                f.write(f"SECRET_KEY={newkey}\n")
        try:
            os.chmod(env_path, 0o600)
        except Exception:
            # chmod peut échouer sur certains systèmes de fichiers (Windows, etc.) — ignorer
            pass
        os.environ['SECRET_KEY'] = newkey
        return newkey, True
    except Exception:
        # Si écriture échoue, retourner la clé en mémoire sans persistance
        os.environ['SECRET_KEY'] = newkey
        return newkey, False

app_secret, created = ensure_secret_key(ENV_PATH)
app.config.update(
    SECRET_KEY=app_secret,
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    PREFERRED_URL_SCHEME='https'
)
app.secret_key = app.config['SECRET_KEY']

# Activer CSRF si disponible (recommandé si formulaire POST/écriture côté utilisateur)
try:
    from flask_wtf import CSRFProtect
    csrf = CSRFProtect()
    csrf.init_app(app)
    _csrf_enabled = True
except Exception:
    _csrf_enabled = False

# Par défaut; sera remplacé par la valeur du fichier .freebox_token si présente
DEFAULT_FREEBOX_URL = "http://mafreebox.freebox.fr"
TIMEOUT = 10  # timeout pour requests en secondes

CONFIG_FILE = os.environ.get('FREEBOX_TOKEN_PATH', os.path.join(BASE_DIR, ".freebox_token"))
# Allow FREEBOX_IP from .env as an override/fallback
ENV_FREEBOX_IP = os.environ.get('FREEBOX_IP')

GAMEARENA_URL = os.environ.get('GAMEARENA_URL')
GAMEARENA_HOST_IP = os.environ.get('GAMEARENA_HOST_IP')
MAX_WAIT_TIME = int(os.environ.get('MAX_WAIT_TIME', '120'))

MACHINES = {
    "windows-pc": {
        "name": "PC Windows (192.168.1.100)",
        "mac": "00:23:24:F2:63:4D",
        "ip": "192.168.1.100"
    },
}

def load_config():
    # defensive: ensure CONFIG_FILE is a valid path-like string
    if not CONFIG_FILE or not isinstance(CONFIG_FILE, (str, bytes, os.PathLike)):
        return None
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
    # If freebox IP is provided via environment, build a URL
    if ENV_FREEBOX_IP:
        # If user provided an IP that likely includes scheme or not, normalize
        if ENV_FREEBOX_IP.startswith('http://') or ENV_FREEBOX_IP.startswith('https://'):
            return ENV_FREEBOX_IP.rstrip('/')
        return f"http://{ENV_FREEBOX_IP}"
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
    except Exception as e:
        print(f"DEBUG: Service check failed for {host}:{port} - {e}")
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

@app.route('/api/service-check')
def api_service_check():
    host, port = parse_host_port_from_url(GAMEARENA_URL)
    check_host = GAMEARENA_HOST_IP or host
    
    ping_result = ping_host(check_host)
    service_result = is_service_up(check_host, port, timeout=2)
    
    return jsonify({
        "gamearena_url": GAMEARENA_URL,
        "check_host": check_host,
        "port": port,
        "ping_ok": ping_result,
        "service_up": service_result
    })

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
    # 1) Vérifier si le service GAMEARENA_URL est joignable (préférence TCP)
    host, port = parse_host_port_from_url(GAMEARENA_URL)
    # si GAMEARENA_HOST_IP est défini, l'utiliser pour les checks locaux
    check_host = GAMEARENA_HOST_IP or host

    # Vérifier d'abord si le PC est allumé (ping)
    pc_online = ping_host(check_host)
    service_ready = is_service_up(check_host, port, timeout=1)
    
    if service_ready:
        # Le service est déjà UP => redirection immédiate
        return redirect(GAMEARENA_URL)
    
    # Si le PC est allumé mais service pas prêt, rediriger quand même
    # Le navigateur attendra que le service soit prêt
    if pc_online:
        return redirect(GAMEARENA_URL)

    # 2) Service non joignable -> tenter le Wake-on-LAN via la Freebox
    config = load_config()
    if not config:
        return render_template('error.html',
                             title="Configuration manquante",
                             message="Le token Freebox n'est pas configuré.",
                             details="Exécutez d'abord: python3 freebox_auth.py")

    # retrouver la MAC correspondant à l'IP locale
    gamearena_mac = None
    for machine in MACHINES.values():
        if machine.get("ip") == GAMEARENA_HOST_IP:
            gamearena_mac = machine.get("mac")
            break

    if not gamearena_mac:
        return render_template('error.html',
                             title="Machine non configurée",
                             message=f"L'adresse IP {GAMEARENA_HOST_IP} n'est pas configurée dans MACHINES.")

    # Attempt login + send WOL. On renvoie le résultat à la page d'attente pour affichage/debug.
    session_token, err = login_freebox(config)
    wol_status = False
    wol_details = None

    if session_token:
        success, details = send_wol(session_token, gamearena_mac, config)
        wol_status = success
        wol_details = details
    else:
        wol_status = False
        wol_details = err

    return render_template('gamearena_waiting.html',
                         mac=gamearena_mac,
                         ip=GAMEARENA_HOST_IP,
                         url=GAMEARENA_URL,
                         max_wait=MAX_WAIT_TIME,
                         wol_status=wol_status,
                         wol_details=wol_details)

@app.route('/debug')
def debug_info():
    # Ne doit être disponible qu'en mode debug explicite ou si ALLOW_DEBUG=1
    allow_debug = os.environ.get('ALLOW_DEBUG', '0') in ('1', 'true', 'True')
    if not (app.debug or allow_debug):
        abort(404)

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

@app.route('/health')
def health_check():
    """Endpoint de santé minimal.
    Retourne 200 si les fichiers de configuration essentiels sont présents et parsables.
    Ne tente PAS d'appeler la Freebox (pour éviter latence/erreurs réseau).
    """
    cfg_exists = False
    cfg_ok = False
    cfg_err = None
    cfg_content = None

    # defensive: ensure CONFIG_FILE is a valid path-like
    if CONFIG_FILE and isinstance(CONFIG_FILE, (str, bytes, os.PathLike)):
        try:
            cfg_exists = os.path.exists(CONFIG_FILE)
        except Exception:
            cfg_exists = False
    else:
        cfg_exists = False

    if cfg_exists:
        try:
            with open(CONFIG_FILE, 'r') as f:
                cfg_content = json.load(f)
            # quick validity checks
            if isinstance(cfg_content, dict) and 'app_id' in cfg_content and 'app_token' in cfg_content:
                cfg_ok = True
            else:
                cfg_err = 'token file missing app_id or app_token'
        except Exception as e:
            cfg_err = str(e)
    else:
        cfg_err = 'token file not found'

    return jsonify({
        'ok': cfg_ok,
        'config_file_path': CONFIG_FILE,
        'config_file_exists': cfg_exists,
        'config_valid': cfg_ok,
        'config_error': cfg_err
    }), (200 if cfg_ok else 503)

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

    secret_key_status = "✅" if not (app.config['SECRET_KEY'] is None) else "❌"
    print(f"\n🔑 Clé secrète chargée: {secret_key_status}")
    if created:
        print("⚠️ Une nouvelle SECRET_KEY a été générée et ajoutée à .env (permissions 600).")

    print("\n🌐 Interface web disponible sur:")
    print("   http://127.0.0.1:5000 (préconisé: exécuter derrière gunicorn/nginx en production)")
    print("\nAppuyez sur Ctrl+C pour arrêter")
    print("="*60)

    # En développement local on permet l'écoute sur 127.0.0.1 par défaut ;
    # en production, n'utilisez pas flask run (préférez gunicorn derrière nginx)
    host = os.environ.get('FLASK_RUN_HOST', '127.0.0.1')
    port = int(os.environ.get('FLASK_RUN_PORT', '5000'))
    debug_flag = os.environ.get('FLASK_DEBUG', '0') in ('1', 'true', 'True')
    app.run(host=host, port=port, debug=debug_flag)
