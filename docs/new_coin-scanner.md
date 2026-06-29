i have an idea. i would like to create a new coin scanner. Every month exchanges lists new coins and I see good movement in direction ( up or down). And I see volume is also increasing for few coins. Now I want to add the new coins to my algo as well. I am planing to trade in 2hr timeframe. 

-------------------------------------------------------------------------
i have asked delta exchange how to find the new listed coins. 

Here is the result 

how do i get newly listed coins ? 

Delta Exchange Logo
To get newly listed coins/products on Delta Exchange, you can use the GET /products endpoint. There is no dedicated "new listings" filter, but you can identify newly listed products by using the created_at field returned in the response and sorting or filtering by it.

Endpoint: GET /products
URL:


https://api.india.delta.exchange/v2/products
Method: GET

No authentication required (public endpoint)

Query Parameters
Parameter	Type	Description
contract_types	string	Filter by contract type. E.g., perpetual_futures, call_options, put_options
states	string	Filter by state: live, upcoming, expired
after	string	Cursor for pagination (next page)
before	string	Cursor for pagination (previous page)
page_size	string	Number of results per page (default: 100)
expiry	string	Filter by expiry date in YYYY-MM-DD format
How to Find Newly Listed Products
Filter by state=live to get all currently active products.
Sort by created_at (descending) in your application to identify the most recently listed products.
Optionally, filter by contract_types to narrow down to specific instrument types.
Example Request
To get all live perpetual futures:


curl -X GET "https://api.india.delta.exchange/v2/products?states=live&contract_types=perpetual_futures&page_size=100" \
  -H "Accept: application/json"

To get upcoming products (coins about to be listed):


curl -X GET "https://api.india.delta.exchange/v2/products?states=upcoming" \
  -H "Accept: application/json"

Sample Response

{
  "success": true,
  "result": [
    {
      "id": 101,
      "symbol": "NEWCOINUSD",
      "description": "NewCoin Perpetual Futures, quoted and settled in USD",
      "created_at": "2026-06-28T10:00:00Z",
      "updated_at": "2026-06-28T10:05:00Z",
      "contract_type": "perpetual_futures",
      "state": "live",
      "trading_status": "operational",
      "tick_size": "0.001",
      "contract_value": "1",
      "contract_unit_currency": "NEWCOIN",
      "initial_margin": "1.0",
      "maintenance_margin": "0.5",
      "taker_commission_rate": "0.0005",
      "maker_commission_rate": "0.0002"
    }
  ]
}

Key Fields to Identify New Listings
created_at - Timestamp when the product was listed. Sort by this (descending) to find the newest.
state - Use upcoming to find products that are listed but not yet live for trading.
trading_status - operational means the product is fully tradable.
Tip: Pagination
The API returns up to 100 products per page by default. Use the after and before cursor parameters to paginate through all products if needed.

----------------------------------------------------------------------------------------------

Also i have done a few research to select the new coins.check the condtions below 


This is actually a good idea. Newly listed coins often have the strongest trends because:

New narratives attract traders.
Market makers provide liquidity.
Volume increases rapidly.
Price discovery creates big directional moves.

But trading every new listing is dangerous. Most new coins become illiquid after the initial hype.

I would create a coin selection filter before adding a symbol to your 2H breakout strategy.

1. Minimum Volume Filter (Most Important)

Only trade coins whose 24-hour volume is above a threshold.

For example:

Exchange Size	Minimum Volume
Small account	$5M
Medium account	$10M
Large account	$20M+

If volume dries up, your signals become unreliable.

2. Age of Listing

Avoid trading on Day 1.

I would wait:

Minimum: 5 days
Better: 10-14 days

Reason:

Day 1 candles are extremely manipulated.
Huge wicks.
Funding rates go crazy.
No proper support/resistance.
3. Relative Volume Growth

Calculate:

RVOL = Today's Volume / Average Volume of last 7 days

Choose coins with:

RVOL > 2

This means participation is increasing.

4. Trend Strength

Since your strategy is breakout-based, only add coins that are already trending.

Example:

20 EMA > 50 EMA

or

ADX(14) > 25

This avoids dead coins.

5. Average Daily Range (ADR)

You need movement.

For example:

ADR > 8%

Some new coins move only 2-3% daily and won't justify trading fees and slippage.

6. Number of Days Closing Above 20 MA

A simple ranking metric:

Score = Consecutive closes above 20 MA

Higher score = stronger trend.

7. Avoid Meme Coins With Tiny Open Interest

Check:

Volume
Open Interest

Sometimes volume is fake. Open interest tells you real money is participating.

I would require:

OI > $1M

or higher depending on the exchange.

My ranking formula for new listings

You could score every new coin:

Score =
30% Volume Rank
30% OI Growth
20% Trend Strength
20% ADR

Then pick the top 3 coins.

Example:

Coin	Volume	OI Growth	ADR	Score
Coin A	High	High	12%	90
Coin B	Medium	High	15%	82
Coin C	High	Low	8%	65

Trade only the top-ranked ones.

Since your algo trades on 2H timeframe, I would use this exact filter:

✅ Listed for at least 7 days
✅ 24H Volume > $10M
✅ RVOL > 2
✅ ADX(14) > 25
✅ ADR(14) > 8%
✅ OI increasing for 3 consecutive days
✅ Price above 20 EMA

If more than one new coin passes, rank them by:

Rank Score =
0.4 × Volume Rank +
0.3 × OI Growth +
0.2 × ADR +
0.1 × ADX

Then trade the top 3 symbols only.

This approach should give you the best chance of capturing strong post-listing trends while avoiding the majority of low-quality listings that quickly lose momentum.

----------------------------------------------------------------------------------------------

Refer below chats for remove rule


Coin selection logic is good. When should stop trading in the new coin? 

This is an important question because newly listed coins eventually lose their edge. You don't want your algo trading dead coins months later.

I would remove a coin from the trading universe when one or more of these conditions occur:

1. Volume Drops Significantly (Primary Exit Rule)

Stop trading if:

Current 7-day average volume < 30% of peak volume

Example:

Peak volume = $100M
Current average volume = $25M

➡️ Remove the coin.

2. Open Interest Falls

Stop trading if:

Current OI < 40% of peak OI

This means traders have lost interest.

3. Volatility Becomes Too Low

For your 2H breakout system:

ATR(14) / Price < 3%

Low volatility means:

More false breakouts
Fees become a bigger percentage of profits
Trend following stops working.
4. No Significant Trend for a Long Time

If:

ADX(14) < 20
for 30 consecutive days

Remove it.

The coin has become range-bound.

5. Poor Strategy Performance

This is the most important rule because it is specific to your strategy.

Maintain rolling statistics:

Last 20 trades
Last 90 days

Remove coin if:

Profit Factor < 1

OR

Win Rate < 35%

OR

Max Drawdown > 2 × average drawdown
6. Market Cap Rank Falls Heavily

Sometimes hype disappears.

Example:

Coin launched in top 50.
Falls to top 300.

Liquidity usually deteriorates.

My suggestion for your Delta algo

Keep three groups:

Permanent Universe

BTC, ETH, SOL, etc.

Active New Listings

New coins being traded.

Watchlist

Coins removed but monitored.

Add Rule
Listing Age >= 7 days
Volume > $20M
OI Growth > 50%
Remove Rule
Volume < $10M
OR
OI < 40% of peak
OR
ATR% < 3%
OR
No profitable trades for 90 days