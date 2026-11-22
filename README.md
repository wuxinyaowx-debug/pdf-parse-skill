# scientific-pdf-parser — 使用与方法说明

面向「文献文档解析：科研阅读」任务的 Agent Skill。将科研文献 PDF 解析为
**可核验**的结构化结果（章节、段落、表格网格、图题、编号公式、参考文献、元数据，
逐项附页码与版面区块定位），并支撑按 task.md 的科研阅读任务（问答/翻译/提取/核验）。
所有结论可回指原文；读不出的部分如实标注——不编造文字、不虚构坐标、不用
"看起来完整"的 JSON 冒充成功。

## 功能特性

- **提得全**：正文、图表题注、参考文献逐字提取；页眉页脚按跨页重复模式剔除并留痕。
- **排得对**：1~4 栏左边缘聚类 + 横带切分还原阅读顺序；通栏标题/图表、居中块、
  跨页续接正确处理；不串栏、不错行。
- **拆得清**：章节层级（编号/无编号、防编号句与数字行误判）、表格网格（视觉行合并、
  单元格切分、多行表头、合并单元格标记、跨页续表按页成格并关联）、编号公式
  （数学特征校验、多行回溯合并）、论文元数据七字段带置信度。
- **核得回**：每个段落/表格/公式/文献条目附页码与 bbox（段落 bbox 由自身文本行计算，
  支持跨页分页 bbox）；OCR 用 Tesseract TSV 真实坐标（300dpi→pt），标注来源与
  未核验状态；无法识别项一律 `uncertain`/`uncertainties`，不靠猜补齐。
- **两阶段任务执行**：脚本做确定性解析与证据检索，Agent 做语义作答并回写合并；
  合并时不重解析 PDF（内容哈希指纹缓存），且逐条校验证据引用（索引/页码/bbox）。
- **运行可靠**：阶段运行前清理残留产物；子进程返回码/超时/损坏输出逐一检查；
  `case_id` 不符拒绝采用，杜绝跨案例串用旧结果。

## 安装与依赖

| 依赖 | 版本 | 用途 | 安装 |
|-|-|-|-|
| Python | ≥ 3.9（仅标准库） | 运行脚本 | 任意发行版 |
| Poppler | ≥ 0.86（`pdftotext`；`pdfinfo`、`pdftoppm` 可选） | 文本层与版面提取、OCR 渲染 | Debian/Ubuntu: `apt install poppler-utils`；macOS: `brew install poppler`；Windows: Poppler for Windows 加入 PATH |
| Tesseract | 任意近期版本 | （可选）扫描页 OCR | `apt install tesseract-ocr` |
| matplotlib | ≥ 3.5 | （仅开发）生成回归夹具 | `pip install matplotlib` |

无网络、无第三方 Python 运行时依赖；不依赖任何个人文件或手工中间步骤。

## 快速开始

评测/案例两阶段模式（与平台 Runtime contract 一致）：

```bash
# 阶段 1：解析 + 任务分析 + 证据检索
python scripts/run_case.py --input /input --output /app/output --work /app/work
# Agent 阅读 /app/output/result.json 与 fulltext.md，作答写入 answers.json
# 阶段 2：合并并校验证据（复用阶段 1 缓存，不重解析）
python scripts/run_case.py --input /input --output /app/output --work /app/work --answers answers.json
```

单文件模式：

```bash
python scripts/parse_pdf.py paper.pdf --out out/
```

回归测试：

```bash
python tests/run_regression.py    # 9 类夹具，84 项实测检查
python tests/run_case_tests.py    # run_case 级：陈旧结果/证据校验/缓存复用等 9 项
```

## 输入与输出

- 输入：科研文献 PDF（单/双/三栏、中英文、文本型/扫描/混合）+ `case.json` + `task.md`。
- 输出：`result.json`（含 `case_id`、`output_contract` 全部字段、`status`、`task_items`、
  `result`、`sources`、`uncertainties`、`changes`）与 `fulltext.md`。
- 字段、状态语义、answers.json 格式见 `references/output-contract.md`；
  方法、阈值与失败模式见 `references/method.md`。

## 适用场景

- 文献解析、阅读问答、参数/结果抽取、翻译与核验等需要**回指原文页码与区块**的任务。
- 双栏/多栏论文阅读顺序修复、复杂表格结构还原、编号公式与参考文献提取、扫描件 OCR。

## 限制（如实声明）

- 关键词证据检索不跨语言：中文问题配英文论文时命中数可能为 0，此时给出标注过的
  类型兜底证据，最终作答依赖 Agent 阶段 2 的语义阅读。
- 表格网格基于水平间隙切分：无线表列距过近、单元格内换行复杂时标 `uncertain`
  并保留原始行，不猜测单元格归属。
- 公式保留提取符号串，上下标版面不还原，需以 bbox 回查原文。
- 元数据中作者/单位为低置信度启发式，期刊/年份取自页眉页脚时为低置信度。
- OCR 端到端在无 tesseract 的环境中不可运行；坐标换算与置信度聚合有独立单元检查。

## 自查方法

1. 看 `status` 与 `uncertainties` 确认受限范围。
2. 抽查 3 处结论按 `page`+`bbox` 回原文逐字核对。
3. 对照 `stats` 与原刊目录确认无漏段漏条。
4. 查 `removed_running_matter` 确认剔除的是页眉页脚。
5. 运行 `tests/run_regression.py` 与 `tests/run_case_tests.py` 复核质量基线。

## 维护

- 阈值集中在 `scripts/parse_pdf.py` 顶部常量；调整须重跑两套测试。
- 每次运行的变更写入 `result.json` 的 `changes`。
