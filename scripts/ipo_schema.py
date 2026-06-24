#!/usr/bin/env python3
"""Canonical field normalization and scoring for HKEX IPO records."""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Dict, Iterable, List, Optional, Tuple


UNKNOWN = "待核实"
UNKNOWN_MARKERS = {
    "",
    "-",
    "?",
    "--",
    "n/a",
    "none",
    "null",
    "未知",
    "待核实",
    "待确认",
    "未披露",
}


def is_unknown(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() in UNKNOWN_MARKERS
    return False


def display(value: Any, fallback: str = UNKNOWN) -> str:
    return fallback if is_unknown(value) else str(value).strip()


def parse_share_count(value: Any) -> int:
    """Parse values such as ``1344.19 万股`` into an integer share count."""
    if isinstance(value, bool) or value is None:
        return 0
    if isinstance(value, (int, float)):
        return max(0, int(value))
    text = str(value).replace(",", "").strip()
    match = re.search(r"([\d.]+)", text)
    if not match:
        return 0
    number = float(match.group(1))
    if "亿" in text:
        number *= 100_000_000
    elif "万" in text:
        number *= 10_000
    elif re.search(r"\b[mM]\b", text):
        number *= 1_000_000
    return max(0, int(round(number)))


def format_share_count(value: Any) -> str:
    shares = parse_share_count(value)
    if not shares:
        return UNKNOWN
    if shares >= 100_000_000:
        return f"{shares / 100_000_000:.2f}亿股"
    if shares >= 10_000:
        return f"{shares / 10_000:.2f}万股"
    return f"{shares:,}股"


def parse_market_cap_hkd(value: Any, assume_yi: bool = False) -> float:
    if isinstance(value, bool) or value is None:
        return 0.0
    if isinstance(value, (int, float)):
        number = float(value)
        if assume_yi and 0 < number < 1_000_000:
            number *= 100_000_000
        return max(0.0, round(number, 2))
    text = str(value).replace(",", "").strip()
    match = re.search(r"([\d.]+)", text)
    if not match:
        return 0.0
    number = float(match.group(1))
    if "亿" in text:
        number *= 100_000_000
    elif "万" in text:
        number *= 10_000
    elif assume_yi and number < 1_000_000:
        number *= 100_000_000
    return max(0.0, round(number, 2))


def format_market_cap(value: Any) -> str:
    amount = parse_market_cap_hkd(value)
    if not amount:
        return UNKNOWN
    return f"{amount / 100_000_000:.2f}亿港元"


def parse_percentage(value: Any, default: float = 0.0) -> float:
    if isinstance(value, (int, float)):
        number = float(value)
        return number / 100 if number > 1 else number
    if value:
        match = re.search(r"([\d.]+)", str(value))
        if match:
            return float(match.group(1)) / 100
    return default


def parse_margin_multiple(value: Any) -> Optional[float]:
    if is_unknown(value) or "暂无" in str(value):
        return None
    match = re.search(r"([\d,.]+)", str(value))
    if not match:
        return None
    return float(match.group(1).replace(",", ""))


def parse_offer_price(value: Any) -> Tuple[Optional[float], Optional[float]]:
    if is_unknown(value):
        return None, None
    numbers = re.findall(r"[\d.]+", str(value))
    if not numbers:
        return None, None
    low = float(numbers[0])
    high = float(numbers[-1])
    return low, high


def _period_dates(record: Dict[str, Any]) -> Tuple[str, str]:
    start = display(
        record.get("subscription_start") or record.get("period_start"), ""
    )
    end = display(record.get("closing_date") or record.get("period_end"), "")
    period = str(record.get("subscription_period") or "")
    dates = re.findall(r"\d{4}[-/]\d{2}[-/]\d{2}", period)
    if len(dates) >= 2:
        start = start or dates[0].replace("/", "-")
        end = end or dates[1].replace("/", "-")
    return start, end


def _normalize_evidence(value: Any, negative_label: str) -> str:
    if is_unknown(value):
        return UNKNOWN
    text = str(value).strip()
    lowered = text.lower()
    if lowered in {"no", "false", "否", "无", "❌"}:
        return negative_label
    if lowered in {"yes", "true", "是", "有", "✅"}:
        return "✅ 有"
    return text


def normalize_ipo(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Return one canonical IPO record without mutating the input."""
    record = deepcopy(raw)
    code = str(record.get("code") or record.get("symbol") or "").strip()
    code = re.sub(r"\.hk$", "", code, flags=re.I)
    record["code"] = code.zfill(5) if code.isdigit() else code
    record["name"] = display(record.get("name") or record.get("stock_name"))

    start, end = _period_dates(record)
    record["subscription_start"] = start
    record["period_start"] = start
    record["closing_date"] = end
    record["period_end"] = end
    record["subscription_period"] = (
        f"{start} 至 {end}" if start and end else display(record.get("subscription_period"))
    )

    record["listing_date"] = display(record.get("listing_date"))
    record["result_date"] = display(record.get("result_date"))
    record["offer_price"] = display(record.get("offer_price"))
    record["board_lot"] = int(record.get("board_lot") or 0)

    global_shares = parse_share_count(
        record.get("global_shares") or record.get("total_shares")
    )
    record["global_shares"] = global_shares
    record["total_shares"] = (
        display(record.get("total_shares"))
        if record.get("total_shares")
        else format_share_count(global_shares)
    )

    market_cap = parse_market_cap_hkd(record.get("est_market_cap_hkd"))
    if not market_cap:
        market_cap = parse_market_cap_hkd(record.get("market_cap"), assume_yi=True)
    record["est_market_cap_hkd"] = market_cap
    record["market_cap"] = format_market_cap(market_cap)

    industry = display(
        record.get("industry") or record.get("description") or record.get("category")
    )
    record["industry"] = industry
    record["description"] = industry

    public_pct = parse_percentage(
        record.get("public_initial_pct") or record.get("public_pct"), default=0.10
    )
    record["public_initial_pct"] = public_pct
    record["public_pct"] = f"{public_pct * 100:g}%"

    public_lots = int(record.get("public_lots") or 0)
    if not public_lots and global_shares and record["board_lot"]:
        public_lots = int(global_shares * public_pct / record["board_lot"])
    record["public_lots"] = public_lots

    entry_fee = record.get("entry_fee") or 0
    try:
        entry_fee = float(str(entry_fee).replace(",", "").split()[0])
    except (TypeError, ValueError):
        entry_fee = 0.0
    if not entry_fee and record["board_lot"]:
        _, high = parse_offer_price(record["offer_price"])
        if high:
            entry_fee = high * record["board_lot"] * 1.01
    record["entry_fee"] = round(entry_fee, 2)

    record["margin_multiple"] = display(record.get("margin_multiple"), "暂无")
    record["margin_data_date"] = display(record.get("margin_data_date"), "")
    record["cornerstone"] = _normalize_evidence(
        record.get("cornerstone"), "❌ 无基石"
    )
    record["greenshoe"] = _normalize_evidence(
        record.get("greenshoe"), "❌ 无绿鞋"
    )
    record["a_h"] = _normalize_evidence(record.get("a_h"), "❌ 纯H股")
    record["sponsors"] = display(record.get("sponsors"))
    record["fundraising"] = display(record.get("fundraising"))
    record["source"] = display(record.get("source"), "来源未标注")
    record["scraped_at"] = display(record.get("scraped_at"), "")
    return record


def extract_records(raw: Any) -> List[Dict[str, Any]]:
    if isinstance(raw, list):
        return [normalize_ipo(item) for item in raw]
    if isinstance(raw, dict):
        records = raw.get("active_ipos") or raw.get("data")
        if isinstance(records, list):
            return [normalize_ipo(item) for item in records]
    raise ValueError("expected a list or an object containing active_ipos/data")


def missing_fields(record: Dict[str, Any], fields: Iterable[str]) -> List[str]:
    missing = []
    for field in fields:
        value = record.get(field)
        if field in {"board_lot", "global_shares", "public_lots"}:
            if not value:
                missing.append(field)
        elif is_unknown(value):
            missing.append(field)
    return missing


def stock_connect_analysis(record: Dict[str, Any]) -> str:
    ah = display(record.get("a_h"))
    if not is_unknown(ah) and "纯H" not in ah and not ah.startswith("❌"):
        return "A+H，实际纳入以港交所公告为准"
    cap = float(record.get("est_market_cap_hkd") or 0)
    if not cap:
        return UNKNOWN
    if cap >= 5_000_000_000:
        return "达到50亿市值观察线，仍需指数及规则审核"
    return "低于50亿市值观察线"


def heat_score(record: Dict[str, Any]) -> Dict[str, Any]:
    """Calculate a 1-5 score while excluding unknown dimensions."""
    components: Dict[str, Optional[float]] = {
        "margin": None,
        "cornerstone": None,
        "lots": None,
        "fee": None,
        "a_h": None,
    }
    weights = {
        "margin": 0.30,
        "cornerstone": 0.25,
        "lots": 0.20,
        "fee": 0.15,
        "a_h": 0.10,
    }

    margin = parse_margin_multiple(record.get("margin_multiple"))
    if margin is not None:
        components["margin"] = (
            5 if margin >= 500 else 4 if margin >= 100 else 3 if margin >= 50
            else 2 if margin >= 15 else 1
        )

    cornerstone = record.get("cornerstone")
    if not is_unknown(cornerstone):
        text = str(cornerstone)
        if text.startswith("❌"):
            components["cornerstone"] = 1
        else:
            count = text.count("、") + text.count(",") + 1
            components["cornerstone"] = 5 if count >= 5 else 4 if count >= 3 else 3

    lots = int(record.get("public_lots") or 0)
    if lots:
        components["lots"] = 5 if lots < 15_000 else 3 if lots <= 30_000 else 2

    fee = float(record.get("entry_fee") or 0)
    if fee:
        components["fee"] = 5 if fee < 3_000 else 3 if fee <= 5_000 else 2

    ah = record.get("a_h")
    if not is_unknown(ah):
        if str(ah).startswith("❌") or "纯H" in str(ah):
            components["a_h"] = 3
        else:
            discount = record.get("ah_discount")
            match = re.search(r"-?[\d.]+", str(discount or ""))
            if match:
                value = float(match.group())
                components["a_h"] = 5 if value > 40 else 4 if value >= 20 else 3
            else:
                components["a_h"] = 3

    available = {key: value for key, value in components.items() if value is not None}
    denominator = sum(weights[key] for key in available)
    score = (
        sum(weights[key] * float(value) for key, value in available.items()) / denominator
        if denominator else 0.0
    )
    return {
        "score": round(score, 2),
        "coverage": f"{len(available)}/5",
        "components": components,
    }
