import json, sys, os, argparse
from datetime import datetime
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from clawback_calculator import calc as _clawback_calc

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def validate_and_enrich(raw):
    if isinstance(raw, list):
        flat = raw
        all_dates = sorted(set(i.get('closing_date', '') for i in flat if i.get('closing_date')))
        today_str = datetime.now().strftime('%Y-%m-%d')
        active = [i for i in flat if i['closing_date'] >= today_str]
        closed = [i for i in flat if i['closing_date'] < today_str]
        matrix = {'rule': 'cutoff gap < 2 days = conflict', 'groups': []}
        if closed:
            matrix['groups'].append({'group_type': 'closed', 'closing_dates': sorted(set(i['closing_date'] for i in closed)), 'members': [i['name'] for i in closed], 'ipo_count': len(closed)})
        for i in active:
            i['days_before_close'] = max(0, (datetime.strptime(i['closing_date'], '%Y-%m-%d') - datetime.strptime(today_str, '%Y-%m-%d')).days)
            i['data_confidence'] = i.get('data_confidence', '\u26ab')
        # --- 18A/18C redistribution (v4.1) ---
        for i in flat:
            ch = i.get('chapter', '')
            redist = i.get('redistribution_pct', 0)
            init_pct = i.get('public_initial_pct', 0.10) * 100
            if ch in ('18A', '18C') and redist > 0:
                margin_str = i.get('margin_multiple', '0')
                margin_num = float(margin_str.replace('倍', '') if '倍' in margin_str else margin_str or 0)
                result = _clawback_calc(ch, margin_num, redist, init_pct)
                new_pct = result['final_pct'] / 100
                orig_pct = i.get('public_initial_pct', 0.10)
                if init_pct > 0 and new_pct > orig_pct:
                    old_lots = i.get('public_lots', 0)
                    i['_public_lots_initial'] = old_lots
                    i['_redistribution_applied'] = result['mechanism']
                    i['public_lots'] = int(old_lots * new_pct / orig_pct)
                    i['public_initial_pct'] = new_pct
        # --- end redistribution ---
        if active:
            matrix['groups'].append({'group_type': 'active', 'closing_dates': sorted(set(i['closing_date'] for i in active)), 'members': [i['name'] for i in active], 'ipo_count': len(active)})
        conf_summary = {}
        for i in flat:
            status = i.get('data_confidence', '\u26ab')
            conf_summary.setdefault(status, []).append(i['name'])
        key_dates = {}
        from datetime import timedelta
        today_deadlines = [i for i in flat if i.get('closing_date') == today_str]
        tomorrow_str = (datetime.strptime(today_str, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')
        tomorrow_deadlines = [i for i in flat if i.get('closing_date') == tomorrow_str]
        future_ipos = [i for i in flat if i.get('closing_date', '') > tomorrow_str]
        key_dates['today_deadline'] = [f"{i['name']}({i.get('code','')}) {i.get('closing_date','')} 16:00截止" for i in today_deadlines] or ['无']
        key_dates['tomorrow_deadline'] = [f"{i['name']}({i.get('code','')}) {i.get('closing_date','')} 16:00截止" for i in tomorrow_deadlines] or ['无']
        if future_ipos:
            nd = sorted(future_ipos, key=lambda x: x.get('closing_date', ''))
            key_dates['next_deadline'] = [f"{nd[0]['name']}({nd[0].get('code','')}) {nd[0].get('closing_date','')} 截止"]
        else:
            key_dates['next_deadline'] = ['暂无']
        return {'active_ipos': flat, 'conflict_matrix': matrix, 'data_confidence_summary': conf_summary, 'key_dates': key_dates, 'snapshot_date': today_str, 'snapshot_time': datetime.now().strftime('%H:%M'), '_auto_enriched': True}
    if isinstance(raw, dict) and 'active_ipos' in raw:
        return raw
    raise ValueError(f'Invalid input format: expected list or dict with active_ipos key, got {type(raw).__name__}')

def load_data():
    parser = argparse.ArgumentParser(description='HKEX IPO Report Generator v4.1.2')
    parser.add_argument('--input', '-i', help='JSON file with IPO data')
    parser.add_argument('--demo', action='store_true', help='Use sample data for demo only (NOT live data)')
    args = parser.parse_args()

    is_demo = False
    if args.input:
        if not os.path.exists(args.input):
            print(f'ERROR: File not found: {args.input}', file=sys.stderr)
            sys.exit(1)
        with open(args.input, 'r', encoding='utf-8') as f:
            raw = json.load(f)
        try:
            return validate_and_enrich(raw)
        except ValueError as e:
            print(f'ERROR: {e}', file=sys.stderr)
            print('       Expected JSON list (from fetch_active_ipos.py) or JSON object with active_ipos key.', file=sys.stderr)
            print('       Pipeline: fetch_active_ipos.py --input results.jsonl > ipos.json', file=sys.stderr)
            print('                  then: generate_report.py --input ipos.json', file=sys.stderr)
            sys.exit(1)
    elif args.demo:
        is_demo = True
        demo_path = os.path.join(SKILL_DIR, 'references', 'sample-data.json')
        if not os.path.exists(demo_path):
            print(f'ERROR: Demo file not found: {demo_path}', file=sys.stderr)
            sys.exit(1)
        with open(demo_path, 'r', encoding='utf-8') as f:
            raw = json.load(f)
        data = validate_and_enrich(raw)
        data['_demo'] = True
        return data
    print('ERROR: No data source. Use --input <file> or --demo.', file=sys.stderr)
    print('       Production: generate_report.py --input ipos.json', file=sys.stderr)
    print('       Demo:       generate_report.py --demo', file=sys.stderr)
    sys.exit(1)


def _stock_connect_analysis(ipo):
    ah = ipo.get("a_h", "")
    if ah and ah != "\u274c":
        return "\u5df2\u7eb3\u5165(A+H)"
    cap = ipo.get("est_market_cap_hkd", 0)
    name = ipo.get("name", "")
    if "DRS" in name or "Merdeka" in name:
        return "\u5916\u56fdDRS,\u5927\u6982\u7387\u4e0d\u7eb3\u5165"
    if cap >= 5e10:
        return "\u9884\u8ba1\u7eb3\u5165(\u5927\u76d8,2026/9\u751f\u6548)"
    elif cap >= 2e10:
        return "\u5f85\u68c0\u8ba8(2026/9\u7a97\u53e3,\u9700\u5165\u6052\u751f\u7efc\u6307)"
    elif cap >= 5e9:
        return "\u63a5\u8fd1\u95e8\u69db(2026/9\u7a97\u53e3,\u9700\u5e02\u503c>=50\u4ebf)"
    else:
        return "\u672a\u8fbe\u6807(\u5e02\u503c<50\u4ebf\u6e2f\u5143)"

data = load_data()

ipos = data['active_ipos']
matrix = data.get('conflict_matrix', {})
conf = data.get('data_confidence_summary', {})
dates = data.get('key_dates', {})
snap = data.get('snapshot_date', '')
snap_time = data.get('snapshot_time', '')
if not snap:
    print('WARNING: Input data missing snapshot_date field. Using current time.', file=sys.stderr)
    snap = datetime.now().strftime('%Y-%m-%d')
    snap_time = datetime.now().strftime('%H:%M')

today = datetime.now().strftime('%Y-%m-%d')
is_demo = not hasattr(sys, 'argv') or '--demo' in sys.argv
if is_demo:
    print('> ⚠️ DEMO MODE: using sample data, NOT live data', file=sys.stderr)

# Separate active vs closed
active = [i for i in ipos if i['closing_date'] >= today]
closed = [i for i in ipos if i['closing_date'] < today]

def heat_score(ipo):
    m = ipo.get('margin_multiple', '')
    has_margin = True
    if '暂无' in m:
        m_num = 0; m_star = 0; has_margin = False
    else:
        try: m_num = float(m.replace('倍', ''))
        except: m_num = 0
        if m_num >= 500: m_star = 5
        elif m_num >= 100: m_star = 4
        elif m_num >= 50: m_star = 3
        elif m_num >= 15: m_star = 2
        else: m_star = 1
    c = ipo.get('cornerstone', '')
    if c and c != '\u274c':
        names = c.replace('\u2705', '').strip()
        count = names.count('\u3001') + 1
        if count >= 5: c_star = 5
        elif count >= 3: c_star = 4
        elif count >= 1: c_star = 3
        else: c_star = 1
    else: c_star = 1
    lots = ipo.get('public_lots', 0)
    if lots < 15000: l_star = 5
    elif lots <= 30000: l_star = 3
    else: l_star = 2
    price_str = ipo.get('offer_price', '0').replace(' HKD', '').replace(' (最高)', '')
    if '-' in price_str: p = float(price_str.split('-')[0])
    else:
        try: p = float(price_str)
        except: p = 100
    fee = p * ipo.get('board_lot', 100)
    if fee < 3000: f_star = 5
    elif fee <= 5000: f_star = 3
    else: f_star = 2
    ah = ipo.get('a_h', '')
    if ah == '\u274c' or not ah: ah_star = 3
    else:
        d = ipo.get('ah_discount', '0%').replace('%', '')
        try:
            disc = float(d)
            if disc > 40: ah_star = 5
            elif disc >= 20: ah_star = 4
            else: ah_star = 3
        except: ah_star = 3
    if has_margin:
        raw = 0.3*m_star + 0.25*c_star + 0.2*l_star + 0.15*f_star + 0.1*ah_star
    else:
        raw = (0.25*c_star + 0.2*l_star + 0.15*f_star + 0.1*ah_star) / 0.7
    return round(raw, 2)

def fmt_lots(n):
    if isinstance(n, int): return f'{n:,}'
    return str(n)

def fmt_shares(n):
    if n >= 1000000:
        if n % 1000000 == 0: return f'{n//1000000}M股'
        return f'{n/1000000:.1f}M股'
    return f'{n:,}股'

def render_table(ipo_list):
    lines = []
    lines.append('| 上市日 | 公司 | 代码 | 截止日 | 距截止 | 全球发售 | 公开手数 | 认购倍数+可信度 | 绿鞋 | 基石 | A+H | 港股通 |')
    lines.append('| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |')
    for ipo in ipo_list:
        conf_icon = ipo.get('data_confidence', '\u26ab')
        margin = ipo.get('margin_multiple', '-')
        mdate = ipo.get('margin_data_date', '')
        if mdate: margin += f' ({mdate})'
        gs = ipo.get('greenshoe', '\u274c')
        cs_raw = ipo.get('cornerstone', '\u274c')
        cs = cs_raw[:50] + '...' if isinstance(cs_raw, str) and len(cs_raw) > 50 else cs_raw
        ah = ipo.get('a_h', '\u274c')
        sc = _stock_connect_analysis(ipo)
        lots = fmt_lots(ipo.get('public_lots', '-'))
        if ipo.get('_redistribution_applied'):
            lots += ' \u2197'
        global_s = ipo.get('global_shares', 0)
        global_str = fmt_shares(global_s)
        days = ipo.get('days_before_close', '-')
        lines.append(
            f"| {ipo.get('listing_date', '-')} "
            f"| {ipo['name']} "
            f"| {ipo['code']} "
            f"| {ipo['closing_date']} "
            f"| {days}天 "
            f"| {global_str} "
            f"| {lots}手 "
            f"| {margin} {conf_icon} "
            f"| {gs} "
            f"| {cs} "
            f"| {ah} "
            f"| {sc} |"
        )
    return '\n'.join(lines)

# BUILD REPORT
print(f"# \U0001f4ca 港交所正在招股公司全景（{snap} {snap_time} 更新）")
print()

# --- Conflict Matrix ---
active_dates = sorted(set(i['closing_date'] for i in active))
print('## \u26a0\ufe0f 资金冲突矩阵')
print()
if active_dates:
    header = '| 截止日 | ' + ' | '.join(active_dates) + ' |'
    sep = '| --- |' + ' --- |' * len(active_dates)
    print(header)
    print(sep)
    for d1 in active_dates:
        row = f'| **{d1[-5:]}** |'
        for d2 in active_dates:
            if d1 == d2:
                row += ' - |'
            else:
                delta = abs((datetime.strptime(d2, '%Y-%m-%d') - datetime.strptime(d1, '%Y-%m-%d')).days)
                if delta < 2:
                    row += f' \U0001f534冲突({delta}天) |'
                else:
                    row += f' \U0001f7e2分流({delta}天) |'
        print(row)
print()

# --- Groups ---
for g in matrix['groups']:
    members_in_group = [i for i in ipos if i['name'] in g['members']]
    if not members_in_group: continue

    statuses = set(i.get('data_confidence', '') for i in members_in_group)
    if '\U0001f7e2' in statuses or all(i.get('days_before_close', 99) == 0 for i in members_in_group):
        label_add = ' \u2705已截止'
    elif '\U0001f7e1' in statuses:
        label_add = ' \u23f0明天截止'
    elif '\U0001f7e0' in statuses:
        label_add = ' \U0001f7e0招股中'
    else:
        label_add = ' \U0001f7e2本周新启动'
    closing_dates_str = '/'.join(sorted(set(i['closing_date'][-5:] for i in members_in_group)))
    print(f"## {g['group_type']}{label_add}（截止 {closing_dates_str}，{len(members_in_group)} 只）")
    print()
    print(render_table(members_in_group))
    print()


print()

# --- Per-IPO Detail Cards (v4.2) ---
print("## 个股详情")
print()

from collections import defaultdict
_dg = defaultdict(list)
for ipo in ipos:
    if ipo.get("closing_date", "") >= snap:
        _dg[ipo.get("closing_date", "?")].append(ipo)

for _cd in sorted(_dg.keys()):
    _mbs = _dg[_cd]
    _cnt = len(_mbs)
    _td_date = datetime.strptime(_cd, "%Y-%m-%d")
    _snap_date = datetime.strptime(snap, "%Y-%m-%d")
    _delta = _td_date - _snap_date
    _dl = _delta.days
    _hl = _dl * 24
    _td_flag = (_dl == 0)
    _nw_flag = any("暂无" in m.get("margin_multiple", "") for m in _mbs)
    _lp = []
    if _td_flag: _lp.append("今日截止")
    if _nw_flag: _lp.append("新启招")
    _ls = " " + " ".join(_lp) if _lp else ""
    print(f"### 截止 {_cd[-5:]} (剩 {_dl} 天 / {_hl}h, {_cnt} 只{_ls})")
    print()

    for _ix, _ip in enumerate(_mbs, 1):
        _nm = _ip.get("name", "?")
        _cd2 = _ip.get("code", "?")
        _of = _ip.get("offer_price", "-")
        _bl = _ip.get("board_lot", 100)
        _ps = _ip.get("period_start", "?")
        _pe = _ip.get("period_end", "?")
        _ts = _ip.get("total_shares", "?")
        _pl = int(_ip.get("public_lots", 0))
        _rt = ""
        if _ip.get("_redistribution_applied"):
            _og = _ip.get("_public_lots_initial", _pl)
            _ch = _ip.get("chapter", "")
            _rt = f" ({_ch}+{_ip.get('redistribution_pct',0)}%: {_og:,}→{_pl:,}手)"
        _ld = f"{_pl:,}手{_rt}" if _pl else "-"
        _mg = _ip.get("margin_multiple", "-")
        _md = "NEW 暂无孖展" if "暂无" in _mg else _mg
        _gs2 = _ip.get("greenshoe", "-")
        _cr = _ip.get("cornerstone", "-")
        if _cr and _cr != "否" and _cr != "-":
            _cds = _cr[:60] + ("..." if len(_cr) > 60 else "")
        else:
            _cds = "无"
        _ah2 = _ip.get("a_h", "-")
        if _ah2 and _ah2 != "否" and _ah2 != "-":
            _dc2 = _ip.get("ah_discount", "")
            _ad = f"A+H (折{_dc2})" if _dc2 else "A+H"
        else:
            _ad = "纯H"
        _lt = _ip.get("listing_date", "?")
        _ls2 = _lt[-5:] if len(_lt) >= 5 else _lt
        _ds = _ip.get("description", "-")
        _rk = _ip.get("risk_flags", [])
        _rs = " | ".join(_rk) if _rk else ""
        _sc2 = _stock_connect_analysis(_ip)
        _hs2 = heat_score(_ip)
        _st = "⭐" * min(round(_hs2), 5) if _hs2 >= 1 else "—"

        print(f"**{_ix}. {_nm} {_cd2}** [{_hs2} {_st}]")
        _l1 = f"  发售价 {_of} | 每手 {_bl} 股 | 招股期 {_ps}~{_pe}"
        if _rs: _l1 += f" | 风险: {_rs}"
        print(_l1)
        print(f"  全球发售 {_ts} | 公开 {_ld} | 孖展 {_md}")
        print(f"  绿鞋 {_gs2} | 基石 {_cds} | {_ad} | 上市日 {_ls2}")
        print(f"  主营 {_ds} | 港股通 {_sc2}")
        print()

print()
# --- Data confidence ---
print('## \U0001f4e1 认购倍数数据可信度')
print()
print('| 状态 | 公司 |')
print('| --- | --- |')
for status, names in conf.items():
    if names:
        joined = '\u3001'.join(names)
        print(f'| {status} | {joined} |')
print()


# --- Key Observations ---
print("## \U0001f50d \u5173\u952e\u89c2\u5bdf")
print()
today_deadlines = [i for i in active if i.get("days_before_close", 99) <= 1]
if today_deadlines:
    names_str = "、".join(i["name"] for i in today_deadlines)
    print(f"1. **\u660e\u65e5\u622a\u6b62\u5012\u8ba1\u65f6**\uff1a{names_str} \u5171{len(today_deadlines)}\u53ea\u660e\u65e5 16:00 \u622a\u6b62\uff0c\u4eca\u6668\u76d8\u524d\u5b50\u5c55\u6570\u636e\u662f\u51b3\u5b9a\u80dc\u8d1f\u5173\u952e")
ah_stocks = [i for i in ipos if i.get("a_h", "") not in ("", "\u274c")]
if ah_stocks:
    discounts = []
    for i in ah_stocks:
        d = i.get("ah_discount", "")
        if d:
            discounts.append(f"{i['name']}(\u6298{d})")
    if discounts:
        print(f"2. **A+H\u6298\u4ef7\u6c47\u603b**\uff1a{chr(10).join(discounts)} \u2014 \u672c\u5468{len(ah_stocks)}\u53eaA+H\u5168\u90e8\u5927\u5e45\u6298\u4ef7\uff0c\u4e0a\u5e02\u540e\u6298\u4ef7\u6536\u7a84\u662f\u6838\u5fc3\u9a71\u52a8\u529b")
redist_stocks = [i for i in ipos if i.get("_redistribution_applied")]
if redist_stocks:
    notes = []
    for i in redist_stocks:
        old_lots = i.get("_public_lots_initial", 0)
        new_lots = i.get("public_lots", 0)
        notes.append(f"{i['name']}: {old_lots:,}\u624b\u2192{new_lots:,}\u624b ({i.get('_redistribution_applied','')})")
    print(f"3. **18A/18C\u91cd\u65b0\u5206\u914d\u4fee\u6b63**\uff1a{chr(10).join('   - '+n for n in notes)}")
risk_stocks = [i for i in ipos if i.get("risk_flags")]
if risk_stocks:
    high_risk = [i for i in risk_stocks if len(i.get("risk_flags", [])) >= 2]
    if high_risk:
        names_str = "、".join(f"{i['name']}({','.join(i['risk_flags'])})" for i in high_risk)
        print(f"4. **\u98ce\u9669\u6807\u8bb0**\uff1a{names_str}")
cold = [i for i in active if i.get("margin_multiple", "0").replace("\u500d", "").replace("\u6682\u65e0", "0") != "0"]
if cold:
    try:
        coldest = min(cold, key=lambda x: float(x.get("margin_multiple", "0").replace("\u500d", "")))
        print(f"5. **\u6781\u51b7\u8b66\u544a**\uff1a{coldest['name']} \u4ec5{coldest.get('margin_multiple','')}\uff0c\u56fd\u914d\u4e0d\u8db3\u53ef\u80fd\u89e6\u53d1\u201c\u5957\u8def\u62e8\u201d")
    except:
        pass
print()
# --- Heat scores ---
print('## \U0001f525 热度评分')
print()
print('| 公司 | 孖展(30%) | 基石(25%) | 手数(20%) | 入场费(15%) | A+H(10%) | 主营 | 港股通 | **综合** |')
print('| --- | --- | --- | --- | --- | --- | --- | --- | --- |')
results = []
for ipo in ipos:
    score = heat_score(ipo)
    results.append((ipo, score))
results.sort(key=lambda x: x[1], reverse=True)
for ipo, score in results:
    stars = '\u2b50' * min(round(score), 5) if score >= 1 else '\u2014'
    m = ipo.get('margin_multiple', '-')
    if '\u6682\u65e0' in m: m_disp = '\U0001f195 \u6682\u65e0'
    else: m_disp = m
    cs = ipo.get('cornerstone', '\u274c')
    lots = fmt_lots(ipo.get('public_lots', '-'))
    price_str = ipo.get('offer_price', '-')
    board_lot = ipo.get('board_lot', 100)
    fee = f'{board_lot}\u00d7{price_str}'
    ah = ipo.get('a_h', '\u274c')
    if ah != '\u274c' and ipo.get('ah_discount'):
        ah += f' \u6298{ipo["ah_discount"]}'
    desc = ipo.get('description', '-')
    sc_h = _stock_connect_analysis(ipo)
    print(f"| {ipo['name']} | {m_disp} | {cs[:40]} | {lots}手 | {fee} | {ah} | {desc} | {sc_h} | {score} {stars} |")
print()

# --- Strategy ---
print("## \u8d44\u91d1\u5206\u6863\u7b56\u7565")
print()

def _entry_fee(ipo):
    price_str = ipo.get("offer_price", "0").replace(" HKD", "").replace(" (\u6700\u9ad8)", "")
    if "-" in price_str:
        p = float(price_str.split("-")[0])
    else:
        try:
            p = float(price_str)
        except:
            p = 100000
    return p * ipo.get("board_lot", 100)

def _pick(top_n, min_score, max_fee):
    candidates = sorted(
        [i for i in active if heat_score(i) >= min_score and _entry_fee(i) <= max_fee],
        key=lambda x: heat_score(x), reverse=True
    )
    if candidates:
        return "\u3001".join(f"{i['name']}({i.get('board_lot',0)}\u00d7{i.get('offer_price','-')})" for i in candidates[:top_n])
    return "\u65e0\u5408\u9002\u6807\u7684"

under_10k = _pick(4, 2.0, 10000)
low_mid = _pick(4, 2.0, 50000)
mid = _pick(5, 2.0, 500000)
high = _pick(5, 2.0, float("inf"))

cold_plays = sorted(
    [i for i in active if heat_score(i) < 2.5 and heat_score(i) >= 1.5],
    key=lambda x: float(x.get("margin_multiple", "0").replace("\u500d", "").replace("\u6682\u65e0", "0") or 0)
)
cold_str = "\u3001".join(f"{i['name']}({i.get('margin_multiple','-')})" for i in cold_plays[:4]) if cold_plays else "\u65e0"

print(f"- **\u22641\u4e07\u6e2f\u5143**\uff1a{under_10k}")
print(f"- **1-5\u4e07\u6e2f\u5143**\uff1a{low_mid}")
print(f"- **5-50\u4e07\u6e2f\u5143**\uff08\u4e3b\u529b\uff09\uff1a{mid}")
print(f"- **>50\u4e07\u6e2f\u5143**\uff1a{high}")
print(f"- **\u51b7\u95e8\u535a**\uff1a{cold_str}")
print()

# --- Key dates ---
print('## \U0001f514 关键时间节点')
print()
for k, v in dates.items():
    if k.startswith('today'): print(f'- **今日**：{v if isinstance(v, str) else chr(10).join(str(x) for x in v)}')
    elif k.startswith('tomorrow'): print(f'- **明日 16:00**：{v if isinstance(v, str) else chr(10).join(str(x) for x in v)}')
    elif 'allotment' in k: print(f'- **配发结果**：{v}')
    elif 'next' in k and not k.startswith('next_'): print(f'- **下一窗口**：{v if isinstance(v, str) else chr(10).join(str(x) for x in v)}')
print()

# --- Footer ---
print('---')
active_notes = [i for i in active if i.get('days_before_close', 99) <= 1]
new_notes = [i for i in active if '\u6682\u65e0' in i.get('margin_multiple', '')]
if active_notes:
    names = '\u3001'.join(i['name'] for i in active_notes)
    print(f'> \u26a0\ufe0f {names} 截止在即，关注最终孖展变化')
if new_notes:
    names2 = '\u3001'.join(i['name'] for i in new_notes)
    print(f'> \u26a0\ufe0f {names2} 刚启动招股，暂无孖展数据，等 1-2 天再判断')
redist_stocks = [i for i in ipos if i.get('_redistribution_applied')]
if redist_stocks:
    notes = '、'.join(f"{i['name']}({i.get('_redistribution_applied','')})" for i in redist_stocks)
    print(f'> \U0001f4cc 18A/18C重新分配：{notes}')
print(f'> \u2139\ufe0f 数据来源：智通财经/金吾资讯/LiveReport/港交所披露易 | 快照 {snap} {snap_time}')
print("> \U0001f4cc **\u6e2f\u80a1\u901a\u7eb3\u5165\u5206\u6790**\uff1a\u57fa\u4e8e\u6052\u751f\u6307\u6570\u516c\u53f8\u300a\u6307\u6570\u7f16\u7b97\u7ec6\u5219\u300b\u53ca\u6e2f\u4ea4\u6240\u300a\u6e2f\u80a1\u901a\u7eb3\u5165\u6761\u4ef6\u300b\u5ba2\u89c2\u8ba1\u7b97\uff0c\u4ec5\u4f9b\u53c2\u8003\uff0c\u4e0d\u6784\u6210\u6295\u8d44\u5efa\u8bae\u3002\u5b9e\u9645\u7eb3\u5165\u4ee5\u6e2f\u4ea4\u6240\u516c\u544a\u4e3a\u51c6\u3002")