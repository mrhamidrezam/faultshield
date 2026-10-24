"""FaultShield Types and Enums.

Provides core data structures, type aliases, and enumerations used across
resilience components.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, Optional, Tuple, Type, Union


class CircuitState(str, Enum):
    """States of a Circuit Breaker."""

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class JitterStrategy(str, Enum):
    """Backoff jitter algorithms for retries."""

    NONE = "NONE"
    FULL = "FULL"
    EQUAL = "EQUAL"
    DECORRELATED = "DECORRELATED"


# Type aliases
ExceptionTypes = Union[Type[BaseException], Tuple[Type[BaseException], ...]]
RetryPredicate = Callable[[BaseException], bool]
FallbackCallable = Callable[..., Any]
StateChangeCallback = Callable[[str, CircuitState, CircuitState, str], None]
RetryCallback = Callable[[int, float, BaseException], None]


@dataclass(frozen=True)
class CircuitBreakerStats:
    """Snapshot of circuit breaker telemetry and sliding window metrics."""

    name: str
    state: CircuitState
    total_calls: int
    successful_calls: int
    failed_calls: int
    slow_calls: int
    failure_rate: float
    slow_call_rate: float
    consecutive_successes: int
    consecutive_failures: int
    time_in_state_seconds: float

    def to_dict(self) -> Dict[str, Any]:
        """Convert snapshot metrics to a dictionary."""
        return {
            "name": self.name,
            "state": self.state.value,
            "total_calls": self.total_calls,
            "successful_calls": self.successful_calls,
            "failed_calls": self.failed_calls,
            "slow_calls": self.slow_calls,
            "failure_rate_pct": round(self.failure_rate, 2),
            "slow_call_rate_pct": round(self.slow_call_rate, 2),
            "consecutive_successes": self.consecutive_successes,
            "consecutive_failures": self.consecutive_failures,
            "time_in_state_seconds": round(self.time_in_state_seconds, 3),
        }


@dataclass
class ExecutionResult:
    """Detailed summary of a protected operation invocation."""

    success: bool
    value: Any = None
    error: Optional[BaseException] = None
    duration_seconds: float = 0.0
    attempts: int = 1
    circuit_state: Optional[CircuitState] = None
    fallback_used: bool = False
