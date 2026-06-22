#!/usr/bin/env python3
import argparse, json, sys
sys.stdout.reconfigure(encoding="utf-8")

def calc_discount(a_price, h_price, rate=0.90):
    diff = 1 - (h_price / a_price * rate)
    if diff > 0.40: tier, advice = ">40% 极佳", "重仓打"
    elif diff >= 0.20: tier, advice = "20-40% 良好", "正常打"
    elif diff > 0: tier, advice = "0-20% 一般", "小仓位"
    else: tier, advice = "溢价", "不打"
    return {"a_price_cny": a_price, "h_price_hkd": h_price, "fx_rate": rate,
            "discount_pct": round(diff * 100, 2), "tier": tier, "advice": advice}

DEMO = [
    ("领益智造", "002600.SZ", 18.32, 10.18, 0.90),
    ("圣邦股份", "300661.SZ", 143.51, 85.20, 0.90),
    ("芯碁微装", "688630.SH", 169.85, 90.00, 0.90),
    ("星源材质", "300568.SZ", 20.74, 8.98, 0.90),
]

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--a", type=float); p.add_argument("--h", type=float)
    p.add_argument("--rate", type=float, default=0.90)
    p.add_argument("--batch"); p.add_argument("--demo", action="store_true")
    args = p.parse_args()
    if args.demo:
        print("A+H 折价分析 (Demo)\n")
        print(f"{'公司':<12} {'A股(CNY)':>8} {'H发售价':>8} {'汇率':>6} {'折价率':>8} {'档位':<12} {'建议':<8}")
        print("-" * 72)
        for name, code, a, h, rate in DEMO:
            r = calc_discount(a, h, rate)
            print(f"{name:<12} {a:>8.2f} {h:>8.2f} {rate:>6.2f} {r['discount_pct']:>7.2f}% {r['tier']:<12} {r['advice']:<8}")
    elif args.batch:
        with open(args.batch, encoding="utf-8") as fh:
            data = json.load(fh)
        results = []
        for item in data:
            r = calc_discount(item.get("a_price", 0), item.get("h_price", 0), item.get("rate", 0.90))
            item.update(r); results.append(item)
        print(json.dumps(results, ensure_ascii=False, indent=2))
    elif args.a and args.h:
        print(json.dumps(calc_discount(args.a, args.h, args.rate), ensure_ascii=False, indent=2))
    else:
        p.print_help()

if __name__ == "__main__":
    main()
