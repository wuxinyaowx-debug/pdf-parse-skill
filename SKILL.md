---
name: scientific-pdf-parser
description: 将科研文献 PDF 解析为可核验的结构化结果（章节层级、段落、表格、图题、公式、参考文献，逐项附页码与版面区块定位），支持双栏/多栏阅读顺序还原、页眉页脚剔除、扫描件检测与 OCR 降级。Use when a task requires parsing a scientific paper PDF, extracting text/tables/equations/references with page-level evidence, fixing multi-column reading order, or producing a verifiable result.json for literature document parsing. 当任务要求解析科研文献 PDF、还原多栏阅读顺序、提取表格公式参考文献并给出页码证据时使用。
---

# Scientific PDF Parser（科研文献 PDF 解析）

将科研文献 PDF 解析为结构化、可回查原文证据的结果。核心原则：**逐字提取、顺序正确、结构可拆、结论可核**；读不出的部分如实标注，不靠猜测补齐。

## 适用条件与触发场景

- 输入为科研文献 PDF（单栏、双栏或多栏排版，中英文均可），任务要求阅读、解析、提取、问答或核验其内容。
- 需要给出可复核证据（页码、段落、图表、公式位置）的结构化输出，尤其是评测约定中的 `result.json`。
- 不适用于：已有可靠结构化全文（如出版社 XML）且无需版面证据的任务——此时直接读取该全文更可靠。

## 环境与依赖

- 必需：`pdftotext`（Poppler，用于版面与文本层提取）、Python ≥ 3.9（仅标准库）。
- 可选：`pdftoppm` + `tesseract`（扫描件 OCR 降级链）；缺失时扫描页如实标注为不可读，不得编造文字。
- 所有路径相对于 Skill 目录解析，不依赖任何个人文件或手工中间步骤。

## 调用方式

### 1. 评测/案例模式（优先）

```
python <skill_dir>/scripts/run_case.py --input /input --output /app/output --work /app/work
```

- 读取 `<input>/case.json` 与 `<input>/task.md`；在输入目录中寻找 PDF 材料。
- 中间产物写入 `<work>`；最终结果写入 `<output>/result.json` 与 `<output>/fulltext.md`。
- `result.json` 保留 `case_id` 及 `case.json` 中 `output_contract` 声明的全部字段，并包含 `status`、`sources`、`uncertainties`、`changes`。

### 2. 单文件解析模式

```
python <skill_dir>/scripts/parse_pdf.py <paper.pdf> --out <output_dir>
```

产出 `<output_dir>/result.json`（结构化结果）与 `<output_dir>/fulltext.md`（阅读顺序正确的全文，含页码锚点）。

## 处理流程（脚本已实现，按下述顺序执行）

1. **输入识别**：检查文件存在性、是否加密、是否有文本层；逐页统计词数，判定文本型/扫描型/混合型。
2. **版面提取**：`pdftotext -bbox-layout` 逐页导出 block/line/word 三级包围盒（XHTML）。
3. **页眉页脚剔除**：跨页重复出现在页面顶部/底部边缘的文本行（数字归一化后比对）判定为页眉页脚，从正文剔除并记录。
4. **分栏与阅读顺序**：按 block 横向跨度区分跨栏块与栏内块；以跨栏块的纵坐标切分页面为横带，横带内先左栏后右栏、栏内自上而下，得到原版式阅读顺序；跨行连字符（词尾 `-` + 下行小写开头）做去连字符合并。
5. **结构识别**：编号标题（`1`、`1.1` 等）与无编号标题（Abstract、References 等）正则识别并还原层级；`Figure/Fig./Table N` 题注定位图表；行尾 `(N)` 编号识别公式；References 之后按 `[n]`/`n.` 切分文献条目。
6. **证据回指**：每个段落、表格、图题、公式、文献条目均记录页码与区块包围盒；全文 Markdown 中插入 `[p.N]` 页码锚点。
7. **如实报告**：加密、无文本层且无 OCR、乱码字体、页码错乱、无法判定项分别写入 `uncertainties`，并给出可人工接管的位置。

## 输出约定

- `status` ∈ `success` / `partial` / `failed` / `unreadable`；部分完成必须说明受限范围。
- 结构化字段：`metadata`、`sections`（含层级）、`paragraphs`、`tables`、`figures`、`equations`、`references`、`removed_running_matter`、`uncertainties`、`stats`、`runtime`、`changes`。详见 `references/output-contract.md`。
- 方法细节、判定阈值与已知失败模式见 `references/method.md`。

## 异常处理

- 加密/损坏 PDF：状态 `failed`，记录工具报错原文，不尝试绕过权限。
- 扫描件：优先 OCR 链；OCR 工具缺失时对应页标注 `unreadable`，其余页正常解析，状态 `partial`。
- 工具缺失（找不到 `pdftotext`）：状态 `failed` 并说明所需依赖与安装方式。
- 任何无法判定的结构（如无主标题表格）保留原文行并标注 `uncertain: true`，绝不虚构内容。

## 最小调用示例

见 `examples/minimal-example.md`（其中输出为示意，不冒充正式案例结果）。
