"""REST API client for Delta Exchange using delta-rest-client library."""

import os
import time
import json
import hmac
import random
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

# ---------------------------------------------------------------------------
# Retry / backoff helpers
# ---------------------------------------------------------------------------

# HTTP status codes that are worth retrying (exchange overload / transient errors)
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

# Read retry config from environment (with sensible defaults)
# API_MAX_RETRIES      – how many times to retry a failed request (default 4)
# API_BACKOFF_BASE_SEC – starting wait time in seconds for first retry (default 2)
# API_BACKOFF_MAX_SEC  – maximum wait time cap in seconds (default 60)
_MAX_RETRIES: int = int(os.getenv("API_MAX_RETRIES", "4"))
_BACKOFF_BASE: float = float(os.getenv("API_BACKOFF_BASE_SEC", "2"))
_BACKOFF_MAX: float = float(os.getenv("API_BACKOFF_MAX_SEC", "60"))


def _backoff_wait(attempt: int) -> None:
    """
    Sleep for an exponentially increasing duration with random jitter.

    Formula: min(base * 2^attempt, max) + uniform_jitter(0, 1)

    The jitter prevents a thundering-herd effect when multiple strategies
    all retry at the same time after a shared transient failure.

    Args:
        attempt: Zero-based retry attempt number (0 = first retry)
    """
    delay = min(_BACKOFF_BASE * (2 ** attempt), _BACKOFF_MAX)
    jitter = random.uniform(0, 1)  # Add up to 1 second of random jitter
    total_wait = delay + jitter
    logger.warning(
        f"API retry backoff: waiting {total_wait:.1f}s "
        f"(attempt {attempt + 1}/{_MAX_RETRIES}, base={_BACKOFF_BASE}s, cap={_BACKOFF_MAX}s)"
    )
    time.sleep(total_wait)


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
        self.config = config
        self.rate_limiter = RateLimiter(max_requests=150, time_window=300)
        self.time_offset = 0 # Offset to synchronize with server time

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
        
        # Retry loop for time synchronization
        max_retries = 1
        for attempt in range(max_retries + 1):
            timestamp = str(int(time.time() + self.time_offset))
            
            # Prepare payload and query string for signature
            query_string = ""
            if params:
                query_string = urllib.parse.urlencode(params)
                url_with_query = f"{url}?{query_string}"
            else:
                url_with_query = url
                
            payload = ""
            if data:
                payload = json.dumps(data)
                
            # For signature, endpoint should include query params
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
                    response = requests.get(url_with_query, headers=headers, timeout=30)
                elif method == "POST":
                    response = requests.post(url_with_query, headers=headers, data=payload, timeout=30)
                else:
                    raise ValueError(f"Unsupported method: {method}")
                    
                # Check for specific error scenarios before raising generic status error
                if response.status_code == 401:
                    try:
                        resp_json = response.json()
                        error_data = resp_json.get("error", {})
                        if error_data.get("code") == "expired_signature" and attempt < max_retries:
                            # Parse server time and sync
                            context = error_data.get("context", {})
                            server_time = context.get("server_time")
                            if server_time:
                                local_time = int(time.time())
                                # Calculate offset: server_time - local_time + 1s buffer
                                diff = server_time - local_time
                                self.time_offset = diff + 2 # Add 2s extra buffer to be safe
                                logger.warning(f"Time drift detected. Syncing clock. Offset: {self.time_offset}s (Server: {server_time}, Local: {local_time})")
                                continue # Retry immediately
                    except Exception:
                        pass # Failed to parse error, just raise normal status
                
                response.raise_for_status()
                return response.json()
            except requests.exceptions.RequestException as e:
                # If we exhausted retries or it's another error
                if attempt == max_retries:
                    logger.error(f"Auth API request failed: {endpoint}", error=str(e))
                    if e.response is not None:
                        logger.error(f"Response: {e.response.text}")
                    raise APIError(f"Auth request failed: {e}")

    def _make_direct_request(self, endpoint: str, params: Optional[Dict] = None) -> Any:
        """
        Make direct API request for public endpoints not in delta-rest-client.

        Implements exponential backoff with jitter on transient failures
        (HTTP 400 'Bad Request' from exchange overload, 429 rate-limit,
        5xx server errors and network timeouts).  The number of retries and
        backoff timing are controlled via environment variables:
            API_MAX_RETRIES      (default 4)
            API_BACKOFF_BASE_SEC (default 2 s)
            API_BACKOFF_MAX_SEC  (default 60 s)

        Non-retryable errors (e.g. 401 Unauthorized) are raised immediately.

        Note: Use delta-rest-client methods when available. This is only for
        public endpoints like /v2/products, /v2/history/candles that are not
        included in the delta-rest-client library.

        Args:
            endpoint: API endpoint path (e.g. '/v2/history/candles')
            params: Optional dictionary of query parameters

        Returns:
            Parsed JSON response dict

        Raises:
            APIError: If all retries are exhausted or a non-retryable error occurs
        """
        import requests

        self.rate_limiter.wait_if_needed()

        url = f"{self.config.base_url}{endpoint}"
        last_exception: Optional[Exception] = None

        for attempt in range(_MAX_RETRIES + 1):  # +1 so we always try at least once
            try:
                response = requests.get(url, params=params, timeout=30)

                # Immediately raise on non-retryable auth errors
                if response.status_code == 401:
                    logger.error(
                        f"Direct API auth error (401) for {endpoint} – not retrying"
                    )
                    response.raise_for_status()

                # For retryable HTTP error codes, log and back off
                if response.status_code in _RETRYABLE_STATUS_CODES:
                    logger.warning(
                        f"Retryable HTTP {response.status_code} from {endpoint}. "
                        f"Attempt {attempt + 1}/{_MAX_RETRIES + 1}"
                    )
                    if attempt < _MAX_RETRIES:
                        _backoff_wait(attempt)
                        continue  # retry
                    # All retries exhausted – raise to surface the real error
                    response.raise_for_status()

                # Handle 400 Bad Request separately – Delta Exchange returns this
                # when the exchange is temporarily overloaded or parameters are
                # marginal (e.g. candle start/end epoch edge cases),
                # so we retry with backoff rather than giving up immediately.
                if response.status_code == 400:
                    logger.warning(
                        f"HTTP 400 Bad Request from {endpoint} – exchange may be busy. "
                        f"Attempt {attempt + 1}/{_MAX_RETRIES + 1}"
                    )
                    if attempt < _MAX_RETRIES:
                        _backoff_wait(attempt)
                        continue  # retry
                    response.raise_for_status()  # Give up after max retries

                response.raise_for_status()
                return response.json()

            except requests.exceptions.Timeout as e:
                # Network timeout – always worth retrying
                last_exception = e
                logger.warning(
                    f"Request timeout for {endpoint}. "
                    f"Attempt {attempt + 1}/{_MAX_RETRIES + 1}"
                )
                if attempt < _MAX_RETRIES:
                    _backoff_wait(attempt)
                    continue

            except requests.exceptions.ConnectionError as e:
                # Connection dropped – retryable
                last_exception = e
                logger.warning(
                    f"Connection error for {endpoint}. "
                    f"Attempt {attempt + 1}/{_MAX_RETRIES + 1}"
                )
                if attempt < _MAX_RETRIES:
                    _backoff_wait(attempt)
                    continue

            except requests.exceptions.RequestException as e:
                # Other request errors (non-retryable, e.g. invalid URL)
                logger.error("Direct API request failed", endpoint=endpoint, error=str(e))
                raise APIError(f"API request failed: {e}")

        # All retries exhausted
        logger.error(
            f"Direct API request failed after {_MAX_RETRIES} retries: {endpoint}",
            error=str(last_exception),
        )
        raise APIError(f"API request failed after {_MAX_RETRIES} retries: {last_exception}")

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
            "180m": 180,
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
        Get wallet balance for all assets.

        Returns:
            Wallet balance information for all assets
        """
        logger.debug("Fetching wallet balance")
        # Use authenticated endpoint directly since get_balances requires asset_id
        # The /v2/wallet/balances endpoint returns all balances
        response = self._make_auth_request("GET", "/v2/wallet/balances")
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
        
        # Use /v2/positions/margined for full details (margin, liq price, etc.)
        # This endpoint accepts 'product_ids' as comma-separated string
        try:
            params = {}
            if product_id:
                params['product_ids'] = str(product_id)
                
            response = self._make_auth_request("GET", "/v2/positions/margined", params=params)
            return cast(List[Dict[str, Any]], response.get('result', []))
        except Exception:
            # Fallback or re-raise
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

    def place_bracket_order(
        self,
        product_id: int,
        product_symbol: str,
        stop_price: str,
        stop_order_type: str = "market_order",
        stop_trigger_method: str = "last_traded_price",
    ) -> Dict[str, Any]:
        """
        Place a bracket stop-loss order attached to an open position.

        Delta Exchange bracket orders are separate from the position order and are
        managed by the exchange matching engine.  A single bracket order per position
        is allowed.  When the market reaches `stop_price` the exchange will
        immediately close the full position using the specified `stop_order_type`.

        API endpoint: POST /v2/orders/bracket

        Args:
            product_id:          Exchange product ID (from get_products()).
            product_symbol:      Symbol string (e.g. "BTCUSD") – used alongside product_id.
            stop_price:          Stop trigger price as a string (e.g. "59000").
            stop_order_type:     How to fill when triggered: "market_order" (default) or
                                 "limit_order".  Use market_order for guaranteed fill.
            stop_trigger_method: Price type used to trigger the stop.
                                 "last_traded_price" (default) or "mark_price".

        Returns:
            API response dict (contains the created bracket order details).

        Raises:
            APIError: If the request fails after retries.
        """
        logger.info(
            f"Placing bracket stop-loss order: product={product_symbol} "
            f"(id={product_id}), stop_price={stop_price}, "
            f"order_type={stop_order_type}, trigger={stop_trigger_method}"
        )

        # Build bracket order payload — only stop_loss_order is required.
        # The exchange uses the existing open position's size automatically,
        # so we do not need to specify a separate size field.
        payload = {
            "product_id": product_id,
            "product_symbol": product_symbol,
            "stop_loss_order": {
                "order_type": stop_order_type,
                "stop_price": stop_price,
            },
            "bracket_stop_trigger_method": stop_trigger_method,
        }

        response = self._make_auth_request("POST", "/v2/orders/bracket", data=payload)
        result = response.get("result", response) if isinstance(response, dict) else response
        logger.info(f"Bracket stop-loss order placed: {result}")
        return cast(Dict[str, Any], result)

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
