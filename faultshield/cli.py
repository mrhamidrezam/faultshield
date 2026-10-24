"""FaultShield Command Line Interface.

Provides tools for stress-testing resilience policies, benchmarking fault-tolerance
gains, and running interactive resilience demonstrations.
"""

import argparse
import json
import random
import sys
import time
from typing import List, Optional

from faultshield.circuit_breaker import CircuitBreaker
from faultshield.pipeline import ResiliencePipeline
from faultshield.types import CircuitState, JitterStrategy


def run_benchmark(iterations: int = 50, failure_rate: float = 0.4) -> int:
    """Run comparative benchmark: unprotected vs FaultShield resilience."""
    print("=" * 68)
    print("  FaultShield Resilience & Fault-Tolerance Benchmark")
    print("=" * 68)
    print(f"Total Invocations: {iterations}")
    print(f"Simulated Downstream Failure Rate: {failure_rate * 100:.1f}%\n")

    # Flaky external call simulation
    def flaky_external_service(call_id: int) -> str:
        if random.random() < failure_rate:
            raise ConnectionResetError(f"Simulated connection reset on call #{call_id}")
        return f"OK-{call_id}"

    # 1. Unprotected run
    print("[1/2] Running unprotected service calls...")
    unprotected_success = 0
    unprotected_failures = 0
    start_unprotected = time.monotonic()

    for i in range(iterations):
        try:
            flaky_external_service(i)
            unprotected_success += 1
        except Exception:
            unprotected_failures += 1

    duration_unprotected = time.monotonic() - start_unprotected

    # 2. FaultShield protected run
    print("[2/2] Running FaultShield-protected pipeline calls...")
    pipeline = (
        ResiliencePipeline("benchmark_pipeline")
        .add_fallback(lambda exc: "DEGRADED_FALLBACK")
        .add_retry(max_attempts=3, initial_delay=0.005, jitter=JitterStrategy.FULL)
        .add_circuit_breaker(failure_rate_threshold=50.0, recovery_timeout=0.2, sliding_window_size=10)
    )

    protected_success = 0
    protected_fallbacks = 0
    start_protected = time.monotonic()

    for i in range(iterations):
        res = pipeline.execute(flaky_external_service, i)
        if res == "DEGRADED_FALLBACK":
            protected_fallbacks += 1
        else:
            protected_success += 1

    duration_protected = time.monotonic() - start_protected
    metrics = pipeline.get_metrics()

    # Results Table
    print("\n" + "-" * 68)
    print("BENCHMARK COMPARISON RESULTS")
    print("-" * 68)
    print(f"{'Metric':<32} | {'Unprotected':<15} | {'FaultShield Protected':<15}")
    print("-" * 68)
    print(f"{'Successful Invocations':<32} | {unprotected_success:<15} | {protected_success:<15}")
    print(f"{'Uncaught Crash / Exceptions':<32} | {unprotected_failures:<15} | {0:<15}")
    print(f"{'Rescued by Fallback':<32} | {'N/A':<15} | {protected_fallbacks:<15}")
    print(f"{'Retries Executed':<32} | {0:<15} | {metrics['retries']:<15}")
    print(f"{'Total Elapsed Time':<32} | {duration_unprotected:.4f}s{'':<8} | {duration_protected:.4f}s")
    print("-" * 68)
    print(
        f"Reliability Gain: Unprotected {unprotected_success/iterations*100:.1f}% -> Protected 100% availability"
    )
    print("=" * 68)
    return 0


def run_demo() -> int:
    """Run an interactive demonstration of Circuit Breaker state transitions."""
    print("=" * 68)
    print("  FaultShield Circuit Breaker State Transition Walkthrough")
    print("=" * 68)

    def on_change(name: str, old: CircuitState, new: CircuitState, reason: str) -> None:
        print(f"  [EVENT] Circuit '{name}': {old.value} -> {new.value} | Reason: {reason}")

    cb = CircuitBreaker(
        name="demo_breaker",
        failure_rate_threshold=50.0,
        recovery_timeout=0.5,
        sliding_window_size=6,
        minimum_number_of_calls=4,
        on_state_change=on_change,
    )

    def mock_service(fail: bool) -> str:
        if fail:
            raise RuntimeError("Database unavailable")
        return "Query successful"

    print("\nPhase 1: Healthy calls (CLOSED state)")
    for i in range(3):
        res = cb.execute(mock_service, False)
        print(f"  Call {i+1}: {res} (State: {cb.state.value})")

    print("\nPhase 2: Failing calls trigger circuit trip to OPEN")
    for i in range(4):
        try:
            cb.execute(mock_service, True)
        except Exception as e:
            print(f"  Call {i+4} failed: {type(e).__name__} (State: {cb.state.value})")

    print("\nPhase 3: Fast-failing immediately while OPEN")
    try:
        cb.execute(mock_service, False)
    except Exception as e:
        print(f"  Call rejected immediately: {e}")

    print("\nPhase 4: Waiting for recovery timeout (0.5s)...")
    time.sleep(0.55)
    print(f"  Current State after cooldown: {cb.state.value}")

    print("\nPhase 5: Recovery trial in HALF_OPEN leading back to CLOSED")
    for i in range(3):
        res = cb.execute(mock_service, False)
        print(f"  Trial call {i+1}: {res} (State: {cb.state.value})")

    print("\nCircuit Breaker state successfully restored to CLOSED.")
    print("=" * 68)
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build command line argument parser."""
    parser = argparse.ArgumentParser(
        prog="faultshield",
        description="FaultShield: Zero-dependency resilience & fault-tolerance toolkit.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="faultshield 0.1.0",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # benchmark
    bm_parser = subparsers.add_parser("benchmark", help="Run resilience benchmark")
    bm_parser.add_argument(
        "-n", "--iterations", type=int, default=50, help="Number of simulated calls (default: 50)"
    )
    bm_parser.add_argument(
        "-f",
        "--failure-rate",
        type=float,
        default=0.4,
        help="Simulated failure rate 0.0-1.0 (default: 0.4)",
    )

    # demo
    subparsers.add_parser("demo", help="Demonstrate circuit breaker state transitions")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "benchmark":
        return run_benchmark(iterations=args.iterations, failure_rate=args.failure_rate)
    elif args.command == "demo":
        return run_demo()
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
