"""FaultShield Retry Policy.

Provides configurable exponential backoff retry algorithms with full, equal,
and decorrelated jitter strategies.
"""

import functools
import random
import time
from typing import Any, Callable, Optional, Tuple, Type, Union

from faultshield.exceptions import MaxRetriesExceededError, ResilienceConfigurationError
from faultshield.types import (
    ExceptionTypes,
    FallbackCallable,
    JitterStrategy,
    RetryCallback,
    RetryPredicate,
)


class RetryPolicy:
    """Configurable retry execution policy with backoff and jitter algorithms."""

    def __init__(
        self,
        max_attempts: int = 3,
        initial_delay: float = 0.1,
        max_delay: float = 30.0,
        backoff_factor: float = 2.0,
        jitter: Union[JitterStrategy, str] = JitterStrategy.FULL,
        retry_on: ExceptionTypes = (Exception,),
        retry_if: Optional[RetryPredicate] = None,
        fallback: Optional[Union[FallbackCallable, Any]] = None,
        on_retry: Optional[RetryCallback] = None,
    ) -> None:
        if max_attempts < 1:
            raise ResilienceConfigurationError(f"max_attempts must be >= 1, got {max_attempts}")
        if initial_delay < 0.0:
            raise ResilienceConfigurationError(
                f"initial_delay must be non-negative, got {initial_delay}"
            )
        if max_delay < initial_delay:
            raise ResilienceConfigurationError(
                f"max_delay ({max_delay}) must be >= initial_delay ({initial_delay})"
            )
        if backoff_factor < 1.0:
            raise ResilienceConfigurationError(
                f"backoff_factor must be >= 1.0, got {backoff_factor}"
            )

        self.max_attempts = max_attempts
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
        self.jitter = JitterStrategy(jitter) if isinstance(jitter, str) else jitter
        self.retry_on: Tuple[Type[BaseException], ...] = (
            retry_on if isinstance(retry_on, tuple) else (retry_on,)
        )
        self.retry_if = retry_if
        self.fallback = fallback
        self.on_retry = on_retry

    def calculate_delay(self, attempt: int, prev_delay: float) -> float:
        """Calculate sleep delay for the given attempt index (1-based)."""
        raw_backoff = min(
            self.max_delay,
            self.initial_delay * (self.backoff_factor ** (attempt - 1)),
        )

        if self.jitter == JitterStrategy.NONE:
            return raw_backoff
        elif self.jitter == JitterStrategy.FULL:
            return random.uniform(0.0, raw_backoff)
        elif self.jitter == JitterStrategy.EQUAL:
            half = raw_backoff / 2.0
            return half + random.uniform(0.0, half)
        elif self.jitter == JitterStrategy.DECORRELATED:
            ceiling = prev_delay * 3.0 if prev_delay > 0 else self.initial_delay * 3.0
            lower = min(self.initial_delay, ceiling)
            chosen = random.uniform(lower, max(lower, ceiling))
            return min(self.max_delay, chosen)

        return raw_backoff

    def should_retry(self, exc: BaseException) -> bool:
        """Determine whether the encountered exception qualifies for a retry."""
        if not isinstance(exc, self.retry_on):
            return False
        if self.retry_if is not None:
            try:
                return bool(self.retry_if(exc))
            except Exception:
                return False
        return True

    def _execute_fallback(self, exc: BaseException) -> Any:
        """Resolve and return fallback value/callable."""
        if self.fallback is None:
            raise MaxRetriesExceededError(self.max_attempts, last_exception=exc)

        if callable(self.fallback):
            try:
                return self.fallback(exc)
            except TypeError:
                return self.fallback()
        return self.fallback

    def execute(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute callable with retries according to configured policy."""
        attempt = 1
        prev_delay = self.initial_delay

        while True:
            try:
                return fn(*args, **kwargs)
            except BaseException as exc:
                if not self.should_retry(exc):
                    if self.fallback is not None:
                        return self._execute_fallback(exc)
                    raise

                if attempt >= self.max_attempts:
                    if self.fallback is not None:
                        return self._execute_fallback(exc)
                    raise MaxRetriesExceededError(attempt, last_exception=exc) from exc

                delay = self.calculate_delay(attempt, prev_delay)
                prev_delay = delay

                if self.on_retry:
                    try:
                        self.on_retry(attempt, delay, exc)
                    except Exception:
                        pass

                if delay > 0:
                    time.sleep(delay)

                attempt += 1

    def __call__(self, fn: Callable[..., Any]) -> Callable[..., Any]:
        """Decorator for applying retry policy to a function."""

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return self.execute(fn, *args, **kwargs)

        wrapper.retry_policy = self  # type: ignore[attr-defined]
        return wrapper
