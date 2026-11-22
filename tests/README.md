# 回归测试说明

本目录是开发用回归测试集，**不是**竞赛正式测试案例，也不包含任何预制答案。

## 组成

- `make_fixtures.py`：用 matplotlib 生成 8 类合成 PDF 夹具（真实文字层，扫描类除外）。
  夹具内容完全由代码构造，真值已知。
- `run_regression.py`：生成夹具（如缺失）→ 调用真实解析器 → 与构造真值比对 →
  写出实测报告。所有指标均为实际运行计算值；无法运行的检查（如无 tesseract 时的
  OCR 端到端）标注 NOT RUN，从不记为通过。
- `regression_work/`：运行产物（夹具 PDF、regression_report.md、regression_results.json、
  两阶段 run_case 测试输出）。该目录为生成物，可随时删除重建。

## 夹具覆盖

| 夹具 | 覆盖点 |
|-|-|
| `singlecol.pdf` | 单栏、元数据（标题/作者/关键词/DOI）、编号句防误判标题 |
| `twocol.pdf` | 双栏阅读顺序、页眉页脚剔除、章节层级、公式、表格、参考文献 |
| `threecol.pdf` | 三栏不等宽版式阅读顺序 |
| `mixedlayout.pdf` | 通栏表格打断双栏、带前后栏内容接续 |
| `table.pdf` | 多行表头、跨行分隔行、数值网格、单元格准确性 |
| `equations.pdf` | 编号公式、多行公式、以 (N) 结尾的正文防误判 |
| `scanned.pdf` | 纯图像页 → unreadable，无编造文字 |
| `mixedlayer.pdf` | 文字层 + 纯图像页混合 → partial 并标记页码 |

另有单元检查：Tesseract TSV 像素坐标 → PDF pt 换算（不需要安装 tesseract）。

## 实测指标

报告（`regression_work/regression_report.md`）记录：文字包含性、阅读顺序锚点、
章节检出与误判、表/图/公式/参考文献计数、表格单元格命中、元数据字段、
bbox 合法性（坐标范围）、状态判定、每夹具耗时与运行环境。

最近一次实测（2026-11-22，Windows + Python 3.12.5 + Poppler，无 tesseract）：
**77/77 检查通过**；OCR 端到端 NOT RUN（坐标换算单元检查通过）。
此数值仅在本机本次运行有效，环境变化后需重跑。

## 运行

```bash
python tests/run_regression.py            # 重建夹具并全量实测
python tests/make_fixtures.py --out dir   # 仅生成夹具
```
