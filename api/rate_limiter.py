"""Rate limiter for API requests."""

import time
from collections import deque
from threading import Lock
from typing import Dict, Optional

from core.logger import get_logger

logger = get_logger(__name__)


class RateLimiter:
    """
    Token bucket rate limiter for API requests.

    Delta Exchange limits: 150 connections per 5 minutes per IP
    """

    def __init__(self, max_requests: int = 150, time_window: int = 300):
        """
        Initialize rate limiter.

        Args:
            max_requests: Maximum number of requests allowed
            time_window: Time window in seconds (default: 300 = 5 minutes)
        """
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests: deque = deque()
        self.lock = Lock()

        logger.info("Rate limiter initialized", max_requests=max_requests, time_window=time_window)

    def acquire(self, endpoint: Optional[str] = None) -> bool:
        """
        Acquire permission to make a request.

        Args:
            endpoint: API endpoint (for logging purposes)

        Returns:
            True if request is allowed, False otherwise
        """
        with self.lock:
            current_time = time.time()

            # Remove requests outside the time window
            while self.requests and self.requests[0] < current_time - self.time_window:
                self.requests.popleft()

            # Check if we can make a new request
            if len(self.requests) < self.max_requests:
                self.requests.append(current_time)
                return True
            else:
                # Calculate wait time
                oldest_request = self.requests[0]
                wait_time = self.time_window - (current_time - oldest_request)

                logger.warning(
                    "Rate limit reached",
                    endpoint=endpoint,
                    wait_time=f"{wait_time:.2f}s",
                    requests_in_window=len(self.requests),
                )
                return False

    def wait_if_needed(self, endpoint: Optional[str] = None) -> None:
        """
        Wait if rate limit is reached.

        Reads `oldest_request` under the lock to avoid a race condition where another
        thread drains the deque between the `acquire()` check and the read.

        Also guards `wait_time` with `max(0, ...)` so that an already-expired oldest
        entry can never produce a negative sleep duration (which would raise
        `ValueError: sleep length must be non-negative`).

        Args:
            endpoint: API endpoint (for logging purposes)
        """
        while not self.acquire(endpoint=endpoint):
            # Re-read under lock: the deque may have changed between acquire() and here.
            with self.lock:
                if not self.requests:
                    # All entries expired between the acquire() check and now — nothing to wait for.
                    break
                current_time = time.time()
                oldest_request = self.requests[0]
                # How long until the oldest request falls outside the window.
                # max(0, ...) ensures we never pass a negative value to time.sleep().
                wait_time = max(0, self.time_window - (current_time - oldest_request)) + 1

            logger.info("Waiting for rate limit", endpoint=endpoint, wait_time=f"{wait_time:.2f}s")
            time.sleep(wait_time)

    def get_remaining_requests(self) -> int:
        """
        Get number of remaining requests in current window.

        Returns:
            Number of remaining requests
        """
        with self.lock:
            current_time = time.time()

            # Remove requests outside the time window
            while self.requests and self.requests[0] < current_time - self.time_window:
                self.requests.popleft()

            return self.max_requests - len(self.requests)

    def reset(self) -> None:
        """Reset the rate limiter."""
        with self.lock:
            self.requests.clear()
            logger.info("Rate limiter reset")


class EndpointRateLimiter:
    """Rate limiter with per-endpoint tracking."""

    def __init__(self, default_max_requests: int = 150, default_time_window: int = 300):
        """
        Initialize endpoint rate limiter.

        Args:
            default_max_requests: Default maximum requests per endpoint
            default_time_window: Default time window in seconds
        """
        self.default_max_requests = default_max_requests
        self.default_time_window = default_time_window
        self.limiters: Dict[str, RateLimiter] = {}
        self.lock = Lock()

    def get_limiter(self, endpoint: str) -> RateLimiter:
        """
        Get or create rate limiter for endpoint.

        Args:
            endpoint: API endpoint

        Returns:
            RateLimiter instance for the endpoint
        """
        with self.lock:
            if endpoint not in self.limiters:
                self.limiters[endpoint] = RateLimiter(
                    max_requests=self.default_max_requests, time_window=self.default_time_window
                )
            return self.limiters[endpoint]

    def acquire(self, endpoint: str) -> bool:
        """
        Acquire permission for endpoint request.

        Args:
            endpoint: API endpoint

        Returns:
            True if request is allowed
        """
        limiter = self.get_limiter(endpoint)
        return limiter.acquire(endpoint=endpoint)

    def wait_if_needed(self, endpoint: str) -> None:
        """
        Wait if rate limit is reached for endpoint.

        Args:
            endpoint: API endpoint
        """
        limiter = self.get_limiter(endpoint)
        limiter.wait_if_needed(endpoint=endpoint)
