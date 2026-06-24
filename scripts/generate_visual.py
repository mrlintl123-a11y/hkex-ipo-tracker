import json, os, sys, argparse
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')
SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_PATH = os.path.join(SKILL_DIR, "ipo_report.html")

parser = argparse.ArgumentParser(description="HKEX IPO Visual Report Generator v4.2")
parser.add_argument("--input", "-i", help="JSON file with IPO data (from fetch_active_ipos.py or generate_report.py pipeline)")
parser.add_argument("--demo", action="store_true", help="Use sample data (demo only, NOT live)")
args = parser.parse_args()

if args.input:
    if not os.path.exists(args.input):
        print(f"ERROR: File not found: {args.input}", file=sys.stderr)
        sys.exit(1)
    with open(args.input, "r", encoding="utf-8") as f:
        ipos = json.load(f)
elif args.demo:
    demo_path = os.path.join(SKILL_DIR, "references", "sample-data.json")
    if not os.path.exists(demo_path):
        print(f"ERROR: Demo data not found: {demo_path}", file=sys.stderr)
        sys.exit(1)
    with open(demo_path, "r", encoding="utf-8") as f:
        raw = json.load(f)
        ipos = raw if isinstance(raw, list) else raw.get("active_ipos", raw.get("data", []))
else:
    live_path = os.path.join(SKILL_DIR, "live_ipos.json")
    if os.path.exists(live_path):
        with open(live_path, "r", encoding="utf-8") as f:
            ipos = json.load(f)
    else:
        print("ERROR: No input provided. Use --input <file> or --demo.", file=sys.stderr)
        sys.exit(1)

today = datetime.now()
snap = today.strftime("%Y-%m-%d %H:%M")

# Sort by heat
def heat_score(ipo):
    m_str = ipo.get("margin_multiple", "0")
    try: m = float(m_str.replace("倍", ""))
    except: m = 0
    if m >= 500: ms = 5
    elif m >= 100: ms = 4
    elif m >= 50: ms = 3
    elif m >= 15: ms = 2
    else: ms = 1
    c = ipo.get("cornerstone", "")
    if c and c != "❌":
        cnt = c.count("、") + 1
        if cnt >= 5: cs = 5
        elif cnt >= 3: cs = 4
        elif cnt >= 1: cs = 3
        else: cs = 1
    else: cs = 1
    lots = ipo.get("public_lots", 0)
    if lots < 15000: ls = 5
    elif lots <= 30000: ls = 3
    else: ls = 2
    price_str = ipo.get("offer_price", "0").replace(" HKD", "").replace(" (最高)", "")
    if "-" in price_str: p = float(price_str.split("-")[0])
    else:
        try: p = float(price_str)
        except: p = 100
    fee = p * ipo.get("board_lot", 100)
    if fee < 3000: fs = 5
    elif fee <= 5000: fs = 3
    else: fs = 2
    ah = ipo.get("a_h", "")
    if ah == "❌" or not ah: ahs = 3
    else:
        d = ipo.get("ah_discount", "0%").replace("%", "")
        try:
            disc = float(d)
            if disc > 40: ahs = 5
            elif disc >= 20: ahs = 4
            else: ahs = 3
        except: ahs = 3
    return round(0.3*ms + 0.25*cs + 0.2*ls + 0.15*fs + 0.1*ahs, 2)



def _try_parse_margin(m_str):
    try:
        return float(m_str.replace("倍", ""))
    except:
        return 0
sorted_ipos = sorted(ipos, key=heat_score, reverse=True)

active = [i for i in ipos if i["closing_date"] >= today.strftime("%Y-%m-%d")]
tomorrow_close = [i for i in active if i.get("days_before_close", 99) <= 1]
ah_stocks = [i for i in ipos if i.get("a_h", "") not in ("", "❌")]
redist = [i for i in ipos if i.get("_redistribution_applied")]
max_mult = max((_try_parse_margin(i.get("margin_multiple","0")) for i in ipos), default=1)

closing_dates = sorted(set(i["closing_date"] for i in active))
matrix_rows = []
for d1 in closing_dates:
    cells = []
    for d2 in closing_dates:
        if d1 == d2: cells.append(("—","same"))
        else:
            delta = abs((datetime.strptime(d2,"%Y-%m-%d")-datetime.strptime(d1,"%Y-%m-%d")).days)
            cells.append((f"{delta}天冲突" if delta<2 else f"{delta}天分流", "conflict" if delta<2 else "safe"))
    matrix_rows.append((d1[-5:], cells))

def bar_color(v, mx):
    ratio = v/mx if mx>0 else 0
    if ratio > 0.5: return "#ef4444"
    if ratio > 0.2: return "#f59e0b"
    return "#3b82f6"

def heat_color(s):
    if s >= 3.5: return "#22c55e"
    if s >= 2.5: return "#3b82f6"
    if s >= 2.0: return "#f59e0b"
    return "#ef4444"

html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>港交所IPO全景 · {snap}</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans SC", sans-serif; background:#f5f7fa; color:#1e293b; line-height:1.6; }}
.container {{ max-width:1200px; margin:0 auto; padding:24px 16px; }}
.header {{ background:linear-gradient(135deg,#1e293b,#334155); color:#fff; padding:32px; border-radius:12px; margin-bottom:24px; }}
.header h1 {{ font-size:28px; font-weight:700; margin-bottom:8px; }}
.header .sub {{ opacity:0.8; font-size:14px; }}
.cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:16px; margin-bottom:24px; }}
.card {{ background:#fff; border-radius:10px; padding:20px; box-shadow:0 1px 3px rgba(0,0,0,.08); }}
.card .num {{ font-size:32px; font-weight:700; }}
.card .label {{ font-size:13px; color:#64748b; margin-top:4px; }}
.card.red .num {{ color:#ef4444; }}
.card.green .num {{ color:#22c55e; }}
.card.blue .num {{ color:#3b82f6; }}
.card.amber .num {{ color:#f59e0b; }}
.section {{ background:#fff; border-radius:10px; padding:24px; margin-bottom:20px; box-shadow:0 1px 3px rgba(0,0,0,.08); }}
.section h2 {{ font-size:18px; margin-bottom:16px; padding-bottom:8px; border-bottom:2px solid #e2e8f0; }}
.bar-chart {{ }}
.bar-row {{ display:flex; align-items:center; margin-bottom:8px; gap:8px; }}
.bar-label {{ width:120px; text-align:right; font-size:13px; flex-shrink:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
.bar-track {{ flex:1; height:24px; background:#f1f5f9; border-radius:4px; position:relative; overflow:hidden; }}
.bar-fill {{ height:100%; border-radius:4px; transition:width .3s; display:flex; align-items:center; padding-left:8px; font-size:11px; color:#fff; font-weight:600; white-space:nowrap; }}
.bar-val {{ width:80px; font-size:12px; flex-shrink:0; color:#64748b; }}
.matrix {{ overflow-x:auto; }}
.matrix table {{ border-collapse:collapse; font-size:13px; width:100%; }}
.matrix th,.matrix td {{ padding:10px 14px; text-align:center; border:1px solid #e2e8f0; }}
.matrix th {{ background:#f8fafc; font-weight:600; }}
.matrix td.conflict {{ background:#fef2f2; color:#dc2626; font-weight:600; }}
.matrix td.safe {{ background:#f0fdf4; color:#16a34a; }}
.matrix td.same {{ background:#f8fafc; color:#94a3b8; }}
.ipo-table {{ overflow-x:auto; }}
.ipo-table table {{ border-collapse:collapse; font-size:13px; width:100%; }}
.ipo-table th,.ipo-table td {{ padding:8px 10px; text-align:left; border-bottom:1px solid #f1f5f9; }}
.ipo-table th {{ background:#f8fafc; font-weight:600; font-size:12px; color:#64748b; white-space:nowrap; }}
.ipo-table tr:hover {{ background:#f8fafc; }}
.tag {{ display:inline-block; padding:2px 8px; border-radius:4px; font-size:11px; font-weight:600; }}
.tag-hot {{ background:#fef2f2; color:#dc2626; }}
.tag-warm {{ background:#fffbeb; color:#d97706; }}
.tag-cold {{ background:#f0fdf4; color:#16a34a; }}
.tag-new {{ background:#f1f5f9; color:#64748b; }}
.star {{ color:#f59e0b; }}
.footer {{ text-align:center; color:#94a3b8; font-size:12px; margin-top:24px; padding:16px; }}
.redist-badge {{ display:inline-block; background:#dbeafe; color:#1d4ed8; padding:1px 6px; border-radius:3px; font-size:11px; margin-left:4px; }}
.obs {{ padding:12px 16px; background:#fffbeb; border-left:3px solid #f59e0b; margin-bottom:8px; border-radius:0 6px 6px 0; font-size:14px; }}
.obs strong {{ color:#d97706; }}
.strat-tier {{ padding:8px 12px; margin-bottom:6px; border-radius:6px; font-size:14px; }}
.strat-tier.main {{ background:#dbeafe; border:1px solid #93c5fd; }}
</style>
</head>
<body>
<div class="container">

<div class="header">
<h1>📊 港交所正在招股公司全景</h1>
<div class="sub">数据快照 {snap} · 金吾资讯实时数据 · 共 {len(ipos)} 只新股</div>
</div>

<div class="cards">
<div class="card red"><div class="num">{len(active)}</div><div class="label">正在招股</div></div>
<div class="card amber"><div class="num">{len(tomorrow_close)}</div><div class="label">明日截止 (6/23 16:00)</div></div>
<div class="card blue"><div class="num">{len(ah_stocks)}</div><div class="label">A+H 折价标的</div></div>
<div class="card green"><div class="num">{len(redist)}</div><div class="label">18A/18C 重新分配</div></div>
</div>

<div class="section">
<h2>📈 孖展认购倍数对比</h2>
<div class="bar-chart">
'''
for ipo in sorted(ipos, key=lambda x: _try_parse_margin(x.get("margin_multiple","0")), reverse=True):
    m_str = ipo.get("margin_multiple", "0")
    try: m = float(m_str.replace("倍",""))
    except: m = 0
    pct = min(m / max(max_mult, 1) * 100, 100)
    color = bar_color(m, max_mult)
    redist_tag = '<span class="redist-badge">重新分配</span>' if ipo.get("_redistribution_applied") else ""
    html += f'<div class="bar-row"><span class="bar-label">{ipo["name"]}{redist_tag}</span><div class="bar-track"><div class="bar-fill" style="width:{pct:.1f}%;background:{color};">{m_str}</div></div><span class="bar-val">{m_str}</span></div>'

html += '</div></div><div class="section"><h2>🔥 热度评分排名</h2><div class="bar-chart">'
for ipo in sorted_ipos:
    s = heat_score(ipo)
    pct = s / 4 * 100
    color = heat_color(s)
    stars = "⭐" * min(round(s), 5)
    html += f'<div class="bar-row"><span class="bar-label">{ipo["name"]}</span><div class="bar-track"><div class="bar-fill" style="width:{pct:.1f}%;background:{color};">{s} {stars}</div></div><span class="bar-val">{s} {stars}</span></div>'
html += '</div></div>'

html += '<div class="section"><h2>⚠️ 资金冲突矩阵</h2><div class="matrix"><table><tr><th>截止日</th>'
for d in closing_dates: html += f'<th>{d[-5:]}</th>'
html += '</tr>'
for label, cells in matrix_rows:
    html += f'<tr><th>{label}</th>'
    for val, cls in cells: html += f'<td class="{cls}">{val}</td>'
    html += '</tr>'
html += '</table></div></div>'

html += '<div class="section"><h2>📋 新股速查表</h2><div class="ipo-table"><table><tr><th>上市日</th><th>公司</th><th>代码</th><th>截止日</th><th>公开手数</th><th>孖展</th><th>绿鞋</th><th>基石</th><th>A+H</th><th>港股通</th><th>主营</th></tr>'
for ipo in sorted(ipos, key=lambda x: x["closing_date"]):
    m = ipo.get("margin_multiple","-")
    try: mv = float(m.replace("倍",""))
    except: mv = 0
    if mv >= 500: tag_cls = "tag-hot"
    elif mv >= 15: tag_cls = "tag-warm"
    elif mv > 0: tag_cls = "tag-cold"
    else: tag_cls = "tag-new"
    redist_tag = ' ↗' if ipo.get("_redistribution_applied") else ""
    sc = "A+H已纳入" if ipo.get("a_h","") not in ("","❌") else ("待检讨" if ipo.get("est_market_cap_hkd",0)>=2e10 else "未达标")
    if "DRS" in ipo.get("name",""): sc = "排除"
    cs = ipo.get("cornerstone","❌")[:30]
    html += f'<tr><td>{ipo.get("listing_date","-")[-5:]}</td><td><strong>{ipo["name"]}</strong></td><td>{ipo["code"]}</td><td>{ipo.get("closing_date","-")[-5:]}</td><td>{ipo.get("public_lots","-"):,}{redist_tag}</td><td><span class="tag {tag_cls}">{m}</span></td><td>{ipo.get("greenshoe","❌")[:6]}</td><td>{cs}</td><td>{ipo.get("a_h","❌")[:10]}</td><td style="font-size:11px;color:#64748b;">{sc}</td><td style="font-size:12px;">{ipo.get("description","-")[:34]}</td></tr>'
html += '</table></div></div>'

html += '<div class="section"><h2>🔍 关键观察</h2>'
if tomorrow_close:
    names = "、".join(i["name"] for i in tomorrow_close)
    html += f'<div class="obs"><strong>⏰ 明日截止</strong>：{names} 共{len(tomorrow_close)}只明日16:00截止，今晚孖展数据是决胜关键</div>'
if ah_stocks:
    items = "、".join(f'{i["name"]}(折{i.get("ah_discount","?")})' for i in ah_stocks)
    html += f'<div class="obs"><strong>📉 A+H折价</strong>：{items} — 上市后折价收窄是核心驱动力</div>'
if redist:
    items = "、".join(f'{i["name"]}({i.get("_public_lots_initial","?"):,}→{i.get("public_lots","?"):,}手)' for i in redist)
    html += f'<div class="obs"><strong>📌 18A/18C重新分配</strong>：{items}</div>'
risk_stocks = [i for i in ipos if i.get("risk_flags")]
if risk_stocks:
    high = [i for i in risk_stocks if len(i.get("risk_flags",[]))>=2]
    if high:
        items = "、".join(f'{i["name"]}({",".join(i["risk_flags"])})' for i in high[:5])
        html += f'<div class="obs"><strong>⚠️ 风险标记</strong>：{items}</div>'
html += '</div>'

html += '<div class="section"><h2>💰 资金分档策略</h2>'
tiers = [("≤1万港元", "入门档，打1-2只小盘低入场费标的"),("1-5万港元", "小资档，可覆盖3-4只中低入场费标的"),("5-50万港元（主力）", "组合打新：中科闻歌+海光芯正+芯碁微装+科拓股份"),(">50万港元", "全覆盖：主力组合+礼邦医药-B+来福谐波+鲟龙科技"),("冷门博", "PT Merdeka Gold(2.56x)、真健康医疗-B(3.61x)、江西生物(4.87x)")]
for i, (t, d) in enumerate(tiers):
    cls = 'main' if i==2 else ''
    html += f'<div class="strat-tier {cls}"><strong>{t}</strong>：{d}</div>'
html += '</div>'

html += f'<div class="footer"><p>数据来源：金吾资讯(ipo.jinwucj.com) · 智通财经 · 港交所披露易 | 多源交叉验证</p><p>📌 港股通分析基于恒生指数公司《指数编算细则》客观计算，仅供参考，不构成投资建议</p><p>报告生成：{snap} · hkex-ipo-tracker v4.1.2</p></div></div></body></html>'

with open(OUT_PATH, "w", encoding="utf-8") as f:
    f.write(html)
print(f"Visual report generated: {OUT_PATH}")