# pyrate-cache

[![CI](https://github.com/JCreatesGH/pyrate-cache/actions/workflows/ci.yml/badge.svg)](https://github.com/JCreatesGH/pyrate-cache/actions)
[![Python](https://img.shields.io/badge/python-3.8%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Tiny, **zero-dependency** rate limiting and caching decorators for Python. Thread-safe and `async`-aware, with TTL + LRU caching, pluggable cache backends, **token-bucket *and* sliding-window** limiters, and **per-key** (per-user / per-IP) limiting.

![screenshot](assets/screenshot.png)

## Install

```bash
pip install pyrate-cache
```

## Usage

```python
from pyrate_cache import cache, rate_limit

@cache(ttl=60, maxsize=1000)         # memoize for 60s, LRU-evict past 1000 entries
def fib(n):
    return n if n < 2 else fib(n - 1) + fib(n - 2)

@rate_limit(calls=5, period=1.0)     # at most 5 calls/sec (blocks)
def call_api(url):
    return requests.get(url)

@rate_limit(calls=100, period=60, block=False)  # raise instead of waiting
def webhook(payload):
    ...

# strict sliding window (never more than N per window), limited *per user*:
@rate_limit(calls=10, period=60, strategy="sliding-window", key=lambda req: req.user_id)
def handle(req):
    ...

fib.cache_info()   # CacheInfo(hits=…, misses=…, maxsize=1000, currsize=…)
```

`@cache` and `@rate_limit` also work transparently on `async def` functions — the cache awaits and
stores the result (not the coroutine), and the limiter uses `await asyncio.sleep` instead of blocking:

```python
@cache(ttl=30)
async def fetch(url):
    async with session.get(url) as r:
        return await r.json()
```

### Why

- **`@cache`** — TTL expiry, **LRU `maxsize`** bound, `.hits` / `.misses` and `.cache_info()`, `.cache_clear()`, correct caching of `None` results, an optional **`key=` callable** to cache by a subset of the args (or ignore a `self`/session arg), and any object with `get/set/clear` works as a backend (swap in Redis in one line).
- **`@rate_limit`** — two strategies: [`token-bucket`](https://en.wikipedia.org/wiki/Token_bucket) (default; smooth, allows bursts up to `calls`) and `sliding-window` (strict; never more than `calls` per trailing window). Blocking *or* non-blocking (`RateLimitExceeded`, which carries `retry_after`), and an optional `key=` callable gives each user/tenant/IP its own independent budget. The `TokenBucket` and `SlidingWindowLimiter` classes are usable standalone too, each exposing **`remaining()`** and `time_until()` so you can emit `X-RateLimit-Remaining` / `Reset` headers.

### Custom backend

```python
from pyrate_cache import cache

class RedisCache:
    def get(self, key): ...        # return the value, or None if absent
    def set(self, key, value, ttl): ...
    def clear(self): ...

@cache(ttl=300, backend=RedisCache())
def heavy(x): ...
```

## Development

```bash
pip install -e .[dev] && python -m pytest -q     # 26 tests, runs in <1s
```

## License

MIT
