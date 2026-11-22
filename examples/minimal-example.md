# 最小调用示例

> 本示例仅说明接口与完整使用流程；其中输出为**示意输出**（数字虚构），
> 并非正式案例结果。真实运行的实测结果见 `tests/` 回归报告。

## 示例 A：单文件解析

```bash
python scripts/parse_pdf.py paper.pdf --out out --case-id demo-001
```

`out/result.json`（节选，示意）：

```json
{
  "case_id": "demo-001",
  "status": "success",
  "metadata": {
    "title": {"value": "A Study of ...", "page": 1,
              "bbox": {"x0": 104.5, "y0": 7.9, "x1": 490.9, "y1": 34.9},
              "confidence": "medium"},
    "doi": {"value": "10.1234/example.2024.1", "page": 1, "bbox": null,
            "confidence": "high"}
  },
  "sections": [{"title": "1 Introduction", "level": 1, "page": 1,
                "bbox": {"x0": 35.7, "y0": 139.2, "x1": 117.4, "y1": 159.9},
                "path": ["1 Introduction"]}],
  "paragraphs": [{"text": "We study ...", "page": 1, "pages": [1],
                  "bbox": {"x0": 35.7, "y0": 160.8, "x1": 282.5, "y1": 229.4},
                  "page_bboxes": {"1": {"x0": 35.7, "y0": 160.8, "x1": 282.5, "y1": 229.4}},
                  "n_lines": 5, "cross_page": false, "section": "1 Introduction"}],
  "tables": [{"label": "Table 1:", "caption": "Table 1: Accuracy ...", "page": 6,
              "bbox": {"x0": 321.5, "y0": 441.9, "x1": 501.0, "y1": 497.0},
              "continued": false,
              "grid": {"n_columns": 3, "n_header_rows": 1,
                       "headers": [["Method", "Order", "Structure"]],
                       "rows": [["Naive", "0.41", "0.55"], ["Ours", "0.97", "0.93"]],
                       "merged_cells": [], "uncertain": false},
              "markdown": "| Method | Order | Structure |\n|---|---|---|\n| Naive | 0.41 | 0.55 |"}],
  "stats": {"pages": 14, "paragraphs": 96, "sections": 12, "tables": 3,
            "figures": 5, "equations": 8, "references": 42, "body_words": 8120}
}
```

## 示例 B：评测两阶段流程

阶段 1（解析 + 任务分析 + 证据检索）：

```bash
python scripts/run_case.py --input /input --output /app/output --work /app/work
# status=partial  case_id=...  task_items=2   （answer=null，不冒充完成）
```

`result.json` 中 `task_items`（示意）：

```json
[{"id": "item-1", "text": "本文的表格结果如何？", "type": "qa",
  "candidate_evidence": [{"kind": "table", "table_index": 0, "page": 6,
                          "bbox": {"x0": 321.5, "y0": 441.9, "x1": 501.0, "y1": 497.0},
                          "keyword_hits": 0,
                          "fallback": "item mentions tables; no keyword hit",
                          "snippet": "Table 1: Accuracy ... | Naive | 0.41 | 0.55 |"}],
  "answer": null, "answer_status": "pending_agent_phase2"}]
```

阶段 2（Agent 阅读 result.json/fulltext.md 后写 `answers.json` 并合并）：

```json
{"items": [{"id": "item-1",
            "answer": "表1中 Ours 的 Order/Structure 为 0.97/0.93，高于 Naive 的 0.41/0.55。",
            "evidence": [{"kind": "table", "table_index": 0, "page": 6}],
            "confidence": "high"}]}
```

```bash
python scripts/run_case.py --input /input --output /app/output --work /app/work --answers answers.json
# status=success（解析无异常且答案齐全时）
```

## 说明

- 扫描件且无 OCR 工具时，期望输出 `status: "unreadable"`（或部分页时 `partial`），
  不含任何猜测正文。
- 输出字段完整定义见 `references/output-contract.md`。
