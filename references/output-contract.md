# 输出约定（v2）

每次运行产出 `result.json`（评测模式在 `<output>/result.json`）与 `fulltext.md`。

## run_case.py 顶层字段

| 字段 | 类型 | 说明 |
|-|-|-|
| `case_id` | string | 来自 `case.json`（缺失则 `unknown`） |
| `status` | string | `success` / `partial` / `failed` / `unreadable`。解析完成但任务条目未答完时为 `partial`，不用成功冒充 |
| `input` | object | PDF 路径与页数 |
| `task` | string | task.md 前 2000 字符 |
| `task_items` | array | 任务条目（见下） |
| `result` | object | 解析器完整输出（见下） |
| `sources` | array | 各类证据在 result 中的定位路径 |
| `uncertainties` | array | 无法判定/未核验/未产出项，含原因 |
| `changes` | array | 变更记录（如合并 agent 答案） |
| `output_contract_raw` | any | case.json 中 output_contract 原文 |
| `runtime` | object | 工具链与耗时 |

`output_contract` 声明的每个字段保证存在于顶层：有确定性来源的填实际值；
无法产出的置 `null` 并在 `uncertainties` 说明原因，**不填假值**。

## task_items[*]

| 字段 | 说明 |
|-|-|
| `id` / `text` / `type` | 条目编号 / 原文 / 分类（qa、translate、extract、verify） |
| `candidate_evidence` | 阶段 1 检索到的证据：`kind`（paragraph/table/figure）、索引、`page`、`bbox`、`keyword_hits`、`snippet`；`keyword_hits=0` 且带 `fallback` 字段者为类型兜底证据（如中文问题提到"表"），不是关键词命中 |
| `answer` | 阶段 2 前为 `null`；Agent 作答并 `--answers` 合并后为答案文本 |
| `answer_status` | `pending_agent_phase2` / `answered_by_agent` |
| `evidence` | Agent 绑定的证据（合并后） |

### answers.json 格式（阶段 2 输入）

```json
{"items": [{"id": "item-1", "answer": "……",
            "evidence": [{"kind": "paragraph", "paragraph_index": 0, "page": 1}],
            "confidence": "high"}]}
```

## result（解析器输出）字段

| 字段 | 说明 |
|-|-|
| `metadata` | `title`/`authors`/`affiliations`/`abstract`/`keywords`/`doi`/`journal`/`year`；每项 `{value, page, bbox, confidence}` 或 `null` |
| `sections` | `title`、`level`、`page`、`bbox`（标题行自身）、`path` |
| `paragraphs` | `text`（去连字符）、`page`、`pages`、`bbox`（段落自身文本行并集）、`page_bboxes`（跨页时分页 bbox）、`n_lines`、`cross_page`、`section` |
| `tables` | `label`、`caption`、`page`、`bbox`（题注+表格体并集）、`continued`、`grid`（`n_columns`、`n_header_rows`、`headers`、`rows`、`merged_cells`、`uncertain`）、`markdown`；无法成格时保留 `raw_lines` 且 `uncertain: true` |
| `figures` | `label`、`caption`、`page`、`bbox` |
| `equations` | `text`、`number`、`page`、`bbox`、`multiline`、`uncertain`、`note`（上下标不还原提示） |
| `references` | `index`、`text`、`page`、`bbox` |
| `removed_running_matter` | 被剔除页眉页脚文本与页码 |
| `uncertainties` | 页面级/文档级不确定项 |
| `stats` | 计数 + `page_classes`（text/sparse/empty）+ `ocr_pages`/`sparse_pages`/`empty_pages` |

## 证据定位

- `bbox` 为 PDF 页面坐标（pt，原点左上）；OCR 块坐标由 300dpi 像素按 72/300 换算，
  并标注 OCR 来源与未核验状态。
- `fulltext.md` 中 `[p.N]` 锚点表示其后内容起始于第 N 物理页。

## 状态语义

- `success`：全部页面解析正常，且（有任务时）任务条目均已作答。
- `partial`：部分页面受限、OCR 缺失、或任务条目待 Agent 作答；`uncertainties` 说明范围。
- `unreadable`：全部页面无文字层且 OCR 无结果；不输出猜测文字。
- `failed`：无法读取输入；`reason` 给出原始报错。
