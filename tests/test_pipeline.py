"""Unit tests for faultshield.pipeline."""

import time
import pytest

from faultshield.exceptions import ExecutionTimeoutError, MaxRetriesExceededError
from faultshield.pipeline import ResiliencePipeline
from faultshield.types import JitterStrategy


def test_pipeline_full_success():
    pipeline = (
        ResiliencePipeline("test_pipe")
        .add_retry(max_attempts=3, initial_delay=0.01)
        .add_circuit_breaker(failure_rate_threshold=50.0, recovery_timeout=1.0)
        .add_timeout(seconds=1.0)
        .add_bulkhead(max_concurrent=5)
        .add_rate_limiter(rate=20)
    )

    result = pipeline.execute(lambda x, y: x + y, 10, 20)
    assert result == 30

    metrics = pipeline.get_metrics()
    assert metrics["pipeline_name"] == "test_pipe"
    assert metrics["successful_calls"] == 1
    assert metrics["failed_calls"] == 0


def test_pipeline_retry_and_circuit_cooperation():
    pipeline = (
        ResiliencePipeline("retry_pipe")
        .add_retry(max_attempts=3, initial_delay=0.01, jitter=JitterStrategy.NONE)
        .add_circuit_breaker(failure_rate_threshold=50.0, recovery_timeout=0.2, minimum_number_of_calls=5)
    )

    attempts = 0

    def flaky():
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise ConnectionError("Intermittent error")
        return "SUCCESS_AFTER_RETRY"

    res = pipeline.execute(flaky)
    assert res == "SUCCESS_AFTER_RETRY"
    assert attempts == 3

    metrics = pipeline.get_metrics()
    assert metrics["retries"] == 2
    assert metrics["successful_calls"] == 1


def test_pipeline_fallback_on_unhandled_error():
    pipeline = (
        ResiliencePipeline("fallback_pipe")
        .add_fallback(lambda exc: {"status": "degraded", "error": type(exc).__name__})
        .add_retry(max_attempts=2, initial_delay=0.01)
    )

    result = pipeline.execute(lambda: (_ for _ in ()).throw(RuntimeError("Out of memory")))
    assert result == {"status": "degraded", "error": "MaxRetriesExceededError"}

    metrics = pipeline.get_metrics()
    assert metrics["fallbacks"] == 1
    assert metrics["failed_calls"] == 1


def test_pipeline_timeout_integration():
    pipeline = (
        ResiliencePipeline("timeout_pipe")
        .add_fallback("TIMEOUT_FALLBACK")
        .add_timeout(seconds=0.05)
    )

    def slow_worker():
        time.sleep(0.12)
        return "too slow"

    res = pipeline.execute(slow_worker)
    assert res == "TIMEOUT_FALLBACK"

    metrics = pipeline.get_metrics()
    assert metrics["timeouts"] == 1
    assert metrics["fallbacks"] == 1


def test_pipeline_execute_with_result():
    pipeline = ResiliencePipeline("result_pipe").add_timeout(seconds=1.0)
    res = pipeline.execute_with_result(lambda: 999)
    assert res.success is True
    assert res.value == 999
    assert res.duration_seconds > 0

    res_err = pipeline.execute_with_result(lambda: (_ for _ in ()).throw(ValueError("bad")))
    assert res_err.success is False
    assert isinstance(res_err.error, ValueError)


def test_pipeline_decorator():
    pipeline = ResiliencePipeline("decorator_pipe")

    @pipeline
    def compute(a, b):
        return a * b

    assert compute(6, 7) == 42
    assert hasattr(compute, "pipeline")
