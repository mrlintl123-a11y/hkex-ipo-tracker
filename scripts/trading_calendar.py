#!/usr/bin/env python3
"""
港股交易日历判断
================
根据 holidays_2026.json 静态表 + 周末规则，判断今天是否港股交易日。

用法：
    python trading_calendar.py                    # 检查今天
    python trading_calendar.py 2026-07-01         # 检查指定日期
    python trading_calendar.py 2026-07-01 --json # JSON 输出

退出码：
    0 = 交易日
    1 = 非交易日
    2 = 未知/异常
"""
import json
import sys
import argparse
from datetime import datetime, date
from pathlib import Path


CALENDAR_FILE = Path(__file__).parent.parent / "references" / "holidays_2026.json"


def load_calendar() -> dict:
    """加载交易日历"""
    if not CALENDAR_FILE.exists():
        return {"trading_calendar": {"hk_closed_days": [], "hk_connect_special_closure": []}}
    with open(CALENDAR_FILE, encoding="utf-8") as f:
        return json.load(f)


def collect_closed_dates(calendar: dict, year: int) -> set:
    """汇总所有休市日（含周末、节假日、港股通特殊休市日）"""
    closed = set()

    # 港股本身的休市日
    for entry in calendar.get("trading_calendar", {}).get("hk_closed_days", []):
        d = entry["date"]
        if d.startswith(str(year)):
            closed.add(d)

    # 港股通特殊休市日（保守判断，把整个 date_range 都加入）
    for entry in calendar.get("trading_calendar", {}).get("hk_connect_special_closure", []):
        rng = entry.get("date_range", "")
        if " to " in rng:
            start, end = rng.split(" to ")
            if start.startswith(str(year)):
                from datetime import timedelta
                d_start = datetime.strptime(start, "%Y-%m-%d")
                d_end = datetime.strptime(end, "%Y-%m-%d")
                while d_start <= d_end:
                    closed.add(d_start.strftime("%Y-%m-%d"))
                    d_start += timedelta(days=1)

    # 周末（周六周日）
    for month in range(1, 13):
        for day in range(1, 32):
            try:
                d = date(year, month, day)
                if d.weekday() >= 5:  # 周六(5)/周日(6)
                    closed.add(d.strftime("%Y-%m-%d"))
            except ValueError:
                break

    return closed


def is_trading_day(target: date = None, calendar: dict = None) -> dict:
    """
    判断 target 是否为港股交易日

    Returns:
        {
            "date": "2026-06-17",
            "is_trading_day": True/False,
            "reason": "...",
            "holiday_name": "..." (if applicable)
        }
    """
    if target is None:
        target = date.today()
    if calendar is None:
        calendar = load_calendar()

    date_str = target.strftime("%Y-%m-%d")
    year = target.year
    closed_set = collect_closed_dates(calendar, year)

    # 超出当前表覆盖范围
    if year > 2026:
        return {
            "date": date_str,
            "is_trading_day": None,
            "reason": f"year_{year}_not_in_calendar",
            "holiday_name": None
        }

    # 周末快速判定
    weekday = target.weekday()
    if weekday >= 5:
        return {
            "date": date_str,
            "is_trading_day": False,
            "reason": "weekend",
            "weekday": ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][weekday],
            "holiday_name": None
        }

    # 查表
    if date_str in closed_set:
        # 找到对应的节日名
        holiday_name = None
        for entry in calendar.get("trading_calendar", {}).get("hk_closed_days", []):
            if entry["date"] == date_str:
                holiday_name = entry["holiday"]
                break
        if not holiday_name:
            for entry in calendar.get("trading_calendar", {}).get("hk_connect_special_closure", []):
                rng = entry.get("date_range", "")
                if " to " in rng:
                    s, e = rng.split(" to ")
                    if s <= date_str <= e:
                        holiday_name = entry.get("reason", "港股通特殊休市")
                        break
        return {
            "date": date_str,
            "is_trading_day": False,
            "reason": "public_holiday",
            "holiday_name": holiday_name
        }

    return {
        "date": date_str,
        "is_trading_day": True,
        "reason": "trading_day",
        "holiday_name": None
    }


def main():
    parser = argparse.ArgumentParser(description="港股交易日判断")
    parser.add_argument("date", nargs="?", help="指定日期 YYYY-MM-DD (默认今天)")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    target = None
    if args.date:
        try:
            target = datetime.strptime(args.date, "%Y-%m-%d").date()
        except ValueError:
            print(f"❌ 日期格式错误: {args.date} (应为 YYYY-MM-DD)", file=sys.stderr)
            sys.exit(2)

    result = is_trading_day(target)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        # JSON 模式保留 exit code 用于 API 调用
        sys.exit(0 if result["is_trading_day"] else 1 if result["is_trading_day"] is False else 2)
    else:
        # CLI 模式总是 exit 0，不让上游脚本被非交易日"报错"
        if result["is_trading_day"]:
            print(f"✅ {result['date']} 是港股交易日")
        elif result["is_trading_day"] is False:
            reason = result.get("holiday_name") or result.get("reason", "")
            print(f"❌ {result['date']} 非交易日 ({reason})")
        else:
            print(f"⚠️  {result['date']} 未在日历覆盖范围 ({result['reason']})")
        sys.exit(0)


if __name__ == "__main__":
    main()
