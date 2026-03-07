#!/bin/bash

# Stop Delta Bot Services
#echo "Stopping Service (BTC)..."
#sudo systemctl stop delta-bot.service

#echo "Stopping ETH Service..."
#sudo systemctl stop delta-bot-eth.service

#echo "Stopping XRP Service..."
#sudo systemctl stop delta-bot-xrp.service

# Donchian Channel — all 5 coins run in a single multi-threaded service
echo "Stopping Donchian multi-coin service (PI, PIPPIN, RIVER, BERA, PAXG)..."
sudo systemctl stop delta-bot-donchian.service

#echo "Stopping BTC EMA Service..."
#sudo systemctl stop delta-bot-btc-ema.service

echo "All services stopped."
