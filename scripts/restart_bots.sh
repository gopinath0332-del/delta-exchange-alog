#!/bin/bash

# Restart Delta Bot Services
#echo "Restarting Service..."
#sudo systemctl restart delta-bot.service

#echo "Restarting ETH Service..."
#sudo systemctl restart delta-bot-eth.service

#echo "Restarting XRP Service..."
#sudo systemctl restart delta-bot-xrp.service

# Donchian Channel — BIOUSD, PIPPINUSD, ARCUSD
# run in a single multi-threaded service. API calls are serialized via the
# shared DeltaRestClient's threading.Lock — no startup rate-limit burst.
echo "Restarting Donchian multi-coin service (BIOUSD, PIPPIN, ARCUSD)..."
sudo systemctl restart delta-bot-donchian.service

#echo "Restarting BTC EMA Service..."
#sudo systemctl restart delta-bot-btc-ema.service

echo "Services restarted."
