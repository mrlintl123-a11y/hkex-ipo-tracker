#!/usr/bin/env python3
"""Audit field provenance and detect acquisition/parser/normalization/render gaps."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ipo_schema import (
    ISSUE_STATUSES,
    STATUS_LABELS,
    extract_records,
    field_meta,
    field_status,
    is_unknown,
)


AUDIT_FIELDS = (
    "subscription_start",
    "closing_date",
    "listing_date",
    "offer_price",
    "board_lot",
    "global_shares",
    "public_lots",
    "margin_multiple",
    "cornerstone",
    "greenshoe",
    "a_h",
    "industry",
    "est_market_cap_hkd",
    "sponsors",
    "fundraising",
)

FIELD_LABELS = {
    "subscription_start": "招股开始日",
    "closing_date": "截止日",
    "listing_date": "上市日",
    "offer_price": "发售价",
    "board_lot": "每手股数",
    "global_shares": "全球发售股数",
    "public_lots": "公开手数",
    "margin_multiple": "孖展倍数",
    "cornerstone": "基石投资者",
    "greenshoe": "绿鞋",
    "a_h": "A+H",
    "industry": "行业",
    "est_market_cap_hkd": "预计市值",
    "sponsors": "保荐人",
    "fundraising": "募资净额",
}


def _by_code(records: Optional[List[Dict[str, Any]]]) -> Dict[str, Dict[str, Any]]:
    return {str(item.get("code", "")).zfill(5): item for item in records or []}


def build_audit(
    final_records: List[Dict[str, Any]],
    scraped_records: Optional[List[Dict[str, Any]]] = None,
    report_text: str = "",
) -> Dict[str, Any]:
    scraped_by_code = _by_code(scraped_records)
    status_counts: Counter = Counter()
    pipeline_errors: Counter = Counter()
    audited = []
    confirmed_statuses = {"collected", "official_confirmed", "derived"}

    for record in final_records:
        code = str(record.get("code", "")).zfill(5)
        scraped = scraped_by_code.get(code, {})
        fields = {}
        for field in AUDIT_FIELDS:
            status = field_status(record, field)
            value = record.get(field)
            meta = field_meta(record, field)
            diagnosis = status

            scraped_value = scraped.get(field)
            if not is_unknown(scraped_value) and is_unknown(value):
                diagnosis = "normalization_loss"
                pipeline_errors[diagnosis] += 1
            elif (
                report_text
                and field in {"cornerstone", "greenshoe", "a_h", "sponsors", "fundraising"}
                and not is_unknown(value)
                and str(value) not in report_text
            ):
                diagnosis = "renderer_loss"
                pipeline_errors[diagnosis] += 1

            status_counts[status] += 1
            fields[field] = {
                "label": FIELD_LABELS.get(field, field),
                "value": value,
                "status": status,
                "status_label": STATUS_LABELS.get(status, status),
                "diagnosis": diagnosis,
                "source_name": meta.get("source_name", ""),
                "source_url": meta.get("source_url", ""),
                "retrieved_at": meta.get("retrieved_at", ""),
                "note": meta.get("note", ""),
            }

        confirmed = sum(
            1 for item in fields.values() if item["status"] in confirmed_statuses
        )
        audited.append(
            {
                "code": code,
                "name": record.get("name", ""),
                "coverage": f"{confirmed}/{len(AUDIT_FIELDS)}",
                "fields": fields,
            }
        )

    total_fields = len(final_records) * len(AUDIT_FIELDS)
    confirmed_fields = sum(
        count for status, count in status_counts.items() if status in confirmed_statuses
    )
    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "summary": {
            "ipo_count": len(final_records),
            "field_count": total_fields,
            "confirmed_fields": confirmed_fields,
            "coverage_pct": round(confirmed_fields / total_fields * 100, 1)
            if total_fields
            else 0.0,
            "status_counts": dict(status_counts),
            "pipeline_errors": dict(pipeline_errors),
        },
        "records": audited,
    }


def render_audit_markdown(audit: Dict[str, Any]) -> str:
    summary = audit["summary"]
    lines = [
        "# IPO 数据链路自查",
        "",
        f"- 新股数量：{summary['ipo_count']}",
        f"- 字段覆盖：{summary['confirmed_fields']}/{summary['field_count']}（{summary['coverage_pct']}%）",
        f"- 规范化/渲染丢失：{sum(summary['pipeline_errors'].values())}",
        "",
        "## 待处理项",
        "",
    ]
    issue_found = False
    for record in audit["records"]:
        grouped: Dict[str, List[str]] = {}
        for field, item in record["fields"].items():
            if item["status"] not in ISSUE_STATUSES and item["diagnosis"] == item["status"]:
                continue
            issue_found = True
            diagnosis = item["diagnosis"]
            if diagnosis == "normalization_loss":
                label = "规范化阶段丢失"
            elif diagnosis == "renderer_loss":
                label = "报告渲染阶段丢失"
            else:
                label = item["status_label"]
            grouped.setdefault(label, []).append(FIELD_LABELS.get(field, field))
        if grouped:
            text = "；".join(
                f"{label}：{'、'.join(fields)}" for label, fields in grouped.items()
            )
            lines.append(f"- **{record['name']}（{record['code']}）**：{text}")
    if not issue_found:
        lines.append("没有发现字段链路问题。")
    lines.extend(
        [
            "",
            "## 判定规则",
            "",
            "- 原始页出现关键词但解析值为空：原文存在但解析失败。",
            "- 抓取 JSON 有值、最终 JSON 无值：规范化阶段丢失。",
            "- 最终 JSON 有值、报告中没有：报告渲染阶段丢失。",
            "- 港交所检索未执行或未找到文件：权威来源获取缺口。",
            "",
        ]
    )
    return "\n".join(lines)


def _load(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as handle:
        return extract_records(json.load(handle))


def main() -> int:
    parser = argparse.ArgumentParser(description="IPO 字段级数据链路自查")
    parser.add_argument("--input", "-i", required=True, help="最终 JSON")
    parser.add_argument("--scraped", help="抓取阶段 JSON，用于检查规范化丢失")
    parser.add_argument("--report", help="Markdown 报告，用于检查渲染丢失")
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-md", required=True)
    args = parser.parse_args()

    report_text = (
        Path(args.report).read_text(encoding="utf-8") if args.report else ""
    )
    audit = build_audit(
        _load(args.input),
        scraped_records=_load(args.scraped) if args.scraped else None,
        report_text=report_text,
    )
    Path(args.output_json).write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    Path(args.output_md).write_text(render_audit_markdown(audit), encoding="utf-8")
    print(
        f"AUDIT_COVERAGE={audit['summary']['coverage_pct']}% "
        f"PIPELINE_ERRORS={sum(audit['summary']['pipeline_errors'].values())}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
