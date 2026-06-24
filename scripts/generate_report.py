#!/usr/bin/env python3
"""Generate a complete Markdown report from canonical HKEX IPO data."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional

from clawback_calculator import calc as clawback_calc
from ipo_schema import (
    UNKNOWN,
    display,
    extract_records,
    format_market_cap,
    format_share_count,
    heat_score,
    missing_fields,
    parse_margin_multiple,
    stock_connect_analysis,
)


sys.stdout.reconfigure(encoding="utf-8")
SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CRITICAL_FIELDS = (
    "name",
    "code",
    "subscription_start",
    "closing_date",
    "listing_date",
    "offer_price",
    "board_lot",
    "global_shares",
)
OPTIONAL_FIELDS = (
    "cornerstone",
    "greenshoe",
    "a_h",
    "sponsors",
    "fundraising",
)
FIELD_LABELS = {
    "name": "公司名称",
    "code": "股票代码",
    "subscription_start": "招股开始日",
    "closing_date": "截止日",
    "listing_date": "上市日",
    "offer_price": "发售价",
    "board_lot": "每手股数",
    "global_shares": "全球发售股数",
    "cornerstone": "基石投资者",
    "greenshoe": "绿鞋",
    "a_h": "A+H",
    "sponsors": "保荐人",
    "fundraising": "募资净额",
}


def _cell(value: Any) -> str:
    return display(value).replace("|", "／").replace("\n", " ")


def _format_entry_fee(record: Dict[str, Any]) -> str:
    fee = float(record.get("entry_fee") or 0)
    return f"{fee:,.2f}港元" if fee else UNKNOWN


def _format_margin(record: Dict[str, Any]) -> str:
    margin = display(record.get("margin_multiple"), "暂无")
    updated = record.get("margin_data_date")
    return f"{margin}（{updated}）" if updated else margin


def _apply_redistribution(record: Dict[str, Any]) -> None:
    chapter = str(record.get("chapter") or "")
    redistribution = float(record.get("redistribution_pct") or 0)
    original_pct = float(record.get("public_initial_pct") or 0.10)
    if chapter not in {"18A", "18C"} or redistribution <= 0:
        return
    margin = parse_margin_multiple(record.get("margin_multiple")) or 0
    result = clawback_calc(chapter, margin, redistribution, original_pct * 100)
    final_pct = float(result["final_pct"]) / 100
    if final_pct <= original_pct:
        return
    old_lots = int(record.get("public_lots") or 0)
    record["_public_lots_initial"] = old_lots
    record["_redistribution_applied"] = result["mechanism"]
    record["public_lots"] = int(old_lots * final_pct / original_pct)
    record["public_initial_pct"] = final_pct


def build_context(raw: Any, now: Optional[datetime] = None) -> Dict[str, Any]:
    now = now or datetime.now()
    records = extract_records(raw)
    today = now.date()

    for record in records:
        _apply_redistribution(record)
        try:
            closing = datetime.strptime(record["closing_date"], "%Y-%m-%d").date()
            record["days_before_close"] = (closing - today).days
        except (TypeError, ValueError):
            record["days_before_close"] = 999

        critical = missing_fields(record, CRITICAL_FIELDS)
        optional = missing_fields(record, OPTIONAL_FIELDS)
        record["_missing_critical"] = critical
        record["_missing_optional"] = optional
        if critical:
            record["data_confidence"] = "🔴"
        elif record["days_before_close"] <= 0:
            record["data_confidence"] = "🟢"
        elif record["days_before_close"] == 1:
            record["data_confidence"] = "🟡"
        else:
            record["data_confidence"] = "🟠"

    active = [record for record in records if record["days_before_close"] >= 0]
    active.sort(key=lambda item: (item.get("closing_date", ""), item.get("code", "")))
    return {
        "records": records,
        "active": active,
        "snapshot": now.strftime("%Y-%m-%d %H:%M"),
        "today": today.strftime("%Y-%m-%d"),
    }


def _render_conflict_matrix(records: List[Dict[str, Any]]) -> List[str]:
    lines = ["## ⚠️ 资金冲突矩阵", ""]
    dates = sorted({item["closing_date"] for item in records if item.get("closing_date")})
    if not dates:
        return lines + ["暂无可计算的截止日。", ""]
    lines.append("| 截止日 | " + " | ".join(dates) + " |")
    lines.append("| --- |" + " --- |" * len(dates))
    for first in dates:
        cells = []
        first_date = datetime.strptime(first, "%Y-%m-%d").date()
        for second in dates:
            if first == second:
                cells.append("—")
                continue
            second_date = datetime.strptime(second, "%Y-%m-%d").date()
            gap = abs((second_date - first_date).days)
            cells.append(f"🔴冲突（{gap}天）" if gap < 2 else f"🟢分流（{gap}天）")
        lines.append(f"| **{first[-5:]}** | " + " | ".join(cells) + " |")
    return lines + [""]


def _render_quick_table(records: List[Dict[str, Any]]) -> List[str]:
    lines = ["## 📋 正在招股速查", ""]
    if not records:
        return lines + ["经实时数据源检查，当前没有正在招股的新股。", ""]
    lines.extend(
        [
            "| 公司 | 代码 | 招股期 | 上市日 | 发售价 | 入场费 | 全球发售 | 公开手数 | 孖展 | 绿鞋 | 基石 | A+H | 行业 | 预计市值 |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for item in records:
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(item["name"]),
                    _cell(item["code"]),
                    _cell(item["subscription_period"]),
                    _cell(item["listing_date"]),
                    _cell(item["offer_price"]),
                    _format_entry_fee(item),
                    format_share_count(item.get("global_shares")),
                    f"{int(item.get('public_lots') or 0):,}手" if item.get("public_lots") else UNKNOWN,
                    _cell(_format_margin(item)),
                    _cell(item["greenshoe"]),
                    _cell(item["cornerstone"]),
                    _cell(item["a_h"]),
                    _cell(item["industry"]),
                    format_market_cap(item.get("est_market_cap_hkd")),
                ]
            )
            + " |"
        )
    return lines + [""]


def _render_details(records: List[Dict[str, Any]]) -> List[str]:
    lines = ["## 🧾 个股详情", ""]
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for item in records:
        grouped[item.get("closing_date", UNKNOWN)].append(item)

    for closing_date in sorted(grouped):
        members = grouped[closing_date]
        days = members[0].get("days_before_close", 999)
        timing = "今日截止" if days == 0 else f"剩{days}天"
        lines.extend([f"### 截止 {closing_date}（{timing}，{len(members)}只）", ""])
        for index, item in enumerate(members, 1):
            score = heat_score(item)
            lines.extend(
                [
                    f"**{index}. {item['name']}（{item['code']}）** — 热度 {score['score']}/5，评分覆盖 {score['coverage']}",
                    f"- 招股期：{item['subscription_period']}；上市日：{item['listing_date']}；配发结果日：{item['result_date']}",
                    f"- 发售价：{item['offer_price']}；每手：{item['board_lot']}股；入场费：{_format_entry_fee(item)}",
                    f"- 全球发售：{format_share_count(item.get('global_shares'))}；初始公开比例：{item['public_pct']}；公开手数：{int(item.get('public_lots') or 0):,}手",
                    f"- 孖展：{_format_margin(item)}；绿鞋：{item['greenshoe']}；基石：{item['cornerstone']}；A+H：{item['a_h']}",
                    f"- 行业：{item['industry']}；预计市值：{format_market_cap(item.get('est_market_cap_hkd'))}；港股通观察：{stock_connect_analysis(item)}",
                    f"- 保荐人：{item['sponsors']}；预计募资净额：{item['fundraising']}",
                    f"- 数据来源：{item['source']}；抓取时间：{display(item.get('scraped_at'))}",
                    "",
                ]
            )
    return lines


def _render_observations(records: List[Dict[str, Any]], now: datetime) -> List[str]:
    lines = ["## 🔍 关键观察", ""]
    today = [item for item in records if item.get("days_before_close") == 0]
    tomorrow = [item for item in records if item.get("days_before_close") == 1]
    if today:
        names = "、".join(item["name"] for item in today)
        lines.append(
            f"1. **今日截止**：{names}；各券商停止认购时间可能不同，请以券商页面为准。"
        )
    if tomorrow:
        names = "、".join(item["name"] for item in tomorrow)
        lines.append(f"2. **明日截止**：{names}，孖展数据仍可能明显变化。")
    known_margins = [
        (item, parse_margin_multiple(item.get("margin_multiple"))) for item in records
    ]
    known_margins = [(item, value) for item, value in known_margins if value is not None]
    if known_margins:
        hottest, hot_value = max(known_margins, key=lambda pair: pair[1])
        coldest, cold_value = min(known_margins, key=lambda pair: pair[1])
        lines.append(
            f"3. **孖展冷热**：最高为{hottest['name']}（{hot_value:g}倍），"
            f"最低为{coldest['name']}（{cold_value:g}倍）。"
        )
    if len(lines) == 2:
        lines.append("暂无足够实时数据形成关键观察。")
    return lines + [""]


def _render_heat(records: List[Dict[str, Any]]) -> List[str]:
    lines = [
        "## 🔥 热度评分",
        "",
        "> 未获取到的维度不会按默认值计分；综合分按已知维度重新归一化。",
        "",
        "| 公司 | 孖展（30%） | 基石（25%） | 手数（20%） | 入场费（15%） | A+H（10%） | 评分覆盖 | 综合 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    ranked = sorted(records, key=lambda item: heat_score(item)["score"], reverse=True)
    for item in ranked:
        score = heat_score(item)
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(item["name"]),
                    _cell(item["margin_multiple"]),
                    _cell(item["cornerstone"]),
                    f"{int(item.get('public_lots') or 0):,}手" if item.get("public_lots") else UNKNOWN,
                    _format_entry_fee(item),
                    _cell(item["a_h"]),
                    score["coverage"],
                    f"{score['score']}/5",
                ]
            )
            + " |"
        )
    return lines + [""]


def _render_funding_reference(records: List[Dict[str, Any]]) -> List[str]:
    lines = ["## 💰 资金容量参考", ""]
    lines.append("> 仅按一手入场费归类，不代表认购建议。")
    lines.append("")
    tiers = (
        ("≤1万港元", 10_000),
        ("≤5万港元", 50_000),
        ("≤50万港元", 500_000),
    )
    for label, budget in tiers:
        eligible = [item for item in records if 0 < float(item.get("entry_fee") or 0) <= budget]
        text = "、".join(
            f"{item['name']}（{_format_entry_fee(item)}）" for item in eligible
        ) or "无"
        lines.append(f"- **{label}可覆盖一手**：{text}")
    return lines + [""]


def _render_data_gaps(records: List[Dict[str, Any]]) -> List[str]:
    lines = ["## 🧩 数据完整性", ""]
    complete = True
    for item in records:
        missing = item.get("_missing_critical", []) + item.get("_missing_optional", [])
        if not missing:
            continue
        complete = False
        labels = "、".join(FIELD_LABELS.get(field, field) for field in missing)
        lines.append(f"- **{item['name']}**：待核实 {labels}")
    if complete:
        lines.append("关键字段与扩展字段均已获取。")
    return lines + [""]


def _render_key_dates(records: List[Dict[str, Any]]) -> List[str]:
    lines = ["## 🔔 关键时间节点", ""]
    for item in records:
        lines.append(
            f"- **{item['name']}（{item['code']}）**："
            f"{item['closing_date']}截止；{item['result_date']}配发结果；"
            f"{item['listing_date']}上市"
        )
    return lines + [""]


def render_report(raw: Any, now: Optional[datetime] = None) -> str:
    now = now or datetime.now()
    context = build_context(raw, now=now)
    active = context["active"]
    lines = [f"# 📊 港交所正在招股信息汇总（{context['snapshot']} 更新）", ""]
    lines.extend(_render_conflict_matrix(active))
    lines.extend(_render_quick_table(active))
    lines.extend(_render_details(active))
    lines.extend(_render_observations(active, now))
    lines.extend(_render_heat(active))
    lines.extend(_render_funding_reference(active))
    lines.extend(_render_data_gaps(active))
    lines.extend(_render_key_dates(active))

    sources = sorted({item["source"] for item in active})
    lines.extend(
        [
            "---",
            f"> 数据来源：{'；'.join(sources) if sources else UNKNOWN}",
            "> 孖展与招股数据会持续变化；缺失字段已明确标记为“待核实”。",
            "> 本报告仅作公开信息汇总，不构成投资建议。",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _load_raw(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def main() -> int:
    parser = argparse.ArgumentParser(description="HKEX IPO Markdown report generator")
    parser.add_argument("--input", "-i", help="实时 IPO JSON 文件")
    parser.add_argument("--demo", action="store_true", help="使用示例数据")
    parser.add_argument("--strict", action="store_true", help="关键字段缺失时退出")
    parser.add_argument("--output", "-o", help="同时写入 Markdown 文件")
    args = parser.parse_args()

    if args.input:
        if not os.path.exists(args.input):
            print(f"ERROR: file not found: {args.input}", file=sys.stderr)
            return 1
        raw = _load_raw(args.input)
    elif args.demo:
        raw = _load_raw(os.path.join(SKILL_DIR, "references", "sample-data.json"))
    else:
        print("ERROR: use --input <file> or --demo", file=sys.stderr)
        return 1

    context = build_context(raw)
    critical = [item for item in context["active"] if item["_missing_critical"]]
    if args.strict and critical:
        for item in critical:
            fields = ", ".join(item["_missing_critical"])
            print(f"ERROR: {item['name']} missing critical fields: {fields}", file=sys.stderr)
        return 2

    report = render_report(raw)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(report)
    print(report, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
