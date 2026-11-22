#!/usr/bin/env python3
"""run_case.py — Harness entry point for the scientific-pdf-parser skill.

Two-phase design (see SKILL.md):

  Phase 1 (this script, deterministic): read <input>/case.json and
  <input>/task.md, locate the PDF, run parse_pdf.py, then build a queryable
  evidence index: the task is split into items, each item is classified
  (qa/translate/extract/verify) and matched against parsed paragraphs by
  keyword retrieval. Nothing is answered by the script — semantic answering
  is the Agent's phase 2.

  Phase 2 (Agent): read <output>/result.json + fulltext.md, answer each task
  item citing paragraph indices/pages, write answers.json, then re-run this
  script with --answers answers.json to merge the answers into result.json.

Defaults match the evaluation contract: --input /input --output /app/output
--work /app/work. Exit code 0 whenever a (possibly partial) result.json was
written; 1 only when no result could be produced at all.
"""
import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
PARSER = SKILL_DIR / "scripts" / "parse_pdf.py"

ITEM_LINE_RE = re.compile(
    r"^\s*(?:\d+\s*[.、)]|[-*•]|Q\d+|问题\s*\d+|任务\s*\d+|第\s*\d+\s*[题问])\s*(.+)")
TASK_TYPE_RULES = [
    ("translate", re.compile(r"翻译|translate|translation", re.IGNORECASE)),
    ("verify", re.compile(r"核验|验证|核对|是否|verify|check|consistent", re.IGNORECASE)),
    ("extract", re.compile(r"提取|抽取|列出|extract|list|identify", re.IGNORECASE)),
    ("qa", re.compile(r"[?？]|什么|如何|为何|多少|what|how|why|which", re.IGNORECASE)),
]
CJK_RE = re.compile(r"[一-鿿]")
LATIN_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9-]{2,}")


def find_pdf(*dirs):
    for d in dirs:
        if d and d.is_dir():
            pdfs = sorted(d.rglob("*.pdf"))
            if pdfs:
                return pdfs[0]
    return None


def split_task_items(task_text):
    """Split task.md into individual task items. Falls back to one item."""
    items = []
    for ln in task_text.splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        m = ITEM_LINE_RE.match(ln)
        if m:
            items.append(m.group(1).strip())
        elif items is not None and ("?" in ln or "？" in ln):
            items.append(ln)
    if not items:
        body = " ".join(ln.strip() for ln in task_text.splitlines()
                        if ln.strip() and not ln.startswith("#"))
        if body:
            items = [body]
    return items


def classify_item(text):
    for ttype, rx in TASK_TYPE_RULES:
        if rx.search(text):
            return ttype
    return "qa"


def item_keywords(text):
    """Latin words (lowered) + CJK bigrams as retrieval terms."""
    words = {w.lower() for w in LATIN_WORD_RE.findall(text)}
    cjk = "".join(CJK_RE.findall(text))
    bigrams = {cjk[i:i + 2] for i in range(len(cjk) - 1)}
    return words | bigrams


def retrieve_evidence(item_text, parsed, top_k=3):
    """Keyword-overlap retrieval over paragraphs, table grids/captions and
    figure captions. Returns real references (index/page/bbox/snippet) —
    retrieval only, never a semantic answer."""
    kws = item_keywords(item_text)
    if not kws:
        return []
    out = []

    def hits_in(text):
        tl = text.lower()
        return sum(1 for k in kws if k in tl or k in text)

    scored = []
    for idx, p in enumerate(parsed.get("paragraphs", [])):
        h = hits_in(p["text"])
        if h:
            scored.append((h, idx, p))
    scored.sort(key=lambda s: -s[0])
    for h, idx, p in scored[:top_k]:
        out.append({"kind": "paragraph", "paragraph_index": idx,
                    "page": p["page"], "pages": p.get("pages", [p["page"]]),
                    "bbox": p["bbox"], "keyword_hits": h,
                    "snippet": p["text"][:300], "section": p.get("section")})
    for idx, t in enumerate(parsed.get("tables", [])):
        h = hits_in(t.get("caption", "") + " " + t.get("markdown", ""))
        if h:
            out.append({"kind": "table", "table_index": idx, "page": t["page"],
                        "bbox": t["bbox"], "keyword_hits": h,
                        "snippet": (t.get("caption", "") + " " +
                                    t.get("markdown", ""))[:300]})
    for idx, f in enumerate(parsed.get("figures", [])):
        h = hits_in(f.get("caption", ""))
        if h:
            out.append({"kind": "figure", "figure_index": idx, "page": f["page"],
                        "bbox": f["bbox"], "keyword_hits": h,
                        "snippet": f.get("caption", "")[:300]})
    # type fallback: cross-lingual keyword retrieval can yield zero hits;
    # attach structurally relevant objects explicitly marked as fallback
    if re.search(r"表|table", item_text, re.IGNORECASE):
        for idx, t in enumerate(parsed.get("tables", [])):
            if not any(e.get("table_index") == idx for e in out):
                out.append({"kind": "table", "table_index": idx, "page": t["page"],
                            "bbox": t["bbox"], "keyword_hits": 0,
                            "fallback": "item mentions tables; no keyword hit",
                            "snippet": (t.get("caption", "") + " " +
                                        t.get("markdown", ""))[:300]})
    if re.search(r"图|figure|fig\.", item_text, re.IGNORECASE):
        for idx, f in enumerate(parsed.get("figures", [])):
            if not any(e.get("figure_index") == idx for e in out):
                out.append({"kind": "figure", "figure_index": idx, "page": f["page"],
                            "bbox": f["bbox"], "keyword_hits": 0,
                            "fallback": "item mentions figures; no keyword hit",
                            "snippet": f.get("caption", "")[:300]})
    out.sort(key=lambda e: -e["keyword_hits"])
    return out[:top_k + 2]


def analyze_task(task_text, parsed):
    items = []
    for i, text in enumerate(split_task_items(task_text)):
        items.append({
            "id": "item-%d" % (i + 1),
            "text": text,
            "type": classify_item(text),
            "candidate_evidence": retrieve_evidence(text, parsed),
            "answer": None,
            "answer_status": "pending_agent_phase2",
        })
    return items


def merge_answers(task_items, answers_obj, uncertainties, changes):
    """Merge Agent-written answers.json into task items.
    Expected format: {"items": [{"id": "item-1", "answer": "...",
    "evidence": [{"paragraph_index": 0, "page": 1}], "confidence": "high"}]}"""
    by_id = {a.get("id"): a for a in answers_obj.get("items", [])
             if isinstance(a, dict)}
    n_merged = 0
    for it in task_items:
        a = by_id.get(it["id"])
        if not a:
            continue
        if not a.get("answer"):
            uncertainties.append({"issue": "answers.json item has empty answer",
                                  "item": it["id"]})
            continue
        it["answer"] = a["answer"]
        it["evidence"] = a.get("evidence", it["candidate_evidence"])
        if "confidence" in a:
            it["confidence"] = a["confidence"]
        it["answer_status"] = "answered_by_agent"
        n_merged += 1
    changes.append("merged %d agent answers from answers.json" % n_merged)
    pending = [it["id"] for it in task_items if it["answer"] is None]
    return pending


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="/input")
    ap.add_argument("--output", default="/app/output")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--answers", default=None,
                    help="agent-written answers.json to merge (phase 2)")
    args = ap.parse_args()

    indir, outdir, workdir = Path(args.input), Path(args.output), Path(args.work)
    outdir.mkdir(parents=True, exist_ok=True)
    workdir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    changes = []
    uncertainties = []

    # ---- read case ----
    case = {}
    case_path = indir / "case.json"
    if case_path.is_file():
        try:
            case = json.loads(case_path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as e:
            changes.append("case.json parse error: %s" % e)
    case_id = case.get("case_id") or case.get("id") or "unknown"
    task_text = ""
    task_path = indir / "task.md"
    if task_path.is_file():
        task_text = task_path.read_text(encoding="utf-8-sig", errors="replace")

    # ---- locate PDF material ----
    pdf = None
    for key in ("pdf", "pdf_path", "file", "document", "material"):
        v = case.get(key)
        if isinstance(v, str):
            cand = Path(v)
            if not cand.is_absolute():
                cand = indir / v
            if cand.is_file():
                pdf = cand
                break
    materials = case.get("materials")
    if pdf is None and isinstance(materials, list):
        for m in materials:
            if isinstance(m, str) and m.lower().endswith(".pdf"):
                cand = Path(m)
                if not cand.is_absolute():
                    cand = indir / m
                if cand.is_file():
                    pdf = cand
                    break
    if pdf is None:
        pdf = find_pdf(indir, workdir)

    if pdf is None:
        result = {
            "case_id": case_id,
            "status": "failed",
            "reason": "no PDF material found in input directory",
            "uncertainties": [{"issue": "missing input PDF"}],
            "sources": [], "changes": changes,
            "runtime": {"seconds": round(time.time() - t0, 2)},
        }
        (outdir / "result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print("status=failed reason=no-pdf")
        return 1

    # ---- phase 1: parse ----
    stdout_log = workdir / "parser.stdout.log"
    stderr_log = workdir / "parser.stderr.log"
    with stdout_log.open("w", encoding="utf-8") as so, \
            stderr_log.open("w", encoding="utf-8") as se:
        subprocess.run([sys.executable, str(PARSER), str(pdf), "--out",
                        str(workdir), "--case-id", str(case_id)],
                       stdout=so, stderr=se, timeout=600)
    parsed_path = workdir / "result.json"
    if not parsed_path.is_file():
        result = {
            "case_id": case_id,
            "status": "failed",
            "reason": "parser produced no result; see work/parser.stderr.log",
            "parser_stderr_tail": stderr_log.read_text(
                encoding="utf-8", errors="replace")[-1000:],
            "uncertainties": [{"issue": "parser hard failure"}],
            "sources": [], "changes": changes,
            "runtime": {"seconds": round(time.time() - t0, 2)},
        }
        (outdir / "result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print("status=failed reason=parser-crash")
        return 1

    parsed = json.loads(parsed_path.read_text(encoding="utf-8"))
    uncertainties.extend(parsed.get("uncertainties", []))

    # ---- phase 1b: task analysis + evidence retrieval (no answering) ----
    task_items = analyze_task(task_text, parsed) if task_text.strip() else []
    if task_items:
        uncertainties.append({
            "issue": "task items are analyzed and evidence-retrieved but NOT "
                     "answered by the script; semantic answering is the Agent "
                     "phase-2 step (see SKILL.md). answers=null until an "
                     "answers.json is merged via --answers.",
            "pending_items": [it["id"] for it in task_items]})

    # ---- optional phase 2 merge ----
    if args.answers:
        apath = Path(args.answers)
        if apath.is_file():
            try:
                answers_obj = json.loads(apath.read_text(encoding="utf-8-sig"))
                pending = merge_answers(task_items, answers_obj,
                                        uncertainties, changes)
                if pending:
                    uncertainties.append({"issue": "task items still unanswered",
                                          "pending_items": pending})
            except json.JSONDecodeError as e:
                uncertainties.append({"issue": "answers.json parse error",
                                      "detail": str(e)})
        else:
            uncertainties.append({"issue": "answers file not found",
                                  "path": str(apath)})

    # ---- assemble final result honoring output_contract ----
    contract = case.get("output_contract")
    fields = []
    if isinstance(contract, dict):
        fields = list(contract.get("fields", contract.keys()))
    elif isinstance(contract, list):
        fields = [f if isinstance(f, str) else f.get("name")
                  for f in contract if f]

    parse_status = parsed.get("status", "partial")
    if parse_status == "failed":
        status = "failed"
    elif task_items and any(it["answer"] is None for it in task_items):
        status = "partial"   # parsed OK, answers pending or partially merged
    else:
        status = parse_status

    final = {
        "case_id": case_id,
        "status": status,
        "input": {"pdf": str(pdf), "pages": parsed.get("input", {}).get("pages")},
        "task": task_text[:2000] if task_text else None,
        "task_items": task_items,
        "result": parsed,
        "sources": [
            {"item": "metadata", "locator": "result.metadata.<field>.page/.bbox"},
            {"item": "paragraphs", "locator": "result.paragraphs[*].page/.pages/.bbox/.page_bboxes"},
            {"item": "tables", "locator": "result.tables[*].page/.bbox/.grid/.markdown"},
            {"item": "figures", "locator": "result.figures[*].page/.bbox"},
            {"item": "equations", "locator": "result.equations[*].page/.bbox/.number"},
            {"item": "references", "locator": "result.references[*].page/.bbox"},
            {"item": "task evidence", "locator": "task_items[*].candidate_evidence / .evidence"},
        ],
        "uncertainties": uncertainties,
        "changes": changes,
        "runtime": {"parser": parsed.get("runtime"),
                    "total_seconds": round(time.time() - t0, 2)},
    }
    for f in fields:
        if isinstance(f, str) and f not in final:
            if f in parsed:
                final[f] = parsed[f]
            else:
                final[f] = None
                final["uncertainties"].append(
                    {"issue": "output_contract field not produced by the pipeline",
                     "field": f,
                     "reason": "no deterministic source for this field; "
                               "null is reported instead of a fabricated value"})
    final["output_contract_raw"] = contract

    (outdir / "result.json").write_text(
        json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")
    ft = workdir / "fulltext.md"
    if ft.is_file():
        (outdir / "fulltext.md").write_text(
            ft.read_text(encoding="utf-8"), encoding="utf-8")
    print("status=%s case_id=%s pdf=%s task_items=%d" % (
        final["status"], case_id, pdf.name, len(task_items)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
