#!/bin/bash

# Delta Exchange Trading Bot - Master Service Restart
echo "-------------------------------------------------------"
echo " Restarting Delta Bot Master Service..."
echo "-------------------------------------------------------"

sudo systemctl restart delta-bot.service

if [ $? -eq 0 ]; then
  echo " Master service restarted successfully."
  echo " Check logs: journalctl -u delta-bot -f"
else
  echo " Error: Failed to restart master service."
fi
echo "-------------------------------------------------------"
