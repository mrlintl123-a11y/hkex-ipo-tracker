#!/usr/bin/env python3
"""Discover HKEX prospectuses and enrich high-value IPO fields from official text."""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ipo_schema import UNKNOWN, extract_records, is_unknown, make_field_meta, normalize_ipo


sys.stdout.reconfigure(encoding="utf-8")

HKEX_BASE = "https://www1.hkexnews.hk"
PREFIX_URL = f"{HKEX_BASE}/search/prefix.do?"
TITLE_SEARCH_URL = f"{HKEX_BASE}/search/titlesearch.xhtml?lang=en"
OFFICIAL_FIELDS = ("cornerstone", "greenshoe", "a_h", "sponsors", "fundraising")
USER_AGENT = "Mozilla/5.0 (compatible; hkex-ipo-tracker/2.0; public-document research)"


def _request(
    url: str,
    data: Optional[bytes] = None,
    timeout: int = 30,
) -> bytes:
    request = urllib.request.Request(
        url,
        data=data,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "en,zh-HK;q=0.8"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def lookup_stock_id(code: str, timeout: int = 30) -> Tuple[str, str]:
    params = urllib.parse.urlencode(
        {
            "lang": "EN",
            "type": "A",
            "name": code.zfill(5),
            "market": "SEHK",
            "callback": "callback",
        }
    )
    payload = _request(PREFIX_URL + params, timeout=timeout).decode("utf-8", "replace")
    match = re.search(r"callback\((.*)\)\s*;?", payload, re.S)
    if not match:
        return "", ""
    data = json.loads(match.group(1))
    for item in data.get("stockInfo", []):
        if str(item.get("code", "")).zfill(5) == code.zfill(5):
            return str(item.get("stockId", "")), str(item.get("name", ""))
    return "", ""


def _strip_tags(fragment: str) -> str:
    fragment = re.sub(r"<br\s*/?>", " | ", fragment, flags=re.I)
    fragment = re.sub(r"<[^>]+>", " ", fragment)
    return html.unescape(re.sub(r"\s+", " ", fragment)).strip()


def search_documents(
    code: str,
    start: date,
    end: date,
    timeout: int = 30,
) -> Tuple[List[Dict[str, str]], str]:
    stock_id, short_name = lookup_stock_id(code, timeout=timeout)
    if not stock_id:
        return [], ""
    form = {
        "lang": "EN",
        "category": "0",
        "market": "SEHK",
        "searchType": "0",
        "documentType": "-1",
        "t1code": "-2",
        "t2Gcode": "-2",
        "t2code": "-2",
        "stockId": stock_id,
        "from": start.strftime("%Y%m%d"),
        "to": end.strftime("%Y%m%d"),
    }
    body = _request(
        TITLE_SEARCH_URL,
        data=urllib.parse.urlencode(form).encode("ascii"),
        timeout=timeout,
    ).decode("utf-8", "replace")
    documents = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", body, re.S | re.I):
        links = re.findall(r'href="([^"]+)"', row, re.I)
        if not links:
            continue
        text = _strip_tags(row)
        for link in links:
            if not re.search(r"\.(?:pdf|htm)(?:$|\?)", link, re.I):
                continue
            documents.append(
                {
                    "title": text,
                    "url": urllib.parse.urljoin(HKEX_BASE, link),
                    "stock_id": stock_id,
                    "short_name": short_name,
                }
            )
    return documents, stock_id


def choose_prospectus(documents: List[Dict[str, str]]) -> Optional[Dict[str, str]]:
    def score(document: Dict[str, str]) -> int:
        title = document.get("title", "").lower()
        url = document.get("url", "").lower()
        points = 0
        if url.endswith(".pdf"):
            points += 20
        if "listing documents" in title or "上市文件" in title:
            points += 50
        if "offer for subscription" in title or "global offering" in title or "全球發售" in title:
            points += 30
        if "formal notice" in title or "allotment results" in title:
            points -= 40
        return points

    candidates = [item for item in documents if score(item) >= 70]
    return max(candidates, key=score) if candidates else None


def download_prospectus(document: Dict[str, str], output: Path, timeout: int = 60) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and output.stat().st_size > 10_000:
        return output
    output.write_bytes(_request(document["url"], timeout=timeout))
    return output


def extract_pdf_text(pdf_path: Path, text_path: Path) -> str:
    if text_path.exists() and text_path.stat().st_size > 1_000:
        return text_path.read_text(encoding="utf-8")
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError(
            "缺少 pypdf；请运行 python3 -m pip install -r requirements.txt"
        ) from exc
    reader = PdfReader(str(pdf_path))
    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            pages.append("")
    text = "\n\f\n".join(pages)
    text_path.write_text(text, encoding="utf-8")
    return text


def _flat(text: str) -> str:
    text = text.replace("\u00a0", " ").replace("\u200b", "")
    text = re.sub(r"-\s*\n\s*", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _percentage(patterns: List[str], text: str) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, re.I | re.S)
        if match:
            return f"{float(match.group(1)):g}%"
    return ""


def _money_to_yi(amount: str, unit: str) -> str:
    number = float(amount.replace(",", ""))
    lowered = unit.lower()
    if "million" in lowered or "百万" in unit or "百萬" in unit:
        number /= 100
    elif "billion" in lowered:
        number *= 10
    return f"{number:.2f}亿港元"


def _extract_sponsor_names(text: str) -> List[str]:
    names = []
    patterns = (
        r"[“\"]Sole Sponsor[”\"]\s+([A-Z][A-Za-z0-9&()'’.,\- ]{3,140}?(?:Limited|Corporation))\b",
        r"[“\"]Joint Sponsors?[”\"]\s+([A-Z][A-Za-z0-9&()'’.,\- ]{3,140}?(?:Limited|Corporation))\b",
        r"(?:Sole Sponsor|Joint Sponsors?)\s*[：:]?\s*\n+\s*([^\n]{3,160}?(?:Limited|Corporation))\s*(?:\n|$)",
        r"(?:獨家保薦人|聯席保薦人|保薦人)\s*[：:]?\s*\n+\s*([^\n]{2,100}(?:有限公司|公司))\s*(?:\n|$)",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.I):
            name = re.sub(r"\s+", " ", match.group(1)).strip(" ,，")
            if name and name not in names:
                names.append(name)

    parties = re.search(
        r"^PARTIES INVOLVED IN THE GLOBAL OFFERING\s*$", text, re.M | re.I
    )
    if parties:
        lines = [
            re.sub(r"\s+", " ", line).strip()
            for line in text[parties.end() : parties.end() + 5_000].splitlines()
        ]
        suffix = re.compile(r"(?:Limited|L\.L\.C\.|Company,? Limited)$", re.I)
        role = re.compile(
            r"(?:Sponsors?|Coordinators?|Representatives?|Bookrunners?|Lead Managers?|Intermediaries)$",
            re.I,
        )
        next_role = re.compile(
            r"^(?:Sponsor-|Overall Coordinator|Joint Overall|Joint Representatives?|Bookrunner|Lead Manager|Capital Market|Legal)",
            re.I,
        )
        address = re.compile(
            r"^(?:\(?in alphabetical order\)?|(?:Hong Kong|Central|Admiralty|PRC|China)$|\d|#|.*(?:Road|Street|Place|Square|Centre|Center|Floor|House|Tower|Queensway)$)",
            re.I,
        )
        pending: List[str] = []
        found_in_parties = False
        for raw_line in lines:
            line = re.sub(
                r"^(?:Sole|Joint) Sponsors?(?:\s+and\s+Sponsor-Overall\s+Coordinators?)?\s+",
                "",
                raw_line,
                flags=re.I,
            )
            if found_in_parties and (
                role.search(raw_line) or next_role.search(raw_line)
            ):
                break
            if not line or role.search(line) or address.search(line):
                pending = []
                continue
            pending.append(line)
            if suffix.search(line):
                candidate = " ".join(pending)
                candidate = candidate.replace("Internat ional", "International")
                candidate = candidate.replace("Securi ties", "Securities")
                if candidate not in names:
                    names.append(candidate)
                pending = []
                found_in_parties = True
    deduped = [
        name
        for name in names
        if not any(
            other != name and other.lower().startswith(name.lower() + " ")
            for other in names
        )
    ]
    return deduped[:3]


def _extract_cornerstone_range(text: str) -> str:
    start = re.search(
        r"^(?:THE CORNERSTONE (?:PLACING|INVESTMENT)|We have entered into cornerstone investment agreements)\s*$",
        text,
        re.I | re.M,
    )
    if not start:
        start = re.search(
            r"We(?:, the Joint Sponsors and the Overall Coordinators)? have entered into cornerstone\s+investment agreements",
            text,
            re.I,
        )
    if not start:
        return ""
    section = text[start.start() : start.start() + 8_000]
    cleaned = re.sub(r"/H\d{4}", " ", _flat(section))
    rows = re.findall(
        r"([\d.]+)%\s+([\d.]+)%\s+([\d.]+)%\s+([\d.]+)%",
        cleaned,
    )
    percentages = []
    for row in rows:
        percentages.extend([float(row[0]), float(row[2])])
    direct = re.findall(
        r"representing.{0,80}?(?:\([ivx]+\)\s*)?(?:approximately\s+)?([\d.]+)%\s+of\s+(?:the\s+)?(?:H Shares offered|Offer Shares)",
        cleaned,
        re.I | re.S,
    )
    percentages.extend(float(value) for value in direct)
    exercised = re.findall(
        r"(?:or|and)\s*\(ii\)\s*(?:approximately\s+)?([\d.]+)%\s+of\s+(?:the\s+)?(?:H Shares offered|Offer Shares)",
        cleaned,
        re.I | re.S,
    )
    percentages.extend(float(value) for value in exercised)
    percentages = [value for value in percentages if 0 < value <= 100]
    if not percentages:
        return ""
    low = min(percentages)
    high = max(percentages)
    return f"{low:g}%" if low == high else f"{low:g}%-{high:g}%"


def parse_official_text(text: str) -> Dict[str, Dict[str, str]]:
    """Extract high-value fields and an explicit status from prospectus text."""
    flat = _flat(text)
    lowered = flat.lower()
    results: Dict[str, Dict[str, str]] = {}

    greenshoe_pct = _percentage(
        [
            r"Over-allotment Option.{0,2500}?represent(?:ing|s)?\s+(?:not more than\s+)?(?:approximately\s+)?([\d.]+)%\s+of\s+(?:the\s+)?(?:Offer Shares|number of Offer Shares)",
            r"超額配股權.{0,1200}?(?:不超過|最多|約)?\s*([\d.]+)%\s*(?:的)?(?:發售股份|全球發售)",
        ],
        flat,
    )
    if greenshoe_pct:
        results["greenshoe"] = {
            "value": f"✅ 有（上限{greenshoe_pct}）",
            "status": "official_confirmed",
            "note": "比例来自港交所招股书超额配股权条款",
        }
    elif "over-allotment option" in lowered or "超額配股權" in flat:
        results["greenshoe"] = {
            "value": UNKNOWN,
            "status": "parse_failed",
            "note": "招股书出现超额配股权条款，但比例规则未命中",
        }
    else:
        results["greenshoe"] = {
            "value": "❌ 无绿鞋",
            "status": "derived",
            "note": "已扫描完整招股书，未发现超额配股权条款",
        }

    cornerstone_pct = _extract_cornerstone_range(text) or _percentage(
        [
            r"Cornerstone (?:Investors?|Placing).{0,6000}?represent(?:ing|s)?\s+(?:approximately\s+)?([\d.]+)%\s+of\s+(?:the\s+)?(?:Offer Shares|Global Offering)",
            r"基石(?:投資者|配售).{0,3000}?(?:佔|占).{0,100}?(?:發售股份|全球發售).*?([\d.]+)%",
        ],
        flat,
    )
    has_cornerstone = bool(
        re.search(r"\bCORNERSTONE INVESTORS?\b", text, re.I)
        or "基石投資者" in text
    )
    if cornerstone_pct:
        results["cornerstone"] = {
            "value": f"✅ 有（约{cornerstone_pct}，招股书情景范围）",
            "status": "official_confirmed",
            "note": "占比来自港交所招股书基石投资者章节",
        }
    elif has_cornerstone:
        results["cornerstone"] = {
            "value": "✅ 有（占比解析失败）",
            "status": "partial",
            "note": "招股书确认有基石投资者，但占比规则未命中",
        }
    else:
        results["cornerstone"] = {
            "value": "❌ 无基石",
            "status": "derived",
            "note": "已扫描完整招股书，未发现基石投资者章节",
        }

    ah_patterns = (
        r"(?:our|the Company.?s?)\s+A Shares.{0,1800}?(Shanghai|Shenzhen) Stock Exchange.{0,800}?(?:stock code|Stock Code)\s*[：:]?\s*(\d{6})",
        r"(?:our|the Company.?s?)\s+A Shares.{0,1800}?(?:listed|traded).{0,400}?(Shanghai|Shenzhen) Stock Exchange.{0,800}?(?:stock code|Stock Code|stock abbreviation and code).{0,100}?(\d{6})",
        r"(?:our|the Company.?s?)\s+A Shares.{0,1200}?(?:stock code|Stock Code)\s*[：:]?\s*(\d{6}).{0,800}?(Shanghai|Shenzhen) Stock Exchange",
        r"(?:本公司|我們的)A股.{0,1200}?(上海|深圳)證券交易所.{0,500}?股份代號\s*[：:]?\s*(\d{6})",
    )
    ah_value = ""
    for index, pattern in enumerate(ah_patterns):
        match = re.search(pattern, flat, re.I | re.S)
        if not match:
            continue
        if index == 2:
            a_code, exchange = match.group(1), match.group(2)
        else:
            exchange, a_code = match.group(1), match.group(2)
        suffix = "SH" if exchange.lower().startswith(("shanghai", "上")) else "SZ"
        ah_value = f"✅ A+H（{a_code}.{suffix}）"
        break
    if ah_value:
        results["a_h"] = {
            "value": ah_value,
            "status": "official_confirmed",
            "note": "A股代码及交易所来自港交所招股书",
        }
    elif "proposed a share listing" in lowered or "建議a股上市" in lowered:
        results["a_h"] = {
            "value": "❌ 尚非A+H（招股书披露拟A股上市）",
            "status": "official_confirmed",
            "note": "港交所招股书仅披露拟议A股上市，当前未见已上市A股",
        }
    else:
        results["a_h"] = {
            "value": "❌ 纯H股（招股书未见已上市A股）",
            "status": "derived",
            "note": "基于完整招股书未检出发行人已上市A股的推断",
        }

    sponsor_names = _extract_sponsor_names(text)
    if sponsor_names:
        results["sponsors"] = {
            "value": "、".join(sponsor_names),
            "status": "official_confirmed",
            "note": "名称来自港交所招股书保荐人栏目",
        }
    else:
        results["sponsors"] = {
            "value": UNKNOWN,
            "status": "parse_failed" if "sponsor" in lowered or "保薦人" in text else "source_not_disclosed",
            "note": "招股书已获取，但保荐人名称规则未命中",
        }

    fundraising_match = re.search(
        r"net proceeds.{0,1200}?(?:estimated to be|will be|of)\s+(?:approximately\s+)?HK\$\s*([\d,.]+)\s*(million|billion)",
        flat,
        re.I | re.S,
    ) or re.search(
        r"所得款項淨額.{0,500}?約?\s*([\d,.]+)\s*(百萬|百万|億)港元",
        flat,
        re.S,
    )
    if fundraising_match:
        results["fundraising"] = {
            "value": _money_to_yi(fundraising_match.group(1), fundraising_match.group(2)),
            "status": "official_confirmed",
            "note": "募资净额来自港交所招股书所得款项章节",
        }
    else:
        results["fundraising"] = {
            "value": UNKNOWN,
            "status": "parse_failed" if "net proceeds" in lowered or "所得款項淨額" in text else "source_not_disclosed",
            "note": "招股书已获取，但募资净额规则未命中",
        }
    return results


def merge_official_fields(
    record: Dict[str, Any],
    parsed: Dict[str, Dict[str, str]],
    source_url: str,
    retrieved_at: str,
) -> Dict[str, Any]:
    result = normalize_ipo(record)
    metadata = result.setdefault("field_meta", {})
    for field in OFFICIAL_FIELDS:
        evidence = parsed.get(field, {})
        value = evidence.get("value", UNKNOWN)
        previous = result.get(field)
        note = evidence.get("note", "")
        if not is_unknown(value):
            if not is_unknown(previous) and str(previous) != str(value):
                note = f"{note}；港交所值覆盖摘要源值：{previous}".strip("；")
            result[field] = value
        metadata[field] = make_field_meta(
            value=result.get(field),
            status=evidence.get("status", "parse_failed"),
            source_name="港交所披露易",
            source_url=source_url,
            retrieved_at=retrieved_at,
            note=note,
        )
    result["official_prospectus_url"] = source_url
    result["official_checked_at"] = retrieved_at
    if "港交所披露易（招股书）" not in result.get("source", ""):
        result["source"] = f"{result.get('source', '')}；港交所披露易（招股书）".strip("；")
    return normalize_ipo(result)


def _mark_official_failure(
    record: Dict[str, Any], status: str, note: str, checked_at: str
) -> Dict[str, Any]:
    result = normalize_ipo(record)
    metadata = result.setdefault("field_meta", {})
    for field in OFFICIAL_FIELDS:
        old = metadata.get(field, {}) if isinstance(metadata.get(field), dict) else {}
        if is_unknown(result.get(field)) or old.get("status") in {
            "partial",
            "authoritative_source_not_fetched",
            "untraced",
        }:
            metadata[field] = make_field_meta(
                value=result.get(field),
                status=status,
                source_name="港交所披露易",
                retrieved_at=checked_at,
                note=note,
            )
    result["official_checked_at"] = checked_at
    return normalize_ipo(result)


def enrich_records(
    records: List[Dict[str, Any]],
    raw_dir: Path,
    lookback_days: int = 45,
    timeout: int = 60,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    raw_dir.mkdir(parents=True, exist_ok=True)
    checked_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    end = date.today()
    start = end - timedelta(days=lookback_days)
    enriched = []
    audit: Dict[str, Any] = {
        "checked_at": checked_at,
        "date_range": [start.isoformat(), end.isoformat()],
        "records": [],
    }
    for record in records:
        code = str(record.get("code", "")).zfill(5)
        item_audit: Dict[str, Any] = {"code": code, "name": record.get("name", "")}
        try:
            documents, stock_id = search_documents(code, start, end, timeout=timeout)
            item_audit["stock_id"] = stock_id
            item_audit["document_count"] = len(documents)
            prospectus = choose_prospectus(documents)
            if not prospectus:
                note = "港交所标题检索未返回招股书 PDF"
                enriched.append(
                    _mark_official_failure(
                        record, "official_document_not_found", note, checked_at
                    )
                )
                item_audit.update({"status": "official_document_not_found", "note": note})
                audit["records"].append(item_audit)
                continue
            item_audit["prospectus_url"] = prospectus["url"]
            pdf_path = raw_dir / f"{code}_prospectus.pdf"
            text_path = raw_dir / f"{code}_prospectus.txt"
            download_prospectus(prospectus, pdf_path, timeout=timeout)
            text = extract_pdf_text(pdf_path, text_path)
            if len(text.strip()) < 1_000:
                raise RuntimeError("招股书可提取文字少于 1,000 字符，可能需要 OCR")
            parsed = parse_official_text(text)
            enriched.append(
                merge_official_fields(
                    record, parsed, prospectus["url"], checked_at
                )
            )
            item_audit.update(
                {
                    "status": "success",
                    "text_characters": len(text),
                    "fields": {
                        field: {
                            "status": parsed[field]["status"],
                            "value": parsed[field]["value"],
                        }
                        for field in OFFICIAL_FIELDS
                    },
                }
            )
        except Exception as exc:
            note = f"{type(exc).__name__}: {exc}"
            enriched.append(
                _mark_official_failure(
                    record, "official_document_fetch_failed", note, checked_at
                )
            )
            item_audit.update({"status": "official_document_fetch_failed", "note": note})
        audit["records"].append(item_audit)
    return enriched, audit


def main() -> int:
    parser = argparse.ArgumentParser(description="港交所招股书自动发现与字段补全")
    parser.add_argument("--input", "-i", required=True, help="抓取阶段 JSON")
    parser.add_argument("--output", "-o", required=True, help="补全后的 JSON")
    parser.add_argument("--raw-dir", required=True, help="招股书 PDF 与提取文本目录")
    parser.add_argument("--audit-output", help="港交所补全审计 JSON")
    parser.add_argument("--lookback-days", type=int, default=45)
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()

    with open(args.input, "r", encoding="utf-8") as handle:
        records = extract_records(json.load(handle))
    enriched, audit = enrich_records(
        records,
        raw_dir=Path(args.raw_dir),
        lookback_days=args.lookback_days,
        timeout=args.timeout,
    )
    Path(args.output).write_text(
        json.dumps(enriched, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if args.audit_output:
        Path(args.audit_output).write_text(
            json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    success = sum(item.get("status") == "success" for item in audit["records"])
    print(f"✅ 港交所招股书补全完成：{success}/{len(enriched)} 只成功", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
