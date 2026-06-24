#!/usr/bin/env python3
"""
IPO 数据补全器 — 从金吾资讯个股详情页抓取招股章程数据。

用法：
    # 从已有基础 IPO 列表补全
    python enrich_ipos.py --input ipos_basic.json > ipos_enriched.json

    # 指定输出文件
    python enrich_ipos.py --input ipos_basic.json --output ipos.json

数据源：金吾资讯 (ipo.jinwucj.com) 个股详情页
URL 模式：/stock/stockDetails/prospectus/{CODE}.hk?name={NAME}&listed=0&industry={INDUSTRY_CODE}

补全字段：
    - offer_price（招股价范围）
    - board_lot（每手股数）
    - entry_fee（入场费）
    - closing_date / listing_date（从招股日期推导）
    - total_shares / market_cap / public_pct
    - greenshoe（超额配股权）
    - 基石投资者 / 保荐人（如有）
"""

import json
import re
import sys
import argparse
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')


def extract(text: str, patterns: list[str]) -> str:
    """用多个正则模式依次尝试提取字段"""
    for p in patterns:
        m = re.search(p, text)
        if m:
            return m.group(1).strip()
    return ""


def scrape_detail(code: str, name: str, industry_code: str = "") -> dict:
    """
    通过 HTTP 请求抓取金吾资讯个股详情页（需要 Playwright）。
    如果 Playwright 不可用，返回空 dict 并打印警告。
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(f"⚠️  Playwright 不可用，跳过 {name}({code}) 的详情抓取。请先安装: pip install playwright && playwright install chromium", file=sys.stderr)
        return {}

    url = (
        f"https://ipo.jinwucj.com/stock/stockDetails/prospectus/{code}.hk"
        f"?name={name}&listed=0&industry={industry_code}"
    )

    result = {"code": code, "name": name}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto(url, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(3000)
            text = page.text_content("body") or ""
            text = re.sub(r"\s+", " ", text).strip()
        except Exception as e:
            print(f"❌ {name}({code}) 页面加载失败: {e}", file=sys.stderr)
            browser.close()
            return result
        browser.close()

    # --- 提取字段 ---
    result["offer_price"] = extract(text, [
        r"招股价范围[：:]\s*([\d.]+~[\d.]+\s*港[币元])",
        r"招股价[：:]\s*([\d.]+~[\d.]+\s*港[币元])",
        r"發售價[：:]\s*([\d.]+~[\d.]+\s*港[币元])",
    ])
    result["board_lot"] = int(lot) if (lot := extract(text, [
        r"每手股数[：:]\s*(\d+)\s*股",
    ])) else 0
    result["entry_fee"] = extract(text, [
        r"入场费[：:]\s*([\d.]+\s*港[币元])",
        r"入場費[：:]\s*([\d.]+\s*港[币元])",
    ])
    sub_period = extract(text, [
        r"招股日期[：:]\s*(\d{4}-\d{2}-\d{2}\s*至\s*\d{4}-\d{2}-\d{2})",
    ])
    if sub_period:
        dates = re.findall(r"\d{4}-\d{2}-\d{2}", sub_period)
        if len(dates) >= 2:
            result["subscription_start"] = dates[0]
            result["closing_date"] = dates[1]
    result["result_date"] = extract(text, [
        r"公布售股结果日期[：:]\s*(\d{4}-\d{2}-\d{2})",
    ])
    result["listing_date"] = extract(text, [
        r"上市日期[：:]\s*(\d{4}-\d{2}-\d{2})",
    ])
    result["total_shares"] = extract(text, [
        r"总发售数量[：:]\s*([\d.]+\s*万?\s*股)",
    ])
    result["market_cap"] = extract(text, [
        r"预计市值[：:]\s*([\d.]+\s*亿)",
    ])
    result["public_pct"] = extract(text, [
        r"公开发售[：:]\s*([\d.]+%)",
    ])
    result["sponsors"] = extract(text, [
        r"保荐人[：:]\s*(.+?)(?:。|$)",
        r"獨家保薦人[：:]\s*(.+?)(?:。|$)",
        r"聯席保薦人[：:]\s*(.+?)(?:。|$)",
    ])
    result["cornerstone"] = extract(text, [
        r"基石投資者[：:]\s*(.+?)(?:。|$)",
        r"基石投资者[：:]\s*(.+?)(?:。|$)",
    ])
    result["greenshoe"] = "yes" if "超额配股权" in text else ("no" if "无超额配股权" in text else "")
    result["a_h"] = "A+H" if any(kw in text for kw in ["A股", "A+H", "两地上市"]) else ""
    result["description"] = extract(text, [
        r"所属行业[：:]\s*(.+?)(?:\s|$)",
    ])

    # 如果 offer_price 为空但 entry_fee 和 board_lot 都有，推导价格
    if not result.get("offer_price") and result.get("entry_fee") and result.get("board_lot"):
        try:
            fee_num = float(re.search(r"[\d.]+", result["entry_fee"]).group())
            price_est = round(fee_num / result["board_lot"], 1)
            result["offer_price"] = f"~{price_est} HKD"
        except Exception:
            pass

    return result


def merge_details(basic_ipos: list[dict], details: dict[str, dict]) -> list[dict]:
    """将详情数据合并到基础 IPO 记录中"""
    for ipo in basic_ipos:
        code = ipo.get("code", "")
        detail = details.get(code, {})
        if not detail:
            continue
        # 只覆盖有值的字段
        for key in ("offer_price", "board_lot", "entry_fee", "closing_date",
                     "listing_date", "total_shares", "market_cap", "public_pct",
                     "sponsors", "cornerstone", "greenshoe", "a_h", "description"):
            val = detail.get(key)
            if val:
                ipo[key] = val
    return basic_ipos


def main():
    parser = argparse.ArgumentParser(description="IPO 数据补全器")
    parser.add_argument("--input", "-i", required=True, help="基础 IPO JSON 文件")
    parser.add_argument("--output", "-o", help="输出文件（默认 stdout）")
    parser.add_argument("--details", "-d", help="预抓取的详情 JSON 文件（跳过实时抓取）")
    parser.add_argument("--scrape", action="store_true", help="启用 Playwright 实时抓取")
    args = parser.parse_args()

    # 加载基础数据
    with open(args.input, "r", encoding="utf-8") as f:
        basic = json.load(f)

    if isinstance(basic, dict) and "active_ipos" in basic:
        basic = basic["active_ipos"]

    # 获取详情数据
    if args.details:
        with open(args.details, "r", encoding="utf-8") as f:
            details = json.load(f)
        print(f"📥 从 {args.details} 加载 {len(details)} 条详情", file=sys.stderr)
    elif args.scrape:
        details = {}
        for ipo in basic:
            code = ipo.get("code", "")
            name = ipo.get("name", "")
            industry = ipo.get("industry", "").split("[")[-1].rstrip("]") if "[" in ipo.get("industry", "") else ""
            # 从 industry 字符串中提取行业代码（如 "050203"）
            ind_code = ipo.get("industry", "")
            result = scrape_detail(code, name, ind_code)
            if result:
                details[code] = result
                print(f"✅ {name}({code}): {result.get('offer_price','?')} | {result.get('entry_fee','?')}", file=sys.stderr)
    else:
        print("⚠️  未指定 --details 或 --scrape，仅做字段补齐不做实时抓取", file=sys.stderr)
        details = {}

    # 合并
    enriched = merge_details(basic, details)

    # 输出
    output = json.dumps(enriched, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"✅ 已写入 {args.output} ({len(enriched)} 只)", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
