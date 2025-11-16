# Vérification de déploiement — Wake-on-LAN

Ce document décrit l'outil de vérification post-déploiement fourni dans le dépôt : `tools/verify_deployment.py`.
Il explique le but de l'outil, ses prérequis, son utilisation, l'interprétation des résultats et des actions de dépannage.

## But

Le script `tools/verify_deployment.py` permet d'automatiser une série de contrôles essentiels après le déploiement de l'application sur un Raspberry Pi (ou autre hôte) :

- Vérifier que le service systemd (gunicorn/wol) est actif
- Vérifier l'endpoint `/health` (valide la présence du fichier `.freebox_token`)
- Vérifier les endpoints API (`/api/machines`, `/api/ping/<ip>`)
- Vérifier la présence et la lisibilité du fichier `.freebox_token`
- Vérifier que l'application écoute sur l'IP et le port attendus

L'outil renvoie un code de sortie non nul en cas d'échec critique (utile pour l'intégration CI ou scripts d'automatisation).

## Emplacement

- Script : `tools/verify_deployment.py`
- Exemple d'utilisation depuis la racine du repo :

```bash
python3 tools/verify_deployment.py --env /home/wol/Wake-on-lan/.env --host 192.168.1.200 --port 5000
```

## Prérequis

- Python 3 installé
- Dans l'environnement où vous exécutez le script, la librairie `requests` doit être disponible (installée dans le venv), sinon le script retourne une erreur et s'arrête :

```bash
# activer venv puis
pip install requests
```

- Accès réseau à l'hôte et au port que vous vérifiez (depuis la machine où vous lancez le script)
- Si vous utilisez un fichier `.env` personnalisé, fournissez son chemin via `--env`

## Options et arguments

Usage :

```bash
python3 tools/verify_deployment.py [--env PATH] [--host HOST_IP] [--port PORT]
```

Options importantes :
- `--env` : chemin vers le fichier `.env` à charger (par défaut `./.env` dans la racine du repo)
- `--host` : IP à tester (surcharge `HOST_IP` depuis `.env`)
- `--port` : port à tester (par défaut `5000`)
- `--service` : nom du service systemd à vérifier (par défaut `wol.service`)
- `--bind-local-service` : nom du service bind-local (par défaut `wol-bind-local.service`)
- `--timeout` : timeout pour les requêtes HTTP (secondes)

## Ce que le script vérifie (détaillé)

1. Systemd
   - Appelle `systemctl is-active <service>` pour `wol.service` et `wol-bind-local.service`.
   - Si aucun des deux services n'est actif, le script considère cela comme un échec critique.

2. Endpoint HTTP `/health`
   - Requête GET sur `http://HOST:PORT/health`.
   - Le script attend un `200 OK` ; sinon c'est un échec critique.
   - Le endpoint `/health` effectue un contrôle léger du fichier `.freebox_token` (présence + contenu minimal).

3. Endpoint HTTP `/api/machines`
   - Requête GET sur `http://HOST:PORT/api/machines`.
   - Le résultat est rapporté dans le rapport ; l'absence de réponse est signalée.

4. (Optionnel) `/api/ping/<GAMEARENA_HOST_IP>`
   - Si `GAMEARENA_HOST_IP` est défini dans le `.env`, le script tente d'interroger `/api/ping/<IP>`.

5. Fichier token Freebox
   - Vérifie que le chemin `FREEBOX_TOKEN_PATH` (depuis `.env` ou valeur par défaut) existe et est lisible.
   - Vérifie grossièrement la présence d'au moins `app_id` et `app_token` dans le contenu.
   - Si le fichier est absent ou non lisible, le script considère cela comme un échec critique.

6. Écoute TCP
   - Essaie d’ouvrir une connexion TCP vers `HOST:PORT`.
   - Si la connexion échoue, échec critique.

## Interprétation des résultats

- Code de sortie `0` : tous les checks critiques (service actif OU bind-local actif, `/health` OK, token présent et lisible, écoute réseau) sont passés.
- Code de sortie `1` : un ou plusieurs checks critiques ont échoué — le script affiche un rapport et signale `FAIL`.
- Code de sortie `2` : erreur d’environnement (par ex. `requests` manquant) — message d’erreur explicite.

Le rapport imprimé contient :
- statut des services systemd et leur sortie
- résultats des requêtes HTTP (status code, extrait)
- état du fichier token (path, exists, readable, presence app_id/app_token)
- état de la connexion TCP

Utilisez ces informations pour diagnostiquer rapidement le problème.

## Exemples

Test standard (à lancer depuis la racine du repo) :

```bash
python3 tools/verify_deployment.py --env /home/wol/Wake-on-lan/.env --host 192.168.1.200 --port 5000
```

Test rapide si le `.env` est à la racine et que vous êtes sur le Pi :

```bash
python3 tools/verify_deployment.py
```

## Scénarios de dépannage et actions recommandées

- `/health` retourne 503 ou l'appel HTTP échoue
  - Vérifiez que l'application est démarrée (`systemctl status wol.service` ou `wol-bind-local.service`).
  - Vérifiez le fichier `.freebox_token` (chemin, permissions, contenu). Exemple :

    ```bash
    ls -l /home/wol/Wake-on-lan/.freebox_token
    sudo chown wol:wol /home/wol/Wake-on-lan/.freebox_token
    sudo chmod 600 /home/wol/Wake-on-lan/.freebox_token
    ```

- JSONDecodeError / erreurs lors de l'appel à la Freebox
  - Testez l'accès direct à la Freebox depuis le Pi :

    ```bash
    curl -v --max-time 10 "http://<freebox_ip>/api/v8/login/"
    ```

  - Vérifiez `freebox_url` dans le fichier `.freebox_token` et que la Freebox est joignable depuis le Pi (NAT, pare-feu, proxys).

- Nginx retourne 502
  - Vérifiez que le socket existe et que les permissions permettent l'accès à `www-data` :

    ```bash
    ls -l /run/wakeonlan/wakeonlan.sock
    sudo journalctl -u wol.service -n 200
    sudo journalctl -u nginx -n 200
    ```

- Gunicorn n'écoute pas la bonne IP (vous vouliez binder sur l'IP locale pour NAT)
  - Vérifiez que `HOST_IP` est défini dans `.env` et que vous avez démarré `wol-bind-local.service`.
  - Redémarrez et revérifiez : `sudo systemctl restart wol-bind-local.service`.

## Intégration CI / surveillance

- Le script retourne un code d'erreur non nul si des checks critiques échouent — il est donc réutilisable dans un job CI ou un playbook Ansible pour valider une mise à jour.
- Vous pouvez scheduler une vérification périodique via `cron` ou systemd timer et envoyer les résultats à votre outil de monitoring.

## Automatisation recommandée

- Ajouter un `systemd` timer ou un `cron` qui exécute `tools/verify_deployment.py` toutes les X minutes et envoie un rapport par e-mail ou webhook en cas d'échec.
- Configurer `fail2ban` et `ufw` sur la Pi si vous exposez un port via NAT.

## Notes de sécurité

- Ne stockez pas `.env` ou `.freebox_token` dans un dépôt public.
- Assurez-vous que `SECRET_KEY` et `app_token` soient lisibles uniquement par l'utilisateur qui exécute le service (`chmod 600`).

## Sécurisation OS : fail2ban

Pour durcir l'accès réseau au Raspberry Pi exposé via NAT, `fail2ban` est un outil simple et efficace pour bloquer automatiquement les adresses IP qui génèrent des tentatives d'authentification ou de requêtes malveillantes répétées.

1) Installation

```bash
sudo apt update
sudo apt install -y fail2ban
```

2) Principes et interaction avec `ufw`

- `fail2ban` lit les logs (ex : `/var/log/auth.log`, `/var/log/nginx/*`) et applique des bans via `iptables` (ou `ufw` si présent).
- Si vous utilisez `ufw`, fail2ban utilisera `iptables` par défaut et fonctionne correctement; veillez simplement à autoriser les ports souhaités dans `ufw` avant d'activer fail2ban.

3) Exemple minimal de configuration

Ne modifiez pas les fichiers d'origine `/etc/fail2ban/jail.conf`. Créez plutôt `/etc/fail2ban/jail.local` avec les jails que vous souhaitez activer :

```ini
[DEFAULT]
# ignore local IPs and other trusted hosts
ignoreip = 127.0.0.1/8 192.168.1.0/24
bantime  = 3600       # durée du ban en secondes (ex: 1h)
findtime  = 600       # fenêtre d'observation pour maxretry (10 min)
maxretry = 5          # nombre d'essais avant ban

[sshd]
enabled = true
port    = ssh
filter  = sshd
logpath = /var/log/auth.log
maxretry = 5

# protection basique pour les erreurs d'auth HTTP basiques (ex: pages protégées)
[nginx-http-auth]
enabled = true
filter = nginx-http-auth
logpath = /var/log/nginx/error.log
maxretry = 3

# bloque les bots et user-agents suspects (exemple)
[nginx-badbots]
enabled  = true
filter   = nginx-badbots
logpath  = /var/log/nginx/access.log
maxretry = 5

# récidive : augmente la peine pour récidivistes
[recidive]
enabled  = true
logpath  = /var/log/fail2ban.log
bantime  = 86400
findtime = 86400
maxretry = 3

```

4) Exemples de filtres utiles

- `nginx-badbots` et `nginx-http-auth` existent souvent dans `/etc/fail2ban/filter.d/`. Adaptez-les si nécessaire ou ajoutez des expressions personnalisées.
- Pour SSH, le filtre `sshd` est fourni par défaut.

5) Activer et tester

```bash
# recharger la configuration
sudo systemctl restart fail2ban
# vérifier status global
sudo fail2ban-client status
# status d'une jail
sudo fail2ban-client status sshd

# pour voir les bans actuels
sudo iptables -L -n --line-numbers | sed -n '1,200p'
```

6) Tester un filtre localement

`fail2ban-regex` permet de tester une expression régulière de filtre contre un fichier de log :

```bash
sudo fail2ban-regex /var/log/auth.log /etc/fail2ban/filter.d/sshd.conf
```

7) Conseils pratiques

- Ajoutez les IPs de confiance à `ignoreip` (votre réseau local, votre IP d'administration) pour éviter d'être banni vous-même.
- Commencez avec des paramètres conservateurs (`maxretry` élevé, `bantime` court) puis resserrez si besoin.
- Surveillez `/var/log/fail2ban.log` et les logs nginx/auth pour détecter faux positifs.
- Pour des analyses prolongées, activez la jail `recidive` pour punir les récidivistes chroniques.
- Testez tout changement en heures creuses et conservez un accès alternatif (accès console locale ou via une autre IP whitelistée).

8) Exemple d'intégration avec notre déploiement

- Autorisez l'accès SSH et le port que vous exposez (par ex. 5000 ou 80/443) via `ufw` avant d'activer `fail2ban` :

```bash
sudo ufw allow OpenSSH
sudo ufw allow 5000/tcp   # si Gunicorn direct
sudo ufw allow 80,443/tcp # si nginx frontal
sudo ufw enable
```

- Installez et activez `fail2ban` puis vérifiez la jail `sshd` et `nginx-*`:

```bash
sudo apt install -y fail2ban
sudo systemctl enable --now fail2ban
sudo fail2ban-client status
sudo fail2ban-client status sshd
sudo fail2ban-client status nginx-http-auth
```

9) Sauvegarde & restauration

- Sauvegardez `/etc/fail2ban/jail.local` avec vos autres fichiers de configuration sensibles.

10) Attention

- Un mauvais filtre ou une configuration trop agressive peut couper l'accès administratif. Toujours tester et mettre en place une IP d'administration dans `ignoreip`.
