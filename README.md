# scientific-pdf-parser v3 — 使用与方法说明

将科研文献 PDF 解析为**可核验**的结构化结果，并支撑按 task.md 的科研阅读任务
（问答/翻译/提取/核验）。所有结论可回指原文页码与版面区块；读不出的部分如实标注，
不编造文字、不虚构坐标、不用 null 填充冒充完成。

## v3 相对 v2 的主要变化（核心改错）

- 运行可靠性：阶段 1 前清理工作目录残留产物；解析器返回码/超时/损坏输出逐一检查；
  `case_id` 不符拒绝采用（防止跨案例串用旧结果）。
- 阶段 2 合并答案时**不再重解析 PDF**（指纹一致的 phase-1 缓存直接复用），并逐条
  **校验证据引用**（索引、页码、bbox），无证据/证据无效的答案明确标记。
- 跨页表格：行不再跨页合并，按页分别成格，显式续表题注或页断位置推断建立
  `continuation_of` 关联（推断者标 uncertain）。
- OCR：TSV 置信度聚合（`ocr_detail` 含 mean_conf、words、verified:false）。
- 标题误判收紧：标题词不得含数字；编号拆行合并要求同一视觉行。
- 测试：9 类夹具 84 项回归检查 + 8 项 run_case 级测试（陈旧结果、证据校验、阶段 2 复用）。

## v2 已有能力（保留）

- 两阶段任务流程；OCR TSV 真实坐标（72/300 换算，禁估算）；表格网格
  （视觉行合并、单元格切分、多行表头、合并单元格、Markdown+JSON）；
  段落自身行 bbox 与跨页段落；元数据七字段带置信度；1~4 栏左边缘聚类阅读顺序。

## 安装与依赖

| 依赖 | 版本 | 用途 | 安装 |
|-|-|-|-|
| Python | ≥ 3.9（仅标准库） | 运行脚本 | 任意发行版 |
| Poppler | ≥ 0.86（`pdftotext`；`pdfinfo`、`pdftoppm` 可选） | 文本层与版面提取、OCR 渲染 | Debian/Ubuntu: `apt install poppler-utils`；macOS: `brew install poppler`；Windows: Poppler for Windows 加入 PATH |
| Tesseract | 任意近期版本 | （可选）扫描页 OCR | `apt install tesseract-ocr` |
| matplotlib | ≥ 3.5 | （仅开发）生成回归夹具 | `pip install matplotlib` |

无网络、无第三方 Python 运行时依赖。

## 快速开始

评测/案例两阶段模式（与平台约定一致）：

```bash
# 阶段 1：解析 + 任务分析 + 证据检索
python scripts/run_case.py --input /input --output /app/output --work /app/work
# 阶段 2：Agent 作答后合并
python scripts/run_case.py --input /input --output /app/output --work /app/work --answers answers.json
```

单文件模式：

```bash
python scripts/parse_pdf.py paper.pdf --out out/
```

回归测试：

```bash
python tests/run_regression.py    # 9 类夹具，84 项实测检查
python tests/run_case_tests.py    # run_case 级：陈旧结果/证据校验/缓存复用等 8 项
```

## 输入与输出

- 输入：科研文献 PDF（单/双/三栏、中英文、文本型/扫描/混合）。
- 输出字段、状态语义、answers.json 格式见 `references/output-contract.md`。
- 方法、阈值与失败模式见 `references/method.md`。

## 限制（如实声明）

- 关键词证据检索不跨语言：中文问题配英文论文时命中数可能为 0，此时给出标注过的
  类型兜底证据，最终作答依赖 Agent 阶段 2 的语义阅读。
- 表格网格基于水平间隙切分：无线表列距过近、单元格内换行复杂时会标 `uncertain`
  并保留原始行，不猜测单元格归属。
- 公式保留提取符号串，上下标版面不还原，需以 bbox 回查原文。
- 元数据中作者/单位为低置信度启发式，期刊/年份取自页眉页脚时为低置信度。
- OCR 端到端在无 tesseract 的环境中不可运行；坐标换算逻辑有独立单元检查。

## 自查方法

1. 看 `status` 与 `uncertainties` 确认受限范围。
2. 抽查 3 处结论按 `page`+`bbox` 回原文逐字核对。
3. 对照 `stats` 与原刊目录确认无漏段漏条。
4. 查 `removed_running_matter` 确认剔除的是页眉页脚。
5. 运行 `tests/run_regression.py` 复核解析质量基线。

## 维护

- 阈值集中在 `scripts/parse_pdf.py` 顶部常量；调整须重跑回归测试。
- 每次运行的变更写入 `result.json` 的 `changes`。
