"""FaultShield Resilience Pipeline.

Provides fluent policy composition combining Circuit Breakers, Retries,
Rate Limiters, Bulkheads, Timeouts, and Fallbacks into a unified,
production-grade execution chain with integrated telemetry.
"""

import functools
import time
from typing import Any, Callable, Dict, List, Optional, Union

from faultshield.bulkhead import Bulkhead
from faultshield.circuit_breaker import CircuitBreaker
from faultshield.exceptions import (
    BulkheadFullError,
    CircuitOpenError,
    ExecutionTimeoutError,
    MaxRetriesExceededError,
    RateLimitExceededError,
)
from faultshield.metrics import ResilienceMetrics
from faultshield.rate_limiter import RateLimiter
from faultshield.retry import RetryPolicy
from faultshield.timeout import TimeoutGuard
from faultshield.types import (
    ExecutionResult,
    FallbackCallable,
    JitterStrategy,
)


class ResiliencePipeline:
    """Fluent policy chain orchestrating multiple fault-tolerance strategies."""

    def __init__(self, name: str = "default_pipeline") -> None:
        self.name = name
        self.metrics = ResilienceMetrics()
        self._circuit_breaker: Optional[CircuitBreaker] = None
        self._retry_policy: Optional[RetryPolicy] = None
        self._rate_limiter: Optional[RateLimiter] = None
        self._bulkhead: Optional[Bulkhead] = None
        self._timeout_guard: Optional[TimeoutGuard] = None
        self._fallback: Optional[Union[FallbackCallable, Any]] = None

    def add_circuit_breaker(
        self,
        failure_rate_threshold: float = 50.0,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 3,
        sliding_window_size: int = 20,
        minimum_number_of_calls: int = 5,
        slow_call_duration_threshold: Optional[float] = None,
        slow_call_rate_threshold: float = 100.0,
        name: Optional[str] = None,
    ) -> "ResiliencePipeline":
        """Configure and attach a CircuitBreaker to the pipeline."""
        cb_name = name or f"{self.name}_cb"
        self._circuit_breaker = CircuitBreaker(
            name=cb_name,
            failure_rate_threshold=failure_rate_threshold,
            recovery_timeout=recovery_timeout,
            half_open_max_calls=half_open_max_calls,
            sliding_window_size=sliding_window_size,
            minimum_number_of_calls=minimum_number_of_calls,
            slow_call_duration_threshold=slow_call_duration_threshold,
            slow_call_rate_threshold=slow_call_rate_threshold,
        )
        return self

    def add_retry(
        self,
        max_attempts: int = 3,
        initial_delay: float = 0.1,
        max_delay: float = 30.0,
        backoff_factor: float = 2.0,
        jitter: Union[JitterStrategy, str] = JitterStrategy.FULL,
    ) -> "ResiliencePipeline":
        """Configure and attach a RetryPolicy to the pipeline."""

        def _on_retry_callback(attempt: int, delay: float, exc: BaseException) -> None:
            self.metrics.record_retry()

        self._retry_policy = RetryPolicy(
            max_attempts=max_attempts,
            initial_delay=initial_delay,
            max_delay=max_delay,
            backoff_factor=backoff_factor,
            jitter=jitter,
            on_retry=_on_retry_callback,
        )
        return self

    def add_rate_limiter(
        self,
        rate: float,
        capacity: Optional[float] = None,
        default_timeout: float = 0.0,
    ) -> "ResiliencePipeline":
        """Configure and attach a RateLimiter to the pipeline."""
        self._rate_limiter = RateLimiter(
            rate=rate,
            capacity=capacity,
            default_timeout=default_timeout,
        )
        return self

    def add_bulkhead(
        self,
        max_concurrent: int = 10,
        max_queued: int = 0,
        queue_timeout: float = 0.0,
    ) -> "ResiliencePipeline":
        """Configure and attach a Bulkhead concurrency barrier to the pipeline."""
        self._bulkhead = Bulkhead(
            max_concurrent=max_concurrent,
            max_queued=max_queued,
            queue_timeout=queue_timeout,
        )
        return self

    def add_timeout(self, seconds: float) -> "ResiliencePipeline":
        """Configure and attach a TimeoutGuard to the pipeline."""
        self._timeout_guard = TimeoutGuard(seconds=seconds)
        return self

    def add_fallback(self, fallback: Union[FallbackCallable, Any]) -> "ResiliencePipeline":
        """Configure a fallback handler or value for the pipeline."""
        self._fallback = fallback
        return self

    def _resolve_fallback(self, exc: BaseException) -> Any:
        """Resolve and execute the configured pipeline fallback."""
        self.metrics.record_fallback()
        if callable(self._fallback):
            try:
                return self._fallback(exc)
            except TypeError:
                return self._fallback()
        return self._fallback

    def execute(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute callable through the configured resilience pipeline layers."""
        start_time = time.monotonic()

        # Build execution pipeline from inside out
        # Inner core: rate limiter and target function
        def run_target() -> Any:
            if self._rate_limiter is not None:
                try:
                    return self._rate_limiter.execute(fn, *args, **kwargs)
                except RateLimitExceededError:
                    self.metrics.record_rate_limit_rejection()
                    raise
            return fn(*args, **kwargs)

        # Layer 1: Bulkhead concurrency isolation
        def run_bulkhead() -> Any:
            if self._bulkhead is not None:
                try:
                    return self._bulkhead.execute(run_target)
                except BulkheadFullError:
                    self.metrics.record_bulkhead_rejection()
                    raise
            return run_target()

        # Layer 2: Timeout guard
        def run_timeout() -> Any:
            if self._timeout_guard is not None:
                try:
                    return self._timeout_guard.execute(run_bulkhead)
                except ExecutionTimeoutError:
                    self.metrics.record_timeout()
                    raise
            return run_bulkhead()

        # Layer 3: Circuit Breaker
        def run_circuit_breaker() -> Any:
            if self._circuit_breaker is not None:
                try:
                    return self._circuit_breaker.execute(run_timeout)
                except CircuitOpenError:
                    self.metrics.record_circuit_rejection()
                    raise
            return run_timeout()

        # Layer 4: Retry Policy
        def run_retry() -> Any:
            if self._retry_policy is not None:
                return self._retry_policy.execute(run_circuit_breaker)
            return run_circuit_breaker()

        # Outer execution and Fallback handling
        try:
            result = run_retry()
            duration = time.monotonic() - start_time
            self.metrics.record_success(duration)
            return result
        except BaseException as exc:
            duration = time.monotonic() - start_time
            self.metrics.record_failure(duration, exc)

            if self._fallback is not None:
                return self._resolve_fallback(exc)
            raise

    def execute_with_result(
        self, fn: Callable[..., Any], *args: Any, **kwargs: Any
    ) -> ExecutionResult:
        """Execute callable and wrap outcome into an ExecutionResult dataclass."""
        start_time = time.monotonic()
        try:
            value = self.execute(fn, *args, **kwargs)
            duration = time.monotonic() - start_time
            cb_state = self._circuit_breaker.state if self._circuit_breaker else None
            return ExecutionResult(
                success=True,
                value=value,
                duration_seconds=duration,
                circuit_state=cb_state,
            )
        except BaseException as exc:
            duration = time.monotonic() - start_time
            cb_state = self._circuit_breaker.state if self._circuit_breaker else None
            return ExecutionResult(
                success=False,
                error=exc,
                duration_seconds=duration,
                circuit_state=cb_state,
            )

    def get_metrics(self) -> Dict[str, Any]:
        """Get snapshot of pipeline telemetry and circuit breaker stats."""
        stats = self.metrics.snapshot()
        stats["pipeline_name"] = self.name
        if self._circuit_breaker:
            stats["circuit_breaker"] = self._circuit_breaker.get_stats().to_dict()
        return stats

    def __call__(self, fn: Callable[..., Any]) -> Callable[..., Any]:
        """Decorator applying the pipeline to a function."""

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return self.execute(fn, *args, **kwargs)

        wrapper.pipeline = self  # type: ignore[attr-defined]
        return wrapper
