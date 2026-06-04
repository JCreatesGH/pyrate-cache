"""Pluggable function-result caching with TTL."""
from __future__ import annotations
import time
import threading
import functools
from typing import Any, Callable, Optional, Protocol, Tuple


def _make_key(args: Tuple[Any, ...], kwargs: dict) -> str:
    return repr(args) + "|" + repr(sorted(kwargs.items()))


class CacheBackend(Protocol):
    """Any object implementing get/set/clear can be a cache backend."""
    def get(self, key: str) -> Optional[Any]: ...
    def set(self, key: str, value: Any, ttl: Optional[float]) -> None: ...
    def clear(self) -> None: ...


class MemoryCache:
    """Thread-safe in-memory cache with optional per-entry TTL."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[Any, Optional[float]]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            item = self._store.get(key)
            if item is None:
                return None
            value, expires_at = item
            if expires_at is not None and time.monotonic() > expires_at:
                del self._store[key]
                return None
            return value

    def set(self, key: str, value: Any, ttl: Optional[float]) -> None:
        expires_at = time.monotonic() + ttl if ttl else None
        with self._lock:
            self._store[key] = (value, expires_at)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


def cache(ttl: Optional[float] = None, backend: Optional[CacheBackend] = None) -> Callable:
    """Cache a function's return value.

    Args:
        ttl: seconds before an entry expires. None means cache forever.
        backend: any CacheBackend (defaults to a per-decorator MemoryCache).
    """
    store: CacheBackend = backend or MemoryCache()

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            key = func.__qualname__ + ":" + _make_key(args, kwargs)
            hit = store.get(key)
            if hit is not None:
                wrapper.hits += 1            # type: ignore[attr-defined]
                return hit
            wrapper.misses += 1              # type: ignore[attr-defined]
            result = func(*args, **kwargs)
            store.set(key, result, ttl)
            return result

        wrapper.hits = 0                     # type: ignore[attr-defined]
        wrapper.misses = 0                   # type: ignore[attr-defined]
        wrapper.cache_clear = store.clear    # type: ignore[attr-defined]
        return wrapper

    return decorator
