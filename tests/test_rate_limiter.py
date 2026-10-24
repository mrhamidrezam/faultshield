"""Unit tests for faultshield.rate_limiter."""

import time
import pytest

from faultshield.exceptions import RateLimitExceededError, ResilienceConfigurationError
from faultshield.rate_limiter import RateLimiter


def test_rate_limiter_init_validation():
    with pytest.raises(ResilienceConfigurationError):
        RateLimiter(rate=0)
    with pytest.raises(ResilienceConfigurationError):
        RateLimiter(rate=-5)
    with pytest.raises(ResilienceConfigurationError):
        RateLimiter(rate=10, capacity=0)


def test_rate_limiter_acquire_immediate():
    limiter = RateLimiter(rate=10, capacity=5)
    assert limiter.acquire(1.0) is True
    assert limiter.acquire(1.0) is True
    assert limiter.available_tokens <= 4.0


def test_rate_limiter_non_blocking_exhaustion():
    limiter = RateLimiter(rate=10, capacity=2, default_timeout=0.0)
    assert limiter.acquire(1.0) is True
    assert limiter.acquire(1.0) is True

    # Next immediate acquire should fail
    assert limiter.acquire(1.0, timeout=0.0) is False

    with pytest.raises(RateLimitExceededError) as exc_info:
        limiter.execute(lambda: "SHOULD_FAIL")

    assert exc_info.value.retry_after >= 0.0


def test_rate_limiter_blocking_replenish():
    limiter = RateLimiter(rate=20, capacity=1)
    assert limiter.acquire(1.0) is True

    start = time.monotonic()
    # Wait for 1 token at 20 tokens/sec -> takes ~0.05s
    assert limiter.acquire(1.0, timeout=0.2) is True
    elapsed = time.monotonic() - start
    assert elapsed >= 0.03


def test_rate_limiter_context_manager():
    limiter = RateLimiter(rate=10, capacity=2)
    with limiter:
        val = 42
    assert val == 42


def test_rate_limiter_decorator():
    limiter = RateLimiter(rate=10, capacity=5)

    @limiter
    def add(a, b):
        return a + b

    assert add(10, 20) == 30
    assert hasattr(add, "rate_limiter")


def test_rate_limiter_oversized_request_rejected():
    limiter = RateLimiter(rate=10, capacity=2)
    with pytest.raises(ResilienceConfigurationError):
        limiter.acquire(5.0)
