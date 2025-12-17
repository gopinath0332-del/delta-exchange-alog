#!/bin/bash

# Restart Delta Bot Services
echo "Restarting Delta Bot Service..."
sudo systemctl restart delta-bot.service

echo "Restarting Delta Bot ETH Service..."
sudo systemctl restart delta-bot-eth.service

echo "Services restarted."
