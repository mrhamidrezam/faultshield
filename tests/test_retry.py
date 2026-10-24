"""Unit tests for faultshield.retry."""

import pytest

from faultshield.exceptions import MaxRetriesExceededError, ResilienceConfigurationError
from faultshield.retry import RetryPolicy
from faultshield.types import JitterStrategy


def test_retry_init_validation():
    with pytest.raises(ResilienceConfigurationError):
        RetryPolicy(max_attempts=0)
    with pytest.raises(ResilienceConfigurationError):
        RetryPolicy(initial_delay=-1.0)
    with pytest.raises(ResilienceConfigurationError):
        RetryPolicy(initial_delay=2.0, max_delay=1.0)
    with pytest.raises(ResilienceConfigurationError):
        RetryPolicy(backoff_factor=0.5)


def test_retry_success_first_attempt():
    policy = RetryPolicy(max_attempts=3, initial_delay=0.01)
    call_count = 0

    def work():
        nonlocal call_count
        call_count += 1
        return "success"

    assert policy.execute(work) == "success"
    assert call_count == 1


def test_retry_eventual_success():
    policy = RetryPolicy(max_attempts=3, initial_delay=0.01)
    attempts = 0

    def flaky():
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise ConnectionError("Temporary failure")
        return "recovered"

    assert policy.execute(flaky) == "recovered"
    assert attempts == 3


def test_retry_exhausted_raises_max_retries():
    policy = RetryPolicy(max_attempts=3, initial_delay=0.01)
    attempts = 0

    def always_fails():
        nonlocal attempts
        attempts += 1
        raise ConnectionResetError("Fatal connection reset")

    with pytest.raises(MaxRetriesExceededError) as exc_info:
        policy.execute(always_fails)

    assert exc_info.value.attempts == 3
    assert isinstance(exc_info.value.last_exception, ConnectionResetError)
    assert attempts == 3


def test_retry_jitter_strategies():
    for strategy in [
        JitterStrategy.NONE,
        JitterStrategy.FULL,
        JitterStrategy.EQUAL,
        JitterStrategy.DECORRELATED,
    ]:
        policy = RetryPolicy(
            max_attempts=2,
            initial_delay=0.01,
            max_delay=0.1,
            jitter=strategy,
        )
        delay = policy.calculate_delay(attempt=1, prev_delay=0.01)
        assert 0.0 <= delay <= 0.1


def test_retry_with_predicate():
    policy = RetryPolicy(
        max_attempts=3,
        initial_delay=0.01,
        retry_if=lambda exc: "temporary" in str(exc),
    )

    attempts = 0

    def fn():
        nonlocal attempts
        attempts += 1
        raise ValueError("fatal unrecoverable issue")

    with pytest.raises(ValueError) as exc_info:
        policy.execute(fn)

    assert "fatal unrecoverable issue" in str(exc_info.value)
    # Should abort immediately on attempt 1 because predicate was False
    assert attempts == 1


def test_retry_on_exception_types():
    policy = RetryPolicy(
        max_attempts=3,
        initial_delay=0.01,
        retry_on=(ConnectionError,),
    )

    with pytest.raises(KeyError):
        policy.execute(lambda: (_ for _ in ()).throw(KeyError("unrelated")))


def test_retry_fallback():
    policy = RetryPolicy(
        max_attempts=2,
        initial_delay=0.01,
        fallback=lambda exc: f"FALLBACK_FOR_{type(exc).__name__}",
    )

    result = policy.execute(lambda: (_ for _ in ()).throw(RuntimeError("oops")))
    assert result == "FALLBACK_FOR_RuntimeError"


def test_retry_callback_invoked():
    retry_log = []

    def on_retry(attempt, delay, exc):
        retry_log.append((attempt, delay, str(exc)))

    policy = RetryPolicy(
        max_attempts=3,
        initial_delay=0.01,
        on_retry=on_retry,
    )

    attempts = 0

    def flaky():
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise TimeoutError(f"fail {attempts}")
        return "ok"

    res = policy.execute(flaky)
    assert res == "ok"
    assert len(retry_log) == 2
    assert retry_log[0][0] == 1
    assert retry_log[1][0] == 2


def test_retry_decorator():
    policy = RetryPolicy(max_attempts=2, initial_delay=0.01)

    @policy
    def greet(name):
        return f"Hello, {name}!"

    assert greet("Hamidreza") == "Hello, Hamidreza!"
    assert hasattr(greet, "retry_policy")
