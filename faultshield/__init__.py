"""FaultShield: Zero-dependency resilience & fault-tolerance toolkit for Python.

Provides production-ready Circuit Breakers, Retry Policies with backoff and jitter,
Token Bucket Rate Limiters, Bulkhead concurrency isolation, Execution Timeouts,
Fallback strategies, and fluent Policy Pipelines with telemetry metrics.
"""

from faultshield.bulkhead import Bulkhead
from faultshield.circuit_breaker import CircuitBreaker
from faultshield.exceptions import (
    BulkheadFullError,
    CircuitOpenError,
    ExecutionTimeoutError,
    FaultShieldError,
    MaxRetriesExceededError,
    RateLimitExceededError,
    ResilienceConfigurationError,
)
from faultshield.metrics import ResilienceMetrics
from faultshield.pipeline import ResiliencePipeline
from faultshield.rate_limiter import RateLimiter
from faultshield.retry import RetryPolicy
from faultshield.timeout import TimeoutGuard
from faultshield.types import (
    CircuitBreakerStats,
    CircuitState,
    ExecutionResult,
    JitterStrategy,
)

__version__ = "0.1.0"
__author__ = "Hamidreza"
__email__ = "h4midrezam@gmail.com"

__all__ = [
    # Core Components
    "CircuitBreaker",
    "RetryPolicy",
    "RateLimiter",
    "Bulkhead",
    "TimeoutGuard",
    "ResiliencePipeline",
    "ResilienceMetrics",
    # Types & Enums
    "CircuitState",
    "JitterStrategy",
    "CircuitBreakerStats",
    "ExecutionResult",
    # Exceptions
    "FaultShieldError",
    "CircuitOpenError",
    "MaxRetriesExceededError",
    "RateLimitExceededError",
    "BulkheadFullError",
    "ExecutionTimeoutError",
    "ResilienceConfigurationError",
    # Metadata
    "__version__",
    "__author__",
    "__email__",
]
