#!/bin/bash

# Delta Exchange Trading Bot - Master Service Deployment Script
# This script installs and enables the unified master service for ALL strategies.

set -e

APP_DIR="/home/pi/delta-exchange-alog"
SERVICE_DIR="/etc/systemd/system"

echo "-------------------------------------------------------"
echo " Delta Exchange Bot - Master Service Deployment"
echo "-------------------------------------------------------"

if [ "$(id -u)" -ne 0 ]; then
  echo "Please run as root (sudo ./deploy.sh)"
  exit 1
fi

if [ ! -d "$APP_DIR" ]; then
  echo "Error: Directory $APP_DIR not found. Please ensure the code is at $APP_DIR"
  exit 1
fi

echo "1. Cleaning up old separate services (if any)..."
# Stop and disable old single-strategy services to prevent conflicts
SERVICES_TO_CLEAN="delta-bot-donchian delta-bot-bb delta-bot-bio delta-bot-bera"
for svc in $SERVICES_TO_CLEAN; do
  if systemctl is-active --quiet "$svc.service"; then
    echo "   Stopping $svc.service..."
    systemctl stop "$svc.service" || true
  fi
  if systemctl is-enabled --quiet "$svc.service"; then
    echo "   Disabling $svc.service..."
    systemctl disable "$svc.service" || true
  fi
  if [ -f "$SERVICE_DIR/$svc.service" ]; then
    echo "   Removing $SERVICE_DIR/$svc.service..."
    rm "$SERVICE_DIR/$svc.service"
  fi
done

echo "2. Setting up logs directory..."
mkdir -p "$APP_DIR/logs"
chown pi:pi "$APP_DIR/logs"

echo "3. Installing unified master service..."
cp "$APP_DIR/service/delta-bot.service" "$SERVICE_DIR/"

echo "4. Reloading systemd daemon..."
systemctl daemon-reload

echo "5. Enabling master service..."
systemctl enable delta-bot.service

echo "6. Starting master service..."
systemctl start delta-bot.service

echo "-------------------------------------------------------"
echo " Master Deployment Complete!"
echo "-------------------------------------------------------"
echo "Status:"
echo "  systemctl status delta-bot"
echo ""
echo "Monitor logs:"
echo "  journalctl -u delta-bot -f"
echo "-------------------------------------------------------"
