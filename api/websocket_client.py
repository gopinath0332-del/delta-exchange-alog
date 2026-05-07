"""WebSocket client for Delta Exchange."""

import threading
import json
import time
import hmac
import hashlib
import ssl
from typing import Callable, Dict, List, Optional, Any

import websocket

from core.config import Config
from core.logger import get_logger

logger = get_logger(__name__)


class DeltaWebSocketClient:
    """
    WebSocket client for Delta Exchange real-time data.
    """

    def __init__(self, config: Config):
        """
        Initialize WebSocket client.

        Args:
            config: Configuration instance
        """
        self.config = config
        self.ws_url = self._get_ws_url()
        self.ws: Optional[websocket.WebSocketApp] = None
        self.is_connected = False
        self.is_authenticated = False
        self.subscriptions: Dict[str, List[Callable]] = {}
        self.thread: Optional[threading.Thread] = None
        self.reconnect_delay = 1.0
        self.max_reconnect_delay = 60.0
        self.should_reconnect = True
        
        # Keep track of requested channels to auto-resubscribe
        self.active_channels: Dict[str, List[str]] = {}

        logger.info(
            "WebSocket client initialized",
            ws_url=self.ws_url,
            environment=config.environment,
        )

    def _get_ws_url(self) -> str:
        """Get WebSocket URL based on environment."""
        if self.config.is_testnet():
            return "wss://socket-ind.testnet.deltaex.org"
        else:
            return "wss://socket.india.delta.exchange"

    def _generate_signature(self, secret: str, message: str) -> str:
        """Generate HMAC SHA256 signature for auth."""
        message_bytes = bytes(message, 'utf-8')
        secret_bytes = bytes(secret, 'utf-8')
        hash_obj = hmac.new(secret_bytes, message_bytes, hashlib.sha256)
        return hash_obj.hexdigest()

    def _authenticate(self) -> None:
        """Send authentication message to Delta Exchange WebSocket."""
        if not self.config.api_key or not self.config.api_secret:
            logger.warning("API keys not configured. Cannot authenticate WebSocket.")
            return

        method = 'GET'
        timestamp = str(int(time.time()))
        path = '/live'
        signature_data = method + timestamp + path
        signature = self._generate_signature(self.config.api_secret, signature_data)

        auth_payload = {
            "type": "key-auth",
            "payload": {
                "api-key": self.config.api_key,
                "signature": signature,
                "timestamp": timestamp
            }
        }
        
        if self.ws and self.is_connected:
            self.ws.send(json.dumps(auth_payload))
            logger.info("Sent authentication message to WebSocket")

    def connect(self) -> None:
        """Connect to WebSocket with auto-reconnect logic."""
        self.should_reconnect = True
        
        def run_forever():
            while self.should_reconnect:
                logger.info(f"Connecting to WebSocket: {self.ws_url}")
                
                self.ws = websocket.WebSocketApp(
                    self.ws_url,
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close
                )
                
                self.ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE})
                
                self.is_connected = False
                self.is_authenticated = False
                
                if self.should_reconnect:
                    logger.info(f"WebSocket disconnected. Reconnecting in {self.reconnect_delay}s...")
                    time.sleep(self.reconnect_delay)
                    # Exponential backoff
                    self.reconnect_delay = min(self.reconnect_delay * 2, self.max_reconnect_delay)

        if self.thread is None or not self.thread.is_alive():
            self.thread = threading.Thread(target=run_forever, daemon=True)
            self.thread.start()

    def disconnect(self) -> None:
        """Disconnect from WebSocket."""
        logger.info("WebSocket disconnect called")
        self.should_reconnect = False
        if self.ws:
            self.ws.close()

    def _on_open(self, ws) -> None:
        """Handle WebSocket connection opened."""
        logger.info("WebSocket connection opened")
        self.is_connected = True
        self.reconnect_delay = 1.0  # Reset reconnect delay on successful connection
        self._authenticate()

    def _on_message(self, ws, message: str) -> None:
        """Handle incoming WebSocket message."""
        try:
            data = json.loads(message)
            msg_type = data.get("type")
            
            if msg_type == "key-auth":
                if data.get("success"):
                    logger.info("WebSocket authentication successful")
                    self.is_authenticated = True
                    self._resubscribe()
                else:
                    logger.error(f"WebSocket authentication failed: {data}")
            
            # Dispatch to subscribers
            channel = data.get("type", "")
            
            if channel in self.subscriptions:
                for callback in self.subscriptions[channel]:
                    try:
                        callback(data)
                    except Exception as e:
                        logger.error(f"Error in WebSocket callback for {channel}: {e}", exc_info=True)
                        
        except json.JSONDecodeError:
            logger.error(f"Failed to decode WebSocket message: {message}")
        except Exception as e:
            logger.error(f"Error handling WebSocket message: {e}", exc_info=True)

    def _on_error(self, ws, error: Exception) -> None:
        """Handle WebSocket error."""
        logger.error(f"WebSocket Error: {error}")

    def _on_close(self, ws, close_status_code, close_msg) -> None:
        """Handle WebSocket connection closed."""
        logger.warning(f"WebSocket connection closed. Status: {close_status_code}, Msg: {close_msg}")
        self.is_connected = False
        self.is_authenticated = False

    def subscribe(self, channel: str, symbols: List[str], callback: Callable) -> None:
        """
        Subscribe to a WebSocket channel.

        Args:
            channel: Channel name (e.g., 'orders', 'positions')
            symbols: List of symbols (e.g., ['all'], ['BTCUSD'])
            callback: Callback function to handle messages
        """
        logger.info(f"Subscribing to channel {channel} for symbols {symbols}")
        
        # Store for auto-resubscribe
        self.active_channels[channel] = symbols
        
        # Add callback
        if channel not in self.subscriptions:
            self.subscriptions[channel] = []
        if callback not in self.subscriptions[channel]:
            self.subscriptions[channel].append(callback)
            
        # Send subscribe message if connected and authenticated (if private)
        if self.is_connected:
            # We assume channels like orders/positions are private and require auth
            if channel in ["orders", "positions", "v2/user_trades"] and not self.is_authenticated:
                logger.debug(f"Cannot subscribe to {channel} yet, not authenticated")
                return
                
            payload = {
                "type": "subscribe",
                "payload": {
                    "channels": [
                        {
                            "name": channel,
                            "symbols": symbols
                        }
                    ]
                }
            }
            try:
                self.ws.send(json.dumps(payload))
                logger.debug(f"Sent subscribe request for {channel}")
            except Exception as e:
                logger.error(f"Failed to send subscribe request: {e}")

    def _resubscribe(self) -> None:
        """Resubscribe to all active channels (usually after reconnect/auth)."""
        logger.info("Resubscribing to active channels...")
        for channel, symbols in self.active_channels.items():
            payload = {
                "type": "subscribe",
                "payload": {
                    "channels": [
                        {
                            "name": channel,
                            "symbols": symbols
                        }
                    ]
                }
            }
            try:
                self.ws.send(json.dumps(payload))
            except Exception as e:
                logger.error(f"Failed to resubscribe to {channel}: {e}")

    def unsubscribe(self, channel: str) -> None:
        """
        Unsubscribe from a WebSocket channel.

        Args:
            channel: Channel name
        """
        logger.info(f"Unsubscribing from {channel}")
        if channel in self.active_channels:
            del self.active_channels[channel]
            
        if channel in self.subscriptions:
            del self.subscriptions[channel]
            
        if self.is_connected:
            payload = {
                "type": "unsubscribe",
                "payload": {
                    "channels": [
                        {
                            "name": channel
                        }
                    ]
                }
            }
            try:
                self.ws.send(json.dumps(payload))
            except Exception as e:
                logger.error(f"Failed to send unsubscribe request: {e}")
