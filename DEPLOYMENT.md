# CyberForge Production Deployment Guide

Deploying CyberForge to a production environment requires a specific architecture, primarily because it interacts directly with a hypervisor (VirtualBox) to provision challenge environments in real-time.

## Architecture Overview

For a true production deployment, you will need:
1.  **Bare-Metal Server / Nested Virtualization Support:** Because CyberForge drives VirtualBox via the `VBoxManage` CLI, the host OS must support hardware virtualization (VT-x/AMD-V). Standard cloud VMs (like basic AWS EC2 or DigitalOcean droplets) often do not support this well without specific instance types (e.g., AWS `.metal` instances).
2.  **PostgreSQL Database:** The SQLite database is for development (`mock` mode). In production, you must safely handle concurrent provisioning workflows and audit events using PostgreSQL.
3.  **Reverse Proxy:** Use Nginx or Caddy to expose the API and serve the static files with SSL/TLS.
4.  **Process Manager:** Use `systemd` to keep the Python FastAPI process (`uvicorn`) running in the background.

---

## 1. Prerequisites (Ubuntu Linux 22.04 LTS Example)

Update your packages and install the core dependencies:

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3.11 python3.11-venv postgresql postgresql-contrib nginx
```

Install VirtualBox:
```bash
sudo apt install -y virtualbox virtualbox-ext-pack
```

## 2. Prepare the VirtualBox Environment

CyberForge requires template VMs to be fully configured and registered in VirtualBox under the user account that will run the application.

1.  Log in as the service user (e.g., `cf-service`).
2.  Create or import your base VMs.
3.  Take a snapshot of them if desired, but ensure they are powered off.
4.  Note their exact registered names (e.g., `cf-ubuntu-attacker-base`, `cf-debian-target-base`).

Verify the service user can see the templates:
```bash
VBoxManage list vms
```

## 3. Configure the Database

Switch to the postgres user and set up the database:

```bash
sudo -u postgres psql

# Run these SQL commands:
CREATE DATABASE cyberforge;
CREATE USER cyberforge_user WITH ENCRYPTED PASSWORD 'your_secure_password';
GRANT ALL PRIVILEGES ON DATABASE cyberforge TO cyberforge_user;
```

## 4. Setup the App Application

Clone or copy the application to `/opt/cyberforge` and set permissions:

```bash
sudo mkdir -p /opt/cyberforge
sudo chown -R $USER:$USER /opt/cyberforge
# (Copy application files into /opt/cyberforge)

cd /opt/cyberforge
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

## 5. Systemd Service Configuration

We need to create a systemd service file to keep the application running continuously. 
Create `/etc/systemd/system/cyberforge.service`:

```ini
[Unit]
Description=CyberForge API Daemon
After=network.target postgresql.service virtualbox.service

[Service]
User=cf-service
Group=cf-service
WorkingDirectory=/opt/cyberforge
Environment="PATH=/opt/cyberforge/.venv/bin:/usr/local/bin:/usr/bin"
Environment="PYTHONPATH=/opt/cyberforge/src"
# --- CyberForge Configuration ---
Environment="CYBERFORGE_REPOSITORY=sqlalchemy"
Environment="CYBERFORGE_DATABASE_URL=postgresql+psycopg://cyberforge_user:your_secure_password@localhost/cyberforge"
Environment="CYBERFORGE_PROVISIONER=virtualbox"
Environment="CYBERFORGE_VBOX_DRY_RUN=false"
Environment="CYBERFORGE_VBOX_ATTACKER_TEMPLATE=cf-ubuntu-attacker-base"
Environment="CYBERFORGE_VBOX_TARGET_TEMPLATE=cf-debian-target-base"
Environment="CYBERFORGE_VALIDATE_CONTENT_STRUCTURE=true"
Environment="CYBERFORGE_CONTENT_ROOT=/opt/cyberforge-content"

# Run Uvicorn via Gunicorn for production worker management
ExecStart=/opt/cyberforge/.venv/bin/python -m uvicorn cyberforge.main:app --host 127.0.0.1 --port 8000 --workers 4

Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Reload the daemon and start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable cyberforge
sudo systemctl start cyberforge
sudo systemctl status cyberforge
```

## 6. Nginx Reverse Proxy Setup

Create an Nginx configuration file at `/etc/nginx/sites-available/cyberforge`:

```nginx
server {
    listen 80;
    server_name yourdomain.com; # Replace with your domain/IP

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Optional: Serve static files directly via Nginx instead of FastAPI
    location /static/ {
        alias /opt/cyberforge/static/;
        expires 30d;
        add_header Cache-Control "public, no-transform";
    }
}
```

Enable the site and restart Nginx:
```bash
sudo ln -s /etc/nginx/sites-available/cyberforge /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx
```

## 7. Security Considerations

1. **VirtualBox Permissions**: VirtualBox usually requires the user running the commands to be within the `vboxusers` group. Run `sudo usermod -aG vboxusers cf-service`.
2. **Network Bridging**: Ensure that the VirtualBox target networks do not securely expose the VMs to your internal management network. Provision the VMs on Host-Only or Internal networks when possible.
3. **SSL/TLS**: Use Let's Encrypt (Certbot) to secure the UI:
   ```bash
   sudo apt install certbot python3-certbot-nginx
   sudo certbot --nginx -d yourdomain.com
   ```
