#!/usr/bin/env python3
"""
HKEX IPO 数据抓取器
====================
使用 mmx search 抓取港交所正在招股的公司数据，
输出标准化 JSON 供 parse_conflict_matrix.py 使用。

用法：
    python fetch_active_ipos.py
    # 抓取当日数据，输出到 stdout

依赖：
    - mmx-cli (MiniMax Token Plan 搜索工具)
"""
import json
import subprocess
import re
from datetime import datetime, timedelta


def search_mmx(query: str, count: int = 10) -> list:
    """调用 mmx search，返回结果列表"""
    try:
        result = subprocess.run(
            ["mmx", "search", "query", query],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode != 0:
            return []

        data = json.loads(result.stdout)
        return data.get("organic", [])
    except Exception as e:
        print(f"[!] mmx 搜索失败: {e}", file=sys.stderr)
        return []


def parse_listing_date(date_str: str) -> str:
    """解析 '2026-06-24' 或 '6月24日' 格式日期"""
    if not date_str:
        return ""
    if re.match(r"\d{4}-\d{2}-\d{2}", date_str):
        return date_str[:10]
    m = re.search(r"(\d{1,2})月(\d{1,2})日", date_str)
    if m:
        year = datetime.now().year
        return f"{year}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    return date_str


def extract_ipo_from_snippet(snippet: str, title: str) -> dict:
    """
    从智通财经搜索结果中提取 IPO 关键信息

    关键字段：
    - 招股期: "6月15日至6月18日招股"
    - 上市日: "6月24日上市"
    - 发售价: "每股101.60港元"
    - 每手: "每手50股"
    - 募资: "10.7亿港元"
    """
    info = {
        "name": "",
        "code": "",
        "subscription_period": "",
        "closing_date": "",
        "listing_date": "",
        "offer_price": "",
        "board_lot": "",
        "fundraising": "",
        "sponsors": "",
        "cornerstone": "",
        "greenshoe": "",
        "a_h": ""
    }

    # 提取公司名（优先从标题）
    m = re.search(r"([^\(\)\,\uff08\u3001]+?)\s*[\(\uff08]?(\d{5})", title)
    if m:
        info["name"] = m.group(1).strip()
        info["code"] = m.group(2)

    # 招股期
    m = re.search(r"(\d{1,2})月(\d{1,2})日至(\d{1,2})月(\d{1,2})日招股", snippet)
    if m:
        info["subscription_period"] = f"{m.group(1)}/{m.group(2)}-{m.group(3)}/{m.group(4)}"
        info["closing_date"] = parse_listing_date(
            f"2026-{int(m.group(3)):02d}-{int(m.group(4)):02d}"
        )

    # 上市日
    m = re.search(r"(\d{1,2})月(\d{1,2})日.*?(?:挂牌|上市|买卖)", snippet)
    if m:
        info["listing_date"] = parse_listing_date(
            f"2026-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
        )

    # 发售价
    m = re.search(r"发售价.*?(\d+(?:\.\d+)?)港元", snippet)
    if m:
        info["offer_price"] = m.group(1) + " 港元"

    # 每手
    m = re.search(r"每手(\d+)股", snippet)
    if m:
        info["board_lot"] = m.group(1) + " 股"

    # 募资
    m = re.search(r"募资(?:约|最高)?(\d+(?:\.\d+)?)亿港元", snippet)
    if m:
        info["fundraising"] = m.group(1) + " 亿港元"

    # A+H
    if "A+H" in snippet or "两地上市" in snippet or re.search(r"00\d{4}\.SZ", snippet):
        info["a_h"] = "A+H"

    # 绿鞋
    if "超额配股权" in snippet:
        m = re.search(r"(\d+)%.*?超额配股权", snippet)
        info["greenshoe"] = f"✅ {m.group(1)}%" if m else "✅"
    elif "无.*?超额配股权" in snippet or "无.*?超配权" in snippet:
        info["greenshoe"] = "❌"

    # 基石
    if "基石" in snippet:
        m = re.search(r"基石.*?(?:认购|协议)", snippet)
        if m:
            info["cornerstone"] = "✅"
        elif "未引入基石" in snippet or "无基石" in snippet:
            info["cornerstone"] = "❌"
    else:
        info["cornerstone"] = "?"

    return info


def fetch_ipo_data() -> list:
    """主抓取函数"""
    queries = [
        '港交所 招股 2026年6月',
        '新股孖展 港股',
        '港股 IPO 周报',
    ]

    all_ipos = []
    seen_codes = set()

    for q in queries:
        results = search_mmx(q, count=15)
        for r in results:
            info = extract_ipo_from_snippet(r.get("snippet", ""), r.get("title", ""))
            if info["code"] and info["code"] not in seen_codes:
                seen_codes.add(info["code"])
                info["source"] = r.get("link", "")
                info["title"] = r.get("title", "")
                info["date"] = r.get("date", "")
                all_ipos.append(info)

    return all_ipos


def main():
    import sys
    print("🔍 正在抓取港交所正在招股的公司...", file=sys.stderr)

    ipos = fetch_ipo_data()

    print(f"✅ 找到 {len(ipos)} 家公司", file=sys.stderr)
    print(json.dumps(ipos, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
