"""Unit tests for faultshield.cli."""

import pytest

from faultshield.cli import build_parser, main, run_benchmark, run_demo


def test_cli_parser_defaults():
    parser = build_parser()
    args = parser.parse_args(["benchmark", "-n", "10", "-f", "0.2"])
    assert args.command == "benchmark"
    assert args.iterations == 10
    assert args.failure_rate == 0.2


def test_cli_benchmark_execution(capsys):
    ret = run_benchmark(iterations=10, failure_rate=0.3)
    assert ret == 0
    captured = capsys.readouterr()
    assert "BENCHMARK COMPARISON RESULTS" in captured.out
    assert "FaultShield Protected" in captured.out


def test_cli_demo_execution(capsys):
    ret = run_demo()
    assert ret == 0
    captured = capsys.readouterr()
    assert "Circuit Breaker State Transition Walkthrough" in captured.out
    assert "Phase 1: Healthy calls" in captured.out
    assert "Circuit Breaker state successfully restored to CLOSED." in captured.out


def test_cli_main_help(capsys):
    ret = main([])
    assert ret == 0
    captured = capsys.readouterr()
    assert "usage:" in captured.out or "FaultShield" in captured.out


def test_cli_main_benchmark():
    ret = main(["benchmark", "-n", "5", "-f", "0.1"])
    assert ret == 0
