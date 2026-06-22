#!/usr/bin/env python3
import argparse, json, sys
sys.stdout.reconfigure(encoding="utf-8")

def standard_clawback(sub_multiple):
    if sub_multiple >= 100: return (50.0, ">=100x -> 50%")
    if sub_multiple >= 50:  return (40.0, "50-100x -> 40%")
    if sub_multiple >= 15:  return (30.0, "15-50x -> 30%")
    return (10.0, "<15x -> 10%")

def calc(chapter, sub_multiple, redistribution_pct=0, initial_pct=10.0):
    if chapter in ("18A", "18C") and redistribution_pct > 0:
        final = min(initial_pct + redistribution_pct, 50.0)
        mechanism = f"18A/18C realloc: {initial_pct}% + {redistribution_pct}% = {final}%"
    else:
        final, mechanism = standard_clawback(sub_multiple)
        if chapter in ("18A", "18C"):
            mechanism += " (no realloc clause, using standard)"
    is_trick = sub_multiple >= 100 and final <= 10
    risk = "TRICK ALLOTMENT: public>=100x but final 10%, HIGH RISK!" if is_trick else ""
    return {"chapter": chapter, "sub_multiple": sub_multiple, "initial_pct": initial_pct,
            "redistribution_pct": redistribution_pct, "final_pct": final,
            "mechanism": mechanism, "trick_allotment": risk}

DEMO = [
    ("18A", 200, 10.0, 10.0, "礼邦医药-B"),
    ("18C", 80, 5.0, 7.5, "中科闻歌"),
    ("标准", 150, 10.0, 0, "星源材质"),
]

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--chapter", default="标准")
    p.add_argument("--multiple", type=float, default=0)
    p.add_argument("--redistribution", type=float, default=0)
    p.add_argument("--initial", type=float, default=10.0)
    p.add_argument("--demo", action="store_true")
    args = p.parse_args()
    if args.demo:
        print("Clawback / Redistribution Calculator (Demo)\n")
        for chapter, mult, init, redist, name in DEMO:
            r = calc(chapter, mult, redist, init)
            s = r["trick_allotment"]
            print(f"{name}: final public {r['final_pct']}% | {r['mechanism']}" + (f" | {s}" if s else ""))
    elif args.multiple > 0:
        print(json.dumps(calc(args.chapter, args.multiple, args.redistribution, args.initial), ensure_ascii=False, indent=2))
    else:
        p.print_help()

if __name__ == "__main__":
    main()
