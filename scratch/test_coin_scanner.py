"""
Local Test Script for NewCoinScanner.
Executes candidate fetching, evaluations, and checks removal warnings.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import get_config
from api.rest_client import DeltaRestClient
from core.coin_scanner import NewCoinScanner

def main():
    print("="*60)
    print(" DELTA COIN SCANNER - LOCAL TEST RUNNER")
    print("="*60)
    
    print("\nInitializing Config and REST Client...")
    config = get_config()
    client = DeltaRestClient(config)
    
    print("\nInitializing NewCoinScanner...")
    scanner = NewCoinScanner(client, config)
    
    print("\n1. Fetching Candidates (Age 7-30 Days)...")
    candidates = scanner.fetch_candidates()
    print(f"Candidates found: {len(candidates)}")
    for c in candidates:
        print(f" - {c['symbol']}: ID {c['product_id']}, Age {c['age_days']} days, Listed {c['created_at']}")
        
    # If no candidates, temporarily expand range for demonstration
    if not candidates:
        print("\n[NOTE] No candidates found in the 7-30 day range.")
        print("Temporarily expanding search range to 365 days to sample existing coins...")
        scanner.scanner_config["max_listing_age_days"] = 365
        candidates = scanner.fetch_candidates()
        print(f"Sample candidates found: {len(candidates)}")
        for c in candidates[:5]:
            print(f" - {c['symbol']}: ID {c['product_id']}, Age {c['age_days']} days")
            
    if not candidates:
        print("\n[ERROR] No perpetual contracts found at all on the exchange.")
        return
        
    print("\n2. Evaluating Candidates & Technical Filters...")
    evaluated = []
    # Sample up to 5 candidates
    for c in candidates[:5]:
        print(f"\nEvaluating {c['symbol']}...")
        metrics = scanner.evaluate_candidate(c)
        if metrics:
            evaluated.append(metrics)
            print(f" • 24H Volume: ${metrics['volume_24h']/1e6:.2f}M (Pass: {metrics['filters']['volume']})")
            print(f" • RVOL: {metrics['rvol']:.2f} (Pass: {metrics['filters']['rvol']})")
            print(f" • ADX(14): {metrics['adx']:.1f} (Pass: {metrics['filters']['adx']})")
            print(f" • ATR% (ADR): {metrics['adr_pct']:.2f}% (Pass: {metrics['filters']['adr']})")
            print(f" • Above EMA(20): {metrics['filters']['ema20']} (Close: {metrics['last_close_ha']} vs EMA20: {metrics['last_ema20']})")
            print(f" • OI Growth Days: {metrics['consecutive_oi_days']} (Pass: {metrics['filters']['oi_growth']})")
            print(f" • PASSES ALL CRITERIA: {metrics['passes']}")
        else:
            print(f" • Evaluation returned None (failed volume check or API error).")
            
    print("\n3. Testing Scoring and Ranks...")
    if evaluated:
        ranked = scanner.score_and_rank(evaluated)
        print("Scoring Results:")
        for idx, r in enumerate(ranked, 1):
            print(f" {idx}. {r['symbol']}: Score {r['score']}")
    else:
        print("No candidates were successfully evaluated.")

    print("\n4. Checking Removal Warnings on Monitored Coins...")
    warnings = scanner.check_removal_criteria()
    print(f"Removal warnings triggered: {len(warnings)}")
    for w in warnings:
        print(f" - {w['symbol']}: {w['reasons']}")

    print("\n5. Testing Discord Notification Delivery...")
    try:
        from notifications.manager import NotificationManager
        from core.runner import _send_scanner_discord_messages
        
        notifier = NotificationManager(config)
        
        # Check if Discord is enabled in configuration
        if not config.discord_enabled or not config.discord_webhook_url:
            print(" [WARNING] Discord notifications are disabled or missing webhook URL in .env!")
        else:
            print(" Sending test qualified coin embed and test removal warning embed...")
            
            # Use real qualified data if available
            real_qualified = [e for e in evaluated if e.get("passes")]
            test_qualified = []
            if real_qualified:
                # Add the 'score' key if not already ranked
                ranked_candidates = scanner.score_and_rank(real_qualified)
                test_qualified = ranked_candidates[:3]
                print(f" Sending real-time qualified data for: {[q['symbol'] for q in test_qualified]}")
            else:
                print(" No qualified coins found (passed all filters); sending fallback TESTCOINUSD mock data...")
                test_qualified = [{
                    "symbol": "TESTCOINUSD",
                    "score": 82.5,
                    "age_days": 13.4,
                    "volume_24h": 15400000.0,
                    "rvol": 2.45,
                    "adx": 28.4,
                    "adr_pct": 9.8,
                    "last_close_ha": 0.042,
                    "last_ema20": 0.038,
                    "consecutive_oi_days": 3
                }]
            
            test_warnings = []
            if warnings:
                test_warnings = warnings
                print(f" Sending real-time removal warnings for: {[w['symbol'] for w in test_warnings]}")
            else:
                print(" No monitored warnings triggered; sending fallback STALECOINUSD mock data...")
                test_warnings = [{
                    "symbol": "STALECOINUSD",
                    "reasons": ["Volume < $10.0M (Current: $8.2M)", "OI < 40% of peak (34% of Peak)"],
                    "volume_24h": 8200000.0,
                    "oi_value_usd": 1200000.0,
                    "peak_oi": 3500000.0,
                    "adx": 18.0,
                    "atr_pct": 2.8
                }]
            
            _send_scanner_discord_messages(notifier, test_qualified, test_warnings)
            print(" Discord test alerts dispatched successfully!")
    except Exception as e:
        print(f" [ERROR] Failed to send Discord alerts: {e}")

    print("\n" + "="*60)
    print(" TEST COMPLETED")
    print("="*60)

if __name__ == "__main__":
    main()
