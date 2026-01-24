# Firebase Trade Journal Integration

Automatically log every trade from delta-exchange-algo to your MyTradeJournal Firebase database.

## Overview

This integration connects your delta-exchange trading bot with the MyTradeJournal web application, automatically creating journal entries for every trade:

- **Entry Logging**: When a trade is executed (ENTRY_LONG/ENTRY_SHORT), it's logged to Firebase
- **Exit Logging**: When a trade closes (EXIT_LONG/EXIT_SHORT), the journal entry is updated with exit price and P&L
- **Profile Support**: Trades are automatically assigned to your "Crypto" profile
- **Real-time Sync**: Changes appear immediately in your MyTradeJournal web app

## Setup

### 1. Get Your Firebase User ID

1. Open your MyTradeJournal web app in a browser
2. Open browser Developer Tools (press F12)
3. Go to the **Console** tab
4. Run this command:
   ```javascript
   firebase.auth().currentUser.uid;
   ```
5. Copy the ID that appears (something like: `"Ab12Cd34Ef56Gh78..."`)

### 2. Configure Environment Variables

Edit `config/.env` and update the Firebase section:

```bash
ENABLE_FIREBASE_JOURNAL=true
FIREBASE_USER_ID=<paste_your_uid_here>
```

That's it! The other Firebase values are already configured.

### 3. Install Dependencies

```bash
cd /Users/admin/Projects/delta-exchange-alog
source venv/bin/activate
pip install requests
```

## Testing

```bash
cd /Users/admin/Projects/delta-exchange-alog
source venv/bin/activate
pip install requests
```

## Testing

Test the integration before running live trades:

```bash
python test_firebase_journal.py
```

This will:

1. Verify Firebase connection
2. Log a test trade entry
3. Update the test trade with an exit
4. Show you the trade ID

Open MyTradeJournal and verify the test trade appears in your Crypto profile.

## How It Works

### Entry Logging

When `execute_strategy_signal()` is called with an ENTRY action:

1. Order is placed on Delta Exchange
2. Trade details are logged to Firebase via REST API
3. Firebase trade ID is returned
4. Strategy stores the ID for later reference

### Exit Logging

When a trade is closed:

1. Strategy calculates P&L
2. Firebase journal is updated with exit price and P&L
3. Exit date is set (final exit only, not partial exits)

### Data Mapping

| Delta Algo Field | Firebase Field | Notes                            |
| ---------------- | -------------- | -------------------------------- |
| symbol           | symbol         | e.g., "BTCUSD"                   |
| action           | tradeType      | "BUY" for long, "SELL" for short |
| price            | entryPrice     | Execution price                  |
| order_size       | quantity       | Position size in contracts       |
| strategy_name    | strategy       | e.g., "RSI-50-EMA"               |
| -                | contract       | Always "Perpetual"               |
| -                | profileId      | Your Crypto profile ID           |
| -                | userId         | Your Firebase user ID            |

## Troubleshooting

### Firebase journal disabled

**Problem**: Logs show "Firebase journal disabled"

**Solutions**:

- Check `ENABLE_FIREBASE_JOURNAL=true` in config/.env
- Verify all required env vars are set (not YOUR_FIREBASE_USER_ID)
- Run test script to see specific missing configs

### Permission denied

**Problem**: "Permission denied accessing Firestore"

**Solutions**:

- Verify FIREBASE_USER_ID matches your authenticated user
- Check Firebase Security Rules allow your user to write to `trades` collection
- Ensure you're logged into MyTradeJournal web app

### Trades not appearing

**Problem**: Test succeeds but trades don't appear in MyTradeJournal

**Solutions**:

- Verify correct profile is selected in MyTradeJournal
- Check browser console for errors
- Refresh the MyTradeJournal page
- Verify FIREBASE_CRYPTO_PROFILE_ID matches your Crypto profile

### Wrong profile

**Problem**: Trades appear in wrong profile or "Default Profile"

**Solution**:

- Update `FIREBASE_CRYPTO_PROFILE_ID` in config/.env
- Get correct ID from Firebase Console → Firestore → profiles collection

## Architecture

```
delta-exchange-algo/
├── core/
│   ├── firebase_journal.py      # Firebase service (REST API)
│   ├── trading.py                # Logs entries after order placement
│   └── runner.py                 # Passes trade IDs to strategies
├── strategies/
│   ├── rsi_50_ema_strategy.py   # Updates exits (example)
│   └── ...                       # Other strategies need updates
├── config/
│   └── .env                      # Firebase configuration
└── test_firebase_journal.py      # Integration test script
```

## Updating Other Strategies

Currently only `rsi_50_ema_strategy.py` has exit logging implemented. To add to other strategies:

1. Update `update_position_state()` signature to accept `firebase_trade_id`
2. Store `firebase_trade_id` in `active_trade` dict on entry
3. On exit, import and call `get_journal_service().update_exit()`

See `rsi_50_ema_strategy.py` lines 185-247 for reference implementation.

## Disabling

To disable automatic journal logging:

```bash
# In config/.env
ENABLE_FIREBASE_JOURNAL=false
```

Trades will still execute normally, just won't log to Firebase.

## Security Notes

- Firebase credentials in `.env` should NOT be committed to git
- The `.env` file is already in `.gitignore`
- API key is safe to use in this context (secured by Firestore rules)
- User ID ensures trades are only written to your account
