# FaultShield

<p align="center">
  <strong>Lightweight, zero-dependency resilience and fault-tolerance toolkit for Python.</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.9+-blue.svg" alt="Python 3.9+">
  <img src="https://img.shields.io/badge/dependencies-zero-brightgreen.svg" alt="Zero Dependencies">
  <img src="https://img.shields.io/badge/tests-53%20passed-success.svg" alt="Tests Passed">
  <img src="https://img.shields.io/badge/license-MIT-purple.svg" alt="License: MIT">
</p>

---

## Overview

Modern distributed systems, microservices, cloud APIs, and background job runners inevitably experience network blips, cascading failures, downstream rate limits, and transient latency spikes.

**`faultshield`** provides production-grade resilience primitives in **pure standard library Python** with zero external dependencies. It brings the power of enterprise resilience patterns (like Polly and Resilience4j) to Python applications with clean decorators, context managers, and a fluent pipeline API.

### Core Capabilities

- **Zero External Dependencies**: Pure Python 3.9+ standard library.
- **Circuit Breaker**: Full state machine (`CLOSED`, `OPEN`, `HALF_OPEN`) with sliding window failure rate evaluation, slow call detection, and automatic recovery.
- **Adaptive Retries with Jitter**: Exponential backoff with `Full`, `Equal`, and `Decorrelated` jitter algorithms to prevent thundering herds.
- **Token Bucket Rate Limiting**: Traffic shaping and quota enforcement with burst tolerance and thread-safe token replenishment.
- **Bulkhead Concurrency Isolation**: Isolate worker pools, limit simultaneous in-flight operations, and protect critical downstream resources.
- **Execution Timeout Guard**: Enforce strict execution time bounds on operations without hanging worker threads.
- **Fallback Strategies**: Graceful degradation to default values or cached responses on failures.
- **Fluent Resilience Pipeline**: Combine all policies into a single cohesive execution chain with integrated telemetry.
- **Embedded Telemetry & Metrics**: Real-time tracking of success rates, retry counts, circuit trips, rejections, and latency percentiles (p50, p90, p99).

---

## Quickstart

### 1. Circuit Breaker

Protect unreliable external APIs with fast failure and automatic recovery:

```python
from faultshield import CircuitBreaker, CircuitOpenError

# Trip circuit when failure rate reaches 50% across 10 calls; cooldown for 30s
breaker = CircuitBreaker(
    name="payment_gateway",
    failure_rate_threshold=50.0,
    recovery_timeout=30.0,
    sliding_window_size=10,
    minimum_number_of_calls=5,
    fallback=lambda exc: {"status": "degraded", "cached": True},
)

@breaker
def charge_card(account_id: str, amount: float):
    # Remote call that may raise ConnectionError
    return api_client.charge(account_id, amount)

# Or invoke directly:
result = breaker.execute(charge_card, "acc_123", 49.99)
```

### 2. Adaptive Retries with Full Jitter

```python
from faultshield import RetryPolicy, JitterStrategy

policy = RetryPolicy(
    max_attempts=3,
    initial_delay=0.1,
    max_delay=5.0,
    backoff_factor=2.0,
    jitter=JitterStrategy.FULL,
    retry_on=(ConnectionError, TimeoutError),
)

@policy
def query_database():
    return db.query("SELECT * FROM items")
```

### 3. Fluent Resilience Pipeline

Combine Retries, Circuit Breaker, Timeout, Bulkhead, and Rate Limiter into a single pipeline:

```python
from faultshield import ResiliencePipeline, JitterStrategy

pipeline = (
    ResiliencePipeline("customer_api")
    .add_fallback(lambda exc: {"status": "fallback", "data": []})
    .add_retry(max_attempts=3, initial_delay=0.05, jitter=JitterStrategy.FULL)
    .add_circuit_breaker(failure_rate_threshold=50.0, recovery_timeout=15.0)
    .add_timeout(seconds=2.0)
    .add_bulkhead(max_concurrent=10)
    .add_rate_limiter(rate=50.0, capacity=100.0)
)

@pipeline
def get_customer(customer_id: int):
    return http_get(f"/customers/{customer_id}")

# Access runtime telemetry
metrics = pipeline.get_metrics()
print(f"Success rate: {metrics['success_rate_pct']}% | Retries: {metrics['retries']}")
```

### 4. Bulkhead & Rate Limiting

```python
from faultshield import Bulkhead, RateLimiter

limiter = RateLimiter(rate=10.0, capacity=20.0)
bulkhead = Bulkhead(max_concurrent=5, max_queued=10, queue_timeout=1.0)

with limiter:
    with bulkhead:
        # Protected critical section
        do_heavy_work()
```

---

## CLI & Benchmarking

FaultShield includes a command-line tool for stress testing and interactive demonstrations:

```bash
# Run comparative benchmark: Unprotected vs FaultShield protected
faultshield benchmark -n 100 -f 0.4

# Run interactive circuit breaker state walkthrough
faultshield demo
```

Sample Benchmark Output:
```text
====================================================================
BENCHMARK COMPARISON RESULTS
--------------------------------------------------------------------
Metric                           | Unprotected     | FaultShield Protected
--------------------------------------------------------------------
Successful Invocations           | 58              | 58             
Uncaught Crash / Exceptions      | 42              | 0              
Rescued by Fallback              | N/A             | 42             
Retries Executed                 | 0               | 26             
Total Elapsed Time               | 0.0028s         | 0.0412s        
--------------------------------------------------------------------
Reliability Gain: Unprotected 58.0% -> Protected 100% availability
====================================================================
```

---

## Architecture & Deep Dive

For mathematical formulations of the jitter algorithms, token bucket equations, and state machine transitions, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

For installation and developer setup instructions, see [docs/SETUP.md](docs/SETUP.md).

---

## License

This project is licensed under the [MIT License](LICENSE).
