"""
Firestore Client for Trade Journaling.

This module provides a centralized Firestore client for logging all trade
executions to Google Cloud Firestore for historical analysis and journaling.
"""

import os
from typing import Optional, Dict, Any
from datetime import datetime
from core.logger import get_logger

logger = get_logger(__name__)

# Global Firestore client instance (singleton pattern)
_firestore_client = None
_firestore_enabled = False
_firestore_collection = "trades"


def initialize_firestore(service_account_path: str, collection_name: str = "trades", enabled: bool = True):
    """
    Initialize Firestore client with service account credentials.
    
    Args:
        service_account_path: Path to Firebase Admin SDK service account JSON file
        collection_name: Firestore collection name for trades
        enabled: Whether Firestore journaling is enabled
    
    Returns:
        bool: True if initialization successful, False otherwise
    """
    global _firestore_client, _firestore_enabled, _firestore_collection
    
    _firestore_enabled = enabled
    _firestore_collection = collection_name
    
    if not enabled:
        logger.info("Firestore trade journaling is disabled in configuration")
        return False
    
    try:
        # Import here to avoid dependency issues if firebase-admin is not installed
        import firebase_admin
        from firebase_admin import credentials, firestore
        
        # Check if service account file exists
        if not os.path.exists(service_account_path):
            logger.error(f"Firestore service account file not found: {service_account_path}")
            _firestore_enabled = False
            return False
        
        # Initialize Firebase Admin SDK (only once)
        if not firebase_admin._apps:
            cred = credentials.Certificate(service_account_path)
            firebase_admin.initialize_app(cred)
            logger.info("Firebase Admin SDK initialized successfully")
        
        # Get Firestore client
        _firestore_client = firestore.client()
        logger.info(f"Firestore client initialized. Collection: '{collection_name}'")
        
        return True
        
    except ImportError as e:
        logger.error(f"Firebase Admin SDK not installed. Run: pip install firebase-admin. Error: {e}")
        _firestore_enabled = False
        return False
    except Exception as e:
        logger.error(f"Failed to initialize Firestore client: {e}", exc_info=True)
        _firestore_enabled = False
        return False


def journal_trade(
    symbol: str,
    action: str,
    side: str,
    price: float,
    order_size: int,
    leverage: int,
    mode: str,
    strategy_name: Optional[str] = None,
    rsi: Optional[float] = None,
    reason: Optional[str] = None,
    is_entry: bool = False,
    is_partial_exit: bool = False,
    entry_price: Optional[float] = None,
    exit_price: Optional[float] = None,
    execution_price: Optional[float] = None,
    pnl: Optional[float] = None,
    funding_charges: Optional[float] = None,
    trading_fees: Optional[float] = None,
    margin_used: Optional[float] = None,
    remaining_margin: Optional[float] = None,
    product_id: Optional[int] = None,
    order_id: Optional[str] = None,
    **kwargs
) -> Optional[str]:
    """
    Journal a trade to Firestore.
    
    This function logs comprehensive trade data to Firestore for historical
    analysis, performance tracking, and trade journaling. It handles all
    errors gracefully to ensure trade execution is never interrupted.
    
    Args:
        symbol: Trading symbol (e.g., 'BTCUSD', 'ETHUSD')
        action: Trade action (e.g., 'ENTRY_LONG', 'EXIT_LONG', 'EXIT_LONG_PARTIAL')
        side: Order side ('buy' or 'sell')
        price: Current market price (candle close price)
        order_size: Number of contracts
        leverage: Leverage used
        mode: Execution mode ('live' or 'paper')
        strategy_name: Name of the strategy (e.g., 'Double Dip RSI')
        rsi: RSI value at trade time
        reason: Trade reason/trigger
        is_entry: Whether this is an entry trade
        is_partial_exit: Whether this is a partial exit
        entry_price: Entry price for this trade (for exits, from strategy state)
        exit_price: Exit price (execution price for exits)
        execution_price: Actual execution price from exchange
        pnl: Profit & Loss (for exits)
        funding_charges: Funding charges (for exits)
        trading_fees: Trading fees/commission (for exits)
        margin_used: Margin used for this trade
        remaining_margin: Remaining margin after trade
        product_id: Delta Exchange product ID
        order_id: Exchange order ID
        **kwargs: Additional fields to store
    
    Returns:
        Optional[str]: Document ID if successful, None otherwise
    """
    global _firestore_client, _firestore_enabled, _firestore_collection
    
    # Check if Firestore is enabled
    if not _firestore_enabled:
        logger.debug("Firestore journaling disabled, skipping trade journal")
        return None
    
    # Check if client is initialized
    if _firestore_client is None:
        logger.warning("Firestore client not initialized, skipping trade journal")
        return None
    
    try:
        # Build trade document
        trade_doc = {
            # Metadata
            "timestamp": datetime.utcnow(),  # Firestore will auto-convert to Timestamp
            "symbol": symbol,
            "strategy_name": strategy_name or "Unknown",
            "mode": mode,
            
            # Action details
            "action": action,
            "side": side,
            "price": price,
            "order_size": order_size,
            "leverage": leverage,
            
            # Entry/Exit classification
            "is_entry": is_entry,
            "is_partial_exit": is_partial_exit,
            "entry_price": entry_price,
            "exit_price": exit_price,
            
            # Financial metrics (mostly for exits)
            "pnl": pnl,
            "funding_charges": funding_charges,
            "trading_fees": trading_fees,
            "margin_used": margin_used,
            "remaining_margin": remaining_margin,
            
            # Technical indicators
            "rsi": rsi,
            "reason": reason,
            
            # Exchange data
            "product_id": product_id,
            "order_id": order_id,
            "execution_price": execution_price or price,
        }
        
        # Add any additional fields from kwargs
        trade_doc.update(kwargs)
        
        # Remove None values to keep documents clean
        trade_doc = {k: v for k, v in trade_doc.items() if v is not None}
        
        # Add document to Firestore (auto-generated ID)
        doc_ref = _firestore_client.collection(_firestore_collection).add(trade_doc)
        doc_id = doc_ref[1].id
        
        logger.info(f"✓ Trade journaled to Firestore: {doc_id} | {symbol} {action} @ ${price:,.2f}")
        
        return doc_id
        
    except Exception as e:
        # Log error but don't raise - we don't want to interrupt trade execution
        logger.error(f"Failed to journal trade to Firestore: {e}", exc_info=True)
        return None


def get_firestore_status() -> Dict[str, Any]:
    """
    Get Firestore client status.
    
    Returns:
        dict: Status information including enabled state, collection name, and connection status
    """
    global _firestore_client, _firestore_enabled, _firestore_collection
    
    return {
        "enabled": _firestore_enabled,
        "connected": _firestore_client is not None,
        "collection": _firestore_collection
    }
