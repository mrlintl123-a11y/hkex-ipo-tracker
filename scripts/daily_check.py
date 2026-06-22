#!/usr/bin/env python3
"""
HKEX IPO 每日例行检查脚本（多后端适配版）
==========================================

供 cron 定时调用，在每个港股交易日 17:00 后运行。

功能：
1. 验证交易日
2. 抓取 3 个数据源（智通财经、金吾资讯、港交所披露易）
3. 交叉验证"是否有新股正在招股"
4. 根据结果生成 3 种输出：有新股 / 确认无新股 / 数据源异常

搜索后端通过 search_provider.py 适配：
  - agent_native : 由 Codex/LLM agent 自行搜索后喂入结果（默认）
  - mmx          : MiniMax mmx CLI
  - custom       : 用户自定义命令

用法：
    python daily_check.py                         # agent_native 模式
    python daily_check.py --input results.jsonl   # 从文件读取已有搜索结果
    python daily_check.py --provider mmx          # 使用 MiniMax
"""

import json
import re
import sys
sys.stdout.reconfigure(encoding='utf-8')
from datetime import datetime
from pathlib import Path
from typing import Optional

SKILL_DIR = Path(__file__).parent.parent

# 导入 search_provider + trading_calendar
sys.path.insert(0, str(SKILL_DIR / "scripts"))
from search_provider import (  # noqa: E402
    SearchQuery,
    SearchResult,
    FetchBatch,
    get_provider,
    build_ipo_queries,
    AgentNativeProvider,
)
from trading_calendar import is_trading_day  # noqa: E402


# ---------------------------------------------------------------------------
# 数据源抓取（通过 search_provider）
# ---------------------------------------------------------------------------

def fetch_zhitong(provider) -> dict:
    """智通财经：搜索新股孖展"""
    query = SearchQuery(
        source="智通财经",
        query="港股 正在招股 新股孖展 2026年6月",
        priority=1,
    )
    result = provider.search(query)
    if not result.success:
        return {"source": "智通财经", "status": "❌", "ipo_count": 0, "raw": [],
                "error": result.error}
    # 统计提及"招股"的段落数作为粗略估算
    mentions = len(re.findall(r"(?:招股|孖展|认购倍)", result.raw_text))
    return {
        "source": "智通财经",
        "status": "✅",
        "ipo_count": mentions,
        "raw": [result.raw_text[:1000]],
    }


def fetch_jinwu(provider) -> dict:
    """金吾资讯：fetch 首页"""
    query = SearchQuery(
        source="金吾资讯",
        query="港交所 IPO 正在招股",
        url="https://ipo.jinwucj.com/",
        priority=1,
    )
    result = provider.search(query)
    if not result.success:
        return {"source": "金吾资讯", "status": "❌", "ipo_count": 0,
                "error": result.error, "raw": []}
    html = result.raw_text
    matches = re.findall(r"截止认购倒计时", html)
    ipo_count = len(matches)
    return {
        "source": "金吾资讯",
        "status": "✅",
        "ipo_count": ipo_count,
        "raw": [],
    }


def fetch_hkexnews(provider) -> dict:
    """港交所披露易：搜索招股章程"""
    query = SearchQuery(
        source="港交所披露易",
        query="港交所披露易 招股章程 2026",
        url="https://www.hkex.com.hk/Listing/IPO/IPO-Documents",
        priority=1,
    )
    result = provider.search(query)
    return {
        "source": "港交所披露易",
        "status": "✅" if result.success else "❌",
        "ipo_count": len(re.findall(r"(?:招股|IPO)", result.raw_text)) if result.success else 0,
        "raw": [result.raw_text[:500]] if result.success else [],
        "error": result.error if not result.success else None,
    }


# ---------------------------------------------------------------------------
# 从 JSONL 读取外部喂入的搜索结果
# ---------------------------------------------------------------------------

def load_results_from_jsonl(path: str) -> dict[str, SearchResult]:
    """读取 JSONL 并按 source 分组"""
    results: dict[str, SearchResult] = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                r = SearchResult(**obj)
                results[r.source] = r
            except (json.JSONDecodeError, TypeError):
                continue
    return results


class JsonlProvider(AgentNativeProvider):
    """从 JSONL 文件回放搜索结果（不实际联网）"""

    name = "jsonl_replay"

    def __init__(self, results_map: dict[str, SearchResult]):
        super().__init__()
        self._results = results_map

    def search(self, query: SearchQuery, timeout: int = 30) -> SearchResult:
        if query.source in self._results:
            return self._results[query.source]
        # fallback: 按 URL 匹配
        for r in self._results.values():
            if query.url and query.url in (r.url or ""):
                return r
        return SearchResult(
            source=query.source,
            query=query.query,
            success=False,
            status="failed",
            error="no matching result in replay file",
        )


# ---------------------------------------------------------------------------
# 交叉验证
# ---------------------------------------------------------------------------

def cross_validate(provider) -> dict:
    """三级交叉验证"""
    sources = {
        "智通财经": fetch_zhitong(provider),
        "金吾资讯": fetch_jinwu(provider),
        "港交所披露易": fetch_hkexnews(provider),
    }

    valid_sources = {k: v for k, v in sources.items() if v["status"] == "✅"}
    failed_sources = {k: v for k, v in sources.items() if v["status"] == "❌"}

    if len(valid_sources) == 0:
        return {
            "level": "L0_全失败",
            "ipo_count_estimate": -1,
            "sources": sources,
            "conclusion": "data_source_failure",
        }

    all_zero = all(v["ipo_count"] == 0 for v in valid_sources.values())

    if all_zero and len(valid_sources) >= 2:
        return {
            "level": "L2_双源确认无新股",
            "ipo_count_estimate": 0,
            "sources": sources,
            "conclusion": "no_active_ipo",
        }
    elif all_zero and len(valid_sources) == 1:
        return {
            "level": "L1_单源无新股",
            "ipo_count_estimate": 0,
            "sources": sources,
            "conclusion": "single_source_zero_need_verify",
        }
    else:
        max_count = max(v["ipo_count"] for v in valid_sources.values())
        return {
            "level": "L2+_有新股",
            "ipo_count_estimate": max_count,
            "sources": sources,
            "conclusion": "active_ipo_found",
        }


def format_report(validation: dict) -> str:
    """根据验证结果生成最终报告"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    conclusion = validation["conclusion"]
    sources = validation["sources"]

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


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="HKEX IPO 每日例行检查（多后端适配版）"
    )
    parser.add_argument(
        "--input", "-i",
        default=None,
        help="从 JSONL 文件读取搜索结果（agent_native 模式推荐）",
    )
    parser.add_argument(
        "--provider",
        default=None,
        help="搜索后端 (agent_native / mmx / custom)",
    )
    args = parser.parse_args()

    print("🔍 港交所每日 IPO 检查启动...", file=sys.stderr)

    # 0. 交易日判断
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
            "exit_code": 0,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
        sys.exit(0)

    # 1. 选择搜索后端
    if args.input:
        results_map = load_results_from_jsonl(args.input)
        provider = JsonlProvider(results_map)
        print(f"📥 从 {args.input} 回放搜索结果 ({len(results_map)} 条)", file=sys.stderr)
    else:
        provider = get_provider(args.provider)
        print(f"🔍 使用后端 [{provider.name}]", file=sys.stderr)

    # 2. 交叉验证
    validation = cross_validate(provider)
    report = format_report(validation)

    output = {
        "timestamp": datetime.now().isoformat(),
        "validation": validation,
        "report": report,
        "exit_code": 0 if validation["conclusion"] != "data_source_failure" else 1,
    }

    print(json.dumps(output, ensure_ascii=False, indent=2))
    sys.exit(output["exit_code"])


if __name__ == "__main__":
    main()
