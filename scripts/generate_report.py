#!/usr/bin/env python3
"""Generate HKEX IPO tracking report from sample data."""
import json
import sys
import os

sys.stdout.reconfigure(encoding='utf-8')

def load_data():
    data_path = os.path.join(os.path.dirname(__file__), '..', 'references', 'sample-data.json')
    with open(data_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def heat_score(ipo):
    m = ipo.get('margin_multiple', '')
    has_margin = True
    if '暂无' in m:
        m_num = 0
        m_star = 0
        has_margin = False
    else:
        try:
            m_num = float(m.replace('倍', ''))
        except:
            m_num = 0
        if m_num >= 500: m_star = 5
        elif m_num >= 100: m_star = 4
        elif m_num >= 50: m_star = 3
        elif m_num >= 15: m_star = 2
        else: m_star = 1

    c = ipo.get('cornerstone', '')
    if c and c != '❌':
        names = c.replace('✅', '').strip()
        count = names.count('、') + 1
        if count >= 5: c_star = 5
        elif count >= 3: c_star = 4
        elif count >= 1: c_star = 3
        else: c_star = 1
    else:
        c_star = 1

    lots = ipo.get('public_lots', 0)
    if lots < 15000: l_star = 5
    elif lots <= 30000: l_star = 3
    else: l_star = 2

    price_str = ipo.get('offer_price', '0').replace(' HKD', '').replace(' (最高)', '')
    if '-' in price_str:
        p = float(price_str.split('-')[0])
    else:
        try: p = float(price_str)
        except: p = 100
    fee = p * ipo.get('board_lot', 100)
    if fee < 3000: f_star = 5
    elif fee <= 5000: f_star = 3
    else: f_star = 2

    ah = ipo.get('a_h', '')
    if ah == '❌' or not ah:
        ah_star = 3
    else:
        d = ipo.get('ah_discount', '0%').replace('%', '')
        try:
            disc = float(d)
            if disc > 40: ah_star = 5
            elif disc >= 20: ah_star = 4
            else: ah_star = 3
        except:
            ah_star = 3

    if has_margin:
        raw = 0.3 * m_star + 0.25 * c_star + 0.2 * l_star + 0.15 * f_star + 0.1 * ah_star
    else:
        raw = (0.25 * c_star + 0.2 * l_star + 0.15 * f_star + 0.1 * ah_star) / 0.7

    return round(raw, 2)

def main():
    data = load_data()
    ipos = data['active_ipos']
    conf = data['data_confidence_summary']
    dates = data['key_dates']

    print('# 📊 港交所正在招股公司全景（2026-06-17 15:55 更新）')
    print()

    # === Conflict Matrix ===
    print('## ⚠️ 资金冲突矩阵')
    print()
    print('| 截止日 ↓ / 截止日 → | 06-16 | 06-17 | 06-18 | 06-23 |')
    print('| --- | --- | --- | --- | --- |')
    print('| **06-16** | - | 🔴冲突 | 🔴冲突 | 🟢分流 |')
    print('| **06-17** | 🔴冲突 | - | 🔴冲突 | 🟢分流 |')
    print('| **06-18** | 🔴冲突 | 🔴冲突 | - | 🟢分流 |')
    print('| **06-23** | 🟢分流 | 🟢分流 | 🟢分流 | - |')
    print()

    # === Super Conflict Group ===
    print('## 🔴 超级冲突组（截止日 6/16-6/18，5 只）')
    print()
    print('| 上市日 | 公司 | 代码 | 截止日 | 距截止 | 全球发售 | 公开手数 | 认购倍数+可信度 | 绿鞋 | 基石 | A+H |')
    print('| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |')

    conflict_dates = ['2026-06-16', '2026-06-17', '2026-06-18']
    for ipo in ipos:
        if ipo['closing_date'] in conflict_dates:
            conf_icon = ipo.get('data_confidence', '🟡')
            margin = ipo.get('margin_multiple', '-')
            mdate = ipo.get('margin_data_date', '')
            if mdate:
                margin += f' ({mdate})'
            gs = ipo.get('greenshoe', '❌')
            cs = ipo.get('cornerstone', '❌')
            ah = ipo.get('a_h', '❌')
            lots = ipo.get('public_lots', '-')
            if isinstance(lots, int):
                lots = f'{lots:,}'
            global_s = ipo.get('global_shares', 0)
            global_str = f'{global_s:,}股' if global_s else '-'
            days = ipo.get('days_before_close', '-')
            line = (
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
            print(line)
    print()

    # === Independent Window ===
    print('## 🟢 独立窗口（截止日 6/23，4 只）')
    print()
    print('| 上市日 | 公司 | 代码 | 截止日 | 距截止 | 全球发售 | 公开手数 | 认购倍数+可信度 | 绿鞋 | 基石 | A+H |')
    print('| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |')

    for ipo in ipos:
        if ipo['closing_date'] == '2026-06-23':
            conf_icon = ipo.get('data_confidence', '⚫')
            margin = ipo.get('margin_multiple', '-')
            mdate = ipo.get('margin_data_date', '')
            if mdate:
                margin += f' ({mdate})'
            gs = ipo.get('greenshoe', '❌')
            cs = ipo.get('cornerstone', '❌')
            ah = ipo.get('a_h', '❌')
            lots = ipo.get('public_lots', '-')
            if isinstance(lots, int):
                lots = f'{lots:,}'
            global_s = ipo.get('global_shares', 0)
            global_str = f'{global_s:,}股' if global_s else '-'
            days = ipo.get('days_before_close', '-')
            line = (
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
            print(line)
    print()

    # === Data Confidence ===
    print('## 📡 认购倍数数据可信度')
    print()
    print('| 状态 | 公司 |')
    print('| --- | --- |')
    for status, names in conf.items():
        if names:
            joined = '、'.join(names)
            print(f'| {status} | {joined} |')
    print()

    # === Heat Scores ===
    print('## 🔥 热度评分')
    print()
    print('| 公司 | 孖展(30%) | 基石(25%) | 手数(20%) | 入场费(15%) | A+H(10%) | **综合** |')
    print('| --- | --- | --- | --- | --- | --- | --- |')
    for ipo in ipos:
        score = heat_score(ipo)
        m = ipo.get('margin_multiple', '-')
        cs = ipo.get('cornerstone', '❌')
        lots = ipo.get('public_lots', '-')
        if isinstance(lots, int):
            lots = f'{lots:,}'
        price_str = ipo.get('offer_price', '-')
        board_lot = ipo.get('board_lot', 100)
        fee = f'{board_lot}×{price_str}'
        ah = ipo.get('a_h', '❌')
        stars = '⭐' * round(score) if score >= 1 else '—'
        if '暂无' in m:
            m_disp = '🆕 暂无'
        else:
            m_disp = m
        line = (
            f"| {ipo['name']} "
            f"| {m_disp} "
            f"| {cs} "
            f"| {lots}手 "
            f"| {fee} "
            f"| {ah} "
            f"| {score} {stars} |"
        )
        print(line)
    print()

    # === Fund Strategy ===
    print('## 🎆 资金分档策略')
    print()
    print('- **<1万港元**：麦科医药-B（一手3,640）、海清智元（一手3,600）、科拓股份（一手2,373）')
    print('- **1-5万港元**：星源材质（一手4,490）、仙工智能（一手5,080）')
    print('- **5-50万港元**：华健未来-B（一手8,180）、中科闻歌（一手12,140）、领益智造（一手6,719）、圣邦股份（一手8,520）')
    print('- **>50万港元**：All-in 大票或乙组申购')
    print()

    # === Key Timeline ===
    today_names = '、'.join(dates.get('today_deadline_17_00', []))
    tomorrow_names = '、'.join(dates.get('tomorrow_deadline_16_00', []))
    print('## 🔔 关键时间节点')
    print()
    print(f'- **今日 {today_names} 16:00**：{today_names} 截止申购')
    print(f'- **明日 {tomorrow_names} 16:00**：{tomorrow_names} 截止申购')
    print(f'- **配发结果**：{dates.get("allotment_results_expected", "")}')
    print(f'- **下一窗口**：{dates.get("next_ipo_window_start", "")} → {dates.get("next_ipo_window_close", "")}')
    print()
    print('---')
    print('> ⚠️ 星源材质、华健未来-B 今日截止，孖展数据为截止前1天，最终倍数可能继续变化')
    print('> ⚠️ 领益/科拓/圣邦/中科闻歌 今日刚启动招股，暂无孖展数据，建议等 6/19 出来后再判断')
    print('> ℹ️ 数据来源：智通财经/金吾资讯/LiveReport/港交所披露易 | 快照 2026-06-17 15:55')


if __name__ == '__main__':
    main()
