#!/usr/bin/env python3
"""End-to-end test for HKEX IPO Tracker v4.1.1"""
import subprocess, sys, os
sys.stdout.reconfigure(encoding="utf-8")

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
def run(cmd, desc):
    print(f"  [{desc}] ", end="", flush=True)
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=SCRIPTS, timeout=30)
    ok = r.returncode == 0
    print("PASS" if ok else f"FAIL (exit={r.returncode})")
    if not ok:
        print(f"    stderr: {r.stderr[:200]}")
    return ok

def main():
    print(f"\n{'HKEX IPO Tracker v4.1.1 E2E Test':=^55}\n")
    results = []

    # Section 1: Core (v3 backwards compat)
    results.append(("trading_calendar", run("python trading_calendar.py 2026-06-17", "trading_calendar")))
    results.append(("parse_conflict", run("echo [] | python parse_conflict_matrix.py", "parse_conflict_matrix")))

    # Section 2: v4.0 modules
    results.append(("calc_ah_discount", run("python calc_ah_discount.py --demo", "calc_ah_discount (demo)")))
    results.append(("clawback", run("python clawback_calculator.py --demo", "clawback_calculator (demo)")))
    results.append(("risk_score", run("python risk_score.py --demo", "risk_score (demo)")))
    results.append(("funding", run("python funding_scheduler.py --demo", "funding_scheduler (demo)")))
    results.append(("historical", run("python historical_first_day.py --demo", "historical_first_day (demo)")))
    results.append(("allotment", run("python allotment_tracker.py --demo", "allotment_tracker (demo)")))

    # Summary
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    print(f"\n{'='*55}")
    print(f"Results: {passed}/{total} passed")
    for name, ok in results:
        print(f"  {'OK' if ok else 'FAIL'}: {name}")
    print(f"{'='*55}\n")
    return 0 if passed == total else 1

if __name__ == "__main__":
    sys.exit(main())
