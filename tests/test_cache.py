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
