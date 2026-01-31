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
    trade_id: Optional[str] = None,  # Links entry and exit trades together
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
        trade_id: Unique ID linking entry and exit of the same trade (optional)
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
        # Determine trade status based on action
        if is_entry:
            status = "OPEN"
        elif is_partial_exit:
            status = "PARTIAL_CLOSED"
        else:
            status = "CLOSED"
        
        if is_entry:
            # **ENTRY: Create a new trade document**
            # Use trade_id as the document ID for easy updates later
            if not trade_id:
                logger.warning("No trade_id provided for entry, skipping journal")
                return None
            
            trade_doc = {
                # Trade identification
                "trade_id": trade_id,
                "status": status,  # OPEN, PARTIAL_CLOSED, or CLOSED
                
                # Entry metadata
                "entry_timestamp": datetime.utcnow(),
                "symbol": symbol,
                "strategy_name": strategy_name or "Unknown",
                "mode": mode,
                
                # Entry details
                "entry_action": action,
                "entry_side": side,
                "entry_price": entry_price,
                "entry_execution_price": execution_price or price,
                "order_size": order_size,
                "leverage": leverage,
                
                # Entry metrics
                "entry_rsi": rsi,
                "entry_reason": reason,
                "margin_used": margin_used,
                
                # Exchange data
                "product_id": product_id,
                "entry_order_id": order_id,
                
                # Fields to be populated on exit
                "exit_timestamp": None,
                "exit_action": None,
                "exit_side": None,
                "exit_price": None,
                "exit_execution_price": None,
                "exit_rsi": None,
                "exit_reason": None,
                "pnl": None,
                "funding_charges": None,
                "trading_fees": None,
                "remaining_margin": remaining_margin,
                "exit_order_id": None,
            }
            
            # Add any additional fields from kwargs
            trade_doc.update(kwargs)
            
            # Remove None values to keep documents clean
            trade_doc = {k: v for k, v in trade_doc.items() if v is not None}
            
            # Create document with trade_id as the document ID
            doc_ref = _firestore_client.collection(_firestore_collection).document(trade_id)
            doc_ref.set(trade_doc)
            
            logger.info(f"✓ Trade OPENED in Firestore: {trade_id} | {symbol} {action} @ ${price:,.2f}")
            
            return trade_id
            
        else:
            # **EXIT: Update existing trade document**
            if not trade_id:
                logger.warning("No trade_id provided for exit, cannot update trade document")
                return None
            
            # Prepare update data
            update_data = {
                "status": status,  # PARTIAL_CLOSED or CLOSED
                "exit_timestamp": datetime.utcnow(),
                "exit_action": action,
                "exit_side": side,
                "exit_price": exit_price,
                "exit_execution_price": execution_price or price,
                "exit_rsi": rsi,
                "exit_reason": reason,
                "pnl": pnl,
                "funding_charges": funding_charges,
                "trading_fees": trading_fees,
                "remaining_margin": remaining_margin,
                "exit_order_id": order_id,
            }
            
            # Add any additional fields from kwargs
            update_data.update(kwargs)
            
            # Remove None values
            update_data = {k: v for k, v in update_data.items() if v is not None}
            
            # Update the existing document
            doc_ref = _firestore_client.collection(_firestore_collection).document(trade_id)
            doc_ref.update(update_data)
            
            logger.info(f"✓ Trade {status} in Firestore: {trade_id} | {symbol} {action} @ ${price:,.2f} | PnL: ${pnl:+,.2f}" if pnl else f"✓ Trade {status} in Firestore: {trade_id} | {symbol} {action} @ ${price:,.2f}")
            
            return trade_id
        
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
