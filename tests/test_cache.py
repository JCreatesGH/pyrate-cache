import asyncio
import time
from pyrate_cache import cache, MemoryCache


def test_caches_repeated_calls():
    calls = []

    @cache()
    def expensive(x):
        calls.append(x)
        return x * 2

    assert expensive(2) == 4
    assert expensive(2) == 4
    assert calls == [2]          # body ran only once
    assert expensive.hits == 1
    assert expensive.misses == 1


def test_kwargs_are_part_of_key():
    @cache()
    def f(a, b=1):
        return a + b

    assert f(1, b=2) == 3
    assert f(1, b=3) == 4
    assert f.misses == 2


def test_ttl_expiry():
    @cache(ttl=0.05)
    def f(x):
        return time.monotonic()

    first = f(1)
    assert f(1) == first
    time.sleep(0.06)
    assert f(1) != first


def test_cache_clear():
    @cache()
    def f(x):
        return object()

    a = f(1)
    f.cache_clear()
    assert f(1) is not a


def test_shared_backend():
    backend = MemoryCache()

    @cache(backend=backend)
    def f(x):
        return x

    f(1)
    assert backend.get("test_shared_backend.<locals>.f:(1,)|[]") == 1


def test_none_is_cached():
    calls = []

    @cache()
    def f(x):
        calls.append(x)
        return None

    assert f(1) is None
    assert f(1) is None
    assert calls == [1]            # body ran once even though it returns None
    assert f.hits == 1 and f.misses == 1


def test_maxsize_evicts_lru():
    calls = []

    @cache(maxsize=2)
    def f(x):
        calls.append(x)
        return x

    f(1); f(2); f(1)      # access 1 -> 1 is most-recently-used
    f(3)                  # evicts 2 (LRU), keeps 1 and 3
    f(1)                  # still cached -> no new call
    f(2)                  # was evicted -> recomputed
    assert calls == [1, 2, 3, 2]
    assert f.cache_info().currsize == 2
    assert f.cache_info().maxsize == 2


def test_cache_info():
    @cache()
    def f(x):
        return x

    f(1); f(1); f(2)
    info = f.cache_info()
    assert info.hits == 1 and info.misses == 2 and info.currsize == 2


def test_async_caching():
    calls = []

    @cache()
    async def f(x):
        calls.append(x)
        return x * 10

    async def run():
        return await f(3), await f(3)

    a, b = asyncio.run(run())
    assert a == 30 and b == 30
    assert calls == [3]           # awaited body ran once
    assert f.hits == 1 and f.misses == 1
