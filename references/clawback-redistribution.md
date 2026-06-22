# 18A/18C 重新分配机制

## 核心规则
18A/18C 新股可在章程中设定"重新分配"条款，优先于标准回拨。

## 判定算法
if 18A/18C redistribution > 0:
    final_public_pct = redistribution_max_pct
else:
    final_public_pct = standard_clawback_pct(subscription_multiple)

## 实战案例
| 新股 | 章节 | 初始公开 | 重新分配 | 最终公开 |
|---|---|---|---|---|
| 礼邦医药-B | 18A | 10% | +10% | 20% |
| 中科闻歌 | 18C | 5% | +15% | 20% |
