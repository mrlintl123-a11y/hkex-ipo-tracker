# HKEX IPO 数据源手册

## A. 港交所披露易（hkexnews.hk）— 权威源

### 用途
- 招股章程（最终发售价、招股期、基石名单、绿鞋比例）
- 配发结果公告（一手中签率、回拨后比例、最终定价）
- 上市文件（公司业务、保荐人）

### 抓取方式
- 直接访问：`https://www.hkex.com.hk/Listing/IPO/IPO-Documents`
- 搜索：「港交所 招股章程」「HKEX IPO prospectus」

### 限制
- PDF 格式，内容提取需做 OCR 或找文字版摘要
- 实时配售结果通常 18:00 后发布

## B. 智通财经（zhitongcaijing.com / so.html5.qq.com）

### 用途
- 每日盘后新股孖展统计（19:00 左右发布）
- 招股期内的"新股速递"快讯
- 配发结果快讯

### 抓取方式
搜索关键词：
- 「新股孖展 月 日」
- 「公司名 配发结果 中签率」

### 优势
- 更新及时（盘后即出）
- 包含孖展金额 + 倍数（最实用的热度指标）

## C. 金吾资讯（ipo.jinwucj.com）

### 用途
- 实时认购倍数排行（按倒计时显示）
- 招股概况一览表
- 聆讯消息

### 抓取方式
直接访问：`https://ipo.jinwucj.com/`

### 优势
- 倒计时直观（"截止认购倒计时 1.5 天"）
- 热度可视化（认购热度星级）

## D. LiveReport 大数据（雪球活报告）

### 用途
- 一手中签率统计
- 招股期新股周报
- 公开 vs 国配倍数对比

### 抓取方式
搜索关键词：
- 「LiveReport 招股周报」
- 「一手中签率 港股」

### 优势
- 一手中签率数据全（回拨后）
- 历史新股的"涨幅/破发率"统计

## E. 格隆汇（gelonghui.com）

### 用途
- 公司公告全文
- 招股详情摘要
- 基石投资者名单

### 抓取方式
搜索关键词：「公司名 招股 公告」

## F. A 股行情（用于 A+H 比价）

### 用途
- A 股实时股价（A+H 折价计算）
- A 股公司公告

### 抓取方式
- 腾讯财经：`https://qt.gtimg.cn/q=sh000001,sz399001`
- 东方财富：`https://quote.eastmoney.com/`

## 数据源组合策略

| 场景 | 推荐组合 | 时点 |
|---|---|---|
| 招股期间日常跟踪 | B 智通 + C 金吾 | 盘后 19:00 |
| 配发结果 | A 港交所 + D LiveReport | 截止日 + 1 个交易日 18:00 后 |
| A+H 折价 | A 港交所 + F A 股 | 招股截止前 1 天 |
| 一手中签率 | D LiveReport + A 港交所 | 配发结果公告后 |

## 🔌 搜索后端适配

本 skill 支持多种搜索后端，通过环境变量 `SEARCH_PROVIDER` 切换：

| 后端 | 说明 | 适用场景 |
|---|---|---|
| `agent_native`（默认） | 由 Codex/Claude/GPT agent 使用自身搜索能力 | Codex、Claude Desktop、ChatGPT 等 |
| `mmx` | MiniMax mmx CLI（需 `pip install mmx-cli`） | MiniMax Token Plan 用户 |
| `custom` | 通过 `CUSTOM_SEARCH_CMD` 指定命令模板 | 其他 CLI 搜索工具 |

示例：
```bash
# agent_native 模式：输出搜索清单，agent 自行搜索后喂回
export SEARCH_PROVIDER=agent_native
python scripts/search_provider.py --emit-queries

# mmx 模式：直接调用
SEARCH_PROVIDER=mmx python scripts/fetch_active_ipos.py --provider mmx

# 自定义模式
export CUSTOM_SEARCH_CMD="web_search --query {query}"
export SEARCH_PROVIDER=custom
```
