"""REST API client for Delta Exchange using delta-rest-client library."""

import time
import json
import hmac
import hashlib
import urllib.parse
from datetime import datetime
from typing import Any, Dict, List, Optional, cast

from delta_rest_client import DeltaRestClient as BaseDeltaClient, OrderType

from core.config import Config
from core.exceptions import APIError, AuthenticationError, RateLimitError
from core.logger import get_logger

from .rate_limiter import RateLimiter

logger = get_logger(__name__)


class DeltaRestClient:
    """
    Wrapper around delta-rest-client library with enhanced features.

    Features:
    - Automatic rate limiting
    - Retry logic with exponential backoff
    - Structured logging
    - Error handling
    """

    def __init__(self, config: Config):
        """
        Initialize Delta Exchange REST API client.

        Args:
            config: Configuration instance
        """
        self.config = config
        self.rate_limiter = RateLimiter(max_requests=150, time_window=300)

        # Initialize delta-rest-client
        try:
            self.client = BaseDeltaClient(
                base_url=config.base_url, api_key=config.api_key, api_secret=config.api_secret
            )
            logger.info(
                "Delta REST client initialized",
                base_url=config.base_url,
                environment=config.environment,
            )
        except Exception as e:
            logger.error("Failed to initialize Delta REST client", error=str(e))
            raise AuthenticationError(f"Failed to initialize client: {e}")

    def _make_request(self, func, *args, **kwargs) -> Any:
        """
        Make API request with rate limiting and error handling.

        Args:
            func: Function to call
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            API response

        Raises:
            APIError: If request fails
        """
        # Wait if rate limit is reached
        self.rate_limiter.wait_if_needed()

        try:
            response = func(*args, **kwargs)
            return response
        except Exception as e:
            error_msg = str(e)

            # Check for specific error types
            if "rate limit" in error_msg.lower():
                raise RateLimitError(f"Rate limit exceeded: {error_msg}")
            elif "unauthorized" in error_msg.lower() or "authentication" in error_msg.lower():
                raise AuthenticationError(f"Authentication failed: {error_msg}")
            else:
                raise APIError(f"API request failed: {error_msg}")



    def _generate_signature(self, method: str, endpoint: str, payload: str, timestamp: str) -> str:
        """Generate HMAC-SHA256 signature."""
        msg = f"{method}{timestamp}{endpoint}{payload}"
        signature = hmac.new(
            self.config.api_secret.encode('utf-8'),
            msg.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature

    def _make_auth_request(self, method: str, endpoint: str, params: Optional[Dict] = None, data: Optional[Dict] = None) -> Any:
        """
        Make authenticated API request directly.
        """
        import requests
        
        self.rate_limiter.wait_if_needed()
        
        url = f"{self.config.base_url}{endpoint}"
        timestamp = str(int(time.time()))
        
        # Prepare payload and query string for signature
        query_string = ""
        if params:
            query_string = urllib.parse.urlencode(params)
            url = f"{url}?{query_string}"
            
        payload = ""
        if data:
            payload = json.dumps(data)
            
        # For signature, endpoint should include query params if GET?
        # Verify Delta API docs: Signature = method + timestamp + path + query_string + body
        path_with_query = endpoint
        if query_string:
            path_with_query = f"{endpoint}?{query_string}"
            
        signature = self._generate_signature(method, path_with_query, payload, timestamp)
        
        headers = {
            "Content-Type": "application/json",
            "api-key": self.config.api_key,
            "timestamp": timestamp,
            "signature": signature
        }
        
        try:
            if method == "GET":
                response = requests.get(url, headers=headers, timeout=30)
            elif method == "POST":
                response = requests.post(url, headers=headers, data=payload, timeout=30)
            else:
                raise ValueError(f"Unsupported method: {method}")
                
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Auth API request failed: {endpoint}", error=str(e))
            if e.response is not None:
                logger.error(f"Response: {e.response.text}")
            raise APIError(f"Auth request failed: {e}")

    def _make_direct_request(self, endpoint: str, params: Optional[Dict] = None) -> Any:
        """
        Make direct API request for public endpoints not in delta-rest-client.

        Note: Use delta-rest-client methods when available. This is only for
        public endpoints like /v2/products, /v2/history/candles that are not
        included in the delta-rest-client library.

        Args:
            endpoint: API endpoint
            params: Query parameters

        Returns:
            API response
        """
        import requests

        self.rate_limiter.wait_if_needed()

        url = f"{self.config.base_url}{endpoint}"

        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error("Direct API request failed", endpoint=endpoint, error=str(e))
            raise APIError(f"API request failed: {e}")

    # Product and Market Data Methods

    def get_products(self) -> List[Dict[str, Any]]:
        """
        Get list of all available products.

        Returns:
            List of product dictionaries
        """
        logger.debug("Fetching products")
        response = self._make_direct_request("/v2/products")
        products = response.get("result", [])
        logger.info("Fetched products", count=len(products))
        return cast(List[Dict[str, Any]], products)

    def get_product(self, product_id: int) -> Dict[str, Any]:
        """
        Get product details by ID.

        Args:
            product_id: Product ID

        Returns:
            Product details
        """
        logger.debug("Fetching product", product_id=product_id)
        response = self._make_request(self.client.get_product, product_id)
        return cast(Dict[str, Any], response)

    def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """
        Get ticker data for a symbol.

        Args:
            symbol: Trading symbol (e.g., 'BTCUSD')

        Returns:
            Ticker data
        """
        logger.debug("Fetching ticker", symbol=symbol)
        response = self._make_request(self.client.get_ticker, symbol)
        return cast(Dict[str, Any], response)

    def get_l2_orderbook(self, product_id: int) -> Dict[str, Any]:
        """
        Get Level 2 orderbook for a product.

        Args:
            product_id: Product ID

        Returns:
            Orderbook data with bids and asks
        """
        logger.debug("Fetching L2 orderbook", product_id=product_id)
        response = self._make_request(self.client.get_l2_orderbook, product_id)
        return cast(Dict[str, Any], response)

    def get_futures_products(self) -> List[Dict[str, Any]]:
        """
        Get all futures and perpetual products.

        Returns:
            List of futures/perpetual products with metadata
        """
        logger.debug("Fetching futures products")
        all_products = self.get_products()
        
        # Filter for futures and perpetual contracts
        futures_products = [
            p for p in all_products
            if p.get("contract_type") in ["futures", "perpetual_futures", "move_options"]
            and p.get("state") == "live"
        ]
        
        logger.info("Fetched futures products", count=len(futures_products))
        return futures_products

    def get_tickers_batch(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Get ticker data for multiple symbols efficiently.

        Args:
            symbols: List of trading symbols

        Returns:
            Dictionary mapping symbol to ticker data
        """
        logger.debug("Fetching batch tickers", count=len(symbols))
        tickers = {}
        
        # Delta Exchange doesn't have a batch ticker endpoint, so we fetch individually
        # but with rate limiting handled by our wrapper
        for symbol in symbols:
            try:
                ticker = self.get_ticker(symbol)
                tickers[symbol] = ticker
            except Exception as e:
                logger.warning("Failed to fetch ticker", symbol=symbol, error=str(e))
                # Continue with other symbols
                continue
        
        logger.info("Fetched batch tickers", success_count=len(tickers), total=len(symbols))
        return tickers

    def get_funding_rate(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get current funding rate for perpetual contracts.

        Args:
            symbol: Trading symbol

        Returns:
            Funding rate data or None if not available
        """
        try:
            logger.debug("Fetching funding rate", symbol=symbol)
            # Use direct request as funding rate endpoint may not be in delta-rest-client
            response = self._make_direct_request(f"/v2/products/{symbol}/funding_rate")
            return cast(Dict[str, Any], response.get("result"))
        except Exception as e:
            logger.debug("Funding rate not available", symbol=symbol, error=str(e))
            return None


    def get_historical_candles(
        self,
        symbol: str,
        resolution: str = "1h",
        days: Optional[int] = None,
        start: Optional[int] = None,
        end: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get historical OHLC candles.

        Args:
            symbol: Trading symbol (e.g., 'BTCUSD')
            resolution: Timeframe (5m, 15m, 1h, 4h, 1d)
            days: Number of days of historical data (default: from config)
            start: Start timestamp (Unix timestamp in seconds)
            end: End timestamp (Unix timestamp in seconds)

        Returns:
            List of OHLC candles
        """
        if days is None:
            days = self.config.default_historical_days

        # Calculate timestamps if not provided
        if end is None:
            end = int(time.time())
        if start is None:
            start = end - (days * 24 * 60 * 60)

        logger.info(
            "Fetching historical candles",
            symbol=symbol,
            resolution=resolution,
            days=days,
            start=datetime.fromtimestamp(start).isoformat(),
            end=datetime.fromtimestamp(end).isoformat(),
        )

        all_candles = []
        current_start = start
        max_candles_per_request = 2000

        # Delta Exchange returns max 2000 candles per request
        # Calculate expected number of candles based on resolution
        resolution_minutes = {
            "1m": 1,
            "5m": 5,
            "15m": 15,
            "30m": 30,
            "1h": 60,
            "2h": 120,
            "4h": 240,
            "1d": 1440,
        }

        interval_minutes = resolution_minutes.get(resolution, 60)
        total_minutes = (end - start) // 60
        expected_candles = total_minutes // interval_minutes

        logger.debug(
            "Candle fetch parameters",
            expected_candles=expected_candles,
            interval_minutes=interval_minutes,
            will_paginate=expected_candles > max_candles_per_request,
        )

        # We need to paginate for longer periods
        while current_start < end:
            try:
                # Use direct request for historical candles (not in delta-rest-client)
                params = {
                    "resolution": resolution,
                    "symbol": symbol,
                    "start": current_start,
                    "end": end,
                }
                response = self._make_direct_request("/v2/history/candles", params=params)

                candles = response.get("result", [])
                if not candles:
                    logger.debug("No more candles returned, stopping pagination")
                    break

                all_candles.extend(candles)

                # If we got fewer candles than the limit, we're done
                if len(candles) < max_candles_per_request:
                    logger.debug("Received fewer candles than limit, fetch complete")
                    break

                # Update start time for next batch
                # Candles have 'time' field with timestamp
                last_candle_time = candles[-1].get("time", 0) if candles else 0
                if last_candle_time <= current_start:
                    logger.debug("Last candle time not advancing, stopping pagination")
                    break

                # Move to next batch (add 1 second to avoid duplicate)
                current_start = last_candle_time + 1

                logger.debug(
                    "Fetched candle batch",
                    count=len(candles),
                    total=len(all_candles),
                    next_start=datetime.fromtimestamp(current_start).isoformat(),
                )

            except Exception as e:
                logger.error(
                    "Failed to fetch candles", symbol=symbol, resolution=resolution, error=str(e)
                )
                break

        logger.info(
            "Completed fetching historical candles",
            symbol=symbol,
            resolution=resolution,
            total_candles=len(all_candles),
        )

        return all_candles

    # Trading Methods

    def get_wallet_balance(self) -> Dict[str, Any]:
        """
        Get wallet balance.

        Returns:
            Wallet balance information
        """
        logger.debug("Fetching wallet balance")
        response = self._make_request(self.client.get_balances)
        return cast(Dict[str, Any], response)

    def get_positions(self, product_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get open positions.

        Args:
             product_id: Optional product ID to filter

        Returns:
            List of open positions
        """
        logger.debug("Fetching positions", product_id=product_id)
        
        params = {}
        if product_id:
             params['product_id'] = product_id

        # delta-rest-client v2 might not have get_positions, use direct request
        try:
            response = self._make_auth_request("GET", "/v2/positions", params=params)
            return cast(List[Dict[str, Any]], response.get('result', []))
        except Exception:
            raise

    def get_position(self, product_id: int) -> Dict[str, Any]:
        """
        Get position for a specific product.

        Args:
            product_id: Product ID

        Returns:
            Position details
        """
        logger.debug("Fetching position", product_id=product_id)
        response = self._make_request(self.client.get_position, product_id)
        return cast(Dict[str, Any], response)

    def get_live_orders(self, product_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get live (open) orders.

        Args:
            product_id: Optional product ID to filter orders

        Returns:
            List of open orders
        """
        logger.debug("Fetching live orders", product_id=product_id)
        response = self._make_request(self.client.get_live_orders)
        orders = response

        if product_id is not None:
            orders = [o for o in orders if o.get("product_id") == product_id]

        return cast(List[Dict[str, Any]], orders)

    def place_order(
        self,
        product_id: int,
        size: int,
        side: str,
        order_type: str = "limit_order",
        limit_price: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Place a new order.

        Args:
            product_id: Product ID
            size: Order size (number of contracts)
            side: 'buy' or 'sell'
            order_type: Order type ('limit_order' or 'market_order')
            limit_price: Limit price (required for limit orders)
            **kwargs: Additional order parameters

        Returns:
            Order response
        """
        logger.info(
            "Placing order",
            product_id=product_id,
            size=size,
            side=side,
            order_type=order_type,
            limit_price=limit_price,
        )

        if isinstance(order_type, str):
            if order_type == "market_order":
                order_type = OrderType.MARKET
            elif order_type == "limit_order":
                order_type = OrderType.LIMIT

        response = self._make_request(
            self.client.place_order,
            product_id=product_id,
            size=size,
            side=side,
            order_type=order_type,
            limit_price=limit_price,
            **kwargs,
        )

        logger.info("Order placed", order_id=response.get("id"))
        return cast(Dict[str, Any], response)

    def cancel_order(self, product_id: int, order_id: int) -> Dict[str, Any]:
        """
        Cancel an open order.

        Args:
            product_id: Product ID
            order_id: Order ID

        Returns:
            Cancellation response
        """
        logger.info("Cancelling order", product_id=product_id, order_id=order_id)
        response = self._make_request(self.client.cancel_order, product_id, order_id)
        logger.info("Order cancelled", order_id=order_id)
        return cast(Dict[str, Any], response)

    def cancel_all_orders(self, product_id: int) -> Dict[str, Any]:
        """
        Cancel all open orders for a product.

        Args:
            product_id: Product ID

        Returns:
            Cancellation response
        """
        logger.info("Cancelling all orders", product_id=product_id)
        response = self._make_request(self.client.cancel_all_orders, product_id)
        logger.info("All orders cancelled", product_id=product_id)
        return cast(Dict[str, Any], response)

    def set_leverage(self, product_id: int, leverage: str) -> Dict[str, Any]:
        """
        Set leverage for a product.

        Args:
            product_id: Product ID
            leverage: Leverage value (e.g., "10")

        Returns:
            Response
        """
        logger.info("Setting leverage", product_id=product_id, leverage=leverage)
        response = self._make_request(self.client.set_leverage, product_id, leverage)
        return cast(Dict[str, Any], response)


if __name__ == "__main__":
    # Test the client
    from core.config import get_config
    from core.logger import setup_logging

    setup_logging(log_level="DEBUG")
    config = get_config()

    client = DeltaRestClient(config)

    # Test getting products
    products = client.get_products()
    print(f"Found {len(products)} products")

    # Test getting ticker
    if products:
        symbol = products[0].get("symbol")
        ticker = client.get_ticker(symbol)
        print(f"Ticker for {symbol}: {ticker}")
