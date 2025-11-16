#!/usr/bin/env bash
# deploy/pi-setup.sh
# Script d'aide pour déployer l'application sur Raspberry Pi
# Usage: sudo ./deploy/pi-setup.sh
# Ajustez les variables ci-dessous avant d'exécuter si nécessaire.

set -euo pipefail

# === Configuration (modifiez si nécessaire) ===
REPO_URL="https://github.com/codingame-team/Wake-on-lan.git"
INSTALL_DIR="/home/wol/Wake-on-lan"
VENV_DIR="$INSTALL_DIR/.venv"
SERVICE_NAME="wol.service"  # or wol-bind-local.service
# Create and use a dedicated system user by default
USE_DEDICATED_USER="yes"     # yes/no
DEDICATED_USER="wol"
DEDICATED_GROUP="wol"
GUNICORN_WORKERS=2
PYTHON_BIN="python3"

# === Fonctions utilitaires ===
log() { echo "[INFO] $*"; }
err() { echo "[ERROR] $*" >&2; exit 1; }

if [ "$(id -u)" -ne 0 ]; then
  err "Ce script doit être exécuté en tant que root (sudo)"
fi

log "Installation des paquets système nécessaires"
apt update
apt install -y python3-venv python3-pip nginx git curl build-essential python3-dev certbot python3-certbot-nginx ufw

# Create dedicated user if requested
if [ "$USE_DEDICATED_USER" = "yes" ]; then
  if ! id -u "$DEDICATED_USER" >/dev/null 2>&1; then
    log "Création de l'utilisateur système $DEDICATED_USER"
    adduser --system --group --home /home/$DEDICATED_USER --shell /bin/bash $DEDICATED_USER || true
    mkdir -p /home/$DEDICATED_USER
    chown $DEDICATED_USER:$DEDICATED_GROUP /home/$DEDICATED_USER
  else
    log "Utilisateur $DEDICATED_USER déjà existant"
  fi
  RUN_USER=$DEDICATED_USER
else
  RUN_USER=pi
fi

log "Clonage ou mise à jour du dépôt dans $INSTALL_DIR"
if [ -d "$INSTALL_DIR/.git" ]; then
  log "Repo exists, pulling latest changes"
  # Ensure correct ownership for pulling
  chown -R $RUN_USER:$RUN_USER $INSTALL_DIR || true
  su - $RUN_USER -c "cd $INSTALL_DIR && git pull --ff-only || true"
else
  # Ensure parent dir exists and owned by run user
  mkdir -p "$(dirname "$INSTALL_DIR")"
  # set ownership of parent dir so the non-root user can create the repo
  chown "$RUN_USER:$RUN_USER" "$(dirname "$INSTALL_DIR")" || true

  log "Clonage du dépôt $REPO_URL dans $INSTALL_DIR"
  # attempt a shallow clone as the run user; fail with actionable message if authentication required
  if ! su - "$RUN_USER" -c "git clone --depth 1 '$REPO_URL' '$INSTALL_DIR'"; then
    echo "[ERROR] git clone failed. Possible causes: repository is private or network/authentication issue." >&2
    echo "Please ensure the Raspberry Pi can access the repository. Options:" >&2
    echo "  - configure an SSH key for user $RUN_USER and use the git+ssh URL (git@github.com:...)" >&2
    echo "  - make the repository public or provide HTTPS credentials (not recommended in scripts)." >&2
    echo "You can also clone manually as the deployment user and re-run this script." >&2
    exit 1
  fi
fi

log "Création et activation d'un virtualenv"
# create venv as the run user
su - $RUN_USER -c "cd $INSTALL_DIR && $PYTHON_BIN -m venv .venv || true"
su - $RUN_USER -c "cd $INSTALL_DIR && . .venv/bin/activate && pip install --upgrade pip setuptools wheel && pip install -r requirements.txt"

log "Affecter la propriété du répertoire au user de déploiement ($RUN_USER)"
chown -R $RUN_USER:$RUN_USER $INSTALL_DIR || true

log "Préparation des unités systemd (adaptation User/Group/WorkingDirectory)"
# Copy and adapt wol.service
if [ -f "$INSTALL_DIR/deploy/wol.service" ]; then
  sed -e "s/^User=.*/User=${RUN_USER}/" -e "s/^Group=.*/Group=${RUN_USER}/" -e "s@WorkingDirectory=.*@WorkingDirectory=${INSTALL_DIR}@" "$INSTALL_DIR/deploy/wol.service" > /etc/systemd/system/wol.service
fi

# Copy and adapt wol-bind-local.service
if [ -f "$INSTALL_DIR/deploy/wol-bind-local.service" ]; then
  sed -e "s/^User=.*/User=${RUN_USER}/" -e "s/^Group=.*/Group=${RUN_USER}/" -e "s@WorkingDirectory=.*@WorkingDirectory=${INSTALL_DIR}@" "$INSTALL_DIR/deploy/wol-bind-local.service" > /etc/systemd/system/wol-bind-local.service
fi

# Copy nginx config
if [ -f "$INSTALL_DIR/deploy/nginx_wol.conf" ]; then
  cp "$INSTALL_DIR/deploy/nginx_wol.conf" /etc/nginx/sites-available/wol
  ln -sf /etc/nginx/sites-available/wol /etc/nginx/sites-enabled/wol || true
fi

log "Reload systemd and enable service"
systemctl daemon-reload
systemctl enable --now wol.service || true

log "Nginx test and reload"
nginx -t && systemctl reload nginx || true

log "Setup complete. Vérifiez les logs via:"
cat <<EOF
sudo journalctl -u wol.service -f
sudo journalctl -u nginx -f
EOF

log "Si vous utilisez la variante bind-local, activez wol-bind-local.service au lieu de wol.service :"
cat <<EOF
sudo systemctl enable --now wol-bind-local.service
sudo journalctl -u wol-bind-local.service -f
EOF

log "Fin du script"
