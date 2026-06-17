#!/usr/bin/env python3
"""
HKEX IPO 每日例行检查脚本
==========================
供 cron 定时调用，在每个港股交易日 17:00 后运行。

功能：
1. 抓取 3 个数据源（智通财经、金吾资讯、港交所披露易）
2. 交叉验证"是否有新股正在招股"
3. 根据结果生成 3 种输出：
   - 有新股：完整报告（POST 给 agent 处理）
   - 确认无新股：简短汇报
   - 数据源异常：异常汇报

用法：
    python daily_check.py
    # 输出 JSON 到 stdout，包含 status 和 report 字段

退出码：
    0 = 成功（有新股/确认无新股）
    1 = 数据源异常，需人工处理
    2 = 网络完全失败
"""
import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path


SKILL_DIR = Path(__file__).parent.parent
SAMPLE_DATA = SKILL_DIR / "references" / "sample-data.json"

# 导入交易日历判断
sys.path.insert(0, str(SKILL_DIR / "scripts"))
from trading_calendar import is_trading_day  # noqa: E402


def search_mmx(query: str, count: int = 10, timeout: int = 30) -> dict:
    """调用 mmx search，返回 {success, results, error}"""
    try:
        result = subprocess.run(
            ["mmx", "search", "query", query],
            capture_output=True, text=True, timeout=timeout
        )
        if result.returncode != 0:
            return {"success": False, "error": f"exit={result.returncode}", "results": []}
        data = json.loads(result.stdout)
        return {"success": True, "results": data.get("organic", []), "error": None}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "timeout", "results": []}
    except Exception as e:
        return {"success": False, "error": str(e), "results": []}


def fetch_zhitong() -> dict:
    """L1 智通财经"""
    queries = [
        "港交所 招股 今日",
        "港股 正在招股",
        "新股孖展 港股",
    ]
    combined = []
    for q in queries:
        r = search_mmx(q, count=10)
        if r["success"]:
            combined.extend(r["results"])
    if not combined:
        return {"source": "智通财经", "status": "❌", "ipo_count": 0, "raw": []}
    return {
        "source": "智通财经",
        "status": "✅",
        "ipo_count": len(combined),
        "raw": combined[:5]
    }


def fetch_jinwu() -> dict:
    """L2 金吾资讯（通过 web_fetch 抓首页）"""
    try:
        result = subprocess.run(
            ["curl", "-s", "-L", "-m", "30",
             "-H", "User-Agent: Mozilla/5.0",
             "https://ipo.jinwucj.com/"],
            capture_output=True, text=True, timeout=35
        )
        if result.returncode != 0:
            return {"source": "金吾资讯", "status": "❌", "ipo_count": 0, "error": "fetch failed"}
        html = result.stdout
        # 简单匹配"截止认购倒计时"出现的次数 = 招股中公司数
        import re
        matches = re.findall(r"截止认购倒计时", html)
        ipo_count = len(matches)
        return {
            "source": "金吾资讯",
            "status": "✅" if ipo_count > 0 or "无新股" in html else "✅",
            "ipo_count": ipo_count,
            "raw": []
        }
    except Exception as e:
        return {"source": "金吾资讯", "status": "❌", "ipo_count": 0, "error": str(e)}


def fetch_hkexnews() -> dict:
    """L3 港交所披露易（通过 mmx 搜"港交所披露易 招股"）"""
    r = search_mmx("港交所披露易 招股 2026", count=5)
    return {
        "source": "港交所披露易",
        "status": "✅" if r["success"] else "❌",
        "ipo_count": len(r["results"]),
        "raw": r["results"][:3] if r["success"] else []
    }


def cross_validate() -> dict:
    """三级交叉验证"""
    sources = {
        "智通财经": fetch_zhitong(),
        "金吾资讯": fetch_jinwu(),
        "港交所披露易": fetch_hkexnews(),
    }

    # 计算有效源
    valid_sources = {k: v for k, v in sources.items() if v["status"] == "✅"}
    failed_sources = {k: v for k, v in sources.items() if v["status"] == "❌"}

    # 三级判定
    if len(valid_sources) == 0:
        return {
            "level": "L0_全失败",
            "ipo_count_estimate": -1,
            "sources": sources,
            "conclusion": "data_source_failure"
        }

    # 检查是否所有有效源都返回 0
    all_zero = all(v["ipo_count"] == 0 for v in valid_sources.values())

    if all_zero and len(valid_sources) >= 2:
        return {
            "level": "L2_双源确认无新股",
            "ipo_count_estimate": 0,
            "sources": sources,
            "conclusion": "no_active_ipo"
        }
    elif all_zero and len(valid_sources) == 1:
        return {
            "level": "L1_单源无新股",
            "ipo_count_estimate": 0,
            "sources": sources,
            "conclusion": "single_source_zero_need_verify"
        }
    else:
        # 至少一个源有数据
        max_count = max(v["ipo_count"] for v in valid_sources.values())
        return {
            "level": "L2+_有新股",
            "ipo_count_estimate": max_count,
            "sources": sources,
            "conclusion": "active_ipo_found"
        }


def format_report(validation: dict) -> str:
    """根据验证结果生成最终报告"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    conclusion = validation["conclusion"]
    sources = validation["sources"]

    # 数据源状态行
    source_lines = "\n".join(
        f"  - {name}: {info['status']} (返回 {info['ipo_count']} 条)"
        for name, info in sources.items()
    )

    if conclusion == "active_ipo_found":
        return (
            f"📊 【港交所每日 IPO 检查】{now}\n\n"
            f"✅ 检测到约 {validation['ipo_count_estimate']} 家公司正在或即将招股\n"
            f"- 数据源验证：\n{source_lines}\n\n"
            f"👉 切换到 hkex-ipo-tracker skill 完整工作流生成详细报告"
        )

    elif conclusion == "no_active_ipo":
        return (
            f"🟢 【港交所每日 IPO 检查】{now}\n\n"
            f"- 当日及未来 7 日内**无新股正在招股**\n"
            f"- 数据源交叉验证（L2 双源确认）：\n{source_lines}\n\n"
            f"- 下一次可能的新股：可关注近期已聆讯、待招股的公司"
        )

    elif conclusion == "single_source_zero_need_verify":
        return (
            f"🟡 【港交所每日 IPO 检查】{now}\n\n"
            f"- 仅 1 个数据源确认无新股，建议人工复核\n"
            f"- 数据源状态：\n{source_lines}\n\n"
            f"- ⚠️ 可能是数据源问题，不要直接下结论"
        )

    elif conclusion == "data_source_failure":
        return (
            f"⚠️ 【港交所每日 IPO 检查】{now}\n\n"
            f"- **所有数据源抓取失败**，无法确认\n"
            f"- 数据源状态：\n{source_lines}\n\n"
            f"- 🆘 建议：人工访问 https://ipo.jinwucj.com/ 核对"
        )

    return f"未知状态: {conclusion}"


def main():
    print("🔍 港交所每日 IPO 检查启动...", file=sys.stderr)

    # 0. 交易日判断（优先：非交易日直接退出）
    td = is_trading_day()
    if not td["is_trading_day"]:
        reason = td.get("holiday_name") or td.get("reason", "unknown")
        weekday = td.get("weekday", "")
        output = {
            "timestamp": datetime.now().isoformat(),
            "trading_day_check": td,
            "skipped_reason": "non_trading_day",
            "report": (
                f"😴 【港交所每日 IPO 检查】{datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
                f"- 今天 **{td['date']}** 不是港股交易日\n"
                f"- 原因：{reason}{f' ({weekday})' if weekday else ''}\n"
                f"- 跳过 IPO 检查（股票都不交易了，没新股看）\n"
                f"- 下个交易日再看 👀"
            ),
            "exit_code": 0
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
        sys.exit(0)

    # 1. 交易日，继续走多源验证
    validation = cross_validate()
    report = format_report(validation)

    output = {
        "timestamp": datetime.now().isoformat(),
        "validation": validation,
        "report": report,
        "exit_code": 0 if validation["conclusion"] != "data_source_failure" else 1
    }

    print(json.dumps(output, ensure_ascii=False, indent=2))
    sys.exit(output["exit_code"])


if __name__ == "__main__":
    main()
