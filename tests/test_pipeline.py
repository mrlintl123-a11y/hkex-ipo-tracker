import os
import sys
import unittest
from datetime import datetime


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
sys.path.insert(0, SCRIPTS)

from generate_report import render_report  # noqa: E402
from generate_visual import render_html  # noqa: E402
from audit_pipeline import build_audit  # noqa: E402
from fetch_hkex_official import parse_official_text  # noqa: E402
from ipo_schema import UNKNOWN, field_status, heat_score, normalize_ipo  # noqa: E402
from scrape_jinwucj import extract_detail  # noqa: E402


PAGE_TEXT = """
资料来源: 测试科技 (01234)
发行资料
招股日期： 2026-06-24 至 2026-06-27
公布售股结果日期： 2026-06-30
上市日期： 2026-07-02
招股价范围： 10.0~12.0 港币
每手股数： 200 股
入场费： 2424.20 港币
所属行业： 软件服务
总发售数量： 1,200.50 万股
预计市值： 84.01 亿
联席保荐人： 中金公司、摩根士丹利
基石投资者： 高瓴、GIC、红杉
在超额配股权未获行使的情况下，全球发售所得款项净额将为约1,003.3百万港元。
公开发售： 10.00%
认购倍数(预估)： 123.45 倍 【数据更新： 2026-06-24 20:18:19】
公司同时在 123456.SH 上市。
"""

OFFICIAL_TEXT = """
GLOBAL OFFERING
“Sole Sponsor” Example Securities Limited
our A Shares are listed on the Shenzhen Stock Exchange under stock code: 300866
^THE CORNERSTONE PLACING$
THE CORNERSTONE PLACING
We have entered into cornerstone investment agreements.
Assuming the Over-allotment Option is not exercised
Approximate % of the Offer Shares
30.00% 3.00% 26.09% 2.90%
We believe that the Cornerstone Placing signifies confidence.
CORNERSTONE INVESTORS
The Over-allotment Option may require additional Offer Shares representing not more than 15% of the Offer Shares.
The net proceeds are estimated to be approximately HK$1,003.3 million.
"""


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.record = extract_detail(PAGE_TEXT, code="01234")
        self.now = datetime(2026, 6, 24, 21, 0)

    def test_scraper_emits_canonical_fields(self):
        self.assertEqual(self.record["name"], "测试科技")
        self.assertEqual(self.record["subscription_start"], "2026-06-24")
        self.assertEqual(self.record["period_start"], "2026-06-24")
        self.assertEqual(self.record["global_shares"], 12_005_000)
        self.assertEqual(self.record["description"], "软件服务")
        self.assertEqual(self.record["est_market_cap_hkd"], 8_401_000_000)
        self.assertEqual(self.record["fundraising"], "10.03亿港元")
        self.assertEqual(self.record["margin_data_date"], "2026-06-24 20:18:19")
        self.assertIn("高瓴", self.record["cornerstone"])
        self.assertTrue(self.record["greenshoe"].startswith("✅"))
        self.assertIn("123456.SH", self.record["a_h"])
        self.assertEqual(field_status(self.record, "cornerstone"), "collected")
        self.assertEqual(field_status(self.record, "public_lots"), "derived")

    def test_scraper_classifies_missing_source_coverage(self):
        text = PAGE_TEXT.replace("基石投资者： 高瓴、GIC、红杉", "")
        record = extract_detail(text, code="01234")
        self.assertEqual(record["cornerstone"], UNKNOWN)
        self.assertEqual(
            field_status(record, "cornerstone"),
            "authoritative_source_not_fetched",
        )

    def test_normalizer_maps_legacy_aliases(self):
        normalized = normalize_ipo(
            {
                "name": "旧数据",
                "code": "9999.HK",
                "subscription_period": "2026-06-20 to 2026-06-25",
                "total_shares": "500万股",
                "market_cap": 60,
                "industry": "医疗",
            }
        )
        self.assertEqual(normalized["code"], "09999")
        self.assertEqual(normalized["period_start"], "2026-06-20")
        self.assertEqual(normalized["global_shares"], 5_000_000)
        self.assertEqual(normalized["est_market_cap_hkd"], 6_000_000_000)
        self.assertEqual(normalized["description"], "医疗")

    def test_unknown_dimensions_do_not_receive_hidden_scores(self):
        record = normalize_ipo(
            {
                "name": "未知扩展字段",
                "code": "01235",
                "closing_date": "2026-06-27",
                "offer_price": "10 HKD",
                "board_lot": 100,
                "public_lots": 10_000,
                "entry_fee": 1_010,
                "cornerstone": "",
                "a_h": "",
                "margin_multiple": "暂无",
            }
        )
        score = heat_score(record)
        self.assertEqual(score["coverage"], "2/5")
        self.assertIsNone(score["components"]["cornerstone"])
        self.assertIsNone(score["components"]["a_h"])

    def test_markdown_contains_values_or_explicit_unknowns(self):
        unknown = dict(self.record)
        unknown["code"] = "01235"
        unknown["name"] = "待核实公司"
        unknown["cornerstone"] = ""
        unknown["a_h"] = ""
        report = render_report([self.record, unknown], now=self.now)
        self.assertNotIn("?~?", report)
        self.assertNotIn("|  |", report)
        self.assertNotIn("| 0股 |", report)
        self.assertIn("2026-06-24 至 2026-06-27", report)
        self.assertIn("软件服务", report)
        self.assertIn(UNKNOWN, report)

    def test_html_has_no_stale_hardcoded_content(self):
        output = render_html([self.record], now=self.now)
        self.assertIn("测试科技", output)
        self.assertIn("2026-06-24 至 2026-06-27", output)
        self.assertNotIn("6/23 16:00", output)
        self.assertNotIn("PT Merdeka Gold", output)
        self.assertNotIn("中科闻歌+", output)

    def test_official_prospectus_parser(self):
        parsed = parse_official_text(OFFICIAL_TEXT)
        self.assertEqual(parsed["greenshoe"]["value"], "✅ 有（上限15%）")
        self.assertIn("30%", parsed["cornerstone"]["value"])
        self.assertEqual(parsed["a_h"]["value"], "✅ A+H（300866.SZ）")
        self.assertEqual(parsed["sponsors"]["value"], "Example Securities Limited")
        self.assertEqual(parsed["fundraising"]["value"], "10.03亿港元")

    def test_pipeline_audit_detects_no_value_loss(self):
        report = render_report([self.record], now=self.now)
        audit = build_audit([self.record], [self.record], report)
        self.assertEqual(audit["summary"]["pipeline_errors"], {})

    def test_pipeline_audit_ignores_records_intentionally_filtered_from_report(self):
        closed = dict(self.record)
        closed["code"] = "09999"
        closed["closing_date"] = "2026-06-23"
        closed["period_end"] = "2026-06-23"
        report = render_report([self.record, closed], now=self.now)
        audit = build_audit([self.record, closed], [self.record, closed], report)
        self.assertNotIn("09999", report)
        self.assertEqual(audit["summary"]["pipeline_errors"], {})


if __name__ == "__main__":
    unittest.main()
