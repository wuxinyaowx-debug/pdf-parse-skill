---
name: scientific-pdf-parser
description: 将科研文献 PDF 解析为可核验的结构化结果（章节层级、段落、表格网格、图题、编号公式、参考文献、论文元数据，逐项附页码与版面区块定位），支持单/双/三栏阅读顺序还原、页眉页脚剔除、扫描件 OCR（Tesseract TSV 真实坐标），并按 task.md 完成科研问答/翻译/提取/核验的两阶段任务流程。Use when a task requires parsing a scientific paper PDF, extracting text/tables/equations/references with page-level evidence, fixing multi-column reading order, or answering literature-reading questions with verifiable citations. 当任务要求解析科研文献 PDF、还原多栏阅读顺序、提取表格公式参考文献并给出页码证据、或依据原文回答科研问题时使用。
---

# Scientific PDF Parser（科研文献 PDF 解析）

将科研文献 PDF 解析为结构化、可回查原文证据的结果，并在此基础上完成 task.md 指定的科研阅读任务。核心原则：**逐字提取、顺序正确、结构可拆、结论可核、答不出就明说**。

## 适用条件与触发场景

- 输入为科研文献 PDF（单/双/三栏、中英文、文本型或扫描件），任务要求阅读、解析、提取、问答、翻译或核验其内容。
- 需要可复核证据（页码、段落、图表、公式位置）的结构化输出，尤其是评测约定中的 `result.json`。
- 不适用：已有可靠结构化全文（如出版社 XML）且无需版面证据的任务。

## 环境与依赖

- 必需：`pdftotext`（Poppler）、Python ≥ 3.9（仅标准库）。
- 可选：`pdfinfo`、`pdftoppm` + `tesseract`（扫描页 OCR，使用 TSV 输出获取真实文字坐标）。
- 开发/测试（非运行必需）：matplotlib（生成合成回归夹具）。
- 所有路径相对于 Skill 目录解析，不依赖个人文件或手工中间步骤。

## 两阶段任务流程（重要）

本 Skill 明确区分**确定性解析**与**语义任务执行**。Python 脚本不做模型推理。
在评测环境（DeepSeek Harness，单案例单次执行）中，Agent 应按 ①阶段 1 →
②语义作答 → ③阶段 2 合并 的顺序在一次执行内完成一个案例，并确认
`/app/output/result.json` 已写出。

### 阶段 1：解析与证据索引（脚本完成）

```
python <skill_dir>/scripts/run_case.py --input /input --output /app/output --work /app/work
```

- 读取 `case.json`（`case_id`、`output_contract`、材料路径）与 `task.md`。
- 运行解析器：全文提取、章节/段落/表格/图题/公式/参考文献、元数据、页码+bbox 证据。
- 将 task.md 拆分为任务条目（item），分类（qa/translate/extract/verify），并对每个条目做关键词检索，输出 `candidate_evidence`（段落/表格/图题的真实索引、页码、bbox、命中数；跨语言零命中时给出标注过的类型兜底证据）。
- 写出 `<output>/result.json` 与 `<output>/fulltext.md`；此时 `answer=null`、`status=partial`，**不冒充任务完成**。

### 阶段 2：Agent 语义作答（调用者完成）

Agent 阅读 `<output>/result.json` 与 `<output>/fulltext.md`，对每个 `task_items[*]`：

1. 优先使用 `candidate_evidence` 定位原文；不够时按 `sections`/`paragraphs` 的页码与 bbox 自行检索。
2. 生成答案，为每项答案绑定证据（段落/表格索引 + 页码）；找不到依据时如实写"原文未报告/无法判断"。
3. 将答案写入 `answers.json`（格式见 `references/output-contract.md`），然后执行合并：

```
python <skill_dir>/scripts/run_case.py --input /input --output /app/output --work /app/work --answers <answers.json>
```

- 合并运行**不重新解析 PDF**：指纹（case/task/PDF）一致时直接复用 `<work>/phase1_final.json`。
- 合并时逐条**校验证据**：索引越界、页码与对象实际页不符、bbox 与实际偏差 > 1.5pt 均判无效；
  `answer_status` 据此为 `answered_verified` / `answered_evidence_suspect` / `answered_no_evidence`，
  无效与无证据答案登记入 `uncertainties`。全部条目有答案后 `status` 由解析状态决定。

### 单文件解析模式（无任务时）

```
python <skill_dir>/scripts/parse_pdf.py <paper.pdf> --out <output_dir>
```

## 解析流程（脚本已实现）

1. **页面分类**：逐页统计词数，区分 文本页 / 少文本页（图表页，0<词数<20）/ 无文字层页（0 词）；少文本页不误判为不可读。
2. **文本层提取**：`pdftotext -bbox-layout` 逐页导出 block/line/word 三级包围盒；无文字层页用 `pdftoppm`(300dpi)+`tesseract tsv` OCR，像素坐标按 72/300 换算为 PDF pt（真实坐标，禁止估算），结果标注 OCR 来源与未核验状态。
3. **页眉页脚剔除**：跨页重复的顶部/底部行（数字归一化）剔除并留痕。
4. **分栏与阅读顺序**：按块左边缘聚类识别 1~4 栏（真实栏至少含 2 个块，栏间距阈值），居中块（题名、作者行、通栏图表）识别为跨栏带；以跨栏块切分横带，带内各栏从左到右、栏内自上而下。
5. **结构识别**：编号/无编号标题（拒绝编号句与数字表格行误判）、图题/表题、表格网格（视觉行合并→按水平间隙切单元格→列对齐→多行表头→合并单元格标记→跨页续表检测）、编号公式（要求数学符号特征，支持多行公式回溯合并，拒绝以括号数字结尾的正文）、参考文献按条目切分。
6. **段落与 bbox**：段落记录自身文本行，bbox 由这些行计算；跨块/跨页段落按句末标点规则续接，跨页段落给出分页 bbox。
7. **元数据**：标题（最大字高块）、作者、单位、摘要、关键词、DOI、期刊/年份（页眉页脚），每字段附页码、bbox 与置信度；缺失为 null，不猜测。
8. **如实报告**：加密、OCR 失败页、乱码、无法判定项写入 `uncertainties` 并给出人工接管位置。

## 输出约定

- `status` ∈ `success` / `partial` / `failed` / `unreadable`；部分完成必须说明受限范围。
- 字段详见 `references/output-contract.md`；方法阈值与已知失败模式见 `references/method.md`。
- 回归测试：`python <skill_dir>/tests/run_regression.py`（9 类合成夹具，实测指标，说明见 `tests/README.md`）。

## 交付物清单

| 路径 | 作用 | 使用条件 |
|-|-|-|
| `scripts/run_case.py` | 评测入口（两阶段、缓存复用、证据校验） | Python ≥ 3.9 + pdftotext |
| `scripts/parse_pdf.py` | 解析器本体（可独立调用） | 同上；OCR 需 pdftoppm + tesseract |
| `references/method.md` | 方法、阈值与失败模式 | 文档 |
| `references/output-contract.md` | result.json 与 answers.json 字段约定 | 文档 |
| `examples/minimal-example.md` | 最小调用示例（输出为示意） | 文档 |
| `tests/` | 开发用回归测试与实测报告（非正式案例、非预制答案） | 运行需 matplotlib |

## 异常处理

- 加密/损坏 PDF：`failed`，记录工具原始报错，不绕过权限。
- 扫描件：有 OCR 工具时按真实坐标恢复并标注未核验；无工具时对应页标 `unreadable`/`partial`，不编造文字。
- 找不到 `pdftotext`：`failed` 并说明依赖安装方式。
- 无法判定的结构保留原文行并标注 `uncertain: true`；output_contract 中无法产出的字段置 null 并说明原因，不填充假值。

## 最小调用示例

见 `examples/minimal-example.md`（输出为示意，不冒充正式案例结果）。
