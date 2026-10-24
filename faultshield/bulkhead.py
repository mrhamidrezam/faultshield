"""FaultShield Bulkhead.

Provides concurrency isolation to prevent resource exhaustion from slow
or unresponsive downstream dependencies.
"""

import functools
import threading
import time
from typing import Any, Callable

from faultshield.exceptions import BulkheadFullError, ResilienceConfigurationError


class Bulkhead:
    """Thread-safe Bulkhead concurrency limiter with optional waiting queue."""

    def __init__(
        self,
        max_concurrent: int = 10,
        max_queued: int = 0,
        queue_timeout: float = 0.0,
    ) -> None:
        if max_concurrent < 1:
            raise ResilienceConfigurationError(f"max_concurrent must be >= 1, got {max_concurrent}")
        if max_queued < 0:
            raise ResilienceConfigurationError(f"max_queued must be non-negative, got {max_queued}")
        if queue_timeout < 0.0:
            raise ResilienceConfigurationError(
                f"queue_timeout must be non-negative, got {queue_timeout}"
            )

        self.max_concurrent = max_concurrent
        self.max_queued = max_queued
        self.queue_timeout = queue_timeout

        self._active_calls = 0
        self._queued_calls = 0
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)

    @property
    def active_calls(self) -> int:
        """Current number of concurrently executing operations."""
        with self._lock:
            return self._active_calls

    @property
    def queued_calls(self) -> int:
        """Current number of callers waiting in queue for execution."""
        with self._lock:
            return self._queued_calls

    def acquire(self) -> None:
        """Acquire an execution slot in the bulkhead.

        Raises BulkheadFullError if execution capacity and queue are saturated,
        or if queue timeout is exceeded.
        """
        with self._cond:
            # Immediate slot available
            if self._active_calls < self.max_concurrent:
                self._active_calls += 1
                return

            # Check if queue has capacity
            if self._queued_calls >= self.max_queued:
                raise BulkheadFullError(self.max_concurrent, self._queued_calls)

            # Wait in queue
            self._queued_calls += 1
            start_time = time.monotonic()
            try:
                while self._active_calls >= self.max_concurrent:
                    remaining_timeout = self.queue_timeout - (time.monotonic() - start_time)
                    if self.queue_timeout > 0 and remaining_timeout <= 0:
                        raise BulkheadFullError(
                            self.max_concurrent,
                            self._queued_calls,
                            message=f"Bulkhead queue wait timeout ({self.queue_timeout}s) exceeded.",
                        )

                    timeout = None if self.queue_timeout <= 0 else remaining_timeout
                    notified = self._cond.wait(timeout=timeout)
                    if not notified and self.queue_timeout > 0:
                        raise BulkheadFullError(
                            self.max_concurrent,
                            self._queued_calls,
                            message=f"Bulkhead queue wait timeout ({self.queue_timeout}s) exceeded.",
                        )

                self._active_calls += 1
            finally:
                self._queued_calls -= 1

    def release(self) -> None:
        """Release execution slot and wake up next waiting caller."""
        with self._cond:
            self._active_calls = max(0, self._active_calls - 1)
            self._cond.notify()

    def execute(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute callable within the bulkhead isolation barrier."""
        self.acquire()
        try:
            return fn(*args, **kwargs)
        finally:
            self.release()

    def __enter__(self) -> "Bulkhead":
        """Context manager entry."""
        self.acquire()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        self.release()

    def __call__(self, fn: Callable[..., Any]) -> Callable[..., Any]:
        """Decorator for bulkhead concurrency isolation."""

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return self.execute(fn, *args, **kwargs)

        wrapper.bulkhead = self  # type: ignore[attr-defined]
        return wrapper
