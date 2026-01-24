# Deploying Firebase Journal Integration to Raspberry Pi

This guide walks you through deploying the Firebase trade journal integration to your Raspberry Pi server.

## Prerequisites

- Raspberry Pi server with delta-exchange-algo already running
- Git repository set up
- SSH access to your Pi
- MyTradeJournal Firebase User ID (see below)

## Step 1: Get Your Firebase User ID

**On your local computer** (in a browser with MyTradeJournal open):

1. Open MyTradeJournal web app
2. Press **F12** to open Developer Tools
3. Go to **Console** tab
4. Run this command:
   ```javascript
   firebase.auth().currentUser.uid;
   ```
5. Copy the returned ID (looks like: `"Ab12Cd34Ef56..."`)
6. Save this ID - you'll need it in Step 4

## Step 2: Commit and Push Changes (Local Machine)

```bash
cd /Users/admin/Projects/delta-exchange-alog

# Check what's changed
git status

# Add all changes
git add .

# Commit with descriptive message
git commit -m "Add Firebase trade journal integration"

# Push to your repository
git push origin main
# (or whatever your branch name is)
```

## Step 3: Pull Changes on Raspberry Pi

SSH into your Pi and pull the latest code:

```bash
# SSH into your Pi
ssh pi@your-pi-ip-address

# Navigate to project directory
cd ~/delta-exchange-algo  # or wherever your project is

# Stop the trading bot (if running)
sudo systemctl stop trading-bot.service
# OR if running manually:
# pkill -f "python.*run_strategy_terminal"

# Pull latest changes
git pull origin main

# Check that new files exist
ls core/firebase_journal.py  # Should show the file
```

## Step 4: Install Dependencies

Install the `requests` library (required for Firebase REST API):

```bash
# Activate virtual environment
source venv/bin/activate

# Install requests
pip install requests

# Verify installation
python -c "import requests; print(requests.__version__)"
```

## Step 5: Configure Firebase User ID

Edit the `.env` file on your Pi:

```bash
nano config/.env
```

Find the Firebase section and update `FIREBASE_USER_ID`:

```bash
# Firebase Trade Journal Integration
ENABLE_FIREBASE_JOURNAL=true

# Firebase Project Configuration (already set)
FIREBASE_API_KEY=AIzaSyDE4Gf_sQrWxsdG-1jXAbW7DeaaPd3HCdg
FIREBASE_PROJECT_ID=tradingjournal-5d147
# ... other config already there ...

# Your Firebase User ID - PASTE THE ID YOU COPIED IN STEP 1
FIREBASE_USER_ID=<paste_your_uid_here>

# Profile ID for Crypto trades (already set)
FIREBASE_CRYPTO_PROFILE_ID=CwILJ7NJbSGaM9rUTaF
```

**Save and exit**: Press `Ctrl+X`, then `Y`, then `Enter`

## Step 6: Test Firebase Connection

Run the test script to verify everything works:

```bash
# Make sure you're in the project directory and venv is activated
cd ~/delta-exchange-algo
source venv/bin/activate

# Run test
python3 test_firebase_journal.py
```

**Expected output:**

```
============================================================
Firebase Trade Journal Integration Test
============================================================
Testing Firebase Journal Service...

✓ Firebase journal service initialized
  Project ID: tradingjournal-5d147
  Profile ID: CwILJ7NJbSGaM9rUTaF
  User ID: Ab12Cd34...

Testing trade entry logging...
✓ Test trade logged successfully!
  Trade ID: xYz123AbC...

Testing trade exit update...
✓ Trade exit updated successfully!

============================================================
Test complete! Check your MyTradeJournal app to verify.
============================================================
```

**If test fails:**

- Check that `FIREBASE_USER_ID` is correctly set (not `YOUR_FIREBASE_USER_ID`)
- Verify Pi has internet connection
- Check logs: `tail -f logs/trading.log`

## Step 7: Verify in MyTradeJournal

1. Open MyTradeJournal web app
2. Go to your **Crypto** profile
3. Check recent trades - you should see a test trade:
   - Symbol: BTCUSD
   - Strategy: TEST
   - Entry: $50,000
   - Exit: $51,000
   - PnL: +$1,000 (+2%)

**Delete the test trade** if you don't want it in your journal.

## Step 8: Start Trading Bot

```bash
# If using systemd service:
sudo systemctl start trading-bot.service

# Check status
sudo systemctl status trading-bot.service

# View logs
journalctl -u trading-bot.service -f

# OR if running manually:
cd ~/delta-exchange-algo
source venv/bin/activate
python3 terminal_trade.py XRPUSD rsi-50-ema live
```

## Step 9: Monitor First Live Trade

Watch the logs to see Firebase journal working:

```bash
# Watch live logs
tail -f logs/trading.log

# Look for these log messages:
# - "✓ Firebase journal initialized and ready"
# - "✓ Trade entry logged to Firebase: XRPUSD BUY @ 0.5234 (ID: abc123...)"
# - "✓ Final exit updated in Firebase: abc123 @ 0.5345 (PnL: 10.50)"
```

## Troubleshooting

### "Firebase journal disabled or misconfigured"

**Problem**: Bot starts but Firebase logging is disabled

**Fix**:

```bash
# Check your .env file
cat config/.env | grep FIREBASE

# Verify lines are uncommented and set:
# ENABLE_FIREBASE_JOURNAL=true
# FIREBASE_USER_ID=<your actual ID, not placeholder>
```

### "No module named 'requests'"

**Problem**: `requests` library not installed

**Fix**:

```bash
source venv/bin/activate
pip install requests
```

### Trades not appearing in MyTradeJournal

**Problem**: Test passes but live trades don't show up

**Fixes**:

1. Check bot is actually placing trades (check Delta Exchange)
2. Verify `ENABLE_FIREBASE_JOURNAL=true` in `.env`
3. Check logs for Firebase errors: `grep -i firebase logs/trading.log`
4. Verify correct profile selected in MyTradeJournal app

### Permission/Firestore errors

**Problem**: "Permission denied" or "Firestore error"

**Possible causes**:

- Wrong user ID
- Firebase security rules blocking writes
- Network/firewall blocking Firebase API

**Fix**:

```bash
# Test internet connectivity
ping -c 3 firestore.googleapis.com

# Re-verify user ID is correct
# Check logs for exact error message
tail -30 logs/trading.log
```

## Rollback (If Needed)

If something goes wrong and you need to rollback:

```bash
# Stop bot
sudo systemctl stop trading-bot.service

# Revert to previous commit
git log --oneline  # Find previous commit hash
git checkout <previous-commit-hash>

# Restart bot
sudo systemctl start trading-bot.service
```

Or simply disable Firebase logging:

```bash
nano config/.env
# Change: ENABLE_FIREBASE_JOURNAL=false
```

## Success Checklist

- [ ] Changes committed and pushed from local machine
- [ ] Changes pulled on Raspberry Pi
- [ ] `requests` library installed
- [ ] Firebase User ID configured in `.env`
- [ ] Test script runs successfully
- [ ] Test trade appears in MyTradeJournal
- [ ] Trading bot restarted
- [ ] First live trade logs to Firebase
- [ ] Live trade visible in MyTradeJournal

## Notes

- Firebase logging is **non-blocking** - if it fails, trades still execute normally
- All Firebase errors are logged to `logs/trading.log`
- You can disable anytime by setting `ENABLE_FIREBASE_JOURNAL=false`
- No additional services or ports needed - uses HTTPS to Firebase API

## Next Steps

Once deployed and verified:

- Monitor first few trades to ensure accuracy
- Check MyTradeJournal regularly to review performance
- Adjust strategies based on journal insights
- Consider adding notifications for failed Firebase writes (optional)
