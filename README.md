### Instruction d'installation

```bash
git clone https://github.com/codingame-team/Wake-on-lan
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Configuration de la clé secrète et variables d'environnement

- Créez un fichier `.env` à la racine du projet (le projet écrira automatiquement une clé si elle est absente):

```ini
# .env.example
# Variables d'environnement pour Wake-on-LAN
# Copiez ce fichier en .env et adaptez si nécessaire
SECRET_KEY=replace-with-a-secret
GAMEARENA_URL=http://127.0.0.1:60001
GAMEARENA_HOST_IP=192.168.1.100
MAX_WAIT_TIME=120
ALLOW_DEBUG=0
```

- L'application utilise `python-dotenv` pour charger `.env`. Lors du premier démarrage, si `SECRET_KEY` n'existe pas, une clé cryptographiquement sûre sera générée et ajoutée à `.env` (le fichier est rendu lisible uniquement par le propriétaire, permission 600 si le système de fichiers le permet).

Déploiement en production (recommandé)

Ne pas utiliser `flask run --host=0.0.0.0` en production. Utilisez Gunicorn (ou uWSGI) derrière un reverse proxy TLS (nginx). Exemple avec Gunicorn et unit systemd sécurisé :

```ini
# /etc/systemd/system/wol.service
[Unit]
Description=Wake-on-LAN Flask app (gunicorn)
After=network.target

[Service]
User=woluser
Group=woluser
WorkingDirectory=/home/woluser/Wake-on-lan
Environment="PATH=/home/woluser/Wake-on-lan/.venv/bin"
# Charger variables d'environnement (optionnel)
EnvironmentFile=/home/woluser/Wake-on-lan/.env
ExecStart=/home/woluser/Wake-on-lan/.venv/bin/gunicorn -w 3 -b 127.0.0.1:5000 wol_app:app

# Hardening
PrivateTmp=yes
ProtectSystem=full
ProtectHome=yes
NoNewPrivileges=yes
PrivateDevices=yes
RestrictAddressFamilies=AF_INET AF_INET6 unix
ReadOnlyPaths=/usr
RestrictNamespaces=yes

Restart=on-failure
RestartSec=5s
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
```

Activation du service

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now wol.service
sudo journalctl -u wol.service -f
```

Développement local

Pour du développement local, vous pouvez lancer l'application en mode non-exposé :

```bash
# activez l'environnement virtuel
source .venv/bin/activate
# lancer l'appli accessible uniquement localement
FLASK_RUN_HOST=127.0.0.1 FLASK_RUN_PORT=5000 FLASK_DEBUG=1 python wol_app.py
```

Notes de sécurité rapides

- Définit SESSION_COOKIE_SECURE, SESSION_COOKIE_HTTPONLY, SESSION_COOKIE_SAMESITE dans la configuration.
- La route `/debug` n'est disponible qu'en mode debug local ou si `ALLOW_DEBUG=1`.
- Active CSRF si `Flask-WTF` est installé (fortement recommandé si vous acceptez des POST depuis des formulaires).

Binder Gunicorn sur l'IP locale (NAT Freebox)

Si vous souhaitez que Gunicorn écoute directement sur l'IP locale du Raspberry Pi (par exemple parce que vous faites une redirection NAT de votre Freebox), deux approches sont possibles :

1) Variante recommandée : Gunicorn + nginx (nginx accepte la connexion publique et reverse-proxy localement)
2) Variante directe : Gunicorn bind sur l'IP locale (moins recommandé car pas de reverse proxy TLS / headers de sécurité)

Pour binder directement sur l'IP locale (approche directe)

- Déterminer l'IP locale du Raspberry Pi :

```bash
# affiche l'IP de l'interface active
ip -4 addr show scope global | sed -n '1,200p'
# ou plus simple (si connecté en ethernet/wlan0) :
ip -4 addr show eth0 | grep -oP '(?<=inet\s)\d+(\.\d+){3}' || ip -4 addr show wlan0 | grep -oP '(?<=inet\s)\d+(\.\d+){3}'
```

- Mettre la variable HOST_IP dans `.env` :

```ini
HOST_IP=192.168.1.42
```

- Exemple de service systemd fourni dans `deploy/wol-bind-local.service` (il attend `HOST_IP` défini dans `.env`). Copiez-le vers `/etc/systemd/system/wol-bind-local.service`, adaptez paths si besoin, puis :

```bash
sudo cp deploy/wol-bind-local.service /etc/systemd/system/wol-bind-local.service
sudo systemctl daemon-reload
sudo systemctl enable --now wol-bind-local.service
sudo journalctl -u wol-bind-local.service -f
```

- Sur la Freebox : configurez la redirection NAT pour rediriger le port externe (ex: 5000 ou 80/443 selon votre décision) vers `HOST_IP:5000` (ou le port choisi). Assurez-vous que votre ISP ne bloque pas les ports et que l'état du NAT est correct.

Sécurité et recommandations :

- Si vous exposez Gunicorn directement sur la WAN via NAT, vous devez au minimum configurer un firewall, nginx ou un reverse proxy pour TLS/HTTP headers, et limiter l'accès (ex: via port forwarding restreint, VPN ou filtrage IP). Sans TLS, les cookies et données transitent en clair.
- Préférez la configuration avec nginx (proxy) et TLS. L'exposition directe de Gunicorn sur Internet n'est pas recommandée.

### Prérequis

- Python 3.9 ou une version plus récente est requis pour exécuter l'application et les scripts de support.

Vérifiez votre version de Python sur le Raspberry Pi :

```bash
python3 --version
```

Si votre Python système est antérieur à 3.9, installez une version plus récente de Python (via apt si disponible ou à partir des sources/pyenv) ou exécutez l'application sur un hôte avec Python 3.9 ou plus.

Exemple pour installer Python 3.9 sur Debian/Raspbian s'il est disponible via apt :

```bash
sudo apt update
sudo apt install -y python3.9 python3.9-venv python3.9-dev
```

Lors de l'utilisation d'un virtualenv, assurez-vous qu'il utilise Python 3.9 :

```bash
python3.9 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Redémarrage manuel de nginx et Gunicorn

Si vous devez redémarrer rapidement le reverse proxy ou l'application, voici les commandes usuelles.

Redémarrage via systemd (recommandé si vous avez installé les units)

```bash
# redémarrer nginx
sudo systemctl restart nginx
sudo systemctl status nginx --no-pager
sudo journalctl -u nginx -n 200 --no-pager

# redémarrer le service gunicorn (unit 'wol.service' ou 'wol-bind-local.service')
sudo systemctl restart wol.service
sudo systemctl status wol.service --no-pager
sudo journalctl -u wol.service -n 200 --no-pager
```

Redémarrage manuel (foreground) — utile pour debug rapide

```bash
# activer le venv puis lancer en foreground (en tant qu'utilisateur d'exécution, ex: 'wol')
cd /home/wol/Wake-on-lan
source .venv/bin/activate
# lancer gunicorn en foreground pour voir les logs directement
/home/wol/Wake-on-lan/.venv/bin/gunicorn -w 2 -b unix:/run/wakeonlan/wakeonlan.sock wol_app:app --access-logfile - --error-logfile -
# ou pour binding TCP (développement)
sudo -u wol -H bash -lc 'cd /home/wol/Wake-on-lan && . .venv/bin/activate && /home/wol/Wake-on-lan/.venv/bin/gunicorn -w 2 -b unix:/run/wakeonlan/wakeonlan.sock wol_app:app --access-logfile - --error-logfile -'
# note: si démarre correctement, Ctrl+C pour quitter ; sinon copiez l'erreur.

# vérifier les erreurs possibles dans les logs système
journalctl -xe --no-pager
```

Vérifier la socket (si vous utilisez socket unix)

```bash
ls -l /run/wakeonlan/wakeonlan.sock
# permissions et ownership doivent permettre à nginx (www-data) d'accéder au socket
```

Notes

- Préférez les unités `systemd` en production : elles gèrent le redémarrage automatique, les droits et le runtime directory.
- Les commandes foreground sont uniquement pour le debug local ; utilisez-les sous un terminal dédié et arrêtez avec Ctrl+C.

### Unités systemd : conserver `wakeonlan.service`, supprimer les anciennes unités

Le déploiement canonique utilise l'unité `wakeonlan.service` fournie dans `deploy/wakeonlan.service` (ou `wakeonlan-bind-local.service` pour la variante bind-local).

Si votre système contient encore les unités historiques `wol.service` ou `wol-bind-local.service`, supprimez-les pour éviter les conflits et redémarrages répétés.

Commandes recommandées (exécuter sur le Raspberry Pi en tant que root / via sudo) :

```bash
# Désactiver et supprimer les unités obsolètes si elles existent
sudo systemctl disable --now wol.service || true
sudo systemctl disable --now wol-bind-local.service || true
sudo rm -f /etc/systemd/system/wol.service /etc/systemd/system/wol-bind-local.service || true
# Recharger systemd pour prendre en compte les suppressions
sudo systemctl daemon-reload
```

Ensuite, installez et activez l'unité recommandée :

```bash
# Copier l'unité recommandée (adaptez les chemins si besoin)
sudo cp deploy/wakeonlan.service /etc/systemd/system/wakeonlan.service
sudo systemctl daemon-reload
# Activer et démarrer le service canonique
sudo systemctl enable --now wakeonlan.service
# Suivre les logs
sudo journalctl -u wakeonlan.service -f
```
