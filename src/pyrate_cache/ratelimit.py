"""Token-bucket rate limiting decorator."""
from __future__ import annotations
import time
import threading
import functools
from typing import Any, Callable


class RateLimitExceeded(Exception):
    """Raised when a call exceeds the configured rate and blocking is off."""

    def __init__(self, retry_after: float) -> None:
        self.retry_after = retry_after
        super().__init__(f"rate limit exceeded, retry after {retry_after:.3f}s")


class TokenBucket:
    """Classic token bucket. `rate` tokens are added per second up to `capacity`."""

    def __init__(self, rate: float, capacity: float) -> None:
        if rate <= 0 or capacity <= 0:
            raise ValueError("rate and capacity must be positive")
        self.rate = rate
        self.capacity = capacity
        self._tokens = capacity
        self._last = time.monotonic()
        self._lock = threading.Lock()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last
        self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
        self._last = now

    def consume(self, amount: float = 1.0) -> bool:
        with self._lock:
            self._refill()
            if self._tokens >= amount:
                self._tokens -= amount
                return True
            return False

    def time_until(self, amount: float = 1.0) -> float:
        with self._lock:
            self._refill()
            if self._tokens >= amount:
                return 0.0
            return (amount - self._tokens) / self.rate


def rate_limit(calls: int, period: float = 1.0, block: bool = True) -> Callable:
    """Limit a function to `calls` invocations per `period` seconds.

    Args:
        calls: max calls per period (bucket capacity).
        period: window length in seconds.
        block: if True, sleep until a token is available; if False, raise
            RateLimitExceeded immediately.
    """
    bucket = TokenBucket(rate=calls / period, capacity=calls)

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if bucket.consume():
                return func(*args, **kwargs)
            wait = bucket.time_until()
            if not block:
                raise RateLimitExceeded(wait)
            time.sleep(wait)
            bucket.consume()
            return func(*args, **kwargs)

        wrapper.bucket = bucket  # type: ignore[attr-defined]
        return wrapper

    return decorator
