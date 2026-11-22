# scientific-pdf-parser — 使用与方法说明

将科研文献 PDF 解析为**可核验**的结构化结果：章节层级、段落、表题、图题、编号公式、
参考文献，每一项都带页码与版面区块（bbox）定位；双栏/多栏按原版式阅读顺序输出；
页眉页脚自动剔除并留痕；扫描件如实标注，不编造文字。

## 安装与依赖

| 依赖 | 版本 | 用途 | 安装 |
|-|-|-|-|
| Python | ≥ 3.9（仅标准库） | 运行脚本 | 任意发行版 |
| Poppler | ≥ 0.86（`pdftotext`、`pdfinfo`） | 文本层与版面提取 | Debian/Ubuntu: `apt install poppler-utils`；macOS: `brew install poppler`；Windows: 使用 Poppler for Windows 发行包并加入 PATH |
| Poppler `pdftoppm` + Tesseract | 任意近期版本 | （可选）扫描件 OCR | `apt install poppler-utils tesseract-ocr` |

无网络、无第三方 Python 包依赖；不依赖任何个人文件或手工中间步骤。

## 快速开始

评测/案例模式（与平台约定一致）：

```bash
python scripts/run_case.py --input /input --output /app/output --work /app/work
```

单文件模式：

```bash
python scripts/parse_pdf.py paper.pdf --out out/
# 产出 out/result.json 与 out/fulltext.md
```

## 输入与输出

- 输入：科研文献 PDF（文本型、扫描型或混合；单栏/双栏/多栏；中英文）。
- 输出字段、状态语义、证据定位方式见 `references/output-contract.md`。
- 方法与阈值见 `references/method.md`。

## 适用场景

- 文献解析、阅读问答、参数/结果抽取等需要**回指原文页码与区块**的任务。
- 双栏论文阅读顺序修复、图表题注定位、编号公式与参考文献条目提取。

## 限制

- 表格当前可靠定位题注与区块，单元格级网格还原需结合 `pdftotext -layout` 或人工核对。
- 公式保留原文符号串，不转 LaTeX；上下标失真时以 bbox 回查原文为准。
- 三栏且栏宽不均的版面可能出现栏间交错（栏内顺序仍正确）。
- 无文本层且环境无 OCR 工具时，对应页面标记 `unreadable`，不输出猜测内容。

## 自查方法

1. 检查 `result.json` 的 `status` 与 `uncertainties`，确认受限范围。
2. 抽 3 处结论，按 `page` + `bbox` 回原文核对文字是否逐字一致。
3. 对照 `stats`（段落/章节/文献条数）与原刊目录页，确认无漏段漏条。
4. 查看 `removed_running_matter`，确认被剔除的确是页眉页脚而非正文。

## 维护

- 阈值（词数、栏宽比、页眉页脚比例）集中在 `scripts/parse_pdf.py` 顶部常量，调整需回归测试。
- 变更记录写入每次运行 `result.json` 的 `changes` 字段。
