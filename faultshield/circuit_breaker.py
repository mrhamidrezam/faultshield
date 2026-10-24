"""FaultShield Circuit Breaker.

Provides state-machine based protection against cascading failures in distributed
systems and unreliable external dependencies.
"""

from collections import deque
import functools
import threading
import time
from typing import Any, Callable, Deque, Optional, Tuple, Type, Union

from faultshield.exceptions import CircuitOpenError, ResilienceConfigurationError
from faultshield.types import (
    CircuitBreakerStats,
    CircuitState,
    ExceptionTypes,
    FallbackCallable,
    StateChangeCallback,
)


class CircuitBreaker:
    """Production-grade, thread-safe Circuit Breaker.

    Transitions through three states:
      - CLOSED: Invocations flow normally; failures and latencies are tracked in a sliding window.
      - OPEN: Invocations are fast-failed immediately without invoking the target function.
      - HALF_OPEN: After recovery_timeout, a limited trial of calls is allowed to evaluate recovery.
    """

    def __init__(
        self,
        name: str = "default",
        failure_rate_threshold: float = 50.0,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 3,
        sliding_window_size: int = 20,
        minimum_number_of_calls: int = 5,
        slow_call_duration_threshold: Optional[float] = None,
        slow_call_rate_threshold: float = 100.0,
        expected_exceptions: ExceptionTypes = (Exception,),
        ignore_exceptions: Optional[ExceptionTypes] = None,
        fallback: Optional[Union[FallbackCallable, Any]] = None,
        on_state_change: Optional[StateChangeCallback] = None,
    ) -> None:
        if failure_rate_threshold <= 0.0 or failure_rate_threshold > 100.0:
            raise ResilienceConfigurationError(
                f"failure_rate_threshold must be in (0, 100], got {failure_rate_threshold}"
            )
        if recovery_timeout < 0.0:
            raise ResilienceConfigurationError(
                f"recovery_timeout must be non-negative, got {recovery_timeout}"
            )
        if half_open_max_calls < 1:
            raise ResilienceConfigurationError(
                f"half_open_max_calls must be >= 1, got {half_open_max_calls}"
            )
        if sliding_window_size < 1:
            raise ResilienceConfigurationError(
                f"sliding_window_size must be >= 1, got {sliding_window_size}"
            )
        if minimum_number_of_calls < 1:
            raise ResilienceConfigurationError(
                f"minimum_number_of_calls must be >= 1, got {minimum_number_of_calls}"
            )

        self.name = name
        self.failure_rate_threshold = failure_rate_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self.sliding_window_size = sliding_window_size
        self.minimum_number_of_calls = minimum_number_of_calls
        self.slow_call_duration_threshold = slow_call_duration_threshold
        self.slow_call_rate_threshold = slow_call_rate_threshold

        self.expected_exceptions: Tuple[Type[BaseException], ...] = (
            expected_exceptions
            if isinstance(expected_exceptions, tuple)
            else (expected_exceptions,)
        )
        self.ignore_exceptions: Tuple[Type[BaseException], ...] = (
            ()
            if ignore_exceptions is None
            else (
                ignore_exceptions
                if isinstance(ignore_exceptions, tuple)
                else (ignore_exceptions,)
            )
        )
        self.fallback = fallback
        self.on_state_change = on_state_change

        self._lock = threading.RLock()
        self._state = CircuitState.CLOSED
        self._last_state_change_time = time.monotonic()
        self._half_open_calls_in_flight = 0
        self._half_open_successes = 0

        # Ring buffer storing (success: bool, is_slow: bool)
        self._window: Deque[Tuple[bool, bool]] = deque(maxlen=sliding_window_size)
        self._lifetime_total_calls = 0
        self._lifetime_successful_calls = 0
        self._lifetime_failed_calls = 0
        self._consecutive_successes = 0
        self._consecutive_failures = 0

    @property
    def state(self) -> CircuitState:
        """Current state with automatic time-based transition check."""
        with self._lock:
            if self._state == CircuitState.OPEN:
                elapsed = time.monotonic() - self._last_state_change_time
                if elapsed >= self.recovery_timeout:
                    self._transition_to(
                        CircuitState.HALF_OPEN,
                        f"Recovery timeout ({self.recovery_timeout}s) elapsed",
                    )
            return self._state

    def _transition_to(self, new_state: CircuitState, reason: str) -> None:
        """Internal transition handler with listener dispatch."""
        old_state = self._state
        if old_state == new_state:
            return

        self._state = new_state
        self._last_state_change_time = time.monotonic()
        if new_state == CircuitState.HALF_OPEN:
            self._half_open_calls_in_flight = 0
            self._half_open_successes = 0
        elif new_state == CircuitState.CLOSED:
            self._window.clear()
            self._half_open_calls_in_flight = 0
            self._half_open_successes = 0

        if self.on_state_change:
            try:
                self.on_state_change(self.name, old_state, new_state, reason)
            except Exception:
                pass  # Do not let callback failures break circuit breaker operation

    def trip(self, reason: str = "Manual trip") -> None:
        """Manually force the circuit breaker into OPEN state."""
        with self._lock:
            self._transition_to(CircuitState.OPEN, reason)

    def reset(self) -> None:
        """Manually reset the circuit breaker into CLOSED state."""
        with self._lock:
            self._transition_to(CircuitState.CLOSED, "Manual reset")

    def _execute_fallback(
        self,
        exc: Optional[BaseException],
        fn: Optional[Callable[..., Any]],
        args: tuple,
        kwargs: dict,
    ) -> Any:
        """Resolve and execute the configured fallback callable or value."""
        if self.fallback is None:
            raise exc or CircuitOpenError(self.name, self._get_recovery_time_remaining())

        if callable(self.fallback):
            # Try passing exception if fallback accepts it, otherwise call without args
            try:
                return self.fallback(exc)
            except TypeError:
                return self.fallback()
        return self.fallback

    def _get_recovery_time_remaining(self) -> float:
        """Seconds remaining before breaker enters HALF_OPEN."""
        with self._lock:
            if self._state != CircuitState.OPEN:
                return 0.0
            elapsed = time.monotonic() - self._last_state_change_time
            return max(0.0, self.recovery_timeout - elapsed)

    def _before_call(self) -> None:
        """Pre-invocation check. Raises CircuitOpenError if calls cannot proceed."""
        with self._lock:
            curr_state = self.state  # evaluates OPEN -> HALF_OPEN timeout
            if curr_state == CircuitState.OPEN:
                remaining = self._get_recovery_time_remaining()
                raise CircuitOpenError(self.name, remaining)

            if curr_state == CircuitState.HALF_OPEN:
                if (
                    self._half_open_calls_in_flight + self._half_open_successes
                    >= self.half_open_max_calls
                ):
                    raise CircuitOpenError(
                        self.name,
                        0.0,
                        f"Circuit breaker '{self.name}' is HALF_OPEN and trial capacity is full.",
                    )
                self._half_open_calls_in_flight += 1

    def _record_success(self, duration: float) -> None:
        """Record successful call completion."""
        with self._lock:
            self._lifetime_total_calls += 1
            self._lifetime_successful_calls += 1
            self._consecutive_successes += 1
            self._consecutive_failures = 0

            is_slow = (
                self.slow_call_duration_threshold is not None
                and duration > self.slow_call_duration_threshold
            )

            if self._state == CircuitState.HALF_OPEN:
                self._half_open_calls_in_flight = max(0, self._half_open_calls_in_flight - 1)
                self._half_open_successes += 1
                if self._half_open_successes >= self.half_open_max_calls:
                    self._transition_to(
                        CircuitState.CLOSED,
                        f"Trial passed: {self._half_open_successes} successful calls in HALF_OPEN",
                    )
            elif self._state == CircuitState.CLOSED:
                self._window.append((True, is_slow))
                self._evaluate_closed_state()

    def _record_failure(self, exc: BaseException, duration: float) -> None:
        """Record failed call completion."""
        with self._lock:
            self._lifetime_total_calls += 1
            self._lifetime_failed_calls += 1
            self._consecutive_failures += 1
            self._consecutive_successes = 0

            is_slow = (
                self.slow_call_duration_threshold is not None
                and duration > self.slow_call_duration_threshold
            )

            if self._state == CircuitState.HALF_OPEN:
                self._half_open_calls_in_flight = max(0, self._half_open_calls_in_flight - 1)
                self._transition_to(
                    CircuitState.OPEN,
                    f"Trial failed in HALF_OPEN due to {type(exc).__name__}: {exc}",
                )
            elif self._state == CircuitState.CLOSED:
                self._window.append((False, is_slow))
                self._evaluate_closed_state()

    def _evaluate_closed_state(self) -> None:
        """Evaluate sliding window metrics to see if breaker should trip to OPEN."""
        if len(self._window) < self.minimum_number_of_calls:
            return

        total = len(self._window)
        failures = sum(1 for success, _ in self._window if not success)
        slow_calls = sum(1 for _, is_slow in self._window if is_slow)

        failure_rate = (failures / total) * 100.0
        slow_call_rate = (slow_calls / total) * 100.0

        if failure_rate >= self.failure_rate_threshold:
            self._transition_to(
                CircuitState.OPEN,
                f"Failure rate {failure_rate:.1f}% exceeded threshold {self.failure_rate_threshold:.1f}%",
            )
        elif (
            self.slow_call_duration_threshold is not None
            and slow_call_rate >= self.slow_call_rate_threshold
        ):
            self._transition_to(
                CircuitState.OPEN,
                f"Slow call rate {slow_call_rate:.1f}% exceeded threshold {self.slow_call_rate_threshold:.1f}%",
            )

    def execute(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute a callable protected by this circuit breaker."""
        try:
            self._before_call()
        except CircuitOpenError as open_err:
            if self.fallback is not None:
                return self._execute_fallback(open_err, fn, args, kwargs)
            raise

        start_time = time.monotonic()
        try:
            result = fn(*args, **kwargs)
            duration = time.monotonic() - start_time
            self._record_success(duration)
            return result
        except BaseException as exc:
            duration = time.monotonic() - start_time
            # Ignore ignored exceptions
            if self.ignore_exceptions and isinstance(exc, self.ignore_exceptions):
                raise

            # Count as failure if matches expected exceptions
            if isinstance(exc, self.expected_exceptions):
                self._record_failure(exc, duration)
                if self.fallback is not None:
                    return self._execute_fallback(exc, fn, args, kwargs)
            raise

    def __call__(self, fn: Callable[..., Any]) -> Callable[..., Any]:
        """Decorator for protecting a function with this circuit breaker."""

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return self.execute(fn, *args, **kwargs)

        wrapper.circuit_breaker = self  # type: ignore[attr-defined]
        return wrapper

    def get_stats(self) -> CircuitBreakerStats:
        """Snapshot current circuit breaker metrics."""
        with self._lock:
            total_window = len(self._window)
            if total_window > 0:
                fails = sum(1 for success, _ in self._window if not success)
                slows = sum(1 for _, is_slow in self._window if is_slow)
                fail_pct = (fails / total_window) * 100.0
                slow_pct = (slows / total_window) * 100.0
            else:
                fail_pct = 0.0
                slow_pct = 0.0

            time_in_state = time.monotonic() - self._last_state_change_time

            return CircuitBreakerStats(
                name=self.name,
                state=self._state,
                total_calls=self._lifetime_total_calls,
                successful_calls=self._lifetime_successful_calls,
                failed_calls=self._lifetime_failed_calls,
                slow_calls=sum(1 for _, s in self._window if s),
                failure_rate=fail_pct,
                slow_call_rate=slow_pct,
                consecutive_successes=self._consecutive_successes,
                consecutive_failures=self._consecutive_failures,
                time_in_state_seconds=time_in_state,
            )
