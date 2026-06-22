#!/usr/bin/env python3
import argparse, json, sys
sys.stdout.reconfigure(encoding="utf-8")

def detect_trick(sub_multiple, final_public_pct, initial_pct=10.0):
    if sub_multiple >= 100 and final_public_pct <= initial_pct + 1:
        return {"trick":True,"risk":"HIGH","detail":f"Public {int(sub_multiple)}x but final only {final_public_pct}% (should be 50%)"}
    if sub_multiple >= 50 and final_public_pct <= initial_pct + 1:
        return {"trick":True,"risk":"MED","detail":f"Public {int(sub_multiple)}x but final only {final_public_pct}%"}
    return {"trick":False,"risk":"NONE","detail":"Normal clawback/redistribution"}

def track(ipo):
    trick = detect_trick(ipo.get("public_multiple",0), ipo.get("final_public_pct",10), ipo.get("initial_public_pct",10))
    return {"name":ipo.get("name","?"),"code":ipo.get("code","?"),
            "final_price":ipo.get("final_price",""),"public_multiple":ipo.get("public_multiple",0),
            "intl_multiple":ipo.get("intl_multiple",0),"one_lot_rate":ipo.get("one_lot_rate",""),
            "final_public_pct":ipo.get("final_public_pct",10),"trick_allotment":trick}

DEMO = [
    {"name":"海清智元","code":"01392.HK","final_price":"7.20","public_multiple":213,"intl_multiple":1.5,
     "one_lot_rate":"2.1%","final_public_pct":30,"initial_public_pct":10},
    {"name":"星源材质","code":"06067.HK","final_price":"8.98","public_multiple":496,"intl_multiple":2.8,
     "one_lot_rate":"TBD","final_public_pct":50,"initial_public_pct":10},
    {"name":"金叶国际","code":"8549.HK","final_price":"0.25","public_multiple":9030,"intl_multiple":0.3,
     "one_lot_rate":"0.01%","final_public_pct":10,"initial_public_pct":10},
]

def main():
    p = argparse.ArgumentParser(); p.add_argument("--demo", action="store_true")
    args = p.parse_args()
    print(f"\n{'Allotment Tracker':-^60}\n")
    for ipo in DEMO:
        r = track(ipo); t = r["trick_allotment"]
        flag = "!! RED FLAG !!" if t["trick"] else "OK"
        print(f"{r['name']} ({r['code']}): Price={r['final_price']} | Pub={r['public_multiple']}x | Intl={r['intl_multiple']}x | 1-Lot={r['one_lot_rate']} | Final={r['final_public_pct']}% | [{flag}]")
        if t["trick"]: print(f"  WARNING: {t['detail']}")
    print()

if __name__ == "__main__":
    main()
