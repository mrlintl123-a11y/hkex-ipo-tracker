#!/usr/bin/env python3
"""Portable end-to-end smoke tests for HKEX IPO Tracker."""

import os
import subprocess
import sys
import tempfile


sys.stdout.reconfigure(encoding="utf-8")
SCRIPTS = os.path.dirname(os.path.abspath(__file__))
PYTHON = sys.executable


def run(command, description, input_text=None):
    print(f"  [{description}] ", end="", flush=True)
    result = subprocess.run(
        command,
        input=input_text,
        capture_output=True,
        text=True,
        cwd=SCRIPTS,
        timeout=60,
    )
    passed = result.returncode == 0
    print("PASS" if passed else f"FAIL (exit={result.returncode})")
    if not passed:
        print(f"    stderr: {result.stderr[:500]}")
    return passed


def main():
    print(f"\n{'HKEX IPO Tracker E2E Test':=^55}\n")
    results = []
    results.append(
        ("trading_calendar", run([PYTHON, "trading_calendar.py", "2026-06-17"], "trading calendar"))
    )
    results.append(
        ("parse_conflict", run([PYTHON, "parse_conflict_matrix.py"], "conflict matrix", "[]"))
    )
    for filename, name in (
        ("calc_ah_discount.py", "A+H discount"),
        ("clawback_calculator.py", "clawback"),
        ("risk_score.py", "risk score"),
        ("funding_scheduler.py", "funding scheduler"),
        ("historical_first_day.py", "historical first day"),
        ("allotment_tracker.py", "allotment tracker"),
    ):
        results.append((name, run([PYTHON, filename, "--demo"], name)))

    results.append(
        ("markdown report", run([PYTHON, "generate_report.py", "--demo"], "Markdown report"))
    )
    with tempfile.TemporaryDirectory() as directory:
        output = os.path.join(directory, "report.html")
        results.append(
            (
                "HTML report",
                run(
                    [PYTHON, "generate_visual.py", "--demo", "--output", output],
                    "HTML report",
                ),
            )
        )

    passed = sum(1 for _, ok in results if ok)
    print(f"\n{'=' * 55}")
    print(f"Results: {passed}/{len(results)} passed")
    for name, ok in results:
        print(f"  {'OK' if ok else 'FAIL'}: {name}")
    print(f"{'=' * 55}\n")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
