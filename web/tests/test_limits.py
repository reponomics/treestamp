from treestamp_web import limits
from treestamp_web.limits import RateLimiter

from .conftest import Clock


def test_bucket_refills_over_time() -> None:
    clock = Clock()
    limiter = RateLimiter(2, clock)
    assert limiter.acquire("a") is None
    assert limiter.acquire("a") is None
    assert limiter.acquire("a") == 30
    assert limiter.acquire("b") is None, "identities are independent"
    clock.now += 30
    assert limiter.acquire("a") is None
    assert limiter.acquire("a") == 30


def test_zero_capacity_disables_limiting_and_prune_drops_full_buckets(
    monkeypatch: object,
) -> None:
    clock = Clock()
    assert RateLimiter(0, clock).acquire("a") is None
    limiter = RateLimiter(60, clock)
    limits.__dict__["_PRUNE_AT"] = 2
    try:
        limiter.acquire("a")
        clock.now += 120
        limiter.acquire("b")
        assert set(limiter._buckets) == {"b"}, "a refilled completely and was pruned"
    finally:
        limits.__dict__["_PRUNE_AT"] = 10_000
