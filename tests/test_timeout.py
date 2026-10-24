"""Unit tests for faultshield.timeout."""

import time
import pytest

from faultshield.exceptions import ExecutionTimeoutError, ResilienceConfigurationError
from faultshield.timeout import TimeoutGuard


def test_timeout_guard_validation():
    with pytest.raises(ResilienceConfigurationError):
        TimeoutGuard(seconds=0)
    with pytest.raises(ResilienceConfigurationError):
        TimeoutGuard(seconds=-1.0)


def test_timeout_guard_fast_function():
    guard = TimeoutGuard(seconds=0.5)

    def fast():
        return "completed"

    assert guard.execute(fast) == "completed"


def test_timeout_guard_slow_function():
    guard = TimeoutGuard(seconds=0.05)

    def slow():
        time.sleep(0.15)
        return "too late"

    with pytest.raises(ExecutionTimeoutError) as exc_info:
        guard.execute(slow)

    assert exc_info.value.timeout_seconds == 0.05


def test_timeout_guard_exception_propagation():
    guard = TimeoutGuard(seconds=0.5)

    def failing():
        raise ZeroDivisionError("division by zero in worker")

    with pytest.raises(ZeroDivisionError):
        guard.execute(failing)


def test_timeout_guard_decorator():
    guard = TimeoutGuard(seconds=0.5)

    @guard
    def work(x):
        return x + 1

    assert work(9) == 10
    assert hasattr(work, "timeout_guard")
