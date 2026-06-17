#!/usr/bin/env python3
"""
HKEX IPO 数据抓取器（多后端适配版）
====================================

支持多种搜索后端（通过 search_provider.py 适配）：
  - agent_native : Codex/LLM agent 原生搜索（默认）
  - mmx          : MiniMax mmx CLI
  - custom       : 用户自定义命令

用法：
    # 直接搜索（需要有效的 SEARCH_PROVIDER 后端）
    python fetch_active_ipos.py

    # 从已有搜索结果文件读取（agent 模式推荐）
    python fetch_active_ipos.py --input results.jsonl

    # 指定搜索后端
    python fetch_active_ipos.py --provider mmx

输出：标准化 JSON 格式的 IPO 列表到 stdout
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# 将 scripts 目录加入路径以导入 search_provider
sys.path.insert(0, str(Path(__file__).resolve().parent))
from search_provider import (
    SearchQuery,
    SearchResult,
    FetchBatch,
    get_provider,
    build_ipo_queries,
    AgentNativeProvider,
)


# ---------------------------------------------------------------------------
# IPO 信息解析（保持原有逻辑）
# ---------------------------------------------------------------------------

def parse_listing_date(date_str: str) -> str:
    """解析日期格式"""
    if not date_str:
        return ""
    if re.match(r"\d{4}-\d{2}-\d{2}", date_str):
        return date_str[:10]
    m = re.search(r"(\d{1,2})月(\d{1,2})日", date_str)
    if m:
        year = datetime.now().year
        return f"{year}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    return date_str


def extract_ipo_info(text: str, source: str = "") -> dict:
    """
    从文本中提取 IPO 关键信息。

    支持多源数据格式：智通财经快讯、金吾资讯表格、港交所披露易摘要等。
    """
    info: dict = {
        "name": "",
        "code": "",
        "subscription_period": "",
        "closing_date": "",
        "listing_date": "",
        "offer_price": "",
        "board_lot": 0,
        "fundraising": "",
        "sponsors": "",
        "cornerstone": "",
        "greenshoe": "",
        "a_h": "",
        "source": source,
    }

    # 股票代码
    m = re.search(r"(\d{5})\s*\.?\s*HK", text, re.IGNORECASE)
    if not m:
        m = re.search(r"[\(（](\d{5})[\)）]", text)
    if m:
        info["code"] = m.group(1)

    # 公司名
    m = re.search(r"([\u4e00-\u9fffA-Za-z\-]{2,12}(?:医药|科技|股份|智能|材质|制造|控股|集团|国际)?(?:-[B])?)", text)
    if m:
        info["name"] = m.group(1).strip()

    # 招股期
    m = re.search(r"(\d{1,2})月(\d{1,2})日(?:至|到|-)\s*(\d{1,2})月(\d{1,2})日.*?招股", text)
    if m:
        info["subscription_period"] = f"{m.group(1)}/{m.group(2)}-{m.group(3)}/{m.group(4)}"
        info["closing_date"] = parse_listing_date(
            f"2026-{int(m.group(3)):02d}-{int(m.group(4)):02d}"
        )
    # 截止日单独匹配
    if not info["closing_date"]:
        m = re.search(r"截止(?:日|认购).*?(\d{1,2})月(\d{1,2})日", text)
        if m:
            info["closing_date"] = parse_listing_date(
                f"2026-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
            )

    # 上市日
    m = re.search(r"(\d{1,2})月(\d{1,2})日.*?(?:挂牌|上市|买卖|交易)", text)
    if m:
        info["listing_date"] = parse_listing_date(
            f"2026-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
        )

    # 发售价
    m = re.search(r"发售价.*?(\d+(?:\.\d+)?)港元", text)
    if m:
        info["offer_price"] = m.group(1) + " HKD"
    elif re.search(r"每股(\d+(?:\.\d+)?)港元", text):
        info["offer_price"] = re.search(r"每股(\d+(?:\.\d+)?)港元", text).group(1) + " HKD"

    # 每手
    m = re.search(r"每手(\d+)股", text)
    if m:
        info["board_lot"] = int(m.group(1))

    # 募资
    m = re.search(r"募资(?:约|最高)?(\d+(?:\.\d+)?)亿港元", text)
    if m:
        info["fundraising"] = m.group(1) + " 亿港元"

    # A+H
    if "A+H" in text or "两地上市" in text or re.search(r"00\d{4}\.SZ", text):
        info["a_h"] = "A+H"

    # 绿鞋
    if "超额配股权" in text:
        m = re.search(r"(\d+)%.*?超额配股权", text)
        info["greenshoe"] = f"yes {m.group(1)}%" if m else "yes"
    elif "无超额配股权" in text or "无超配权" in text:
        info["greenshoe"] = "no"

    # 基石
    if "基石" in text:
        if "未引入基石" in text or "无基石" in text:
            info["cornerstone"] = "no"
        else:
            info["cornerstone"] = "yes"

    return info


# ---------------------------------------------------------------------------
# 批量解析搜索结果
# ---------------------------------------------------------------------------

def parse_search_results(results: list[SearchResult]) -> list[dict]:
    """从多个搜索结果中提取 IPO 信息并去重"""
    all_ipos: list[dict] = []
    seen_codes: set[str] = set()

    for result in results:
        if not result.success or not result.raw_text:
            continue
        info = extract_ipo_info(result.raw_text, source=result.source)
        code = info.get("code", "")
        if code and code not in seen_codes:
            seen_codes.add(code)
            all_ipos.append(info)

    return all_ipos


# ---------------------------------------------------------------------------
# 从外部 JSONL 读取（agent_native 模式）
# ---------------------------------------------------------------------------

def load_results_from_jsonl(path: str) -> list[SearchResult]:
    """读取 JSONL 格式的搜索结果文件"""
    results: list[SearchResult] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                results.append(SearchResult(**obj))
            except (json.JSONDecodeError, TypeError) as e:
                print(f"[!] 跳过无效行: {e}", file=sys.stderr)
    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="HKEX IPO 数据抓取器（多后端适配版）"
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
    parser.add_argument(
        "--emit-queries",
        action="store_true",
        help="仅输出搜索查询清单，不执行搜索（agent_native 模式）",
    )
    parser.add_argument(
        "--output-queries", "-o",
        default=None,
        help="将查询清单写入文件",
    )
    args = parser.parse_args()

    # 模式 1: 仅输出查询
    if args.emit_queries:
        provider = get_provider("agent_native")
        queries = build_ipo_queries()
        payload = provider.emit_queries(queries)
        if args.output_queries:
            with open(args.output_queries, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            print(f"✅ 查询清单已写入 {args.output_queries}", file=sys.stderr)
        else:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    # 模式 2: 从文件读取已有结果
    if args.input:
        print(f"📥 从 {args.input} 读取搜索结果...", file=sys.stderr)
        results = load_results_from_jsonl(args.input)
        ipos = parse_search_results(results)
        print(f"✅ 解析出 {len(ipos)} 家公司", file=sys.stderr)
        print(json.dumps(ipos, ensure_ascii=False, indent=2))
        return

    # 模式 3: 实时搜索
    provider = get_provider(args.provider)
    print(f"🔍 使用后端 [{provider.name}] 搜索港交所 IPO...", file=sys.stderr)

    if isinstance(provider, AgentNativeProvider):
        print(
            "⚠️  agent_native 模式需要外部喂入搜索结果。请使用 --input 或 --emit-queries",
            file=sys.stderr,
        )
        queries = build_ipo_queries()
        provider.emit_queries(queries)
        return

    queries = build_ipo_queries()
    results = provider.batch_search(queries)
    ipos = parse_search_results(results)
    print(f"✅ 找到 {len(ipos)} 家公司", file=sys.stderr)
    print(json.dumps(ipos, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
