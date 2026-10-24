"""Example: Basic Circuit Breaker usage."""

import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from faultshield import CircuitBreaker, CircuitOpenError, CircuitState


def on_state_transition(name: str, old_state: CircuitState, new_state: CircuitState, reason: str):
    print(f"[*] State transition on '{name}': {old_state.value} -> {new_state.value} ({reason})")


cb = CircuitBreaker(
    name="payment_service",
    failure_rate_threshold=50.0,
    recovery_timeout=1.0,
    half_open_max_calls=2,
    minimum_number_of_calls=3,
    on_state_change=on_state_transition,
    fallback=lambda exc: {"status": "degraded", "message": "Service temporarily unavailable"},
)


@cb
def process_payment(account_id: str, amount: float):
    if amount > 1000:
        raise ConnectionResetError("Remote payment gateway timed out")
    return {"status": "success", "account": account_id, "amount": amount}


if __name__ == "__main__":
    print("Executing successful transactions:")
    for i in range(3):
        print(" ", process_payment(f"acc_{i}", 50.0))

    print("\nExecuting failing transactions (tripping breaker):")
    for i in range(3):
        print(" ", process_payment(f"acc_{i}", 5000.0))

    print(f"\nCurrent Circuit Breaker State: {cb.state.value}")
    print("Subsequent fast-failed call with fallback:")
    print(" ", process_payment("acc_test", 20.0))

    print("\nWaiting for recovery timeout (1.0s)...")
    time.sleep(1.1)
    print(f"State after recovery timeout: {cb.state.value}")

    print("Executing trial recovery calls:")
    print(" ", process_payment("acc_recovery_1", 20.0))
    print(" ", process_payment("acc_recovery_2", 20.0))
    print(f"Final Circuit Breaker State: {cb.state.value}")
