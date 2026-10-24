# FaultShield Setup & Installation Guide

This guide covers setup, installation, development workflows, and testing for **FaultShield**.

---

## 1. Requirements

- **Python**: 3.9, 3.10, 3.11, 3.12, 3.13, or 3.14+
- **Zero External Runtime Dependencies**: Standard library only.

---

## 2. Installation

### From Source (Editable / Development Mode)

Clone the repository and install with development dependencies:

```bash
git clone https://github.com/mrhamidrezam/faultshield.git
cd faultshield
pip install -e ".[dev]"
```

### Standard Installation

```bash
pip install .
```

---

## 3. Running the Test Suite

Verify all unit tests and telemetry metrics using pytest:

```bash
pytest -v
```

Expected output:
```text
============================= 53 passed in 1.47s ==============================
```

---

## 4. Running the Examples

FaultShield includes self-contained examples demonstrating each resilience pattern:

```bash
# 1. Basic Circuit Breaker with transitions
python examples/basic_circuit_breaker.py

# 2. End-to-end Resilience Pipeline
python examples/resilience_pipeline.py

# 3. Rate Limiter and Bulkhead isolation
python examples/rate_limiting_bulkhead.py
```

---

## 5. Using the Command Line Interface (CLI)

FaultShield ships with a built-in CLI utility for benchmarking and interactive demonstrations:

```bash
# Display CLI help
faultshield --help

# Run resilience benchmark comparing unprotected vs protected execution
faultshield benchmark -n 100 -f 0.4

# Run circuit breaker state walkthrough
faultshield demo
```
