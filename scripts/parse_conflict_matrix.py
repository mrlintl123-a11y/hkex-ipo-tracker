#!/usr/bin/env python3
"""
HKEX IPO 冲突矩阵计算器
========================
根据"招股截止日间隔 < 2 天 = 资金冲突"规则，
将多只新股按截止日分组，输出冲突矩阵和超级冲突组。

用法：
    python parse_conflict_matrix.py <<'EOF'
    [
      {"name": "海清智元", "code": "01392", "closing": "2026-06-16"},
      {"name": "星源材质", "code": "06067", "closing": "2026-06-17"},
      ...
    ]
    EOF
"""
import json
import sys
from datetime import datetime, timedelta
from collections import defaultdict
from itertools import combinations


def parse_date(s: str) -> datetime:
    """解析 YYYY-MM-DD 格式日期"""
    return datetime.strptime(s.strip(), "%Y-%m-%d")


def build_matrix(ipos: list) -> tuple:
    """
    构建冲突矩阵和超级冲突组

    Returns:
        (matrix_html, super_groups)
        matrix_html: HTML 格式的冲突矩阵
        super_groups: 超级冲突组列表（每组含多个新股）
    """
    n = len(ipos)
    if n == 0:
        return "", []

    # 1. 计算两两冲突
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py

    # 2. 截止日去重排序
    closing_dates = sorted({i["closing"] for i in ipos})

    # 3. 对每对截止日判定
    conflict_pairs = []
    for d1, d2 in combinations(closing_dates, 2):
        dt1, dt2 = parse_date(d1), parse_date(d2)
        diff = abs((dt2 - dt1).days)
        if diff < 2:  # 间隔 < 2 天 = 冲突
            conflict_pairs.append((d1, d2, diff))

    # 4. 用并查集求超级冲突组（按截止日）
    date_idx = {d: i for i, d in enumerate(closing_dates)}
    for d1, d2, _ in conflict_pairs:
        union(date_idx[d1], date_idx[d2])

    date_groups = defaultdict(list)
    for d in closing_dates:
        date_groups[find(date_idx[d])].append(d)

    # 5. 把新股归到对应日期组
    super_groups = []
    for root_id, dates in date_groups.items():
        group_ipos = [i for i in ipos if i["closing"] in dates]
        super_groups.append({
            "closing_dates": sorted(dates),
            "color": "🔴" if len(dates) > 1 or any(
                len([g for g in date_groups.values() if d in g]) > 1 for d in dates
            ) else "🟢",
            "ipos": group_ipos
        })

    # 6. 生成 HTML 矩阵
    matrix_html = "<table border='1' cellpadding='5'>\n"
    matrix_html += "<tr><th>截止日</th>"
    for d in closing_dates:
        matrix_html += f"<th>{d}</th>"
    matrix_html += "</tr>\n"

    for d1 in closing_dates:
        matrix_html += f"<tr><th>{d1}</th>"
        for d2 in closing_dates:
            if d1 == d2:
                matrix_html += "<td>—</td>"
            else:
                diff = abs((parse_date(d2) - parse_date(d1)).days)
                if diff < 2:
                    matrix_html += f"<td style='background:#fee'>🔴 {diff}天</td>"
                else:
                    matrix_html += f"<td style='background:#efe'>🟢 {diff}天</td>"
        matrix_html += "</tr>\n"
    matrix_html += "</table>"

    return matrix_html, super_groups


def format_markdown(ipos: list) -> str:
    """生成 Markdown 格式的冲突分析报告"""
    matrix_html, groups = build_matrix(ipos)

    md = "## ⚠️ 资金冲突矩阵\n\n"
    md += matrix_html.replace("<table", "<table style='border-collapse:collapse'") + "\n\n"
    md += "> 🔴 = 资金冲突 ｜ 🟢 = 资金可分流 ｜ 间隔 ≥ 2 天即可并行打新\n\n"

    md += "## 超级冲突组\n\n"
    for i, g in enumerate(groups, 1):
        color = "🔴 冲突组" if len(g["closing_dates"]) > 1 else "🟢 独立窗口"
        md += f"### {color}（截止日 {'/'.join(g['closing_dates'])}，{len(g['ipos'])} 只）\n\n"
        for ipo in g["ipos"]:
            md += f"- **{ipo['name']}** ({ipo['code']}) - 截止 {ipo['closing']}\n"
        md += "\n"

    return md


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # 从命令行参数读取 JSON 文件
        with open(sys.argv[1], encoding="utf-8") as f:
            ipos = json.load(f)
    else:
        # 从 stdin 读取
        ipos = json.loads(sys.stdin.read())

    print(format_markdown(ipos))
