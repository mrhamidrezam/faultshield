"""FaultShield Resilience Metrics.

Tracks runtime telemetry, performance latencies, and fault occurrences across
resilience policies.
"""

from collections import deque
import threading
from typing import Any, Deque, Dict, List, Optional


class ResilienceMetrics:
    """Thread-safe runtime telemetry collector for resilience policies."""

    def __init__(self, history_size: int = 1000) -> None:
        self.history_size = max(10, history_size)
        self._lock = threading.Lock()
        self._total_calls = 0
        self._successful_calls = 0
        self._failed_calls = 0
        self._retry_count = 0
        self._circuit_rejections = 0
        self._rate_limit_rejections = 0
        self._bulkhead_rejections = 0
        self._timeout_count = 0
        self._fallback_count = 0
        self._latencies: Deque[float] = deque(maxlen=self.history_size)
        self._errors_by_type: Dict[str, int] = {}

    def record_success(self, duration: float) -> None:
        """Record a successful execution."""
        with self._lock:
            self._total_calls += 1
            self._successful_calls += 1
            self._latencies.append(duration)

    def record_failure(self, duration: float, exc: BaseException) -> None:
        """Record an execution failure."""
        with self._lock:
            self._total_calls += 1
            self._failed_calls += 1
            self._latencies.append(duration)
            err_name = type(exc).__name__
            self._errors_by_type[err_name] = self._errors_by_type.get(err_name, 0) + 1

    def record_retry(self) -> None:
        """Record a retry attempt."""
        with self._lock:
            self._retry_count += 1

    def record_circuit_rejection(self) -> None:
        """Record a circuit breaker fast-fail rejection."""
        with self._lock:
            self._circuit_rejections += 1

    def record_rate_limit_rejection(self) -> None:
        """Record a rate limit rejection."""
        with self._lock:
            self._rate_limit_rejections += 1

    def record_bulkhead_rejection(self) -> None:
        """Record a bulkhead capacity rejection."""
        with self._lock:
            self._bulkhead_rejections += 1

    def record_timeout(self) -> None:
        """Record a timeout occurrence."""
        with self._lock:
            self._timeout_count += 1

    def record_fallback(self) -> None:
        """Record an execution falling back to default/cache."""
        with self._lock:
            self._fallback_count += 1

    def reset(self) -> None:
        """Reset all counters and latency buffers."""
        with self._lock:
            self._total_calls = 0
            self._successful_calls = 0
            self._failed_calls = 0
            self._retry_count = 0
            self._circuit_rejections = 0
            self._rate_limit_rejections = 0
            self._bulkhead_rejections = 0
            self._timeout_count = 0
            self._fallback_count = 0
            self._latencies.clear()
            self._errors_by_type.clear()

    def snapshot(self) -> Dict[str, Any]:
        """Produce a complete metrics dictionary snapshot."""
        with self._lock:
            latencies = sorted(self._latencies)
            n = len(latencies)

            def percentile(p: float) -> float:
                if not latencies:
                    return 0.0
                idx = int(p * (n - 1))
                return latencies[idx]

            avg_latency = (sum(latencies) / n) if n > 0 else 0.0
            min_latency = latencies[0] if n > 0 else 0.0
            max_latency = latencies[-1] if n > 0 else 0.0

            success_rate = (
                (self._successful_calls / self._total_calls * 100.0)
                if self._total_calls > 0
                else 100.0
            )

            return {
                "total_calls": self._total_calls,
                "successful_calls": self._successful_calls,
                "failed_calls": self._failed_calls,
                "success_rate_pct": round(success_rate, 2),
                "retries": self._retry_count,
                "circuit_rejections": self._circuit_rejections,
                "rate_limit_rejections": self._rate_limit_rejections,
                "bulkhead_rejections": self._bulkhead_rejections,
                "timeouts": self._timeout_count,
                "fallbacks": self._fallback_count,
                "latency_stats": {
                    "count": n,
                    "avg_ms": round(avg_latency * 1000.0, 3),
                    "min_ms": round(min_latency * 1000.0, 3),
                    "max_ms": round(max_latency * 1000.0, 3),
                    "p50_ms": round(percentile(0.50) * 1000.0, 3),
                    "p90_ms": round(percentile(0.90) * 1000.0, 3),
                    "p99_ms": round(percentile(0.99) * 1000.0, 3),
                },
                "errors_by_type": dict(self._errors_by_type),
            }
