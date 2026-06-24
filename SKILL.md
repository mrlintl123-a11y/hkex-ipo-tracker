---
name: hkex-ipo-tracker
description: "查询并汇总港交所（HKEX）正在招股的公司，含招股详情、认购倍数、公开手数、中签率预估、绿鞋机制、基石投资者、A+H 标记，以及资金冲突矩阵。触发关键词：港股招股、港交所IPO、正在招股、新股打新、IPO 周报、HKEX IPO、配发结果、孖展认购、招股期、新股中签率、孖展倍数、回拨。"
---

# CRITICAL: 三步强制工作流

每次调用此 skill 必须完整执行以下三步，不可跳过任何一步：

## STEP 1: 抓取实时数据
- 检查交易日: python scripts/trading_calendar.py
- 抓取 IPO 数据: python scripts/scrape_jinwucj.py --output fresh_ipos.json
- 若抓取失败，改用 Playwright 直接访问 https://ipo.jinwucj.com/ 提取内容后手工编译 JSON

## STEP 2: 生成两份报告
```bash
python scripts/generate_report.py --input fresh_ipos.json
python scripts/generate_visual.py --input fresh_ipos.json
```

## STEP 3: 完整输出
- 将 generate_report.py 的 **完整 stdout** 逐字粘贴到对话框
- 附上 HTML 链接: [ipo_report.html](C:/Users/a/.codex/skills/hkex-ipo-tracker/ipo_report.html)
- **严禁** summarize、截断、只贴部分行

# 输出禁止事项
- 不要用"..."省略表格行
- 不要说"详见完整报告"
- 不要说"共XX只，这里展示前N只"
- 所有 IPO 必须出现在报告正文中

# 数据源
- 主源: 金吾资讯 (ipo.jinwucj.com)
- 备用: 智通财经, LiveReport, 港交所披露易
- 所有数据必须实时获取，禁止使用缓存文件替代

# 参考脚本
- scripts/scrape_jinwucj.py — Playwright 抓取金吾资讯详情页
- scripts/generate_report.py — 生成 Markdown 报告（含个股详情卡片）
- scripts/generate_visual.py — 生成 ipo_report.html 可视化
- scripts/trading_calendar.py — 交易日判断
- scripts/clawback_calculator.py — 18A/18C 回拨计算
- scripts/risk_score.py — 五维风险评估
- scripts/funding_scheduler.py — 资金排期助手

# 报告格式（由 generate_report.py 自动生成）
报告包含以下板块：资金冲突矩阵 → 新股速查表 → 个股详情（按截止日分组） → 关键观察 → 热度评分 → 资金分档策略 → 关键时间节点
