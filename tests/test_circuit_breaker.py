"""Unit tests for faultshield.circuit_breaker."""

import time
import pytest

from faultshield.circuit_breaker import CircuitBreaker
from faultshield.exceptions import CircuitOpenError, ResilienceConfigurationError
from faultshield.types import CircuitState


def test_circuit_breaker_init_validation():
    with pytest.raises(ResilienceConfigurationError):
        CircuitBreaker(failure_rate_threshold=0)
    with pytest.raises(ResilienceConfigurationError):
        CircuitBreaker(failure_rate_threshold=101)
    with pytest.raises(ResilienceConfigurationError):
        CircuitBreaker(recovery_timeout=-1.0)
    with pytest.raises(ResilienceConfigurationError):
        CircuitBreaker(half_open_max_calls=0)
    with pytest.raises(ResilienceConfigurationError):
        CircuitBreaker(sliding_window_size=0)
    with pytest.raises(ResilienceConfigurationError):
        CircuitBreaker(minimum_number_of_calls=0)


def test_circuit_breaker_healthy_calls():
    cb = CircuitBreaker(name="test_cb", minimum_number_of_calls=3)

    def healthy(x):
        return x * 2

    assert cb.execute(healthy, 5) == 10
    assert cb.execute(healthy, 10) == 20
    assert cb.execute(healthy, 15) == 30
    assert cb.state == CircuitState.CLOSED

    stats = cb.get_stats()
    assert stats.successful_calls == 3
    assert stats.failed_calls == 0
    assert stats.failure_rate == 0.0


def test_circuit_breaker_trips_to_open():
    events = []

    def on_change(name, old, new, reason):
        events.append((name, old, new))

    cb = CircuitBreaker(
        name="test_trip",
        failure_rate_threshold=50.0,
        recovery_timeout=0.2,
        sliding_window_size=4,
        minimum_number_of_calls=4,
        on_state_change=on_change,
    )

    def faulty(should_fail):
        if should_fail:
            raise ValueError("Failure")
        return "OK"

    cb.execute(faulty, False)
    cb.execute(faulty, False)
    with pytest.raises(ValueError):
        cb.execute(faulty, True)
    with pytest.raises(ValueError):
        cb.execute(faulty, True)

    assert cb.state == CircuitState.OPEN
    assert len(events) == 1
    assert events[0] == ("test_trip", CircuitState.CLOSED, CircuitState.OPEN)


def test_circuit_breaker_fast_fails_when_open():
    cb = CircuitBreaker(name="fast_fail", recovery_timeout=5.0)
    cb.trip("Forced trip")

    assert cb.state == CircuitState.OPEN
    with pytest.raises(CircuitOpenError) as exc_info:
        cb.execute(lambda: "OK")

    assert "fast_fail" in str(exc_info.value)
    assert exc_info.value.circuit_name == "fast_fail"


def test_circuit_breaker_fallback_when_open():
    cb = CircuitBreaker(
        name="fallback_test",
        recovery_timeout=5.0,
        fallback=lambda exc: "DEFAULT_VALUE",
    )
    cb.trip("Tripped")

    result = cb.execute(lambda: "UNREACHABLE")
    assert result == "DEFAULT_VALUE"


def test_circuit_breaker_recovery_cycle():
    cb = CircuitBreaker(
        name="recovery_test",
        failure_rate_threshold=50.0,
        recovery_timeout=0.1,
        half_open_max_calls=2,
        minimum_number_of_calls=2,
    )

    # Trip breaker
    with pytest.raises(RuntimeError):
        cb.execute(lambda: (_ for _ in ()).throw(RuntimeError("error 1")))
    with pytest.raises(RuntimeError):
        cb.execute(lambda: (_ for _ in ()).throw(RuntimeError("error 2")))

    assert cb.state == CircuitState.OPEN

    # Wait for recovery timeout
    time.sleep(0.12)
    assert cb.state == CircuitState.HALF_OPEN

    # First trial success in HALF_OPEN
    assert cb.execute(lambda: "Trial 1") == "Trial 1"
    assert cb.state == CircuitState.HALF_OPEN

    # Second trial success -> transitions back to CLOSED
    assert cb.execute(lambda: "Trial 2") == "Trial 2"
    assert cb.state == CircuitState.CLOSED


def test_circuit_breaker_half_open_failure_reopens():
    cb = CircuitBreaker(
        name="half_open_fail",
        failure_rate_threshold=50.0,
        recovery_timeout=0.08,
        half_open_max_calls=2,
        minimum_number_of_calls=2,
    )

    cb.trip()
    time.sleep(0.09)
    assert cb.state == CircuitState.HALF_OPEN

    # Failure during HALF_OPEN should immediately reopen
    with pytest.raises(ValueError):
        cb.execute(lambda: (_ for _ in ()).throw(ValueError("trial failure")))

    assert cb.state == CircuitState.OPEN


def test_circuit_breaker_manual_trip_and_reset():
    cb = CircuitBreaker(name="manual_ctrl")
    assert cb.state == CircuitState.CLOSED
    cb.trip("Testing trip")
    assert cb.state == CircuitState.OPEN
    cb.reset()
    assert cb.state == CircuitState.CLOSED


def test_circuit_breaker_slow_call_threshold():
    cb = CircuitBreaker(
        name="slow_call_test",
        slow_call_duration_threshold=0.02,
        slow_call_rate_threshold=50.0,
        minimum_number_of_calls=2,
        sliding_window_size=2,
    )

    def slow_fn():
        time.sleep(0.03)
        return "done"

    cb.execute(slow_fn)
    cb.execute(slow_fn)

    assert cb.state == CircuitState.OPEN


def test_circuit_breaker_ignore_exceptions():
    cb = CircuitBreaker(
        name="ignore_test",
        failure_rate_threshold=50.0,
        minimum_number_of_calls=2,
        ignore_exceptions=(KeyError,),
    )

    with pytest.raises(KeyError):
        cb.execute(lambda: (_ for _ in ()).throw(KeyError("missing")))
    with pytest.raises(KeyError):
        cb.execute(lambda: (_ for _ in ()).throw(KeyError("missing 2")))

    # Should still be CLOSED because KeyError is ignored
    assert cb.state == CircuitState.CLOSED


def test_circuit_breaker_decorator():
    cb = CircuitBreaker(name="decorator_test")

    @cb
    def multiply(a, b):
        return a * b

    assert multiply(3, 4) == 12
    assert hasattr(multiply, "circuit_breaker")
