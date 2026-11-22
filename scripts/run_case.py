#!/usr/bin/env python3
"""run_case.py — Harness entry point for the scientific-pdf-parser skill.

Reads <input>/case.json and <input>/task.md, locates the PDF material, runs
parse_pdf.py, and writes the final deliverables under <output>:

  result.json   all fields declared by case.json's output_contract, plus
                case_id, status, sources, uncertainties, changes
  fulltext.md   restored-reading-order full text with page anchors

Defaults match the evaluation contract: --input /input --output /app/output
--work /app/work. Exit code is 0 whenever a (possibly partial) result.json
was written; 1 only when no result could be produced at all.
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
PARSER = SKILL_DIR / "scripts" / "parse_pdf.py"


def find_pdf(*dirs):
    for d in dirs:
        if d and d.is_dir():
            pdfs = sorted(d.rglob("*.pdf"))
            if pdfs:
                return pdfs[0]
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="/input")
    ap.add_argument("--output", default="/app/output")
    ap.add_argument("--work", default="/app/work")
    args = ap.parse_args()

    indir, outdir, workdir = Path(args.input), Path(args.output), Path(args.work)
    outdir.mkdir(parents=True, exist_ok=True)
    workdir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    changes = []

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
        task_text = task_path.read_text(encoding="utf-8", errors="replace")

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

    # ---- run parser (stdout/stderr to files; pipes are forbidden in some
    # sandboxed runtimes) ----
    stdout_log = workdir / "parser.stdout.log"
    stderr_log = workdir / "parser.stderr.log"
    with stdout_log.open("w", encoding="utf-8") as so, \
            stderr_log.open("w", encoding="utf-8") as se:
        proc = subprocess.run(
            [sys.executable, str(PARSER), str(pdf), "--out", str(workdir),
             "--case-id", str(case_id)],
            stdout=so, stderr=se, timeout=600)
    proc_stderr_tail = stderr_log.read_text(encoding="utf-8", errors="replace")[-1000:]

    parsed_path = workdir / "result.json"
    if not parsed_path.is_file():
        result = {
            "case_id": case_id,
            "status": "failed",
            "reason": "parser produced no result; see work/parser.stderr.log",
            "parser_stderr_tail": proc_stderr_tail,
            "uncertainties": [{"issue": "parser hard failure"}],
            "sources": [], "changes": changes,
            "runtime": {"seconds": round(time.time() - t0, 2)},
        }
        (outdir / "result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print("status=failed reason=parser-crash")
        return 1

    parsed = json.loads(parsed_path.read_text(encoding="utf-8"))

    # ---- assemble final result honoring output_contract ----
    contract = case.get("output_contract")
    fields = []
    if isinstance(contract, dict):
        fields = list(contract.get("fields", contract.keys()))
    elif isinstance(contract, list):
        fields = contract

    final = {
        "case_id": case_id,
        "status": parsed.get("status", "partial"),
        "input": {"pdf": str(pdf), "pages": parsed.get("input", {}).get("pages")},
        "task": task_text[:2000] if task_text else None,
        "result": parsed,
        "sources": [
            {"item": "paragraphs", "locator": "result.paragraphs[*].page/.bbox"},
            {"item": "tables", "locator": "result.tables[*].page/.bbox"},
            {"item": "figures", "locator": "result.figures[*].page/.bbox"},
            {"item": "equations", "locator": "result.equations[*].page/.bbox"},
            {"item": "references", "locator": "result.references[*].page/.bbox"},
        ],
        "uncertainties": parsed.get("uncertainties", []),
        "changes": changes,
        "runtime": {"parser": parsed.get("runtime"),
                    "total_seconds": round(time.time() - t0, 2)},
    }
    # guarantee every contract field exists
    for f in fields:
        if isinstance(f, str) and f not in final:
            if f in parsed:
                final[f] = parsed[f]
            else:
                final[f] = None
                final["uncertainties"].append(
                    {"issue": "output_contract field not produced", "field": f})

    (outdir / "result.json").write_text(
        json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")
    ft = workdir / "fulltext.md"
    if ft.is_file():
        (outdir / "fulltext.md").write_text(
            ft.read_text(encoding="utf-8"), encoding="utf-8")
    print("status=%s case_id=%s pdf=%s" % (final["status"], case_id, pdf.name))
    return 0


if __name__ == "__main__":
    sys.exit(main())
