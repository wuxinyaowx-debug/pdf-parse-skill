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
import hashlib
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


def validate_evidence(ev, parsed):
    """Check one evidence reference against the parsed result. Returns a list
    of problems (empty = valid). Never silently accepts bad indices/pages."""
    problems = []
    kind = ev.get("kind", "paragraph")
    coll_map = {"paragraph": ("paragraphs", "paragraph_index"),
                "table": ("tables", "table_index"),
                "figure": ("figures", "figure_index")}
    if kind not in coll_map:
        return ["unknown evidence kind %r" % kind]
    coll_name, idx_name = coll_map[kind]
    coll = parsed.get(coll_name, [])
    idx = ev.get(idx_name)
    if not isinstance(idx, int) or isinstance(idx, bool) or not (0 <= idx < len(coll)):
        return ["%s %r out of range (collection size %d)" % (idx_name, idx, len(coll))]
    obj = coll[idx]
    obj_pages = obj.get("pages", [obj.get("page")])
    if ev.get("page") is not None and ev["page"] not in obj_pages:
        problems.append("page %r does not match %s pages %s"
                        % (ev["page"], kind, obj_pages))
    if ev.get("bbox"):
        actual = obj.get("bbox") or {}
        for k in ("x0", "y0", "x1", "y1"):
            if k in ev["bbox"] and k in actual \
                    and abs(ev["bbox"][k] - actual[k]) > 1.5:
                problems.append("bbox.%s %r does not match actual %r"
                                % (k, ev["bbox"][k], actual[k]))
                break
    return problems


def merge_answers(task_items, answers_obj, parsed, uncertainties, changes):
    """Merge Agent-written answers.json into task items, validating every
    evidence reference against the phase-1 parsed result.
    Expected format: {"items": [{"id": "item-1", "answer": "...",
    "evidence": [{"kind": "paragraph", "paragraph_index": 0, "page": 1}],
    "confidence": "high"}]}"""
    by_id = {a.get("id"): a for a in answers_obj.get("items", [])
             if isinstance(a, dict)}
    n_merged = 0
    for it in task_items:
        a = by_id.get(it["id"])
        if not a:
            continue
        if not a.get("answer") or not str(a["answer"]).strip():
            uncertainties.append({"issue": "answers.json item has empty answer",
                                  "item": it["id"]})
            continue
        it["answer"] = a["answer"]
        evidence = a.get("evidence") or []
        it["evidence"] = evidence
        if "confidence" in a:
            it["confidence"] = a["confidence"]
        # --- evidence validation (not just a non-empty check) ---
        invalid = []
        for ev in evidence:
            for prob in validate_evidence(ev, parsed):
                invalid.append({"evidence": ev, "problem": prob})
        it["evidence_validation"] = {"checked": len(evidence),
                                     "invalid": invalid}
        if not evidence:
            it["answer_status"] = "answered_no_evidence"
            uncertainties.append({
                "issue": "answer provided without any evidence reference",
                "item": it["id"]})
        elif invalid:
            it["answer_status"] = "answered_evidence_suspect"
            uncertainties.append({
                "issue": "answer evidence failed validation",
                "item": it["id"], "invalid": invalid})
        else:
            it["answer_status"] = "answered_verified"
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

    # ---- fingerprint for phase-1 reuse (phase 2 must NOT re-parse) ----
    # includes the PDF content hash so a swapped PDF of the same name/size
    # can never hit a stale cache
    fp_current = {
        "case_id": case_id,
        "pdf": str(pdf.resolve()),
        "pdf_size": pdf.stat().st_size,
        "pdf_md5": hashlib.md5(pdf.read_bytes()).hexdigest(),
        "case_md5": hashlib.md5(case_path.read_bytes()).hexdigest()
        if case_path.is_file() else None,
        "task_md5": hashlib.md5(task_path.read_bytes()).hexdigest()
        if task_path.is_file() else None,
    }
    fp_path = workdir / "phase1_fingerprint.json"
    final_path = workdir / "phase1_final.json"

    parsed = None
    task_items = None
    phase1_ran = False
    if args.answers and fp_path.is_file() and final_path.is_file():
        try:
            fp_old = json.loads(fp_path.read_text(encoding="utf-8"))
            if fp_old == fp_current:
                cached = json.loads(final_path.read_text(encoding="utf-8"))
                if cached.get("case_id") == case_id:
                    parsed = cached["result"]
                    task_items = cached.get("task_items", [])
                    uncertainties.extend(cached.get("uncertainties", []))
                    changes.append("phase-1 result reused from work cache "
                                   "(PDF not re-parsed)")
                    print("phase1=reused case_id=%s" % case_id)
                else:
                    changes.append(
                        "cache case_id %r != current %r; cache ignored"
                        % (cached.get("case_id"), case_id))
            else:
                changes.append("fingerprint mismatch (case/task/PDF changed); "
                               "cache ignored")
        except (json.JSONDecodeError, KeyError) as e:
            changes.append("phase-1 cache unreadable, re-running: %s" % e)

    if parsed is None:
        phase1_ran = True
        # ---- phase 1: parse (stale-artifact protection) ----
        for stale in ("result.json", "fulltext.md"):
            (workdir / stale).unlink(missing_ok=True)
        stdout_log = workdir / "parser.stdout.log"
        stderr_log = workdir / "parser.stderr.log"
        proc, proc_err = None, None
        try:
            with stdout_log.open("w", encoding="utf-8") as so, \
                    stderr_log.open("w", encoding="utf-8") as se:
                proc = subprocess.run([sys.executable, str(PARSER), str(pdf),
                                       "--out", str(workdir), "--case-id",
                                       str(case_id)],
                                      stdout=so, stderr=se, timeout=600)
        except subprocess.TimeoutExpired:
            proc_err = "parser exceeded 600 s timeout"
        except OSError as e:
            proc_err = "parser spawn failed: %s" % e

        parsed_path = workdir / "result.json"
        fail_reason = None
        if proc_err:
            fail_reason = proc_err
        elif proc is not None and proc.returncode != 0:
            fail_reason = "parser exited with code %d" % proc.returncode
        elif not parsed_path.is_file():
            fail_reason = "parser produced no result.json"
        if fail_reason:
            result = {
                "case_id": case_id,
                "status": "failed",
                "reason": fail_reason + "; see work/parser.stderr.log",
                "parser_stderr_tail": stderr_log.read_text(
                    encoding="utf-8", errors="replace")[-1000:]
                if stderr_log.is_file() else "",
                "uncertainties": [{"issue": "parser hard failure",
                                   "detail": fail_reason}],
                "sources": [], "changes": changes,
                "runtime": {"seconds": round(time.time() - t0, 2)},
            }
            (outdir / "result.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            print("status=failed reason=%s" % fail_reason)
            return 1

        try:
            parsed = json.loads(parsed_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            (outdir / "result.json").write_text(json.dumps({
                "case_id": case_id, "status": "failed",
                "reason": "parser result.json is not valid JSON: %s" % e,
                "uncertainties": [{"issue": "parser output corrupt"}],
                "sources": [], "changes": changes,
                "runtime": {"seconds": round(time.time() - t0, 2)}},
                ensure_ascii=False, indent=2), encoding="utf-8")
            print("status=failed reason=corrupt-parser-output")
            return 1
        # guard: never accept another case's result
        if parsed.get("case_id") != case_id:
            (outdir / "result.json").write_text(json.dumps({
                "case_id": case_id, "status": "failed",
                "reason": "parser output case_id %r does not match current "
                          "case %r; refusing to reuse" % (parsed.get("case_id"),
                                                         case_id),
                "uncertainties": [{"issue": "case_id mismatch"}],
                "sources": [], "changes": changes,
                "runtime": {"seconds": round(time.time() - t0, 2)}},
                ensure_ascii=False, indent=2), encoding="utf-8")
            print("status=failed reason=case-id-mismatch")
            return 1
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

    # ---- phase 1b: task analysis + evidence retrieval (no answering) ----
    task_items = analyze_task(task_text, parsed) if task_text.strip() else []
    if task_items:
        uncertainties.append({
            "issue": "task items are analyzed and evidence-retrieved but NOT "
                     "answered by the script; semantic answering is the Agent "
                     "phase-2 step (see SKILL.md). answers=null until an "
                     "answers.json is merged via --answers.",
            "pending_items": [it["id"] for it in task_items]})

    # ---- optional phase 2 merge (evidence-validated) ----
    if args.answers:
        apath = Path(args.answers)
        if apath.is_file():
            try:
                answers_obj = json.loads(apath.read_text(encoding="utf-8-sig"))
                pending = merge_answers(task_items, answers_obj, parsed,
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

    # cache phase-1 output so a later --answers run can reuse it without
    # re-parsing the PDF; refresh the cache whenever phase 1 actually ran
    if phase1_ran:
        fp_path.write_text(json.dumps(fp_current, ensure_ascii=False, indent=2),
                           encoding="utf-8")
        final_path.write_text(json.dumps(final, ensure_ascii=False),
                              encoding="utf-8")

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
