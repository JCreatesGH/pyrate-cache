"""Pluggable function-result caching with TTL, LRU bounds, and async support."""
from __future__ import annotations
import asyncio
import time
import threading
import functools
from collections import OrderedDict, namedtuple
from typing import Any, Callable, Optional, Protocol, Tuple

# Sentinel stored in place of a real ``None`` result, so a function that returns
# ``None`` is cached correctly (a backend returning ``None`` means "no entry").
_NULL = object()

CacheInfo = namedtuple("CacheInfo", ["hits", "misses", "maxsize", "currsize"])


def _make_key(args: Tuple[Any, ...], kwargs: dict) -> str:
    return repr(args) + "|" + repr(sorted(kwargs.items()))


class CacheBackend(Protocol):
    """Any object implementing get/set/clear can be a cache backend.

    ``get`` returns the stored value, or ``None`` when the key is absent.
    """
    def get(self, key: str) -> Optional[Any]: ...
    def set(self, key: str, value: Any, ttl: Optional[float]) -> None: ...
    def clear(self) -> None: ...


class MemoryCache:
    """Thread-safe in-memory cache with optional per-entry TTL and LRU bound."""

    def __init__(self, maxsize: Optional[int] = None) -> None:
        self._store: "OrderedDict[str, tuple[Any, Optional[float]]]" = OrderedDict()
        self._maxsize = maxsize
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
            self._store.move_to_end(key)   # mark most-recently-used
            return value

    def set(self, key: str, value: Any, ttl: Optional[float]) -> None:
        expires_at = time.monotonic() + ttl if ttl else None
        with self._lock:
            self._store[key] = (value, expires_at)
            self._store.move_to_end(key)
            if self._maxsize is not None:
                while len(self._store) > self._maxsize:
                    self._store.popitem(last=False)   # evict least-recently-used

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._store)


def cache(ttl: Optional[float] = None, maxsize: Optional[int] = None,
          backend: Optional[CacheBackend] = None,
          key: Optional[Callable[..., Any]] = None) -> Callable:
    """Cache a function's (or coroutine's) return value.

    Args:
        ttl: seconds before an entry expires. None means cache forever.
        maxsize: max entries before least-recently-used eviction (default: unbounded).
            Ignored when an explicit ``backend`` is supplied.
        backend: any CacheBackend (defaults to a per-decorator MemoryCache).
        key: optional ``key(*args, **kwargs)`` returning a hashable cache key — cache by a
            subset of the arguments, or normalize them (e.g. ignore a `self`/session arg).
            Defaults to keying on all positional + keyword arguments.
    """
    # NB: `backend or ...` would be wrong — an empty MemoryCache is falsy (it has __len__).
    store: CacheBackend = backend if backend is not None else MemoryCache(maxsize=maxsize)

    def decorator(func: Callable) -> Callable:
        def make_key(args: Tuple[Any, ...], kwargs: dict) -> str:
            inner = repr(key(*args, **kwargs)) if key is not None else _make_key(args, kwargs)
            return func.__qualname__ + ":" + inner

        def lookup(key_: str, holder: Callable):
            hit = store.get(key_)
            if hit is not None:
                holder.hits += 1                        # type: ignore[attr-defined]
                return True, (None if hit is _NULL else hit)
            holder.misses += 1                          # type: ignore[attr-defined]
            return False, None

        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def awrapper(*args: Any, **kwargs: Any) -> Any:
                k = make_key(args, kwargs)
                found, value = lookup(k, awrapper)
                if found:
                    return value
                result = await func(*args, **kwargs)
                store.set(k, _NULL if result is None else result, ttl)
                return result
            _attach(awrapper, store, maxsize)
            return awrapper

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            k = make_key(args, kwargs)
            found, value = lookup(k, wrapper)
            if found:
                return value
            result = func(*args, **kwargs)
            store.set(k, _NULL if result is None else result, ttl)
            return result
        _attach(wrapper, store, maxsize)
        return wrapper

    return decorator


def _attach(wrapper: Callable, store: CacheBackend, maxsize: Optional[int]) -> None:
    wrapper.hits = 0                              # type: ignore[attr-defined]
    wrapper.misses = 0                            # type: ignore[attr-defined]
    wrapper.cache_clear = store.clear             # type: ignore[attr-defined]

    def cache_info() -> CacheInfo:
        currsize = len(store) if hasattr(store, "__len__") else -1   # type: ignore[arg-type]
        return CacheInfo(wrapper.hits, wrapper.misses, maxsize, currsize)  # type: ignore[attr-defined]

    wrapper.cache_info = cache_info              # type: ignore[attr-defined]
