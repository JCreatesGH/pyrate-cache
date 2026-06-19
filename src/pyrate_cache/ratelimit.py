"""Rate-limiting decorators: token bucket (bursty) and sliding window (strict)."""
from __future__ import annotations
import asyncio
import time
import threading
import functools
from collections import deque
from typing import Any, Callable, Dict, Optional


class RateLimitExceeded(Exception):
    """Raised when a call exceeds the configured rate and blocking is off."""

    def __init__(self, retry_after: float) -> None:
        self.retry_after = retry_after
        super().__init__(f"rate limit exceeded, retry after {retry_after:.3f}s")


class TokenBucket:
    """Classic token bucket. `rate` tokens are added per second up to `capacity`.
    Allows short bursts up to `capacity`."""

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

    def remaining(self) -> int:
        """Whole calls available right now — for an ``X-RateLimit-Remaining`` header."""
        with self._lock:
            self._refill()
            return int(self._tokens)


class SlidingWindowLimiter:
    """Sliding-window-log limiter: at most `limit` calls in any trailing
    `period` seconds. Stricter than a token bucket — it never allows a burst
    larger than `limit` within a window."""

    def __init__(self, limit: int, period: float) -> None:
        if limit <= 0 or period <= 0:
            raise ValueError("limit and period must be positive")
        self.limit = limit
        self.period = period
        self._hits: "deque[float]" = deque()
        self._lock = threading.Lock()

    def _evict(self, now: float) -> None:
        cutoff = now - self.period
        while self._hits and self._hits[0] <= cutoff:
            self._hits.popleft()

    def consume(self, amount: float = 1.0) -> bool:
        with self._lock:
            now = time.monotonic()
            self._evict(now)
            if len(self._hits) < self.limit:
                self._hits.append(now)
                return True
            return False

    def time_until(self, amount: float = 1.0) -> float:
        with self._lock:
            now = time.monotonic()
            self._evict(now)
            if len(self._hits) < self.limit:
                return 0.0
            # a slot frees when the oldest hit leaves the trailing window
            return max(0.0, self._hits[0] + self.period - now)

    def remaining(self) -> int:
        """Calls still allowed in the current trailing window — for an
        ``X-RateLimit-Remaining`` header."""
        with self._lock:
            self._evict(time.monotonic())
            return max(0, self.limit - len(self._hits))


def _make_limiter(strategy: str, calls: int, period: float):
    if strategy in ("token-bucket", "token_bucket", "bucket"):
        return TokenBucket(rate=calls / period, capacity=calls)
    if strategy in ("sliding-window", "sliding_window", "sliding"):
        return SlidingWindowLimiter(limit=calls, period=period)
    raise ValueError(f"unknown strategy {strategy!r} (use 'token-bucket' or 'sliding-window')")


def rate_limit(calls: int, period: float = 1.0, block: bool = True, *,
               strategy: str = "token-bucket", key: Optional[Callable[..., Any]] = None) -> Callable:
    """Limit a function to `calls` invocations per `period` seconds.

    Args:
        calls: max calls per period.
        period: window length in seconds.
        block: if True, sleep until allowed; if False, raise RateLimitExceeded.
        strategy: ``"token-bucket"`` (default, allows bursts up to `calls`) or
            ``"sliding-window"`` (strict — never more than `calls` per window).
        key: optional ``key(*args, **kwargs)`` returning a hashable; each distinct
            key gets its own independent limiter (per-user / per-IP limiting).
    """
    # `limiter` is the single global limiter (key=None); `limiters` is the
    # per-key registry. Exactly one is active; both are defined for the closure.
    limiter = None if key is not None else _make_limiter(strategy, calls, period)
    limiters: Dict[Any, Any] = {}
    reg_lock = threading.Lock()

    def get_limiter(args: tuple, kwargs: dict):
        if key is None:
            return limiter
        k = key(*args, **kwargs)
        with reg_lock:
            lim = limiters.get(k)
            if lim is None:
                lim = limiters[k] = _make_limiter(strategy, calls, period)
            return lim

    def decorator(func: Callable) -> Callable:
        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def awrapper(*args: Any, **kwargs: Any) -> Any:
                limiter_ = get_limiter(args, kwargs)
                while not limiter_.consume():
                    wait = limiter_.time_until()
                    if not block:
                        raise RateLimitExceeded(wait)
                    await asyncio.sleep(wait)
                return await func(*args, **kwargs)

            _attach_rl(awrapper, key, limiter, limiters)
            return awrapper

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Loop rather than consume-once-after-sleep: under contention another
            # caller may grab the freed slot first.
            limiter_ = get_limiter(args, kwargs)
            while not limiter_.consume():
                wait = limiter_.time_until()
                if not block:
                    raise RateLimitExceeded(wait)
                time.sleep(wait)
            return func(*args, **kwargs)

        _attach_rl(wrapper, key, limiter, limiters)
        return wrapper

    return decorator


def _attach_rl(wrapper: Callable, key, limiter, limiters) -> None:
    # Inspection handles: a single `.bucket`/`.limiter` for the global case, or
    # the `.limiters` registry for the keyed case.
    if key is None:
        wrapper.bucket = limiter      # type: ignore[attr-defined]  (back-compat name)
        wrapper.limiter = limiter     # type: ignore[attr-defined]
    else:
        wrapper.limiters = limiters   # type: ignore[attr-defined]
