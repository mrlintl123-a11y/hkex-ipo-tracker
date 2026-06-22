#!/usr/bin/env python3
import argparse, json, sys
sys.stdout.reconfigure(encoding="utf-8")

HIST = {
    "market_cap": {"<5":28.7,"5-20":15.3,"20-50":8.1,">50":2.1},
    "cornerstone": {"7+":26.8,"4-6":18.2,"1-3":12.5,"0":10.2},
    "subscription": {">500":42.5,"100-500":25.3,"15-100":12.8,"<15":3.5},
    "ah_discount": {">40":12.3,"20-40":5.1,"<20":1.2,"premium":-3.8},
}

def _lookup(table, val, kt):
    if kt == "market_cap":
        if val < 5: return table["<5"]
        if val < 20: return table["5-20"]
        if val < 50: return table["20-50"]
        return table[">50"]
    if kt == "cornerstone":
        if val >= 7: return table["7+"]
        if val >= 4: return table["4-6"]
        if val >= 1: return table["1-3"]
        return table["0"]
    if kt == "subscription":
        if val >= 500: return table[">500"]
        if val >= 100: return table["100-500"]
        if val >= 15: return table["15-100"]
        return table["<15"]
    if kt == "ah_discount":
        if val > 40: return table[">40"]
        if val >= 20: return table["20-40"]
        if val > 0: return table["<20"]
        return table["premium"]
    return 0

def predict(ipo):
    cap = _lookup(HIST["market_cap"], ipo.get("market_cap_billion",20), "market_cap")
    cs = _lookup(HIST["cornerstone"], ipo.get("cornerstone_count",1), "cornerstone")
    sub = _lookup(HIST["subscription"], ipo.get("margin_multiple",15), "subscription")
    ah = _lookup(HIST["ah_discount"], ipo.get("ah_discount_pct",0), "ah_discount")
    w = ah*0.30 + cs*0.30 + sub*0.20 + cap*0.20
    low = round(max(w*0.5,-30),1); high = round(w*1.5,1)
    up_prob = round(min(50+w*1.2,95),1)
    conf = "High" if ipo.get("margin_multiple",0)>50 else "Med" if ipo.get("margin_multiple",0)>15 else "Low"
    return {"name":ipo.get("name","?"),"range":f"+{low}% ~ +{high}%","mid":round(w,1),"up_prob":up_prob,"confidence":conf}

DEMO = [
    {"name":"中科闻歌","margin_multiple":0,"cornerstone_count":5,"market_cap_billion":8,"ah_discount_pct":0},
    {"name":"圣邦股份","margin_multiple":0,"cornerstone_count":7,"market_cap_billion":40,"ah_discount_pct":41},
    {"name":"来福谐波","margin_multiple":0,"cornerstone_count":10,"market_cap_billion":12,"ah_discount_pct":0},
]

def main():
    p = argparse.ArgumentParser(); p.add_argument("--demo", action="store_true")
    args = p.parse_args()
    print(f"\n{'First-Day Prediction (332 IPOs, 2024-2026)':-^70}\n")
    print(f"{'Company':<14} {'Range':>14} {'Mid':>6} {'Up Prob':>8} {'Conf':>6}")
    print("-" * 54)
    for ipo in DEMO:
        r = predict(ipo)
        print(f"{r['name']:<14} {r['range']:>14} {r['mid']:>5.1f}% {r['up_prob']:>7.1f}% {r['confidence']:>6}")
    print()

if __name__ == "__main__":
    main()
