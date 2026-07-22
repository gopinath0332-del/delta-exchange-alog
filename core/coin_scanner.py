"""
New Coin Scanner Module.
Scans Delta Exchange for newly listed perpetual contracts, evaluates them using
technical indicators on 2H Heikin Ashi candles, tracks daily snapshots, and sends reports.
"""

import os
import json
import time
import math
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Tuple, Optional
import pandas as pd
import numpy as np
import yaml
import ta

from core.config import Config
from api.rest_client import DeltaRestClient
from core.logger import get_logger

logger = get_logger(__name__)

# State paths
STATE_FILE = "data/scanner_state.json"
OI_SNAPSHOTS_FILE = "data/oi_snapshots.json"


class NewCoinScanner:
    """Scans and monitors newly listed perpetual coins on Delta Exchange."""

    def __init__(self, client: DeltaRestClient, config: Config):
        self.client = client
        self.config = config
        self.scanner_config = self._load_scanner_config()
        self._ensure_data_dir()

    def _load_scanner_config(self) -> dict:
        """Load coin scanner specific configuration."""
        yaml_path = "config/coin_scanner.yaml"
        if os.path.exists(yaml_path):
            try:
                with open(yaml_path, "r") as f:
                    data = yaml.safe_load(f)
                    return data.get("coin_scanner", {})
            except Exception as e:
                logger.error(f"Failed to load config/coin_scanner.yaml: {e}")
        
        # Safe default configuration
        return {
            "min_listing_age_days": 7,
            "max_listing_age_days": 30,
            "min_24h_volume_usd": 10000000,
            "min_rvol": 2.0,
            "min_adx": 25,
            "min_adr_pct": 8.0,
            "min_oi_growth_days": 3,
            "require_above_ema20": True,
            "top_n_coins": 3,
            "removal_volume_min": 10000000,
            "removal_oi_pct_of_peak": 0.40,
            "removal_atr_pct_min": 3.0,
            "removal_adx_min": 20,
            "removal_adx_days": 30,
        }

    def _ensure_data_dir(self):
        """Ensure the data folder exists."""
        os.makedirs("data", exist_ok=True)

    def _load_json(self, filepath: str) -> dict:
        """Helper to load JSON file safely."""
        if os.path.exists(filepath):
            try:
                with open(filepath, "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading JSON file {filepath}: {e}")
        return {}

    def _save_json(self, filepath: str, data: dict):
        """Helper to save JSON file safely."""
        try:
            with open(filepath, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving JSON file {filepath}: {e}")

    def fetch_candidates(self) -> List[Dict[str, Any]]:
        """
        Fetch candidate perpetual products listed between 7 and 30 days ago.
        Handles API pagination cursor automatically.
        """
        logger.info("Fetching new coin candidates...")
        try:
            params = {
                "states": "live",
                "contract_types": "perpetual_futures",
                "page_size": 100
            }
            products = []
            
            while True:
                response = self.client._make_direct_request("/v2/products", params=params)
                if not response:
                    break
                
                batch = response.get("result", [])
                if not batch:
                    break
                    
                products.extend(batch)
                
                # Check for pagination cursor
                next_cursor = response.get("meta", {}).get("after")
                if not next_cursor:
                    break
                params["after"] = next_cursor

            now = datetime.now(timezone.utc)
            candidates = []

            min_age = self.scanner_config.get("min_listing_age_days", 7)
            max_age = self.scanner_config.get("max_listing_age_days", 30)

            for p in products:
                symbol = p.get("symbol", "")
                if not symbol.endswith("USD"):
                    continue

                created_at_str = p.get("launch_time", p.get("created_at"))
                if not created_at_str:
                    continue

                try:
                    # Parse timestamp (e.g. "2026-06-28T10:00:00Z")
                    created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                    age_days = (now - created_at).total_seconds() / (24 * 3600)

                    if min_age <= age_days <= max_age:
                        candidates.append({
                            "symbol": symbol,
                            "product_id": p.get("id"),
                            "created_at": created_at_str,
                            "age_days": round(age_days, 1)
                        })
                except Exception as e:
                    logger.warning(f"Error parsing created_at for {symbol}: {e}")

            logger.info(f"Fetched {len(products)} total products. Found {len(candidates)} candidates matching listing age filter.")
            return candidates

        except Exception as e:
            logger.error(f"Failed to fetch candidates: {e}", exc_info=True)
            return []

    def apply_heikin_ashi(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply Heikin Ashi transformation to candle DataFrame."""
        ha = df.copy()
        
        # Convert columns to float
        o = df["open"].astype(float)
        h = df["high"].astype(float)
        l = df["low"].astype(float)
        c = df["close"].astype(float)

        ha["close"] = (o + h + l + c) / 4.0
        
        ha_open = [(o.iloc[0] + c.iloc[0]) / 2.0]
        for i in range(1, len(df)):
            ha_open.append((ha_open[-1] + ha["close"].iloc[i - 1]) / 2.0)
        ha["open"] = ha_open
        
        ha["high"] = pd.concat([h, ha["open"], ha["close"]], axis=1).max(axis=1)
        ha["low"] = pd.concat([l, ha["open"], ha["close"]], axis=1).min(axis=1)
        return ha

    def update_oi_snapshots(self, symbol: str, current_oi: float):
        """Append today's OI snapshot and keep last 7 days."""
        snapshots = self._load_json(OI_SNAPSHOTS_FILE)
        
        if symbol not in snapshots:
            snapshots[symbol] = {}
            
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        snapshots[symbol][today_str] = current_oi
        
        # Sort and keep only the last 7 snapshots to prevent file bloating
        dates_sorted = sorted(snapshots[symbol].keys())
        if len(dates_sorted) > 7:
            for old_date in dates_sorted[:-7]:
                snapshots[symbol].pop(old_date)
                
        self._save_json(OI_SNAPSHOTS_FILE, snapshots)

    def check_oi_growth(self, symbol: str, current_oi: float) -> Tuple[bool, int, float]:
        """
        Check if Open Interest has been increasing for consecutive days.
        Returns: (is_growing_3_days, consecutive_days, growth_rate_3_days)
        """
        snapshots = self._load_json(OI_SNAPSHOTS_FILE)
        symbol_data = snapshots.get(symbol, {})
        
        # Get sorted historical snapshot entries
        sorted_dates = sorted(symbol_data.keys())
        if len(sorted_dates) < 3:
            # Not enough history yet - return False but show progress
            return False, len(sorted_dates), 0.0
            
        # Get last 3 values
        val_today = symbol_data[sorted_dates[-1]]
        val_yesterday = symbol_data[sorted_dates[-2]]
        val_day_before = symbol_data[sorted_dates[-3]]
        
        is_increasing = (val_today > val_yesterday) and (val_yesterday > val_day_before)
        
        # Calculate consecutive up days (max 5)
        consecutive = 0
        for i in range(len(sorted_dates) - 1, 0, -1):
            if symbol_data[sorted_dates[i]] > symbol_data[sorted_dates[i - 1]]:
                consecutive += 1
            else:
                break
                
        # Calculate 3-day growth rate
        growth_rate = 0.0
        if val_day_before > 0:
            growth_rate = (val_today - val_day_before) / val_day_before
            
        return is_increasing, consecutive, growth_rate

    def evaluate_candidate(self, candidate: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Evaluate a single candidate against all 7 entry criteria.
        Returns metrics dict if passes initial checks, otherwise None.
        """
        symbol = candidate["symbol"]
        
        try:
            # 1. Fetch Ticker for Volume & current stats
            ticker = self.client.get_ticker(symbol)
            if not ticker:
                return None
                
            volume_24h = float(ticker.get("turnover_usd", ticker.get("volume", 0.0)))
            current_price = float(ticker.get("close", ticker.get("mark_price", 0.0)))
            current_oi = float(ticker.get("oi_value_usd", 0.0))

            # Always update OI snapshots before any filter checks so daily OI history
            # accumulates even on low-volume days. This is required for the OI growth
            # filter to have enough data points across consecutive days.
            self.update_oi_snapshots(symbol, current_oi)

            # Minimum Volume Check
            min_vol = self.scanner_config.get("min_24h_volume_usd", 10000000)
            if volume_24h < min_vol:
                return None
            
            # 2. Fetch candles (last 30 days of 2H candles)
            # 30 days of 2H = 360 candles
            end_time = int(time.time())
            start_time = end_time - (30 * 24 * 3600)
            
            candles = self.client.get_historical_candles(
                symbol=symbol,
                resolution="2h",
                start=start_time,
                end=end_time
            )
            
            if not candles or len(candles) < 84:  # requires at least 7 days (84 2H bars)
                logger.warning(f"Skipping {symbol}: insufficient candle history ({len(candles) if candles else 0} bars)")
                return None
                
            df = pd.DataFrame(candles)
            # Ensure chronological order
            if df["time"].iloc[0] > df["time"].iloc[-1]:
                df = df.iloc[::-1].reset_index(drop=True)
                
            # Apply Heikin Ashi transformation
            ha = self.apply_heikin_ashi(df)
            
            # 3. Calculate indicators
            # EMA(20) on HA close
            ema20 = ta.trend.ema_indicator(ha["close"], window=20)
            # ATR(14) on HA candles
            atr14 = ta.volatility.average_true_range(ha["high"], ha["low"], ha["close"], window=14)
            # ADX(14) on HA candles
            adx14_indicator = ta.trend.ADXIndicator(ha["high"], ha["low"], ha["close"], window=14)
            adx14 = adx14_indicator.adx()
            
            # Today's volume vs 7-day average of 24h volume
            # Each day is 12 candles on 2H.
            today_vol = df["volume"].iloc[-12:].sum()
            
            # Mean daily volume over last 7 days
            daily_volumes = []
            for d in range(7):
                start_idx = -12 * (d + 1)
                end_idx = -12 * d if d > 0 else None
                if end_idx:
                    daily_volumes.append(df["volume"].iloc[start_idx:end_idx].sum())
                else:
                    daily_volumes.append(df["volume"].iloc[start_idx:].sum())
            avg_vol_7d = float(np.mean(daily_volumes)) if daily_volumes else 0.0
            rvol = float(today_vol / avg_vol_7d) if avg_vol_7d > 0.0 else 0.0
            
            # Current values
            last_close_ha = float(ha["close"].iloc[-1])
            last_ema20 = float(ema20.iloc[-1])
            last_atr = float(atr14.iloc[-1])
            last_adx = float(adx14.iloc[-1])
            adr_pct = float(last_atr / current_price * 100.0)
            
            # Check OI growth
            oi_growing, consecutive_oi_days, oi_growth_rate = self.check_oi_growth(symbol, current_oi)
            oi_growing = bool(oi_growing)
            consecutive_oi_days = int(consecutive_oi_days)
            oi_growth_rate = float(oi_growth_rate)
            
            # Check Entry Filters
            min_rvol = float(self.scanner_config.get("min_rvol", 2.0))
            min_adx = float(self.scanner_config.get("min_adx", 25))
            min_adr = float(self.scanner_config.get("min_adr_pct", 8.0))
            require_ema20 = bool(self.scanner_config.get("require_above_ema20", True))
            min_oi_days = int(self.scanner_config.get("min_oi_growth_days", 3))
            
            filters_status = {
                "age": True,  # Already filtered in candidate list
                "volume": bool(volume_24h >= min_vol),
                "rvol": bool(rvol >= min_rvol),
                "adx": bool(last_adx >= min_adx),
                "adr": bool(adr_pct >= min_adr),
                "ema20": bool(last_close_ha > last_ema20 if require_ema20 else True),
                "oi_growth": bool(consecutive_oi_days >= min_oi_days or oi_growing)  # pass if growing or matches days
            }
            
            # Check if all filters pass
            passes_all = bool(all(filters_status.values()))
            
            metrics = {
                "symbol": symbol,
                "product_id": candidate["product_id"],
                "age_days": candidate["age_days"],
                "volume_24h": volume_24h,
                "rvol": round(rvol, 2),
                "adx": round(last_adx, 2),
                "adr_pct": round(adr_pct, 2),
                "last_close_ha": round(last_close_ha, 4),
                "last_ema20": round(last_ema20, 4),
                "consecutive_oi_days": consecutive_oi_days,
                "oi_value_usd": current_oi,
                "oi_growth_rate": oi_growth_rate,
                "passes": passes_all,
                "filters": filters_status
            }
            
            return metrics
            
        except Exception as e:
            logger.error(f"Error evaluating candidate {symbol}: {e}", exc_info=True)
            return None

    def score_and_rank(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Rank the qualified candidates using percentile ranking.
        Score = 0.4*Vol_Rank + 0.3*OI_Rank + 0.2*ADR_Rank + 0.1*ADX_Rank
        """
        if not candidates:
            return []
            
        # Helper to get relative percentile ranks
        def get_ranks(values: list, reverse: bool = False) -> list:
            if not values:
                return []
            series = pd.Series(values)
            if reverse:
                return (series.rank(method="min", ascending=False) / len(series)).tolist()
            return (series.rank(method="min", ascending=True) / len(series)).tolist()

        # Extract values for ranking
        vols = [c["volume_24h"] for c in candidates]
        oi_growths = [c["oi_growth_rate"] for c in candidates]
        adrs = [c["adr_pct"] for c in candidates]
        adxs = [c["adx"] for c in candidates]
        
        # Calculate ranks (higher values are better, so ascending=True matches higher percentile)
        vol_ranks = get_ranks(vols)
        oi_ranks = get_ranks(oi_growths)
        adr_ranks = get_ranks(adrs)
        adx_ranks = get_ranks(adxs)
        
        ranked_candidates = []
        for i, c in enumerate(candidates):
            score = (
                0.4 * vol_ranks[i] +
                0.3 * oi_ranks[i] +
                0.2 * adr_ranks[i] +
                0.1 * adx_ranks[i]
            ) * 100.0
            
            c_copy = c.copy()
            c_copy["score"] = round(score, 1)
            ranked_candidates.append(c_copy)
            
        # Sort by score descending
        ranked_candidates.sort(key=lambda x: x["score"], reverse=True)
        return ranked_candidates

    def save_monitored_coins(self, qualified: List[Dict[str, Any]]):
        """Save newly qualified coins to the monitored list in scanner_state.json."""
        state = self._load_json(STATE_FILE)
        
        if "monitored_coins" not in state:
            state["monitored_coins"] = []
            
        monitored_symbols = {m["symbol"] for m in state["monitored_coins"]}
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        for q in qualified:
            symbol = q["symbol"]
            if symbol not in monitored_symbols:
                state["monitored_coins"].append({
                    "symbol": symbol,
                    "date_added": today_str,
                    "peak_volume": q["volume_24h"],
                    "peak_oi": q["oi_value_usd"],
                    "consecutive_low_adx_days": 0
                })
                logger.info(f"Added {symbol} to monitored coins state.")
                
        state["last_run_date"] = today_str
        self._save_json(STATE_FILE, state)

    def check_removal_criteria(self) -> List[Dict[str, Any]]:
        """
        Evaluate currently monitored coins in scanner_state.json against removal rules.
        Removes triggering coins from state and returns list of warnings.
        """
        state = self._load_json(STATE_FILE)
        monitored = state.get("monitored_coins", [])
        
        if not monitored:
            return []
            
        warnings_triggered = []
        remaining_coins = []
        
        vol_min = self.scanner_config.get("removal_volume_min", 10000000)
        oi_peak_ratio = self.scanner_config.get("removal_oi_pct_of_peak", 0.40)
        atr_pct_min = self.scanner_config.get("removal_atr_pct_min", 3.0)
        adx_min = self.scanner_config.get("removal_adx_min", 20)
        adx_days_max = self.scanner_config.get("removal_adx_days", 30)
        
        for m in monitored:
            symbol = m["symbol"]
            remove = False
            reasons = []
            
            try:
                # 1. Fetch current ticker stats
                ticker = self.client.get_ticker(symbol)
                if not ticker:
                    remaining_coins.append(m)  # Keep if network call fails
                    continue
                    
                volume_24h = float(ticker.get("turnover_usd", ticker.get("volume", 0.0)))
                current_price = float(ticker.get("close", ticker.get("mark_price", 0.0)))
                current_oi = float(ticker.get("oi_value_usd", 0.0))
                
                # Update peaks in state dict
                m["peak_volume"] = max(m.get("peak_volume", 0.0), volume_24h)
                m["peak_oi"] = max(m.get("peak_oi", 0.0), current_oi)
                
                # Fetch recent candles (14 days of 2H candles)
                end_time = int(time.time())
                start_time = end_time - (14 * 24 * 3600)
                
                candles = self.client.get_historical_candles(
                    symbol=symbol,
                    resolution="2h",
                    start=start_time,
                    end=end_time
                )
                
                if candles and len(candles) >= 14:
                    df = pd.DataFrame(candles)
                    if df["time"].iloc[0] > df["time"].iloc[-1]:
                        df = df.iloc[::-1].reset_index(drop=True)
                        
                    ha = self.apply_heikin_ashi(df)
                    atr14 = ta.volatility.average_true_range(ha["high"], ha["low"], ha["close"], window=14)
                    adx14_ind = ta.trend.ADXIndicator(ha["high"], ha["low"], ha["close"], window=14)
                    adx14 = adx14_ind.adx()
                    
                    last_atr = float(atr14.iloc[-1])
                    last_adx = float(adx14.iloc[-1])
                    atr_pct = float(last_atr / current_price * 100.0)
                else:
                    last_adx = 25.0
                    atr_pct = 5.0
                
                # Rule 1: Volume drops below $10M
                if volume_24h < vol_min:
                    remove = True
                    reasons.append(f"Volume < ${vol_min/1e6:.1f}M (Current: ${volume_24h/1e6:.2f}M)")
                    
                # Rule 2: OI drops below 40% of peak OI
                peak_oi = m["peak_oi"]
                if peak_oi > 0 and (current_oi / peak_oi) < oi_peak_ratio:
                    remove = True
                    reasons.append(f"OI < {oi_peak_ratio*100:.0f}% of peak (Current: ${current_oi/1e6:.2f}M vs Peak: ${peak_oi/1e6:.2f}M)")
                    
                # Rule 3: ATR% drops below 3%
                if atr_pct < atr_pct_min:
                    remove = True
                    reasons.append(f"Volatility ATR% < {atr_pct_min:.1f}% (Current: {atr_pct:.2f}%)")
                    
                # Rule 4: ADX < 20 for 30 consecutive days
                if last_adx < adx_min:
                    # Each day has 12 candles on 2H resolution.
                    # Since we scan daily, we increment the counter by 1.
                    m["consecutive_low_adx_days"] = m.get("consecutive_low_adx_days", 0) + 1
                else:
                    m["consecutive_low_adx_days"] = 0
                    
                if m["consecutive_low_adx_days"] >= adx_days_max:
                    remove = True
                    reasons.append(f"ADX < {adx_min} for {adx_days_max} consecutive days")
                    
                if remove:
                    warnings_triggered.append({
                        "symbol": symbol,
                        "reasons": reasons,
                        "volume_24h": volume_24h,
                        "oi_value_usd": current_oi,
                        "peak_oi": peak_oi,
                        "adx": last_adx,
                        "atr_pct": atr_pct
                    })
                    logger.info(f"Monitored coin {symbol} triggered removal criteria: {reasons}")
                else:
                    remaining_coins.append(m)
                    
            except Exception as e:
                logger.error(f"Error checking removal criteria for {symbol}: {e}", exc_info=True)
                remaining_coins.append(m)  # Keep on error to prevent losing state
                
        # Save updated monitored list (removing triggered ones)
        state["monitored_coins"] = remaining_coins
        self._save_json(STATE_FILE, state)
        
        return warnings_triggered

    def run_daily_scan(self) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Main execution path:
        1. Fetch candidates and evaluate entry criteria.
        2. Score & rank qualified new coins.
        3. Save qualified coins to monitored state.
        4. Evaluate existing monitored coins against removal criteria.
        Returns: (qualified_coins, removal_warnings)
        """
        logger.info("Executing New Coin Scanner Daily run...")
        
        # 1. Check entry criteria
        candidates = self.fetch_candidates()
        qualified = []
        
        for c in candidates:
            # Politeness delay to prevent rate limit starvation
            time.sleep(2.0)
            
            metrics = self.evaluate_candidate(c)
            if metrics and metrics["passes"]:
                qualified.append(metrics)
                
        # Rank qualified coins
        ranked_qualified = self.score_and_rank(qualified)
        
        # Limit to top N
        top_n = self.scanner_config.get("top_n_coins", 3)
        top_qualified = ranked_qualified[:top_n]
        
        # Save newly qualified ones to state
        if top_qualified:
            self.save_monitored_coins(top_qualified)
            
        # 2. Check removal criteria
        removal_warnings = self.check_removal_criteria()
        
        # Update last run date
        state = self._load_json(STATE_FILE)
        state["last_run_date"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self._save_json(STATE_FILE, state)
        
        return top_qualified, removal_warnings

    def run_startup_check_if_needed(self) -> Optional[Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]]:
        """Run daily scan on startup if not already run today."""
        state = self._load_json(STATE_FILE)
        last_run = state.get("last_run_date")
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        if last_run != today_str:
            logger.info(f"Scanner has not run today yet (last run: {last_run}). Running startup scan...")
            return self.run_daily_scan()
        else:
            logger.info("Scanner already ran today. Skipping startup scan.")
            return None
