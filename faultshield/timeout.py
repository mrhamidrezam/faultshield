"""FaultShield Timeout Guard.

Provides execution time bounding to prevent operations from blocking indefinitely.
"""

from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
import functools
import threading
from typing import Any, Callable

from faultshield.exceptions import ExecutionTimeoutError, ResilienceConfigurationError


class TimeoutGuard:
    """Enforces execution timeouts on synchronous callables using worker threads."""

    def __init__(self, seconds: float) -> None:
        if seconds <= 0.0:
            raise ResilienceConfigurationError(f"Timeout seconds must be positive, got {seconds}")
        self.seconds = float(seconds)

    def execute(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute a callable with strict timeout enforcement.

        Raises ExecutionTimeoutError if function does not complete within `seconds`.
        """
        result_holder = []
        exception_holder = []
        done_event = threading.Event()

        def worker() -> None:
            try:
                res = fn(*args, **kwargs)
                result_holder.append(res)
            except BaseException as exc:
                exception_holder.append(exc)
            finally:
                done_event.set()

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        completed = done_event.wait(timeout=self.seconds)
        if not completed:
            raise ExecutionTimeoutError(self.seconds)

        if exception_holder:
            raise exception_holder[0]

        return result_holder[0] if result_holder else None

    def __call__(self, fn: Callable[..., Any]) -> Callable[..., Any]:
        """Decorator for timeout protection."""

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return self.execute(fn, *args, **kwargs)

        wrapper.timeout_guard = self  # type: ignore[attr-defined]
        return wrapper
