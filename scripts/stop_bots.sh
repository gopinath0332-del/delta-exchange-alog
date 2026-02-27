#!/bin/bash

# Stop Delta Bot Services
#echo "Stopping Service (BTC)..."
#sudo systemctl stop delta-bot.service

#echo "Stopping ETH Service..."
#sudo systemctl stop delta-bot-eth.service

#echo "Stopping XRP Service..."
#sudo systemctl stop delta-bot-xrp.service

echo "Stopping River Service..."
sudo systemctl stop delta-bot-river.service

echo "Stopping Pippin Service..."
sudo systemctl stop delta-bot-pippin.service

#echo "Stopping BTC EMA Service..."
#sudo systemctl stop delta-bot-btc-ema.service

echo "Stopping PIUSD Service..."
sudo systemctl stop delta-bot-pi.service

echo "Stopping BERAUSD Service..."
sudo systemctl stop delta-bot-bera.service

echo "All services stopped."
