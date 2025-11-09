### Instruction d'installation

```bash
git clone https://github.com/codingame-team/Wake-on-lan
python3 -m venv .venv
source .venv/bin/activate
python.exe -m pip install --upgrade pip
pip install -r requirements.txt
```

```bash
# Create a systemd service file for the Flask application
# sudo nano /etc/systemd/system/flaskapp.service
[Unit]
Description=Application Flask
After=network.target

[Service]
User=pi
Group=pi
WorkingDirectory=/home/pi/Wake-on-LAN
Environment="PATH=/home/pi/Wake-on-LAN/.venv/bin"
Environment="FLASK_APP=wol_app.py"
ExecStart=/home/pi/Wake-on-LAN/.venv/bin/flask run --host=0.0.0.0 --port=5000
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
# Enable and start the Flask application service
sudo systemctl daemon-reload
sudo systemctl restart flask_app.service
sudo systemctl status flask_app.service
```

```bash
# View the logs of the Flask application service
journalctl -u flask_app.service -f
```