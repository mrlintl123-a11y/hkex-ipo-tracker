#!/usr/bin/env python3
"""Run the complete live HKEX IPO report pipeline with one command."""

from __future__ import annotations

import argparse
import importlib.util
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent


def run(command, capture=False):
    result = subprocess.run(
        command,
        cwd=str(SKILL_DIR),
        text=True,
        capture_output=capture,
        timeout=300,
    )
    if result.returncode:
        if capture:
            sys.stderr.write(result.stderr)
        raise RuntimeError(f"command failed ({result.returncode}): {' '.join(command)}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the live HKEX IPO report pipeline")
    parser.add_argument("--output-dir", default=str(SKILL_DIR), help="报告输出目录")
    parser.add_argument("--codes", help="可选：逗号分隔的股票代码")
    parser.add_argument("--strict", action="store_true", help="关键字段缺失时失败")
    args = parser.parse_args()

    if importlib.util.find_spec("playwright") is None:
        print(
            "ERROR: 缺少 Playwright。请先运行：\n"
            f"  {sys.executable} -m pip install -r {SKILL_DIR / 'requirements.txt'}\n"
            f"  {sys.executable} -m playwright install chromium",
            file=sys.stderr,
        )
        return 2

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    data_path = output_dir / "fresh_ipos.json"
    markdown_path = output_dir / "ipo_report.md"
    html_path = output_dir / "ipo_report.html"

    run([sys.executable, str(SCRIPT_DIR / "trading_calendar.py")])
    scrape_command = [
        sys.executable,
        str(SCRIPT_DIR / "scrape_jinwucj.py"),
        "--output",
        str(data_path),
    ]
    if args.codes:
        scrape_command.extend(["--codes", args.codes])
    run(scrape_command)

    report_command = [
        sys.executable,
        str(SCRIPT_DIR / "generate_report.py"),
        "--input",
        str(data_path),
        "--output",
        str(markdown_path),
    ]
    if args.strict:
        report_command.append("--strict")
    report = run(report_command, capture=True)
    run(
        [
            sys.executable,
            str(SCRIPT_DIR / "generate_visual.py"),
            "--input",
            str(data_path),
            "--output",
            str(html_path),
        ]
    )

    print(report.stdout, end="")
    print(f"\nHTML_REPORT={html_path}")
    print(f"MARKDOWN_REPORT={markdown_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
