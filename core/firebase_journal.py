"""
Firebase Trade Journal Integration
Automatically logs trades to MyTradeJournal Firebase database
"""
import os
from datetime import datetime
from typing import Optional, Dict, Any
from core.logger import get_logger

logger = get_logger(__name__)


class FirebaseJournalService:
    """Service for logging trades to Firebase Firestore using REST API"""
    
    def __init__(self):
        """Initialize Firebase journal service"""
        self.enabled = os.getenv('ENABLE_FIREBASE_JOURNAL', 'false').lower() == 'true'
        self.user_id = os.getenv('FIREBASE_USER_ID')
        self.profile_id = os.getenv('FIREBASE_CRYPTO_PROFILE_ID')
        self.api_key = os.getenv('FIREBASE_API_KEY')
        self.project_id = os.getenv('FIREBASE_PROJECT_ID')
        
        if self.enabled:
            self._validate_config()
    
    def _validate_config(self):
        """Validate Firebase configuration"""
        missing = []
        if not self.api_key:
            missing.append('FIREBASE_API_KEY')
        if not self.project_id:
            missing.append('FIREBASE_PROJECT_ID')
        if not self.user_id or self.user_id == 'YOUR_FIREBASE_USER_ID':
            missing.append('FIREBASE_USER_ID')
        if not self.profile_id:
            missing.append('FIREBASE_CRYPTO_PROFILE_ID')
        
        if missing:
            logger.warning(
                f"Firebase journal enabled but missing config: {', '.join(missing)}. "
                "Trade logging will be disabled."
            )
            self.enabled = False
        else:
            logger.info("✓ Firebase journal initialized and ready")
    
    def log_entry(
        self,
        symbol: str,
        trade_type: str,  # 'BUY' or 'SELL'
        entry_price: float,
        quantity: int,
        strategy: str,
        contract: str = "Perpetual"
    ) -> Optional[str]:
        """
        Log a trade entry to Firebase
        
        Args:
            symbol: Trading symbol (e.g., 'BTCUSD')
            trade_type: 'BUY' for long, 'SELL' for short
            entry_price: Entry price
            quantity: Position size in contracts
            strategy: Strategy name
            contract: Contract type (default: 'Perpetual')
            
        Returns:
            trade_id: Firebase document ID if successful, None otherwise
        """
        if not self.enabled:
            logger.debug("Firebase journal disabled, skipping entry log")
            return None
        
        try:
            now = datetime.utcnow().isoformat() + 'Z'
            
            trade_data = {
                'symbol': symbol,
                'contract': contract,
                'tradeType': trade_type,
                'entryDate': now,
                'entryPrice': entry_price,
                'quantity': quantity,
                'strategy': strategy,
                'confidence': 3,  # Default confidence level
                'positionSize': quantity,
                'fees': 0.0,  # Will be calculated on exit
                'profileId': self.profile_id,
                'userId': self.user_id,
                'createdAt': now,
                'updatedAt': now,
                'notes': f'Auto-logged from delta-exchange-algo'
            }
            
            # Add document via REST API
            doc_id = self._add_document_rest('trades', trade_data)
            
            if doc_id:
                logger.info(f"✓ Trade entry logged to Firebase: {symbol} {trade_type} @ {entry_price} (ID: {doc_id})")
                return doc_id
            else:
                logger.error(f"✗ Failed to log trade entry to Firebase")
            
        except Exception as e:
            logger.error(f"Failed to log entry to Firebase: {e}")
            
        return None
    
    def update_exit(
        self,
        trade_id: str,
        exit_price: float,
        pnl_amount: float,
        pnl_percentage: float,
        is_partial: bool = False
    ) -> bool:
        """
        Update trade with exit information
        
        Args:
            trade_id: Firebase document ID
            exit_price: Exit price
            pnl_amount: P&L in currency  
            pnl_percentage: P&L as percentage
            is_partial: Whether this is a partial exit
            
        Returns:
            Success status
        """
        if not self.enabled or not trade_id:
            return False
        
        try:
            now = datetime.utcnow().isoformat() + 'Z'
            
            update_data = {
                'exitPrice': exit_price,
                'pnlAmount': pnl_amount,
                'pnlPercentage': pnl_percentage,
                'updatedAt': now
            }
            
            # Only set exit date on final exit (not partial)
            if not is_partial:
                update_data['exitDate'] = now
            
            success = self._update_document_rest('trades', trade_id, update_data)
            
            if success:
                exit_type = "Partial exit" if is_partial else "Final exit"
                logger.info(f"✓ {exit_type} updated in Firebase: {trade_id} @ {exit_price} (PnL: {pnl_amount:.2f})")
            else:
                logger.error(f"✗ Failed to update exit in Firebase: {trade_id}")
                
            return success
            
        except Exception as e:
            logger.error(f"Failed to update exit in Firebase: {e}")
            return False
    
    def _add_document_rest(self, collection: str, data: Dict[str, Any]) -> Optional[str]:
        """Add document using Firestore REST API"""
        try:
            import requests
            
            url = (
                f"https://firestore.googleapis.com/v1/"
                f"projects/{self.project_id}/databases/(default)/documents/{collection}"
                f"?key={self.api_key}"
            )
            
            # Convert data to Firestore format
            firestore_data = self._to_firestore_format(data)
            
            response = requests.post(url, json={'fields': firestore_data}, timeout=10)
            
            if response.status_code == 200:
                result = response.json()
                # Extract document ID from name: "projects/.../documents/trades/DOC_ID"
                doc_id = result['name'].split('/')[-1]
                return doc_id
            else:
                logger.error(f"Firebase REST API error: {response.status_code} - {response.text[:200]}")
                return None
                
        except Exception as e:
            logger.error(f"Failed to add document via REST: {e}")
            return None
    
    def _update_document_rest(self, collection: str, doc_id: str, data: Dict[str, Any]) -> bool:
        """Update document using Firestore REST API"""
        try:
            import requests
            
            url = (
                f"https://firestore.googleapis.com/v1/"
                f"projects/{self.project_id}/databases/(default)/documents/{collection}/{doc_id}"
                f"?key={self.api_key}"
            )
            
            # Convert data to Firestore format
            firestore_data = self._to_firestore_format(data)
            
            # Build update mask
            mask = '&'.join([f'updateMask.fieldPaths={field}' for field in data.keys()])
            url += f'&{mask}'
            
            response = requests.patch(url, json={'fields': firestore_data}, timeout=10)
            
            return response.status_code == 200
            
        except Exception as e:
            logger.error(f"Failed to update document via REST: {e}")
            return False
    
    def _to_firestore_format(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Python dict to Firestore REST API format"""
        result = {}
        for key, value in data.items():
            if isinstance(value, str):
                result[key] = {'stringValue': value}
            elif isinstance(value, bool):
                result[key] = {'booleanValue': value}
            elif isinstance(value, int):
                result[key] = {'integerValue': value}
            elif isinstance(value, float):
                result[key] = {'doubleValue': value}
            elif value is None:
                result[key] = {'nullValue': None}
            else:
                # Fallback: convert to string
                result[key] = {'stringValue': str(value)}
        return result


# Global instance
_journal_service = None


def get_journal_service() -> FirebaseJournalService:
    """Get or create the global journal service instance"""
    global _journal_service
    if _journal_service is None:
        _journal_service = FirebaseJournalService()
    return _journal_service
