#!/usr/bin/env python3
import argparse, json, sys
sys.stdout.reconfigure(encoding="utf-8")

LIMITS = {"Conservative":3,"Moderate":5,"Aggressive":8}

def allocate(funds, preference, leverage, ipos):
    max_pos = LIMITS.get(preference, 5)
    allocs = []; remaining = funds * leverage
    for ipo in sorted(ipos, key=lambda x: x.get("score",0), reverse=True):
        if len(allocs) >= max_pos: break
        entry = ipo.get("entry_fee",5000)
        position = min(remaining * 0.3, entry * 10)
        if position < entry: continue
        allocs.append({"name":ipo["name"],"code":ipo["code"],"entry_fee":entry,
                       "position":round(position,0),"lots":round(position/entry),
                       "score":ipo.get("score",0)})
        remaining -= position
    return {"funds":funds,"leverage":leverage,"buying_power":funds*leverage,
            "preference":preference,"max_positions":max_pos,"allocations":allocs,"remaining":round(remaining,0)}

DEMO = [
    {"name":"礼邦医药-B","code":"09637.HK","entry_fee":4800,"score":3.69},
    {"name":"来福谐波","code":"03952.HK","entry_fee":5600,"score":3.12},
    {"name":"圣邦股份","code":"03661.HK","entry_fee":8520,"score":3.58},
    {"name":"中科闻歌","code":"01956.HK","entry_fee":12140,"score":3.87},
    {"name":"芯碁微装","code":"09630.HK","entry_fee":9000,"score":3.35},
]

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--funds", type=float, default=50000)
    p.add_argument("--preference", default="Moderate", choices=["Conservative","Moderate","Aggressive"])
    p.add_argument("--leverage", type=int, default=25)
    p.add_argument("--demo", action="store_true")
    args = p.parse_args()
    result = allocate(args.funds, args.preference, args.leverage, DEMO)
    print(f"\n{'Funding Schedule':-^55}\n")
    print(f"Funds: HK | Leverage: {args.leverage}x | Buying Power: HK")
    print(f"Preference: {args.preference} | Max Positions: {LIMITS[args.preference]}\n")
    print(f"{'Company':<14} {'Entry':>8} {'Position':>10} {'Lots':>6} {'Score':>6}")
    print("-" * 50)
    for a in result["allocations"]:
        print(f"{a['name']:<14} {a['entry_fee']:>8,.0f} {a['position']:>10,.0f} {a['lots']:>6} {a['score']:>6.2f}")
    print(f"\nRemaining: HK\n")

if __name__ == "__main__":
    main()
