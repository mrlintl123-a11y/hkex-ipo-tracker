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
2. 从金吾资讯实时发现正在招股的新股并逐只抓取详情。
3. 生成 `fresh_ipos.json`、`ipo_report.md` 和 `ipo_report.html`。
4. 将完整 Markdown 报告输出到 stdout。

若一键流程失败，可逐步执行：

```bash
python3 scripts/trading_calendar.py
python3 scripts/scrape_jinwucj.py --output fresh_ipos.json
python3 scripts/generate_report.py --input fresh_ipos.json --output ipo_report.md
python3 scripts/generate_visual.py --input fresh_ipos.json --output ipo_report.html
```

## 输出要求

- 将 `generate_report.py` 或 `run_report.py` 输出的完整 Markdown 原样展示，不省略任何 IPO。
- 附上命令最后打印的 `HTML_REPORT` 实际路径，不得写死 Windows 或用户目录。
- 所有表格单元格必须有值；未从来源确认的字段显示“待核实”。
- 不得把“待核实”解释为“没有”，也不得让未知维度参与热度评分。
- 报告必须注明真实使用的数据来源与抓取时间，不得声称未执行的多源验证。

## 数据质量

主数据源为金吾资讯；孖展数据由其汇总自捷利交易宝。港交所披露易是招股书、配发结果、基石与绿鞋信息的权威来源。若用户要求权威核验，优先用港交所文件补充“待核实”字段，再重新生成报告。

字段规范与公式见 `references/ipo-fields.md`，数据源选择见 `references/data-sources.md`。

本 skill 仅汇总公开信息，不构成投资建议。
