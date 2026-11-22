# 最小调用示例

> 本示例仅说明接口与完整使用流程；其中输出为**示意输出**，并非正式案例结果。

## 输入

- `paper.pdf`：一篇双栏英文论文（文本型 PDF，14 页）。

## 调用

```bash
python scripts/parse_pdf.py paper.pdf --out out --case-id demo-001
```

## 示意输出（节选，标记为示例）

`out/result.json`：

```json
{
  "case_id": "demo-001",
  "status": "success",
  "input": {"file": "paper.pdf", "pages": 14},
  "sections": [
    {"title": "1 Introduction", "level": 1, "page": 1,
     "bbox": {"x0": 54.0, "y0": 240.3, "x1": 300.1, "y1": 252.8},
     "path": ["1 Introduction"]}
  ],
  "paragraphs": [
    {"text": "We study the reading-order problem ...", "page": 1,
     "bbox": {"x0": 54.0, "y0": 260.0, "x1": 300.1, "y1": 420.5},
     "section": "1 Introduction"}
  ],
  "tables": [{"label": "Table 1", "caption": "Table 1: Accuracy ...", "page": 6,
              "bbox": {"x0": 320.0, "y0": 90.0, "x1": 560.0, "y1": 110.0},
              "note": "caption located; grid content preserved as paragraph lines"}],
  "figures": [{"label": "Figure 2", "caption": "Figure 2: Pipeline ...", "page": 4,
               "bbox": {"x0": 54.0, "y0": 500.0, "x1": 300.0, "y1": 520.0}}],
  "equations": [{"text": "L = sum_i log p(x_i) (3)", "page": 5,
                 "bbox": {"x0": 330.0, "y0": 200.0, "x1": 540.0, "y1": 215.0},
                 "uncertain": false}],
  "references": [{"index": "1", "text": "[1] A. Author. Title. Journal, 2020.",
                  "page": 12, "bbox": {"x0": 54.0, "y0": 100.0, "x1": 300.0, "y1": 115.0}}],
  "removed_running_matter": [{"text": "Journal of Examples, Vol. 1", "pages": [2, 3, 4]}],
  "uncertainties": [],
  "stats": {"pages": 14, "paragraphs": 96, "sections": 12, "tables": 3,
            "figures": 5, "equations": 8, "references": 42, "body_words": 8120},
  "runtime": {"tool": "pdftotext -bbox-layout (Poppler)", "seconds": 3.2},
  "changes": []
}
```

`out/fulltext.md`（节选）：

```markdown
[p.1]

## 1 Introduction

We study the reading-order problem ...

[p.2]

...
```

## 说明

- 真实运行时数值以实际 PDF 为准；本示例数字均为虚构演示。
- 若输入为扫描件且无 OCR 工具，期望输出 `status: "unreadable"` 且不含任何猜测正文。
