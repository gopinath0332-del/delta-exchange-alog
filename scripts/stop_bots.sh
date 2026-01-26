#!/bin/bash

# Stop Delta Bot Services
echo "Stopping Service (BTC)..."
sudo systemctl stop delta-bot.service

echo "Stopping ETH Service..."
sudo systemctl stop delta-bot-eth.service

echo "Stopping XRP Service..."
sudo systemctl stop delta-bot-xrp.service

echo "Stopping River Service..."
sudo systemctl stop delta-bot-river.service

echo "All services stopped."
