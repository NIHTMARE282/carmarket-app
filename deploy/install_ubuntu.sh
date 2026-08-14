#!/usr/bin/env bash
set -e
APP_DIR="/var/www/carmarket"
sudo apt update
sudo apt install -y python3 python3-venv nginx
sudo mkdir -p "$APP_DIR"
sudo chown -R "$USER:$USER" "$APP_DIR"
cd "$APP_DIR"
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
echo "Now create .env, then configure deploy/carmarket.service and deploy/nginx.conf."
