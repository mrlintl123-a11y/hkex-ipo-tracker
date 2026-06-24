# 字段来源与数据链路自查

每条 IPO 记录的 `field_meta` 按字段保存以下内容：

- `value`：规范化后的字段值。
- `status`：当前获取或处理状态。
- `source_name` / `source_url`：实际来源和原文地址。
- `retrieved_at`：获取时间。
- `note`：推导、覆盖、冲突或失败原因。

## 状态

| 状态 | 含义 |
|---|---|
| `official_confirmed` | 已由港交所文件确认 |
| `collected` | 已从摘要或动态源获取 |
| `derived` | 由已确认字段推导，报告必须说明推导依据 |
| `partial` | 已确认字段存在，但比例、名单等仍不完整 |
| `authoritative_source_not_fetched` | 摘要源没有完整值，港交所文件尚未抓取 |
| `official_document_not_found` | 已执行港交所检索，但没有找到招股书 |
| `official_document_fetch_failed` | 找到文件，但下载、PDF 解析或 OCR 失败 |
| `parse_failed` | 原文出现字段或章节，但规则没有提取出值 |
| `source_not_disclosed` | 已检查来源，来源本身没有披露该值 |
| `conflict` | 不同来源值不一致，或字段值与元数据状态矛盾 |
| `untraced` | 旧数据没有记录字段来源链路 |

## 自动判定

- 原始页出现字段关键词而抓取 JSON 为空：抓取解析失败。
- 抓取 JSON 有值而最终 JSON 为空：规范化阶段丢失。
- 最终 JSON 有值而 Markdown 报告没有：渲染阶段丢失。
- 港交所检索未执行、未找到文件或文件解析失败：权威来源获取缺口。

运行 `scripts/audit_pipeline.py` 会生成机器可读 JSON 和人工可读 Markdown。每次发布前应满足：

1. `pipeline_errors` 为 0。
2. 关键字段没有 `conflict`。
3. `partial` 和 `parse_failed` 均有原文 URL，可用固定招股书样本复现。
