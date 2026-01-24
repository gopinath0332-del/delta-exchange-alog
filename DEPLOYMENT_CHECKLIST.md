# Quick Deployment Checklist - Firebase Journal to Pi

## Before You Start

- [ ] Get Firebase User ID from browser console: `firebase.auth().currentUser.uid`
- [ ] Copy the ID somewhere safe

## On Your Local Machine

```bash
cd /Users/admin/Projects/delta-exchange-alog

# 1. Check changes
git status

# 2. Add and commit
git add .
git commit -m "Add Firebase trade journal integration"

# 3. Push to repository
git push origin main
```

## On Raspberry Pi (SSH)

```bash
# 1. SSH into Pi
ssh pi@your-pi-ip

# 2. Navigate to project
cd ~/delta-exchange-algo

# 3. Stop bot
sudo systemctl stop trading-bot.service

# 4. Pull changes
git pull origin main

# 5. Install dependency
source venv/bin/activate
pip install requests

# 6. Configure Firebase User ID
nano config/.env
# Update: FIREBASE_USER_ID=<paste your ID here>
# Save: Ctrl+X, Y, Enter

# 7. Test
python3 test_firebase_journal.py

# 8. Start bot
sudo systemctl start trading-bot.service

# 9. Monitor
tail -f logs/trading.log
```

## Verify

- [ ] Test script shows success
- [ ] Test trade appears in MyTradeJournal
- [ ] Bot logs show: "✓ Firebase journal initialized and ready"
- [ ] First trade logs to Firebase successfully

## Quick Rollback (if needed)

```bash
# Option 1: Disable feature
nano config/.env
# Set: ENABLE_FIREBASE_JOURNAL=false

# Option 2: Full rollback
git log --oneline  # Find previous commit
git checkout <commit-hash>
sudo systemctl restart trading-bot.service
```

---

**Full guide:** See [docs/DEPLOYMENT_FIREBASE.md](file:///Users/admin/Projects/delta-exchange-alog/docs/DEPLOYMENT_FIREBASE.md)
