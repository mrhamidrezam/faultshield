"""Example: Comprehensive Resilience Pipeline."""

import os
import random
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from faultshield import JitterStrategy, ResiliencePipeline


pipeline = (
    ResiliencePipeline("user_service")
    .add_fallback(lambda exc: {"id": -1, "status": "cached_fallback", "name": "Guest"})
    .add_retry(
        max_attempts=3,
        initial_delay=0.05,
        max_delay=1.0,
        backoff_factor=2.0,
        jitter=JitterStrategy.FULL,
    )
    .add_circuit_breaker(
        failure_rate_threshold=50.0,
        recovery_timeout=2.0,
        sliding_window_size=10,
        minimum_number_of_calls=4,
    )
    .add_timeout(seconds=1.5)
    .add_bulkhead(max_concurrent=5)
    .add_rate_limiter(rate=20.0, capacity=30.0)
)


@pipeline
def fetch_user_profile(user_id: int):
    # Simulate intermittent network failures
    if random.random() < 0.4:
        raise ConnectionError(f"Temporary database timeout for user {user_id}")
    return {"id": user_id, "status": "active", "name": f"User_{user_id}"}


if __name__ == "__main__":
    print("Testing FaultShield Resilience Pipeline under simulated flakiness:")
    for i in range(15):
        profile = fetch_user_profile(i)
        print(f"Request {i+1:02d}:", profile)

    print("\nPipeline Metrics Telemetry:")
    metrics = pipeline.get_metrics()
    for key, value in metrics.items():
        if key != "circuit_breaker":
            print(f"  {key}: {value}")
