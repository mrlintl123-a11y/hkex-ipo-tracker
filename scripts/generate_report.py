import json, sys, os, argparse
from datetime import datetime
sys.stdout.reconfigure(encoding='utf-8')

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
        if active:
            matrix['groups'].append({'group_type': 'active', 'closing_dates': sorted(set(i['closing_date'] for i in active)), 'members': [i['name'] for i in active], 'ipo_count': len(active)})
        conf_summary = {}
        for i in flat:
            status = i.get('data_confidence', '\u26ab')
            conf_summary.setdefault(status, []).append(i['name'])
        key_dates = {}
        for k in ['today_deadline', 'tomorrow_deadline', 'next_deadline']:
            key_dates[k] = []
        return {'active_ipos': flat, 'conflict_matrix': matrix, 'data_confidence_summary': conf_summary, 'key_dates': key_dates, 'snapshot_date': today_str, 'snapshot_time': datetime.now().strftime('%H:%M'), '_auto_enriched': True}
    if isinstance(raw, dict) and 'active_ipos' in raw:
        return raw
    raise ValueError(f'Invalid input format: expected list or dict with active_ipos key, got {type(raw).__name__}')

def load_data():
    parser = argparse.ArgumentParser(description='HKEX IPO Report Generator v4.1.1')
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
    lines.append('| 上市日 | 公司 | 代码 | 截止日 | 距截止 | 全球发售 | 公开手数 | 认购倍数+可信度 | 绿鞋 | 基石 | A+H |')
    lines.append('| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |')
    for ipo in ipo_list:
        conf_icon = ipo.get('data_confidence', '\u26ab')
        margin = ipo.get('margin_multiple', '-')
        mdate = ipo.get('margin_data_date', '')
        if mdate: margin += f' ({mdate})'
        gs = ipo.get('greenshoe', '\u274c')
        cs_raw = ipo.get('cornerstone', '\u274c')
        cs = cs_raw[:50] + '...' if isinstance(cs_raw, str) and len(cs_raw) > 50 else cs_raw
        ah = ipo.get('a_h', '\u274c')
        lots = fmt_lots(ipo.get('public_lots', '-'))
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
            f"| {ah} |"
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

# --- Heat scores ---
print('## \U0001f525 热度评分')
print()
print('| 公司 | 孖展(30%) | 基石(25%) | 手数(20%) | 入场费(15%) | A+H(10%) | **综合** |')
print('| --- | --- | --- | --- | --- | --- | --- |')
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
    print(f"| {ipo['name']} | {m_disp} | {cs[:40]} | {lots}手 | {fee} | {ah} | {score} {stars} |")
print()

# --- Strategy ---
print('## \U0001f386 资金分档策略')
print()
under_10k = [i for i in active if heat_score(i) > 2 and i.get('board_lot', 100) * (float(i.get('offer_price','0').replace(' HKD','').replace(' (最高)','').split('-')[0]) if '-' in i.get('offer_price','') else float(i.get('offer_price','0').replace(' HKD','').replace(' (最高)','') or '100')) < 10000]
mid_10_50k = [i for i in active if heat_score(i) > 2]
for tier in ['<1万港元', '1-5万港元', '5-50万港元', '>50万港元']:
    candidates = [i for i in active if heat_score(i) >= 2.5]
    if candidates:
        names_str = '\u3001'.join(f"{i['name']}({i.get('board_lot',0)}\u00d7{i.get('offer_price','-')})" for i in candidates[:4])
        print(f'- **{tier}**：{names_str}')
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
print(f'> \u2139\ufe0f 数据来源：智通财经/金吾资讯/LiveReport/港交所披露易 | 快照 {snap} {snap_time}')