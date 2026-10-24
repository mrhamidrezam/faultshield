"""FaultShield Rate Limiter.

Implements a thread-safe Token Bucket rate limiter for traffic shaping,
concurrency smoothing, and upstream API quota compliance.
"""

import functools
import threading
import time
from typing import Any, Callable, Optional

from faultshield.exceptions import RateLimitExceededError, ResilienceConfigurationError


class RateLimiter:
    """Thread-safe Token Bucket rate limiter.

    Tokens are replenished at `rate` per second up to `capacity`.
    """

    def __init__(
        self,
        rate: float,
        capacity: Optional[float] = None,
        default_timeout: float = 0.0,
    ) -> None:
        if rate <= 0.0:
            raise ResilienceConfigurationError(f"Rate must be positive, got {rate}")

        self.rate = float(rate)
        self.capacity = float(capacity) if capacity is not None else float(rate)
        if self.capacity <= 0.0:
            raise ResilienceConfigurationError(f"Capacity must be positive, got {self.capacity}")

        self.default_timeout = default_timeout
        self._tokens = self.capacity
        self._last_replenish_time = time.monotonic()
        self._lock = threading.Lock()

    @property
    def available_tokens(self) -> float:
        """Current number of available tokens in bucket."""
        with self._lock:
            self._replenish()
            return self._tokens

    def _replenish(self) -> None:
        """Internal replenish logic (must be called with self._lock held)."""
        now = time.monotonic()
        elapsed = now - self._last_replenish_time
        if elapsed > 0:
            added = elapsed * self.rate
            self._tokens = min(self.capacity, self._tokens + added)
            self._last_replenish_time = now

    def acquire(self, tokens: float = 1.0, timeout: Optional[float] = None) -> bool:
        """Acquire specified tokens.

        Args:
            tokens: Number of tokens requested (default: 1.0).
            timeout: Max seconds to wait. None means wait indefinitely; 0.0 is non-blocking.

        Returns:
            True if tokens were acquired, False if timeout expired.
        """
        if tokens <= 0.0:
            return True
        if tokens > self.capacity:
            raise ResilienceConfigurationError(
                f"Requested tokens ({tokens}) exceeds total capacity ({self.capacity})"
            )

        start_time = time.monotonic()
        effective_timeout = self.default_timeout if timeout is None else timeout

        while True:
            with self._lock:
                self._replenish()
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return True

                missing = tokens - self._tokens
                wait_time = missing / self.rate

            # Check if timeout allows waiting
            if effective_timeout is not None:
                elapsed = time.monotonic() - start_time
                if effective_timeout <= 0.0 or elapsed >= effective_timeout:
                    return False
                sleep_duration = min(wait_time, effective_timeout - elapsed)
            else:
                sleep_duration = wait_time

            if sleep_duration > 0:
                time.sleep(sleep_duration)

    def execute(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute callable protected by rate limiter."""
        if not self.acquire(1.0, timeout=self.default_timeout):
            with self._lock:
                self._replenish()
                missing = max(0.0, 1.0 - self._tokens)
                retry_after = missing / self.rate
            raise RateLimitExceededError(retry_after=retry_after)

        return fn(*args, **kwargs)

    def __enter__(self) -> "RateLimiter":
        """Context manager entry."""
        if not self.acquire(1.0, timeout=self.default_timeout):
            with self._lock:
                self._replenish()
                missing = max(0.0, 1.0 - self._tokens)
                retry_after = missing / self.rate
            raise RateLimitExceededError(retry_after=retry_after)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        pass

    def __call__(self, fn: Callable[..., Any]) -> Callable[..., Any]:
        """Decorator for rate limiting a function."""

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return self.execute(fn, *args, **kwargs)

        wrapper.rate_limiter = self  # type: ignore[attr-defined]
        return wrapper
