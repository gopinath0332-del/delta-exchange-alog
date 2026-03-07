This alggo application is running on raspberry pi. It is running as a single service and each service is trading a crypto currency. Right now i have deployed 5 services. Each service is trading a different crypto currency. (delta-bot-pi.service, delta-bot-pippin.service, delta-bot-river.service, delta-bot-bera.service, delta-bot-paxg.service). 
All 5 servcies are running single strategy. (donchain channel strategy). 

Recently i have changed a settings in the donchain startegy config . i have changed historical_days to 90 from 30.

The issue i obeserve is that when rasberry pi is rebooted, all the services are started at same time, and all the services are trying to fetch the historical data at same time. This is causing the rate limit error and one or 2 services are able to fetch data and rest of the services are getting rate limit error and waiting for the datae to be fetced. So this causes time difference in startegy data analysis. Eg. Pippin service is able to fetch data and start trading at 10:30 but River service is waiting for data to be fetched and it is not trading and 5mintues latest 10:35 it is able to fetch data and start trading. This is not the expected behavior. 
