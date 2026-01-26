#!/bin/bash

# Restart Delta Bot Services
echo "Restarting Service..."
sudo systemctl restart delta-bot.service

echo "Restarting ETH Service..."
sudo systemctl restart delta-bot-eth.service

echo "Restarting XRP Service..."
sudo systemctl restart delta-bot-xrp.service

echo "Restarting River Service..."
sudo systemctl restart delta-bot-river.service

echo "Services restarted."
