# HKEX IPO 数据源手册

## A. 港交所披露易（hkexnews.hk）— 权威源

### 用途
- 招股章程（最终发售价、招股期、基石名单、绿鞋比例）
- 配发结果公告（一手中签率、回拨后比例、最终定价）
- 上市文件（公司业务、保荐人）

### 抓取方式
```
web_fetch url="https://www1.hkexnews.hk/listedco/listconews/sehk/[year]/[docid]/[filename].pdf"
```

### 常用搜索
- 新股档案：`https://www.hkex.com.hk/Listing/IPO/IPO-Documents`
- 招股结果：`https://www.hkex.com.hk/Listing/IPO-Information-Centre`

### 限制
- PDF 格式，web_fetch 解析效果差；建议结合 mmx search 找文字版摘要
- 实时配售结果通常 18:00 后发布

## B. 智通财经（zhitongcaijing.com / so.html5.qq.com）

### 用途
- 每日盘后新股孖展统计（19:00 左右发布）
- 招股期内的"新股速递"快讯
- 配发结果快讯

### 抓取方式
```
mmx search query "新股孖展 6月X日"
mmx search query "X公司 配发结果 中签率"
```

### 关键 URL 模式
- `so.html5.qq.com/page/real/search_news?docid=70000021_XXXXX` — 智通快讯

### 优势
- 更新及时（盘后即出）
- 包含孖展金额 + 倍数（最实用的热度指标）

## C. 金吾资讯（ipo.jinwucj.com）

### 用途
- 实时认购倍数排行（按倒计时显示）
- 招股概况一览表
- 聆讯消息

### 抓取方式
```
web_fetch url="https://ipo.jinwucj.com/"
```

### 优势
- 倒计时直观（"截止认购倒计时 1.5 天"）
- 热度可视化（认购热度星级）

## D. LiveReport 大数据（雪球活报告）

### 用途
- 一手中签率统计
- 招股期新股周报
- 公开 vs 国配倍数对比

### 抓取方式
```
mmx search query "LiveReport 招股周报"
mmx search query "一手中签率 港股"
```

### 优势
- 一手中签率数据全（回拨后）
- 历史新股的"涨幅/破发率"统计

## E. 格隆汇（gelonghui.com）

### 用途
- 公司公告全文
- 招股详情摘要
- 基石投资者名单

### 抓取方式
```
mmx search query "X公司 招股 公告"
```

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
