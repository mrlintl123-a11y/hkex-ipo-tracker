#!/usr/bin/env python3
"""Generate a standalone HTML report from canonical HKEX IPO data."""

from __future__ import annotations

import argparse
import html
import json
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

from generate_report import build_context
from ipo_schema import (
    UNKNOWN,
    display,
    format_market_cap,
    format_share_count,
    heat_score,
    parse_margin_multiple,
    stock_connect_analysis,
)


sys.stdout.reconfigure(encoding="utf-8")
SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def esc(value: Any) -> str:
    return html.escape(display(value))


def _entry_fee(record: Dict[str, Any]) -> str:
    value = float(record.get("entry_fee") or 0)
    return f"{value:,.2f}港元" if value else UNKNOWN


def _margin_class(value: Optional[float]) -> str:
    if value is None:
        return "neutral"
    if value >= 100:
        return "hot"
    if value >= 15:
        return "warm"
    return "cold"


def _unknown_class(value: Any) -> str:
    return "unknown" if display(value) == UNKNOWN else ""


def render_html(raw: Any, now: Optional[datetime] = None) -> str:
    now = now or datetime.now()
    context = build_context(raw, now=now)
    records: List[Dict[str, Any]] = context["active"]
    deadline_count = sum(item.get("days_before_close", 99) <= 1 for item in records)
    confirmed_ah = sum(
        item.get("a_h") not in {UNKNOWN, "❌ 纯H股"} for item in records
    )
    average_coverage = (
        sum(int(heat_score(item)["coverage"].split("/")[0]) for item in records)
        / len(records)
        if records else 0
    )
    sources = sorted({item["source"] for item in records})

    parts = [
        "<!doctype html>",
        '<html lang="zh-CN"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        f"<title>港交所 IPO 信息汇总 · {esc(context['snapshot'])}</title>",
        """<style>
        :root{--ink:#132238;--muted:#64748b;--line:#dbe3ed;--bg:#f4f7fb;
        --panel:#fff;--blue:#2563eb;--red:#dc2626;--amber:#d97706;--green:#15803d}
        *{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
        font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans SC",sans-serif;
        line-height:1.55}.container{max-width:1440px;margin:auto;padding:24px}
        header{background:linear-gradient(135deg,#10233e,#234d7d);color:#fff;padding:30px;
        border-radius:16px;box-shadow:0 10px 30px rgba(15,35,62,.18)}
        header h1{margin:0 0 8px;font-size:30px}.sub{opacity:.8}.cards{display:grid;
        grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;margin:18px 0}
        .card,.section{background:var(--panel);border:1px solid var(--line);border-radius:12px;
        box-shadow:0 3px 12px rgba(15,35,62,.05)}.card{padding:18px}.number{font-size:28px;
        font-weight:750}.label{font-size:13px;color:var(--muted)}.section{padding:20px;margin:16px 0}
        h2{font-size:19px;margin:0 0 14px}.scroll{overflow:auto}table{border-collapse:collapse;
        width:100%;min-width:1100px;font-size:13px}th,td{padding:9px 10px;border-bottom:1px solid
        #edf1f5;text-align:left;vertical-align:top}th{position:sticky;top:0;background:#f8fafc;
        color:#475569;white-space:nowrap}.muted{color:var(--muted)}.tag{display:inline-block;
        padding:2px 7px;border-radius:999px;font-size:11px;font-weight:700}.hot{background:#fee2e2;
        color:#b91c1c}.warm{background:#fef3c7;color:#92400e}.cold{background:#dcfce7;
        color:#166534}.neutral{background:#e2e8f0;color:#475569}.bars{display:grid;gap:9px}
        .bar-row{display:grid;grid-template-columns:140px 1fr 90px;gap:10px;align-items:center}
        .track{height:22px;background:#edf2f7;border-radius:6px;overflow:hidden}.fill{height:100%;
        min-width:2px;background:var(--blue);color:#fff;font-size:11px;padding-left:7px;white-space:nowrap}
        .matrix td,.matrix th{text-align:center}.conflict{background:#fff1f2;color:#be123c}
        .safe{background:#f0fdf4;color:#166534}.unknown{color:#9a3412;font-weight:650}
        .gap-list{margin:0;padding-left:20px}.footer{font-size:12px;color:var(--muted);
        text-align:center;padding:20px}@media(max-width:850px){.cards{grid-template-columns:1fr 1fr}
        .container{padding:12px}.bar-row{grid-template-columns:100px 1fr 75px}}
        </style></head><body><div class="container">""",
        "<header>",
        "<h1>港交所正在招股信息汇总</h1>",
        f'<div class="sub">实时快照 {esc(context["snapshot"])} · 缺失字段明确标注“待核实”</div>',
        "</header>",
        '<div class="cards">',
        f'<div class="card"><div class="number">{len(records)}</div><div class="label">正在招股</div></div>',
        f'<div class="card"><div class="number">{deadline_count}</div><div class="label">今日或明日截止</div></div>',
        f'<div class="card"><div class="number">{confirmed_ah}</div><div class="label">已确认 A+H</div></div>',
        f'<div class="card"><div class="number">{average_coverage:.1f}/5</div><div class="label">平均评分覆盖</div></div>',
        "</div>",
    ]

    margins = [(item, parse_margin_multiple(item.get("margin_multiple"))) for item in records]
    known_values = [value for _, value in margins if value is not None]
    max_margin = max(known_values, default=1)
    parts.extend(['<section class="section"><h2>孖展认购倍数</h2><div class="bars">'])
    for item, value in sorted(margins, key=lambda pair: pair[1] or -1, reverse=True):
        width = min((value or 0) / max_margin * 100, 100)
        label = item.get("margin_multiple") or "暂无"
        parts.append(
            f'<div class="bar-row"><strong>{esc(item["name"])}</strong>'
            f'<div class="track"><div class="fill" style="width:{width:.1f}%">{esc(label)}</div></div>'
            f'<span class="tag {_margin_class(value)}">{esc(label)}</span></div>'
        )
    parts.append("</div></section>")

    dates = sorted({item["closing_date"] for item in records})
    parts.extend([
        '<section class="section"><h2>资金冲突矩阵</h2><div class="scroll"><table class="matrix"><tr><th>截止日</th>'
    ])
    parts.extend(f"<th>{esc(date[-5:])}</th>" for date in dates)
    parts.append("</tr>")
    for first in dates:
        parts.append(f"<tr><th>{esc(first[-5:])}</th>")
        first_date = datetime.strptime(first, "%Y-%m-%d")
        for second in dates:
            if first == second:
                parts.append("<td>—</td>")
                continue
            gap = abs((datetime.strptime(second, "%Y-%m-%d") - first_date).days)
            css = "conflict" if gap < 2 else "safe"
            text = f"{gap}天冲突" if gap < 2 else f"{gap}天分流"
            parts.append(f'<td class="{css}">{text}</td>')
        parts.append("</tr>")
    parts.append("</table></div></section>")

    parts.extend([
        '<section class="section"><h2>新股完整速查</h2><div class="scroll"><table>',
        "<tr><th>公司/代码</th><th>招股期</th><th>上市日</th><th>发售价/入场费</th>"
        "<th>全球发售/公开手数</th><th>孖展</th><th>绿鞋</th><th>基石</th>"
        "<th>A+H</th><th>行业/市值</th><th>港股通观察</th><th>来源</th></tr>",
    ])
    for item in records:
        parts.append(
            "<tr>"
            f'<td><strong>{esc(item["name"])}</strong><br><span class="muted">{esc(item["code"])}</span></td>'
            f'<td>{esc(item["subscription_period"])}</td>'
            f'<td>{esc(item["listing_date"])}</td>'
            f'<td>{esc(item["offer_price"])}<br><span class="muted">{esc(_entry_fee(item))}</span></td>'
            f'<td>{esc(format_share_count(item.get("global_shares")))}<br>'
            f'<span class="muted">{int(item.get("public_lots") or 0):,}手</span></td>'
            f'<td><span class="tag {_margin_class(parse_margin_multiple(item.get("margin_multiple")))}">'
            f'{esc(item["margin_multiple"])}</span><br><span class="muted">{esc(item.get("margin_data_date"))}</span></td>'
            f'<td class="{_unknown_class(item["greenshoe"])}">{esc(item["greenshoe"])}</td>'
            f'<td class="{_unknown_class(item["cornerstone"])}">{esc(item["cornerstone"])}</td>'
            f'<td class="{_unknown_class(item["a_h"])}">{esc(item["a_h"])}</td>'
            f'<td>{esc(item["industry"])}<br><span class="muted">{esc(format_market_cap(item.get("est_market_cap_hkd")))}</span></td>'
            f'<td>{esc(stock_connect_analysis(item))}</td>'
            f'<td class="muted">{esc(item["source"])}</td>'
            "</tr>"
        )
    parts.append("</table></div></section>")

    ranked = sorted(records, key=lambda item: heat_score(item)["score"], reverse=True)
    parts.extend(['<section class="section"><h2>热度评分（未知维度不计分）</h2><div class="bars">'])
    for item in ranked:
        score = heat_score(item)
        width = score["score"] / 5 * 100
        parts.append(
            f'<div class="bar-row"><strong>{esc(item["name"])}</strong>'
            f'<div class="track"><div class="fill" style="width:{width:.1f}%">'
            f'{score["score"]}/5</div></div><span>{score["coverage"]}维</span></div>'
        )
    parts.append("</div></section>")

    parts.extend(['<section class="section"><h2>数据完整性</h2><ul class="gap-list">'])
    gaps = 0
    labels = {
        "subscription_start": "招股开始日",
        "global_shares": "全球发售股数",
        "cornerstone": "基石投资者",
        "greenshoe": "绿鞋",
        "a_h": "A+H",
        "sponsors": "保荐人",
        "fundraising": "募资净额",
    }
    for item in records:
        missing = item.get("_missing_critical", []) + item.get("_missing_optional", [])
        if missing:
            gaps += 1
            text = "、".join(labels.get(field, field) for field in missing)
            parts.append(f'<li><strong>{esc(item["name"])}</strong>：待核实 {esc(text)}</li>')
    if not gaps:
        parts.append("<li>关键字段与扩展字段均已获取。</li>")
    parts.append("</ul></section>")

    parts.append(
        f'<div class="footer">数据来源：{esc("；".join(sources) if sources else UNKNOWN)}<br>'
        "本报告仅作公开信息汇总，不构成投资建议。</div></div></body></html>"
    )
    return "".join(parts)


def _load(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def main() -> int:
    parser = argparse.ArgumentParser(description="HKEX IPO standalone HTML generator")
    parser.add_argument("--input", "-i", help="实时 IPO JSON 文件")
    parser.add_argument("--demo", action="store_true", help="使用示例数据")
    parser.add_argument(
        "--output", "-o", default=os.path.join(SKILL_DIR, "ipo_report.html")
    )
    args = parser.parse_args()

    if args.input:
        if not os.path.exists(args.input):
            print(f"ERROR: file not found: {args.input}", file=sys.stderr)
            return 1
        raw = _load(args.input)
    elif args.demo:
        raw = _load(os.path.join(SKILL_DIR, "references", "sample-data.json"))
    else:
        print("ERROR: use --input <file> or --demo", file=sys.stderr)
        return 1

    output = os.path.abspath(args.output)
    with open(output, "w", encoding="utf-8") as handle:
        handle.write(render_html(raw))
    print(f"Visual report generated: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
