"""Unit tests for faultshield.metrics."""

from faultshield.metrics import ResilienceMetrics


def test_metrics_success_and_failure_recording():
    metrics = ResilienceMetrics(history_size=100)
    metrics.record_success(0.012)
    metrics.record_success(0.018)
    metrics.record_failure(0.050, ConnectionError("network drop"))

    snap = metrics.snapshot()
    assert snap["total_calls"] == 3
    assert snap["successful_calls"] == 2
    assert snap["failed_calls"] == 1
    assert snap["success_rate_pct"] == 66.67
    assert snap["errors_by_type"]["ConnectionError"] == 1
    assert snap["latency_stats"]["count"] == 3
    assert snap["latency_stats"]["min_ms"] > 0


def test_metrics_rejections_and_fallbacks():
    metrics = ResilienceMetrics()
    metrics.record_retry()
    metrics.record_retry()
    metrics.record_circuit_rejection()
    metrics.record_rate_limit_rejection()
    metrics.record_bulkhead_rejection()
    metrics.record_timeout()
    metrics.record_fallback()

    snap = metrics.snapshot()
    assert snap["retries"] == 2
    assert snap["circuit_rejections"] == 1
    assert snap["rate_limit_rejections"] == 1
    assert snap["bulkhead_rejections"] == 1
    assert snap["timeouts"] == 1
    assert snap["fallbacks"] == 1


def test_metrics_reset():
    metrics = ResilienceMetrics()
    metrics.record_success(0.01)
    metrics.record_retry()
    assert metrics.snapshot()["total_calls"] == 1

    metrics.reset()
    snap = metrics.snapshot()
    assert snap["total_calls"] == 0
    assert snap["retries"] == 0
    assert snap["latency_stats"]["count"] == 0
