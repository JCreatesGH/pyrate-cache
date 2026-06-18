import asyncio
import time
import pytest
from pyrate_cache import rate_limit, RateLimitExceeded, TokenBucket, SlidingWindowLimiter


def test_token_bucket_capacity():
    b = TokenBucket(rate=10, capacity=3)
    assert b.consume() and b.consume() and b.consume()
    assert not b.consume()


def test_refill_over_time():
    b = TokenBucket(rate=100, capacity=1)
    assert b.consume()
    assert not b.consume()
    time.sleep(0.02)
    assert b.consume()


def test_non_blocking_raises():
    @rate_limit(calls=1, period=10, block=False)
    def f():
        return "ok"

    assert f() == "ok"
    with pytest.raises(RateLimitExceeded):
        f()


def test_blocking_waits():
    @rate_limit(calls=2, period=0.1, block=True)
    def f():
        return time.monotonic()

    f(); f()
    start = time.monotonic()
    f()  # must wait for a refill
    assert time.monotonic() - start > 0.01


def test_invalid_params():
    with pytest.raises(ValueError):
        TokenBucket(rate=0, capacity=1)


def test_async_non_blocking_raises():
    @rate_limit(calls=1, period=10, block=False)
    async def f():
        return "ok"

    async def run():
        first = await f()
        with pytest.raises(RateLimitExceeded):
            await f()
        return first

    assert asyncio.run(run()) == "ok"


def test_async_blocking_waits():
    @rate_limit(calls=2, period=0.1, block=True)
    async def f():
        return time.monotonic()

    async def run():
        await f(); await f()
        start = time.monotonic()
        await f()   # must await a refill
        return time.monotonic() - start

    assert asyncio.run(run()) > 0.01


def test_sliding_window_limiter():
    w = SlidingWindowLimiter(limit=2, period=10)
    assert w.consume() and w.consume()
    assert not w.consume()
    assert w.time_until() > 0
    with pytest.raises(ValueError):
        SlidingWindowLimiter(limit=0, period=1)


def test_sliding_window_evicts_old_hits():
    w = SlidingWindowLimiter(limit=1, period=0.02)
    assert w.consume()
    assert not w.consume()
    time.sleep(0.03)
    assert w.consume()          # old hit fell out of the window


def test_rate_limit_sliding_strategy_blocks():
    @rate_limit(calls=1, period=10, block=False, strategy="sliding-window")
    def f():
        return "ok"
    assert f() == "ok"
    with pytest.raises(RateLimitExceeded):
        f()


def test_unknown_strategy_raises():
    with pytest.raises(ValueError):
        rate_limit(calls=1, strategy="nope")(lambda: None)


def test_keyed_rate_limit_is_per_key():
    @rate_limit(calls=1, period=10, block=False, key=lambda user: user)
    def hit(user):
        return user

    assert hit("alice") == "alice"
    assert hit("bob") == "bob"            # different key -> own budget
    with pytest.raises(RateLimitExceeded):
        hit("alice")                       # alice's single token is spent
    assert len(hit.limiters) == 2
