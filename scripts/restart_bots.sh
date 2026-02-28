#!/bin/bash

# Restart Delta Bot Services
#echo "Restarting Service..."
#sudo systemctl restart delta-bot.service

#echo "Restarting ETH Service..."
#sudo systemctl restart delta-bot-eth.service

#echo "Restarting XRP Service..."
#sudo systemctl restart delta-bot-xrp.service

echo "Restarting River Service..."
sudo systemctl restart delta-bot-river.service

echo "Restarting Pippin Service..."
sudo systemctl restart delta-bot-pippin.service

echo "Restarting PIUSD Service..."
sudo systemctl restart delta-bot-pi.service

echo "Restarting BERAUSD Service..."
sudo systemctl restart delta-bot-bera.service

echo "Restarting PAXGUSD Service..."
sudo systemctl restart delta-bot-paxg.service

#echo "Restarting BTC EMA Service..."
#sudo systemctl restart delta-bot-btc-ema.service

echo "Services restarted."
