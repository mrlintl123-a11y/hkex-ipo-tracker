#!/usr/bin/env python3
"""Scrape active HKEX IPO data from Jinwu Finance with Playwright."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from ipo_schema import (
    PROVENANCE_FIELDS,
    UNKNOWN,
    is_unknown,
    make_field_meta,
    normalize_ipo,
    parse_market_cap_hkd,
    parse_percentage,
    parse_share_count,
)


sys.stdout.reconfigure(encoding="utf-8")

CALENDAR_URL = "https://ipo.jinwucj.com/"
DETAIL_URL = "https://ipo.jinwucj.com/stock/stockDetails/prospectus/{code}.hk"

FIELD_KEYWORDS = {
    "name": ("资料来源", "stockName"),
    "subscription_start": ("招股日期",),
    "closing_date": ("招股日期",),
    "result_date": ("结果日期",),
    "listing_date": ("上市日期",),
    "offer_price": ("招股价", "發售價"),
    "board_lot": ("每手股数", "每手股數"),
    "entry_fee": ("入场费", "入場費"),
    "global_shares": ("总发售数量", "總發售數量"),
    "public_initial_pct": ("公开发售", "公開發售"),
    "margin_multiple": ("认购倍数", "認購倍數"),
    "cornerstone": ("基石投资者", "基石投資者"),
    "greenshoe": ("超额配售", "超額配售", "超额配股", "超額配股"),
    "a_h": ("A+H", "A股及H股", "两地上市", "兩地上市"),
    "industry": ("所属行业", "所屬行業"),
    "est_market_cap_hkd": ("预计市值", "預計市值"),
    "sponsors": ("保荐人", "保薦人"),
    "fundraising": ("所得款项净额", "所得款項淨額"),
}


def _extract(pattern: str, text: str, flags: int = 0) -> str:
    match = re.search(pattern, text, flags)
    return match.group(1).strip() if match else ""


def _extract_company_name(text: str, code: str) -> str:
    escaped = re.escape(code)
    patterns = (
        rf"资料来源\s*[：:]\s*(.+?)\s*\({escaped}\)",
        rf'"stockName"\s*:\s*"([^"]+)".*?"symbol"\s*:\s*"{escaped}(?:\.hk)?"',
        rf'"symbol"\s*:\s*"{escaped}(?:\.hk)?".*?"stockName"\s*:\s*"([^"]+)"',
    )
    for pattern in patterns:
        value = _extract(pattern, text, re.S)
        if value:
            return re.sub(r"\s+", " ", value).strip()
    return ""


def _extract_fundraising(text: str) -> str:
    match = re.search(
        r"全球发售所得款项净额.*?约\s*([\d,.]+)\s*(百万|亿)港元",
        text,
        re.S,
    )
    if not match:
        return UNKNOWN
    amount = float(match.group(1).replace(",", ""))
    unit = match.group(2)
    amount_yi = amount / 100 if unit == "百万" else amount
    return f"{amount_yi:.2f}亿港元"


def _extract_cornerstone(text: str) -> str:
    if re.search(r"(?:未引入|没有|无)基石(?:投资者|投資者)?", text):
        return "❌ 无基石"
    value = _extract(
        r"基石(?:投资者|投資者)[：:]\s*(.+?)(?:\n|绿鞋|超额配售|保荐人|$)",
        text,
        re.S,
    )
    value = re.sub(r"\s+", " ", value).strip(" 。")
    return f"✅ {value}" if value else UNKNOWN


def _extract_greenshoe(text: str) -> str:
    if re.search(r"(?:无|不设|没有)超额(?:配售|配股)(?:权|權)", text):
        return "❌ 无绿鞋"
    percent = _extract(
        r"([\d.]+)%[^。\n]{0,40}超额(?:配售|配股)(?:权|權)", text
    ) or _extract(
        r"超额(?:配售|配股)(?:权|權)[^。\n]{0,40}?([\d.]+)%", text
    )
    if percent:
        return f"✅ {percent}%"
    if re.search(r"超额(?:配售|配股)(?:权|權)", text):
        return "✅ 有（比例待核实）"
    return UNKNOWN


def _extract_a_h(text: str) -> str:
    code_match = re.search(r"(\d{6})\s*\.\s*(SH|SZ)", text, re.I)
    if code_match:
        return f"✅ A+H（{code_match.group(1)}.{code_match.group(2).upper()}）"
    if re.search(r"\bA\s*\+\s*H\b|A股及H股|两地上市", text, re.I):
        return "✅ A+H"
    if re.search(r"(?:非A\+H|纯H股)", text, re.I):
        return "❌ 纯H股"
    return UNKNOWN


def _build_field_meta(record: Dict, text: str, source_url: str, retrieved_at: str) -> Dict:
    metadata = {}
    derived_fields = {"global_shares", "public_lots"}
    for field in PROVENANCE_FIELDS:
        value = record.get(field)
        if not is_unknown(value) and value not in {0, 0.0}:
            status = "derived" if field in derived_fields else "collected"
            note = "由摘要页字段计算" if status == "derived" else ""
            if field == "greenshoe" and "比例待核实" in str(value):
                status = "partial"
                note = "摘要页确认设有超额配售权，但未提取比例"
        else:
            keywords = FIELD_KEYWORDS.get(field, ())
            status = (
                "parse_failed"
                if keywords and any(keyword in text for keyword in keywords)
                else "authoritative_source_not_fetched"
            )
            note = (
                "摘要页出现字段关键词，但当前规则未提取出值"
                if status == "parse_failed"
                else "摘要页未提供完整值，尚未核验港交所招股书"
            )
        metadata[field] = make_field_meta(
            value=value,
            status=status,
            source_name="金吾资讯",
            source_url=source_url,
            retrieved_at=retrieved_at,
            note=note,
        )
    return metadata


def extract_detail(
    text: str, code: str = "", name: str = "", source_url: str = ""
) -> Dict:
    """Extract a canonical IPO record from one rendered detail-page body."""
    code = code.replace(".hk", "").replace(".HK", "")
    company_name = name or _extract_company_name(text, code)

    start = _extract(r"招股日期[：:]\s*(\d{4}-\d{2}-\d{2})", text)
    closing = _extract(
        r"招股日期[：:]\s*\d{4}-\d{2}-\d{2}\s*至\s*(\d{4}-\d{2}-\d{2})",
        text,
    )
    result_date = _extract(
        r"公布(?:售股|配售)?结果日期[：:]\s*(\d{4}-\d{2}-\d{2})", text
    )
    listing_date = _extract(r"上市日期[：:]\s*(\d{4}-\d{2}-\d{2})", text)

    price_low = _extract(r"招股价(?:范围)?[：:]\s*([\d.]+)", text)
    price_high = _extract(
        r"招股价(?:范围)?[：:]\s*[\d.]+\s*[~–-]\s*([\d.]+)", text
    )
    offer_price = (
        f"{price_low}-{price_high} HKD"
        if price_low and price_high
        else f"{price_low} HKD" if price_low else UNKNOWN
    )

    lot_text = _extract(r"每手股数[：:]\s*([\d,]+)", text)
    board_lot = int(lot_text.replace(",", "")) if lot_text else 0
    fee_text = _extract(r"入场费[：:]\s*([\d,.]+)", text)
    entry_fee = float(fee_text.replace(",", "")) if fee_text else 0.0

    total_shares = _extract(
        r"总发售数量[：:]\s*([\d,.]+\s*[万亿]?\s*股)", text
    )
    market_cap_text = _extract(
        r"预计市值[：:]\s*([\d,.]+\s*[万亿]?)(?:\s*港元)?", text
    )
    industry = _extract(
        r"所属行业[：:]\s*(.+?)\s+总发售数量[：:]", text, re.S
    )
    industry = re.sub(r"\s+", " ", industry).strip() or UNKNOWN

    margin = _extract(
        r"认购倍数[（(](?:预估|實際|实际)[)）][：:]\s*([\d,.]+)\s*倍", text
    )
    margin_multiple = f"{margin.replace(',', '')}倍" if margin else "暂无"
    update_dates = re.findall(
        r"数据更新[：:]\s*(\d{4}-\d{2}-\d{2}\s+[\d:]+)", text
    )
    margin_data_date = max(update_dates) if update_dates else ""

    public_pct_text = _extract(r"公开发售[：:]\s*([\d.]+%)", text)
    public_pct = parse_percentage(public_pct_text, default=0.10)
    global_shares = parse_share_count(total_shares)
    public_lots = int(global_shares * public_pct / board_lot) if board_lot else 0

    sponsors = _extract(
        r"(?:联席|独家)?保荐人[：:]\s*(.+?)(?:\n|基石|超额配售|$)",
        text,
        re.S,
    )
    sponsors = re.sub(r"\s+", " ", sponsors).strip(" 。") or UNKNOWN

    retrieved_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    source_url = source_url or DETAIL_URL.format(code=code)
    record = {
        "code": code,
        "name": company_name or UNKNOWN,
        "source": "金吾资讯（基础资料）；捷利交易宝（孖展，经金吾汇总）",
        "scraped_at": retrieved_at,
        "subscription_start": start,
        "closing_date": closing,
        "subscription_period": f"{start} 至 {closing}" if start and closing else UNKNOWN,
        "result_date": result_date,
        "listing_date": listing_date,
        "offer_price": offer_price,
        "board_lot": board_lot,
        "entry_fee": entry_fee,
        "total_shares": total_shares,
        "global_shares": global_shares,
        "market_cap": market_cap_text,
        "est_market_cap_hkd": parse_market_cap_hkd(market_cap_text),
        "industry": industry,
        "description": industry,
        "margin_multiple": margin_multiple,
        "margin_data_date": margin_data_date,
        "public_initial_pct": public_pct,
        "public_lots": public_lots,
        "cornerstone": _extract_cornerstone(text),
        "greenshoe": _extract_greenshoe(text),
        "a_h": _extract_a_h(text),
        "sponsors": sponsors,
        "fundraising": _extract_fundraising(text),
    }
    normalized = normalize_ipo(record)
    normalized["field_meta"] = _build_field_meta(
        normalized, text=text, source_url=source_url, retrieved_at=retrieved_at
    )
    return normalize_ipo(normalized)


def discover_active_ipos(
    page, snapshot_path: Optional[Path] = None
) -> List[Dict[str, str]]:
    """Discover under-subscription IPO codes and names from the live calendar API."""
    calendar: Dict = {}

    def on_response(response) -> None:
        if response.url.endswith("getNewIssueCalendar") and response.ok:
            try:
                calendar.update(response.json())
            except Exception:
                return

    page.on("response", on_response)
    page.goto(CALENDAR_URL, wait_until="networkidle", timeout=40_000)
    page.wait_for_timeout(2_000)

    if snapshot_path:
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_text(
            json.dumps(calendar, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    body = calendar.get("body", {}) if isinstance(calendar, dict) else {}
    records = []
    for ipo in body.get("underSubscription", []):
        symbol = str(ipo.get("symbol", ""))
        code = re.sub(r"\.hk$", "", symbol, flags=re.I)
        if code:
            records.append({"code": code, "name": str(ipo.get("stockName", ""))})
    return records


def scrape_all(
    codes: Optional[List[str]] = None,
    timeout: int = 25_000,
    raw_dir: Optional[Path] = None,
) -> List[Dict]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "[!] 缺少 Playwright。运行：python3 -m pip install -r requirements.txt "
            "&& python3 -m playwright install chromium",
            file=sys.stderr,
        )
        return []

    results = []
    if raw_dir:
        raw_dir = Path(raw_dir)
        raw_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        discovery_page = browser.new_page()
        discovered = discover_active_ipos(
            discovery_page,
            snapshot_path=raw_dir / "calendar.json" if raw_dir else None,
        )
        discovery_page.close()
        name_map = {item["code"]: item["name"] for item in discovered}
        targets = codes or [item["code"] for item in discovered]
        if not targets:
            print("[!] 实时日历未发现正在招股的新股", file=sys.stderr)
            browser.close()
            return []

        print(f"🔍 准备抓取 {len(targets)} 只新股详情: {targets}", file=sys.stderr)
        for code in targets:
            page = browser.new_page()
            try:
                print(f"  📄 {code} ...", file=sys.stderr, end=" ")
                page.goto(
                    DETAIL_URL.format(code=code),
                    wait_until="networkidle",
                    timeout=timeout,
                )
                page.wait_for_timeout(2_000)
                text = page.text_content("body") or ""
                detail_url = DETAIL_URL.format(code=code)
                if raw_dir:
                    (raw_dir / f"{code}_detail.txt").write_text(text, encoding="utf-8")
                detail = extract_detail(
                    text,
                    code=code,
                    name=name_map.get(code, ""),
                    source_url=detail_url,
                )
                if detail.get("closing_date") and detail.get("offer_price") != UNKNOWN:
                    results.append(detail)
                    print(
                        f"✅ {detail['name']} 招股价={detail['offer_price']} "
                        f"截止={detail['closing_date']}",
                        file=sys.stderr,
                    )
                else:
                    print("⚠️ 关键字段不完整，跳过", file=sys.stderr)
            except Exception as exc:
                print(f"❌ {exc}", file=sys.stderr)
            finally:
                page.close()
        browser.close()
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="金吾资讯 HKEX IPO 实时抓取器")
    parser.add_argument("--codes", help="逗号分隔的股票代码；默认自动发现")
    parser.add_argument("--output", "-o", help="输出 JSON 文件；默认 stdout")
    parser.add_argument("--timeout", type=int, default=25_000, help="单页超时毫秒数")
    parser.add_argument("--raw-dir", help="保存日历响应和逐只详情页原文")
    args = parser.parse_args()

    codes = [item.strip() for item in args.codes.split(",")] if args.codes else None
    results = scrape_all(
        codes=codes,
        timeout=args.timeout,
        raw_dir=Path(args.raw_dir) if args.raw_dir else None,
    )
    if not results:
        print("❌ 未获取到有效 IPO 数据", file=sys.stderr)
        return 1

    output = json.dumps(results, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(output)
        print(f"✅ 已写入 {args.output}（{len(results)}只）", file=sys.stderr)
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
