"""FaultShield Exceptions.

Defines the hierarchy of exceptions raised by FaultShield resilience components.
"""

from typing import Optional


class FaultShieldError(Exception):
    """Base exception for all FaultShield errors."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class CircuitOpenError(FaultShieldError):
    """Raised when a circuit breaker rejects an invocation because the circuit is open."""

    def __init__(
        self,
        circuit_name: str,
        recovery_time_remaining: float,
        message: Optional[str] = None,
    ) -> None:
        self.circuit_name = circuit_name
        self.recovery_time_remaining = max(0.0, recovery_time_remaining)
        default_msg = (
            f"Circuit breaker '{circuit_name}' is OPEN. "
            f"Execution rejected. Recovery in {self.recovery_time_remaining:.2f}s."
        )
        super().__init__(message or default_msg)


class MaxRetriesExceededError(FaultShieldError):
    """Raised when an operation fails after exhausting all configured retry attempts."""

    def __init__(
        self,
        attempts: int,
        last_exception: Optional[BaseException] = None,
        message: Optional[str] = None,
    ) -> None:
        self.attempts = attempts
        self.last_exception = last_exception
        default_msg = f"Operation failed after {attempts} attempts. Last exception: {last_exception}"
        super().__init__(message or default_msg)


class RateLimitExceededError(FaultShieldError):
    """Raised when an operation cannot be executed due to rate limit constraints."""

    def __init__(
        self,
        retry_after: float = 0.0,
        message: Optional[str] = None,
    ) -> None:
        self.retry_after = max(0.0, retry_after)
        default_msg = (
            f"Rate limit exceeded. Available in {self.retry_after:.3f}s."
            if self.retry_after > 0
            else "Rate limit exceeded."
        )
        super().__init__(message or default_msg)


class BulkheadFullError(FaultShieldError):
    """Raised when bulkhead concurrent execution capacity and queue are fully saturated."""

    def __init__(
        self,
        max_concurrent: int,
        queued_count: int,
        message: Optional[str] = None,
    ) -> None:
        self.max_concurrent = max_concurrent
        self.queued_count = queued_count
        default_msg = (
            f"Bulkhead execution capacity ({max_concurrent}) and queue ({queued_count}) are saturated."
        )
        super().__init__(message or default_msg)


class ExecutionTimeoutError(FaultShieldError):
    """Raised when an operation execution exceeds the configured timeout threshold."""

    def __init__(
        self,
        timeout_seconds: float,
        message: Optional[str] = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        default_msg = f"Operation timed out after {timeout_seconds:.2f} seconds."
        super().__init__(message or default_msg)


class ResilienceConfigurationError(FaultShieldError):
    """Raised when resilience policy parameters or thresholds are invalid."""
