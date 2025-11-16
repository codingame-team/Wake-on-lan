#!/usr/bin/env python3
"""tools/verify_deployment.py
Script de vérification post-déploiement pour Wake-on-LAN
Vérifie :
 - état du service systemd (wol.service et wol-bind-local.service)
 - endpoint /health
 - endpoint /api/machines
 - endpoint /api/ping/<machine_ip>
 - présence et permissions du fichier .freebox_token
 - écoute réseau (HOST_IP:PORT)

Usage:
  python3 tools/verify_deployment.py [--env /path/to/.env] [--host HOST_IP] [--port PORT]

Retourne 0 si tous les checks critiques sont OK, 1 sinon.
"""

import os
import sys
import json
import argparse
import subprocess
import socket
from pathlib import Path
from pprint import pprint

# Try to use python-dotenv to load .env if available
try:
    from dotenv import load_dotenv
    DOTENV_AVAILABLE = True
except Exception:
    DOTENV_AVAILABLE = False

try:
    import requests
except Exception:
    print("ERROR: 'requests' package is required. Install in venv: pip install requests")
    sys.exit(2)

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_ENV_PATH = BASE_DIR / '.env'
DEFAULT_PORT = 5000

parser = argparse.ArgumentParser(description='Vérification post-déploiement Wake-on-LAN')
parser.add_argument('--env', help='Chemin vers fichier .env', default=str(DEFAULT_ENV_PATH))
parser.add_argument('--host', help='HOST_IP à tester (surcharge .env)')
parser.add_argument('--port', help='PORT à tester (par défaut 5000)', type=int, default=DEFAULT_PORT)
parser.add_argument('--service', help='Nom du service systemd à vérifier', default='wol.service')
parser.add_argument('--bind-local-service', help='Nom du service bind-local', default='wol-bind-local.service')
parser.add_argument('--timeout', help='Timeout requêtes HTTP (s)', type=float, default=5.0)
args = parser.parse_args()

# Load env
env_path = Path(args.env)
if DOTENV_AVAILABLE and env_path.exists():
    load_dotenv(dotenv_path=str(env_path))
else:
    # fallback: parse basic KEY=VALUE lines
    if env_path.exists():
        try:
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    if '=' in line:
                        k, v = line.split('=', 1)
                        os.environ.setdefault(k.strip(), v.strip().strip('"\''))
        except Exception as e:
            print(f"Warning: failed to parse {env_path}: {e}")

HOST = args.host or os.environ.get('HOST_IP') or '127.0.0.1'
PORT = args.port or int(os.environ.get('FLASK_RUN_PORT', DEFAULT_PORT))
FREEBOX_TOKEN_PATH = os.environ.get('FREEBOX_TOKEN_PATH') or str(BASE_DIR / '.freebox_token')
GAMEARENA_HOST_IP = os.environ.get('GAMEARENA_HOST_IP') or None

results = {
    'service_status': {},
    'http_checks': {},
    'token_check': {},
    'listen_check': {},
}

critical_fail = False

def check_systemd(service_name):
    try:
        p = subprocess.run(['systemctl', 'is-active', service_name], capture_output=True, text=True, timeout=3)
        active = p.returncode == 0 and p.stdout.strip() == 'active'
        return {'service': service_name, 'active': active, 'output': p.stdout.strip() + p.stderr.strip()}
    except FileNotFoundError:
        return {'service': service_name, 'active': False, 'output': 'systemctl not found on this system'}
    except Exception as e:
        return {'service': service_name, 'active': False, 'output': str(e)}

# 1) systemd checks
for svc in (args.service, args.bind_local_service):
    r = check_systemd(svc)
    results['service_status'][svc] = r
    if not r['active']:
        # mark as non-critical only if both are inactive? We'll mark critical if both inactive
        pass

if not (results['service_status'].get(args.service, {}).get('active') or results['service_status'].get(args.bind_local_service, {}).get('active')):
    critical_fail = True

# 2) HTTP checks
base_url = f'http://{HOST}:{PORT}'
health_url = base_url + '/health'
machines_url = base_url + '/api/machines'

# helper for http GET
def http_get(url, timeout=args.timeout):
    try:
        r = requests.get(url, timeout=timeout)
        return {'ok': True, 'status_code': r.status_code, 'text_snippet': (r.text or '')[:1000]}
    except Exception as e:
        return {'ok': False, 'error': str(e)}

results['http_checks']['base_url'] = base_url
h = http_get(health_url)
results['http_checks']['health'] = h
if not (h.get('ok') and h.get('status_code') == 200):
    critical_fail = True

m = http_get(machines_url)
results['http_checks']['machines'] = m
if not (m.get('ok') and m.get('status_code') == 200):
    # not critical? mark as warning
    critical_fail = critical_fail or False

# ping check against GAMEARENA_HOST_IP if provided
if GAMEARENA_HOST_IP:
    ping_url = base_url + f'/api/ping/{GAMEARENA_HOST_IP}'
    p = http_get(ping_url)
    results['http_checks']['ping_gamearena'] = p

# 3) token file
try:
    p = Path(FREEBOX_TOKEN_PATH)
    exists = p.exists()
    readable = os.access(str(p), os.R_OK)
    results['token_check']['path'] = str(p)
    results['token_check']['exists'] = exists
    results['token_check']['readable'] = readable
    if exists and readable:
        try:
            txt = p.read_text()
            # quick validation
            ok = 'app_id' in txt and 'app_token' in txt
            results['token_check']['content_has_app_id_app_token'] = ok
            if not ok:
                critical = False
            else:
                pass
        except Exception as e:
            results['token_check']['read_error'] = str(e)
            critical_fail = True
    else:
        critical_fail = True
except Exception as e:
    results['token_check']['error'] = str(e)
    critical_fail = True

# 4) listen check (try to open TCP connection)
sock_ok = False
try:
    with socket.create_connection((HOST, int(PORT)), timeout=3):
        sock_ok = True
except Exception as e:
    results['listen_check']['error'] = str(e)
results['listen_check']['listening'] = sock_ok
if not sock_ok:
    critical_fail = True

# Final report
print('\n--- Verify Deployment Report ---\n')
print('Host:', HOST, 'Port:', PORT)
print('\nService status:')
for svc, info in results['service_status'].items():
    print(f" - {svc}: active={info['active']} output={info['output']}")

print('\nHTTP checks:')
for k,v in results['http_checks'].items():
    print(f" - {k}: {v}")

print('\nToken check:')
p = results['token_check']
pprint(p)

print('\nListen check:')
print(results['listen_check'])

print('\nSummary:')
if critical_fail:
    print('FAIL: one or more critical checks failed')
    sys.exit(1)
else:
    print('OK: all critical checks passed')
    sys.exit(0)

