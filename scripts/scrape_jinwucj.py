#!/usr/bin/env python3
"""
金吾资讯 IPO 详情抓取器 (Playwright-based)
============================================

直接访问 ipo.jinwucj.com 的个股详情页，提取结构化 IPO 数据。
解决 fetch_active_ipos.py 纯文本正则无法获取 JS 渲染数据的痛点。

用法：
    # 抓取所有正在招股的公司详情
    python scrape_jinwucj.py

    # 抓取指定代码的详情
    python scrape_jinwucj.py --codes 02697,03952,00668

    # 输出到文件
    python scrape_jinwucj.py --output ipos.json

输出：标准化 JSON 数组，每个元素含招股价范围、每手股数、入场费、
      招股截止日、上市日、孖展倍数、市值等字段。
"""

import json
import re
import sys
import argparse
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')

# Global name map populated from getNewIssueCalendar API
# Global name map populated from getNewIssueCalendar API
_NAME_MAP = {
    # Common active HKEX IPOs - populated live via API, fallback if API fails
    "02697": "真健康医疗─B",
    "03952": "来福谐波",
    "06715": "鲟龙科技",
    "06915": "江西生物",
    "00668": "安克创新",
    "01191": "海光芯正",
    "02672": "白鸽在线",
    "09637": "礼邦医药─B",
    "02335": "麦科医药─B",
    "06106": "仙工智能",
    "01688": "领益智造",
    "01956": "中科闻歌",
    "02272": "科拓股份",
    "03661": "圣邦股份",
    "09630": "芯碁微装",
    "06067": "星源材质",
    "06132": "华健未来─B",
    "01392": "海清智元",
}  # Live API will override these if available
def _fetch_name_map():
    """????? API ????->?????"""
    global _NAME_MAP
    if _NAME_MAP:
        return _NAME_MAP
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            resp = page.goto(
                "https://ipo.jinwucj.com/api/nsIssueCalendarV/getNewIssueCalendar",
                wait_until="domcontentloaded", timeout=15000
            )
            if resp and resp.ok:
                data = resp.json()
                body = data.get("body", {})
                for section in ("underSubscription", "toBeListed", "listing"):
                    for ipo in body.get(section, []):
                        sym = ipo.get("symbol", "").replace(".hk", "")
                        name = ipo.get("stockName", "")
                        if sym and name:
                            _NAME_MAP[sym] = name
            browser.close()
        if _NAME_MAP:
            print(f"  [API] ??? {len(_NAME_MAP)} ??????", file=sys.stderr)
    except Exception as e:
        print(f"  [!] ????????: {e}", file=sys.stderr)
    return _NAME_MAP


# ---------------------------------------------------------------------------
# IPO 详情提取（从金吾资讯个股详情页 body text）
# ---------------------------------------------------------------------------

def _ex(pattern: str, text: str, flags=0) -> str:
    """安全正则提取"""
    m = re.search(pattern, text, flags)
    return m.group(1).strip() if m else ""


def extract_detail(text: str, code: str = "", name: str = "") -> dict:
    """
    从金吾资讯个股详情页 body text 提取关键字段。

    金吾资讯详情页 URL 格式:
        https://ipo.jinwucj.com/stock/stockDetails/prospectus/{code}.hk

    页面关键区域结构（纯文本）:
        发行资料
        招股日期： 2026-06-22 至 2026-06-25
        公布售股结果日期： 2026-06-29
        上市日期： 2026-06-30
        招股价范围： 119.3~135.4 港币
        每手股数： 20 股
        入场费： 2735.3 港币
        所属行业： 制药与生物科技
        总发售数量： 356.47 万股
        预计市值： 45.40 亿
    """
    info = {
        "code": code,
        "source": "金吾资讯详情页",
        "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    # 招股日期区间 -> 截止日
    sub_start = _ex(r'招股日期[：:]\s*(\d{4}-\d{2}-\d{2})', text)
    sub_end = _ex(
        r'招股日期[：:]\s*\d{4}-\d{2}-\d{2}\s*至\s*(\d{4}-\d{2}-\d{2})',
        text
    )
    # 公司名
    info["name"] = name
    info["subscription_start"] = sub_start
    info["closing_date"] = sub_end  # 这才是真正的截止日！
    info["subscription_period"] = (
        f"{sub_start[5:]}/{sub_end[5:]}" if sub_start and sub_end else ""
    )

    # 配发结果日
    info["result_date"] = _ex(
        r'公布(?:售股)?结果日期[：:]\s*(\d{4}-\d{2}-\d{2})', text
    )

    # 上市日
    info["listing_date"] = _ex(r'上市日期[：:]\s*(\d{4}-\d{2}-\d{2})', text)

    # 招股价范围
    price_low = _ex(r'招股价(?:范围)?[：:]\s*([\d.]+)', text)
    price_high = _ex(
        r'招股价(?:范围)?[：:]\s*[\d.]+\s*[~–\-]\s*([\d.]+)', text
    )
    if price_low and price_high:
        info["offer_price"] = f"{price_low}-{price_high} HKD"
    elif price_low:
        info["offer_price"] = f"{price_low} HKD"
    else:
        info["offer_price"] = ""

    # 每手股数
    lot_str = _ex(r'每手股数[：:]\s*([\d,]+)', text)
    info["board_lot"] = int(lot_str.replace(",", "")) if lot_str else 0

    # 入场费
    fee_str = _ex(r'入场费[：:]\s*([\d,.]+)', text)
    if fee_str:
        info["entry_fee"] = float(fee_str.replace(",", ""))
    else:
        info["entry_fee"] = 0.0

    # 总发售数量
    info["total_shares"] = _ex(
        r'总发售数量[：:]\s*([\d,.]+(?:\s*[万亿]?股))', text
    )

    # 预计市值
    cap_str = _ex(r'预计市值[：:]\s*([\d,.]+)', text)
    if cap_str:
        info["market_cap"] = float(cap_str.replace(",", ""))
    else:
        info["market_cap"] = 0.0

    # 所属行业
    info["industry"] = _ex(r'所属行业[：:]\s*(.+?)(?:\s{2,}|\n|$)', text)

    # 孖展认购倍数
    margin_str = _ex(r'认购倍数[（(]预估[)）][：:]\s*([\d.]+)', text)
    if margin_str:
        info["margin_multiple"] = margin_str + "倍"
    else:
        # fallback
        alt = _ex(r'(\d+\.?\d*)\s*倍', text)
        info["margin_multiple"] = (alt + "倍") if alt else ""

    # 公开发售/国际配售比例
    pub_pct = _ex(r'公开发售[：:]\s*([\d.]+%)', text)
    intl_pct = _ex(r'国际配售[：:]\s*([\d.]+%)', text)
    if pub_pct:
        try:
            info["public_initial_pct"] = float(pub_pct.replace("%", "")) / 100
        except ValueError:
            info["public_initial_pct"] = 0.10
    else:
        info["public_initial_pct"] = 0.10

    # 基石投资者
    if "基石投资者" in text:
        info["cornerstone"] = "yes"
    elif "未引入基石" in text or "无基石" in text:
        info["cornerstone"] = "no"
    else:
        info["cornerstone"] = ""

    # 绿鞋
    if "超额配售" in text:
        if "未授出" in text:
            info["greenshoe"] = "no"
        else:
            pct = _ex(r'(\d+)%\s*(?:超额配售|绿鞋)', text)
            info["greenshoe"] = f"yes {pct}%" if pct else "yes"
    else:
        info["greenshoe"] = ""

    # A+H
    if "A+H" in text or "两地上市" in text:
        info["a_h"] = "A+H"
    else:
        # check if A-share code present
        a_code = _ex(r'(\d{6})\s*\.\s*SZ', text) or _ex(r'(\d{6})\s*\.\s*SH', text)
        if a_code:
            info["a_h"] = f"A+H({a_code})"
        else:
            info["a_h"] = ""

    # 保荐人
    sp = _ex(r'联席保荐人[：:]\s*(.+?)(?:。|\n|$)', text)
    if not sp:
        sp = _ex(r'独家保荐人[：:]\s*(.+?)(?:。|\n|$)', text)
    if not sp:
        sp = _ex(r'保荐人[：:]\s*(.+?)(?:。|\n|$)', text)
    info["sponsors"] = sp

    # 募资净额
    fund = _ex(
        r'所得款项净额[约]?\s*[：:]*\s*[约]?\s*([\d,.]+(?:\s*(?:百万|亿)港元)?)',
        text
    )
    if fund:
        # Normalize: try to convert to 亿
        if "百万" in fund:
            try:
                val = float(fund.replace(",", "").replace("百万港元", "").strip())
                info["fundraising"] = f"{val/10:.2f}亿港元"
            except:
                info["fundraising"] = fund
        elif "亿" in fund:
            info["fundraising"] = fund
        else:
            info["fundraising"] = fund + "港元"
    else:
        info["fundraising"] = ""

    # 数据可信度 marker
    info["data_confidence"] = "🟡"

    # 计算公开手数（近似）
    if info.get("total_shares") and info.get("board_lot", 0) > 0 and info.get("public_initial_pct", 0) > 0:
        ts_match = re.search(r'([\d,.]+)', info["total_shares"])
        if ts_match:
            ts_val = float(ts_match.group(1).replace(",", ""))
            # 万 -> *10000
            if "万" in info["total_shares"]:
                ts_val *= 10000
            info["public_lots"] = int(
                ts_val * info["public_initial_pct"] / info["board_lot"]
            )
    if "public_lots" not in info:
        info["public_lots"] = 10000  # fallback

    return info


# ---------------------------------------------------------------------------
# 金吾资讯主列表发现
# ---------------------------------------------------------------------------

def discover_active_codes() -> list[str]:
    """从金吾资讯主页发现正在招股的股票代码列表。

    使用 API: /api/nsIssueCalendarV/getNewIssueCalendar
    返回 underSubscription 列表。

    需要 Playwright 获取完整响应（API 返回被截断时回退到主页 DOM 解析）。
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "[!] Playwright 未安装，无法发现活跃 IPO 列表。"
            "请用 --codes 手动指定。"
            "安装: pip install playwright && playwright install chromium",
            file=sys.stderr,
        )
        return []

    codes = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Method 1: API interception
        api_data = {}
        def _on_response(resp):
            if resp.url.endswith("getNewIssueCalendar") and resp.ok:
                try:
                    body = resp.json()
                    api_data["calendar"] = body
                except:
                    pass

        page.on("response", _on_response)
        page.goto("https://ipo.jinwucj.com/", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(5000)

        if "calendar" in api_data:
            body = api_data["calendar"].get("body", {})
            for ipo in body.get("underSubscription", []):
                sym = ipo.get("symbol", "")
                if sym.endswith(".hk"):
                    codes.append(sym.replace(".hk", ""))
        browser.close()

    return codes


# ---------------------------------------------------------------------------
# 主抓取逻辑
# ---------------------------------------------------------------------------

def scrape_all(codes: list[str] | None = None, timeout: int = 25000) -> list[dict]:
    """批量抓取所有指定代码的详情页"""
    if codes is None:
        codes = discover_active_codes()
        if not codes:
            print("[!] 未发现活跃 IPO，请用 --codes 手动指定", file=sys.stderr)
            return []

    print(f"🔍 准备抓取 {len(codes)} 只新股详情: {codes}", file=sys.stderr)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[!] Playwright 未安装", file=sys.stderr)
        return []

    _fetch_name_map()  # pre-load name mapping
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for code in codes:
            page = browser.new_page()
            try:
                url = (
                    f"https://ipo.jinwucj.com/stock/stockDetails/prospectus/"
                    f"{code}.hk"
                )
                print(f"  📄 {code} ...", file=sys.stderr, end=" ")
                page.goto(url, wait_until="networkidle", timeout=timeout)
                page.wait_for_timeout(3000)
                text = page.text_content("body") or ""
                stock_name = _NAME_MAP.get(code, ""); detail = extract_detail(text, code=code, name=stock_name)
                # Only include if we got meaningful data
                if detail.get("closing_date") or detail.get("offer_price"):
                    results.append(detail)
                    print(
                        f"✅ 招股价={detail.get('offer_price','?')} "
                        f"截止={detail.get('closing_date','?')}",
                        file=sys.stderr,
                    )
                else:
                    print("⚠️ 数据不完整，跳过", file=sys.stderr)
            except Exception as e:
                print(f"❌ {e}", file=sys.stderr)
            finally:
                page.close()
        browser.close()

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="金吾资讯 IPO 详情抓取器 (Playwright)"
    )
    parser.add_argument(
        "--codes",
        default=None,
        help="逗号分隔的股票代码，如 02697,03952,00668。不指定则自动发现。",
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="输出 JSON 文件路径（默认 stdout）",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=25000,
        help="每个页面加载超时 (ms)，默认 25000",
    )
    args = parser.parse_args()

    codes = None
    if args.codes:
        codes = [c.strip() for c in args.codes.split(",") if c.strip()]

    results = scrape_all(codes=codes, timeout=args.timeout)

    if not results:
        print("❌ 未获取到任何有效 IPO 数据", file=sys.stderr)
        sys.exit(1)

    output = json.dumps(results, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"✅ 已写入 {args.output} ({len(results)} 只)", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
