import time
import pytest
from pyrate_cache import rate_limit, RateLimitExceeded, TokenBucket


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
