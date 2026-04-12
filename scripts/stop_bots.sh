#!/bin/bash

# Delta Exchange Trading Bot - Master Service Stop
echo "-------------------------------------------------------"
echo " Stopping Delta Bot Master Service..."
echo "-------------------------------------------------------"

sudo systemctl stop delta-bot.service

if [ $? -eq 0 ]; then
  echo " Master service stopped successfully."
else
  echo " Error: Failed to stop master service."
fi
echo "-------------------------------------------------------"
