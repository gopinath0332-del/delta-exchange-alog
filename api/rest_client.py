"""REST API client for Delta Exchange using delta-rest-client library."""

import time
from datetime import datetime
from typing import Any, Dict, List, Optional, cast

from delta_rest_client import DeltaRestClient as BaseDeltaClient

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

    def _make_direct_request(self, endpoint: str, params: Optional[Dict] = None) -> Any:
        """
        Make direct API request for endpoints not in delta-rest-client.

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
        return cast(Dict[str, Any], response.get("result", {}))

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
        return cast(Dict[str, Any], response.get("result", {}))

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
        return cast(Dict[str, Any], response.get("result", {}))

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

        # Delta Exchange returns max 2000 candles per request
        # We need to paginate for longer periods
        while current_start < end:
            try:
                params = {
                    "resolution": resolution,
                    "symbol": symbol,
                    "start": current_start,
                    "end": end,
                }

                response = self._make_direct_request("/v2/history/candles", params=params)

                candles = response.get("result", [])
                if not candles:
                    break

                all_candles.extend(candles)

                # Update start time for next batch
                # Candles have 'time' field with timestamp
                last_candle_time = candles[-1].get("time", 0) if candles else 0
                if last_candle_time <= current_start:
                    break
                current_start = last_candle_time + 1

                logger.debug("Fetched candle batch", count=len(candles), total=len(all_candles))

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
        return cast(Dict[str, Any], response.get("result", {}))

    def get_positions(self) -> List[Dict[str, Any]]:
        """
        Get open positions.

        Returns:
            List of open positions
        """
        logger.debug("Fetching positions")
        response = self._make_request(self.client.get_positions)
        return cast(List[Dict[str, Any]], response.get("result", []))

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
        return cast(Dict[str, Any], response.get("result", {}))

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
        orders = response.get("result", [])

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

        response = self._make_request(
            self.client.place_order,
            product_id=product_id,
            size=size,
            side=side,
            order_type=order_type,
            limit_price=limit_price,
            **kwargs,
        )

        logger.info("Order placed", order_id=response.get("result", {}).get("id"))
        return cast(Dict[str, Any], response.get("result", {}))

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
        return cast(Dict[str, Any], response.get("result", {}))

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
        return cast(Dict[str, Any], response.get("result", {}))

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
        return cast(Dict[str, Any], response.get("result", {}))


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
