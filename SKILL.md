---
name: hkex-ipo-tracker
description: "实时查询并汇总港交所（HKEX）正在招股的新股，生成完整 Markdown 与 HTML 报告，涵盖招股期、发售价、入场费、全球发售、公开手数、孖展倍数、绿鞋、基石投资者、A+H、行业、市值、资金冲突和数据完整性。用于港股招股、港交所 IPO、正在招股、新股打新、IPO 周报、孖展认购、配发结果、中签率、回拨等请求。"
---

# 港交所 IPO 实时汇总

始终使用实时抓取数据，不得用仓库中的 `live_ipos.json` 或示例数据冒充最新结果。

## 首次运行

要求 Python 3.9+。若 Playwright 尚未安装，执行：

```bash
python3 -m pip install -r requirements.txt
python3 -m playwright install chromium
```

## 标准工作流

在 skill 根目录执行一键流程：

```bash
python3 scripts/run_report.py
```

该命令会依次：

1. 检查港股交易日。
2. 从金吾资讯实时发现正在招股的新股并逐只抓取详情，同时保存原始页面文本。
3. 按股票代码检索港交所披露易，自动下载招股书并补全绿鞋、基石、A+H、保荐人和募资净额。
4. 生成字段级来源记录和数据链路自查结果。
5. 生成 `fresh_ipos.json`、`ipo_report.md` 和 `ipo_report.html`，并将完整 Markdown 输出到 stdout。

主要审计产物：

- `scraped_ipos.json`：摘要源抓取阶段。
- `raw/jinwu/`：金吾日历响应和个股详情原文。
- `raw/hkex/`：港交所招股书 PDF 和提取文本。
- `official_enrichment_audit.json`：港交所文件发现及字段解析结果。
- `data_audit.json` / `data_audit.md`：获取、解析、规范化和渲染全链路检查。

若一键流程失败，可逐步执行：

```bash
python3 scripts/trading_calendar.py
python3 scripts/scrape_jinwucj.py --output scraped_ipos.json --raw-dir raw/jinwu
python3 scripts/fetch_hkex_official.py --input scraped_ipos.json --output fresh_ipos.json --raw-dir raw/hkex
python3 scripts/generate_report.py --input fresh_ipos.json --output ipo_report.md
python3 scripts/generate_visual.py --input fresh_ipos.json --output ipo_report.html
python3 scripts/audit_pipeline.py --input fresh_ipos.json --scraped scraped_ipos.json --report ipo_report.md --output-json data_audit.json --output-md data_audit.md
```

仅在港交所临时不可访问且用户明确接受降级结果时，才使用 `python3 scripts/run_report.py --skip-official`。

## 输出要求

- 将 `generate_report.py` 或 `run_report.py` 输出的完整 Markdown 原样展示，不省略任何 IPO。
- 附上命令最后打印的 `HTML_REPORT` 实际路径，不得写死 Windows 或用户目录。
- 所有表格单元格必须有值；未确认字段必须显示具体状态，例如“未找到港交所招股书”“原文存在但解析失败”或“来源冲突”，不得只写笼统的“待核实”。
- 不得把未知解释为“没有”，也不得让未知维度参与热度评分。
- 报告必须注明真实使用的数据来源与抓取时间，不得声称未执行的多源验证。
- 港交所招股书自动补全失败时，必须保留失败原因和官方检索时间，不得用摘要源推断替代官方确认。

## 数据质量

金吾资讯用于发现正在招股标的及获取动态摘要；孖展数据由其汇总自捷利交易宝。港交所披露易是招股书、配发结果、基石与绿鞋信息的权威来源，标准流程默认执行港交所招股书核验。

字段规范与公式见 `references/ipo-fields.md`，数据源选择见 `references/data-sources.md`，链路状态与自查规则见 `references/data-quality.md`。

本 skill 仅汇总公开信息，不构成投资建议。
