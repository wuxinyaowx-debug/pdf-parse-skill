# 输出约定（result.json 字段说明）

每次解析产出一份 `result.json`。评测模式下由 `run_case.py` 写入 `<output>/result.json`，
单文件模式下由 `parse_pdf.py` 写入 `<out>/result.json`。

## 顶层字段

| 字段 | 类型 | 说明 |
|-|-|-|
| `case_id` | string | 来自 `case.json` 的 `case_id`（无则 `unknown`） |
| `status` | string | `success` / `partial` / `failed` / `unreadable` |
| `input` | object | 输入 PDF 路径与页数 |
| `metadata` | object | 题名猜测（附置信度说明，须人工回第 1 页核对） |
| `sections` | array | 章节：`title`、`level`（1=一级）、`page`、`bbox`、`path`（层级路径） |
| `paragraphs` | array | 正文段落：`text`（去连字符后逐字拼接）、`page`、`bbox`、`section` |
| `tables` | array | 表：`label`、`caption`、`page`、`bbox`、`note`（网格还原程度说明） |
| `figures` | array | 图题：`label`、`caption`、`page`、`bbox` |
| `equations` | array | 编号公式：`text`（原文符号串）、`page`、`bbox`、`uncertain` |
| `references` | array | 文献条目：`index`、`text`、`page`、`bbox` |
| `removed_running_matter` | array | 被剔除的页眉页脚文本及出现页码 |
| `uncertainties` | array | 无法判定项：扫描页、提取失败页、未产出字段等 |
| `stats` | object | 各类元素计数与正文词数 |
| `runtime` | object | 工具链与耗时 |
| `changes` | array | 本次运行对输入/配置的变更记录（通常为空） |

## 证据定位

- `bbox` 为 PDF 页面坐标（pt，原点左上）：`{x0, y0, x1, y1}`，与 `pdftotext -bbox-layout` 一致。
- `fulltext.md` 中 `[p.N]` 锚点表示其后内容起始于第 N 页，配合 `bbox` 可回查原文区块。
- 任何结论引用都必须能指回至少一个 `page`；无法定位的内容写入 `uncertainties`，不得写成事实。

## 状态语义

- `success`：全部页面有文本层且解析无异常。
- `partial`：部分页面扫描/提取失败，或存在无法判定的结构；`uncertainties` 必须说明受限范围与人工接管位置。
- `unreadable`：全部页面无文本层且无 OCR 结果；不输出任何猜测文字。
- `failed`：无法读取输入（加密、损坏、缺工具）；`reason` 给出原始报错。

## output_contract 对齐

`run_case.py` 读取 `case.json` 的 `output_contract`（dict 或 list），保证其声明的每个字段在
最终 `result.json` 顶层存在；无法产出的字段置 `null` 并在 `uncertainties` 中登记，不凭空填充。
