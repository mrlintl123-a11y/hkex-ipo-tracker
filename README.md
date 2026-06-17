# 📊 hkex-ipo-tracker

汇总港交所（HKEX）正在招股的公司，给港股打新投资者做**资金排期 + 标的筛选 + 热度判断**。

## ✨ 核心特性

- 📅 **资金冲突矩阵**：自动按"招股截止日间隔 < 2 天"分组，识别资金互锁的批次
- 🔍 **多源交叉验证**：智通财经 + 金吾资讯 + 港交所披露易三源校验，避免"无新股"误报
- ⏰ **认购倍数时点标注**：必标"截止前 N 天"，未至截止加 `⚠️ 仍会变`
- 📋 **一表速查**：上市日 / 公司 / 截止日 / 公开手数 / 认购倍数 / 绿鞋 / 基石 / A+H
- 🚫 **「无新股」也要汇报**：绝不静默（避免用户错过真实新股）
- 🏖️ **港股交易日判断**：内置 2026 年节假日表，非交易日自动跳过

## 🚀 快速开始

### 1. 直接使用（作为 OpenClaw Skill）

把这个目录放到你的 OpenClaw workspace 的 `skills/` 目录下：

```bash
cp -r hkex-ipo-tracker ~/.openclaw/workspace/skills/
```

然后触发关键词即可：

- `港股招股` / `港交所IPO` / `正在招股` / `新股打新`
- `IPO 周报` / `HKEX IPO` / `配发结果` / `孖展`
- `招股期` / `新股中签率` / `孖展倍数` / `回拨`

### 2. 单独使用 CLI 工具

```bash
# 检查今天是否港股交易日
python3 scripts/trading_calendar.py

# 检查指定日期
python3 scripts/trading_calendar.py 2026-07-01

# 每日 IPO 例行检查
python3 scripts/daily_check.py

# 冲突矩阵计算
python3 scripts/parse_conflict_matrix.py <<'EOF'
[
  {"name": "新股A", "code": "01000", "closing": "2026-06-16"},
  {"name": "新股B", "code": "02000", "closing": "2026-06-17"},
  {"name": "新股C", "code": "03000", "closing": "2026-06-23"}
]
EOF
```

## 📁 目录结构

```
hkex-ipo-tracker/
├── SKILL.md                        # 主工作流（6 步）
├── LICENSE                         # MIT License
├── .gitignore
├── references/
│   ├── data-sources.md             # 6 个数据源抓取指南
│   ├── ipo-fields.md               # 字段定义 + 计算公式
│   ├── ipo-mechanics.md            # 港股 IPO 机制（回拨/绿鞋/基石/FINI）
│   ├── holidays_2026.json          # 2026 年港股休市日
│   └── sample-data.json            # 模板数据
├── scripts/
│   ├── trading_calendar.py         # 港股交易日判断
│   ├── daily_check.py              # 每日例行检查（多源验证）
│   ├── parse_conflict_matrix.py    # 冲突矩阵计算
│   └── fetch_active_ipos.py        # mmx-cli 抓取脚本
```

## 🧠 工作流（6 步）

1. **交易日判断** → 非交易日直接跳过
2. **多源数据抓取** → 智通 + 金吾 + 港交所
3. **三级交叉验证** → L0/L1/L2/L3 确认机制
4. **字段计算** → 公开手数 / 中签率预估 / 冲突组
5. **热度评分** → 孖展倍数 + 基石 + 公开手数 + 入场费 + A+H 折价
6. **表格化输出** → 冲突矩阵 + 一表速查 + 策略建议

详细流程见 [`SKILL.md`](./SKILL.md)。

## 📊 输出示例

```markdown
## ⚠️ 资金冲突矩阵
| 截止日 | 6/16 | 6/17 | 6/18 | 6/23 |
|---|:---:|:---:|:---:|:---:|
| 6/16 | — | 🔴 1天 | 🟢 2天 | 🟢 7天 |
| 6/17 | 🔴 | — | 🔴 1天 | 🟢 6天 |
| 6/18 | 🟢 | 🔴 | — | 🟢 5天 |
| 6/23 | 🟢 | 🟢 | 🟢 | — |

## 🔴 超级冲突组（截止日 6/16-6/18，5 只）
| 公司 | 代码 | 截止日 | 认购倍数 | 绿鞋 | 基石 | A+H |
|---|---|---|---|:---:|:---:|:---:|
| ... | ... | ... | ... | ... | ... | ... |
```

## 🔧 数据源

| 源 | 用途 | 优先级 |
|---|---|---|
| 智通财经 | 每日孖展统计 | ⭐⭐⭐ 主源 |
| 金吾资讯 (ipo.jinwucj.com) | 招股概况一览 | ⭐⭐⭐ |
| 港交所披露易 (hkexnews.hk) | 招股章程 / 配发结果 | ⭐⭐⭐⭐ 权威 |
| LiveReport (雪球) | 一手中签率 | ⭐⭐ |
| 格隆汇 | 公司公告 | ⭐⭐ |
| A 股行情 | A+H 比价 | ⭐ |

## ⚙️ 依赖

- Python 3.7+
- mmx-cli（[MiniMax Token Plan](https://MiniMax.io) 搜索工具，用于智通财经检索）

## 📅 维护

- 每年 12 月底前用 `mmx search query "次年 港股 交易日 安排"` 更新 `references/holidays_YYYY.json`
- 重阳节日期需以港交所官方公告为准（基于农历推算）

## ⚠️ 免责声明

本工具仅供信息汇总和学习使用，**不构成任何投资建议**。打新有风险，投资需谨慎。请独立判断并自负盈亏。

## 📜 License

MIT License — 详见 [LICENSE](./LICENSE)
