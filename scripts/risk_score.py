#!/usr/bin/env python3
import argparse, json, sys
sys.stdout.reconfigure(encoding="utf-8")

TOP_CS = {"GIC","JPMAM","CPE","淡马锡","高瓴","红杉","腾讯","CPP Investments",
          "嘉实国际","富国基金","广发基金","睿远基金","大家人寿"}

def _score_cs(cs_list):
    if not cs_list: return 0.3
    n = len(cs_list)
    qty = 3.0 if n >= 5 else (2.0 if n >= 3 else (1.0 if n >= 1 else 0))
    qual = min(sum(2.0 for c in cs_list if any(t in str(c) for t in TOP_CS)), 2.0)
    return (qty + qual) / 5.0 * 5.0

def _score_theme(cat, ch=""):
    themes = {"AI":5,"机器人":5,"创新药":4,"半导体":4,"新能源":3,"生物科技":4,"消费电子":3}
    for kw, s in themes.items():
        if kw in str(cat): return float(s)
    if ch == "18C": return 4.0
    if ch == "18A": return 3.5
    return 2.5

def _score_val(ah_disc, entry_fee):
    ah = 3.0 if ah_disc > 40 else (2.0 if ah_disc > 20 else (1.0 if ah_disc > 0 else 0))
    fee = 2.0 if entry_fee < 5000 else (1.5 if entry_fee < 10000 else 1.0)
    return (ah + fee) / 5.0 * 5.0

def _score_retail(mult):
    if mult >= 500: return 5.0
    if mult >= 100: return 4.0
    if mult >= 50: return 3.0
    if mult >= 15: return 2.0
    return 1.0

def _score_risk(events):
    penalties = {"ipo_failed":-1.0,"refiled":-0.5,"regulatory_inquiry":-0.5,
                 "exec_departure":-0.5,"related_party_high":-0.3,"single_shareholder":-0.3,"loss_no_growth":-0.5}
    return max(5.0 + sum(penalties.get(e,0) for e in events), 0.5)

def calc_score(ipo):
    cs = _score_cs(ipo.get("cornerstone_investors",[]))
    th = _score_theme(ipo.get("category",""), ipo.get("chapter",""))
    vl = _score_val(ipo.get("ah_discount_pct",0), ipo.get("entry_fee",5000))
    rt = _score_retail(ipo.get("margin_multiple",0))
    rk = _score_risk(ipo.get("risk_events",[]))
    raw = cs*0.30 + th*0.20 + vl*0.20 + rt*0.15 + rk*0.15
    stars = "⭐" * min(round(raw), 5)
    if raw >= 4.5: rating = "强烈推荐"
    elif raw >= 4.0: rating = "推荐"
    elif raw >= 3.0: rating = "中性"
    elif raw >= 2.0: rating = "谨慎"
    else: rating = "风险"
    return {"name":ipo.get("name","?"),"code":ipo.get("code","?"),
            "scores":{"cornerstone":round(cs,1),"theme":round(th,1),"valuation":round(vl,1),
                      "retail":round(rt,1),"risk":round(rk,1)},
            "raw":round(raw,2),"stars":stars,"rating":rating}

DEMO = [
    {"name":"中科闻歌","code":"01956.HK","chapter":"18C","category":"AI",
     "cornerstone_investors":["嘉实国际","前海国际基金","国惠","华泰资本","民银国际"],
     "ah_discount_pct":0,"entry_fee":12140,"margin_multiple":0,"risk_events":[]},
    {"name":"礼邦医药-B","code":"09637.HK","chapter":"18A","category":"创新药",
     "cornerstone_investors":["嘉实国际","瑞银","清池资本","Hudson Bay","OrbiMed"],
     "ah_discount_pct":0,"entry_fee":4800,"margin_multiple":0,"risk_events":[]},
    {"name":"圣邦股份","code":"03661.HK","chapter":"","category":"半导体",
     "cornerstone_investors":["GIC","JPMAM","CPE","大家人寿","广发基金","嘉实国际","CPP Investments"],
     "ah_discount_pct":40.96,"entry_fee":8520,"margin_multiple":0,"risk_events":[]},
    {"name":"芯碁微装","code":"09630.HK","chapter":"","category":"半导体设备",
     "cornerstone_investors":["广发基金","苏州天使母基金"],
     "ah_discount_pct":40.46,"entry_fee":9000,"margin_multiple":0,"risk_events":[]},
    {"name":"来福谐波","code":"03952.HK","chapter":"","category":"机器人",
     "cornerstone_investors":["高瓴","红杉","IDG","源码","元璟","深创投","张江高科","米哈游","美团","比亚迪"],
     "ah_discount_pct":0,"entry_fee":5600,"margin_multiple":0,"risk_events":[]},
]

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input"); p.add_argument("--demo", action="store_true")
    args = p.parse_args()
    ipos = DEMO if args.demo else []
    if args.input and not args.demo:
        with open(args.input, encoding="utf-8") as fh: ipos = json.load(fh)
    if not ipos: p.print_help(); return
    results = sorted([calc_score(ipo) for ipo in ipos], key=lambda x: x["raw"], reverse=True)
    print(f"\n{'5-Dim Risk Score v4.1.1':-^60}\n")
    print(f"{'#':<3} {'Company':<14} {'CS':>5} {'Theme':>5} {'Val':>5} {'Retail':>5} {'Risk':>5} {'Total':>6} {'Rating':<10}")
    print("-" * 68)
    for i, r in enumerate(results, 1):
        s = r["scores"]
        print(f"{i:<3} {r['name']:<14} {s['cornerstone']:>5.1f} {s['theme']:>5.1f} {s['valuation']:>5.1f} {s['retail']:>5.1f} {s['risk']:>5.1f} {r['raw']:>6.2f} {r['stars']} {r['rating']}")
    print()

if __name__ == "__main__":
    main()
