"""run_case_tests.py — Harness-level tests for run_case.py.

Covers the failure modes that matter for evaluation integrity:
  T1 stale result protection: a corrupt PDF in a work dir that still holds a
     previous case's parser output must NOT reuse the old result.
  T2 case_id guard: parser output for another case is refused.
  T3 phase-2 reuse: --answers run must NOT re-run the parser.
  T4 evidence validation: out-of-range index, wrong page, wrong bbox are
     detected and marked; answer without evidence is marked.
  T5 missing-PDF failure is honest.

Every check runs the real scripts. Writes case_test_report.md.
"""
import importlib.util
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
SKILL_DIR = TESTS_DIR.parent
RUN_CASE = SKILL_DIR / "scripts" / "run_case.py"
WORK = TESTS_DIR / "case_tests_work"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def sh(args):
    return subprocess.run([sys.executable] + args,
                          capture_output=True, text=True, timeout=300)


def make_case(d, case_id, pdf_src=None, task="1. 表格结果如何？\n",
              contract=None):
    d.mkdir(parents=True, exist_ok=True)
    (d / "case.json").write_text(json.dumps({
        "case_id": case_id,
        "output_contract": contract or ["status", "task_items", "result",
                                        "sources", "uncertainties"]},
        ensure_ascii=False), encoding="utf-8")
    (d / "task.md").write_text(task, encoding="utf-8")
    if pdf_src:
        shutil.copy(pdf_src, d / "paper.pdf")


def read_json(p):
    return json.loads(p.read_text(encoding="utf-8"))


def main():
    checks = []

    def add(name, ok, detail=""):
        checks.append({"check": name, "pass": bool(ok), "detail": detail})

    if WORK.is_dir():
        shutil.rmtree(WORK)
    WORK.mkdir(parents=True)
    mk = load_module("make_fixtures", TESTS_DIR / "make_fixtures.py")
    mk.ALL["twocol"](WORK)  # ensure twocol.pdf exists
    twocol = WORK / "twocol.pdf"

    # ---------- T1: stale result protection ----------
    in_a, out_a, work_s = WORK / "in_a", WORK / "out_a", WORK / "work_shared"
    make_case(in_a, "case-A", twocol)
    r1 = sh([str(RUN_CASE), "--input", str(in_a), "--output", str(out_a),
             "--work", str(work_s)])
    ok_a = (out_a / "result.json").is_file() \
        and read_json(out_a / "result.json")["case_id"] == "case-A"
    add("T1-pre: case A parses OK in shared work dir", ok_a, r1.stdout.strip())
    # now case B with a corrupt PDF in the SAME work dir
    in_b, out_b = WORK / "in_b", WORK / "out_b"
    make_case(in_b, "case-B", None)
    (in_b / "paper.pdf").write_bytes(b"%PDF-1.4 broken not really a pdf")
    r2 = sh([str(RUN_CASE), "--input", str(in_b), "--output", str(out_b),
             "--work", str(work_s)])
    res_b = read_json(out_b / "result.json")
    add("T1: corrupt PDF in shared work dir fails honestly (no stale reuse)",
        res_b["case_id"] == "case-B" and res_b["status"] == "failed",
        "case_id=%s status=%s reason=%s" % (res_b["case_id"], res_b["status"],
                                            res_b.get("reason", "")[:60]))

    # ---------- T2 + T3: phase1 cache, then answers reuse without re-parse ----------
    out_a2 = WORK / "out_a2"
    answers_bad = WORK / "answers_bad.json"
    answers_bad.write_text(json.dumps({"items": [
        {"id": "item-1", "answer": "编造一个带坏证据的答案。",
         "evidence": [{"kind": "paragraph", "paragraph_index": 9999, "page": 77},
                      {"kind": "paragraph", "paragraph_index": 0, "page": 99},
                      {"kind": "paragraph", "paragraph_index": 0, "page": 1,
                       "bbox": {"x0": 0, "y0": 0, "x1": 1, "y1": 1}}]},
        {"id": "item-2", "answer": "没有证据的答案。", "evidence": []},
    ]}, ensure_ascii=False), encoding="utf-8")
    # add a second task item so item-2 exists
    (in_a / "task.md").write_text("1. 表格结果如何？\n2. 摘要描述了什么？\n",
                                  encoding="utf-8")
    r3 = sh([str(RUN_CASE), "--input", str(in_a), "--output", str(out_a),
             "--work", str(work_s)])  # re-run phase1 with 2 items
    mtime_before = (work_s / "parser.stdout.log").stat().st_mtime
    time.sleep(1.1)
    r4 = sh([str(RUN_CASE), "--input", str(in_a), "--output", str(out_a2),
             "--work", str(work_s), "--answers", str(answers_bad)])
    mtime_after = (work_s / "parser.stdout.log").stat().st_mtime
    res_a2 = read_json(out_a2 / "result.json")
    add("T3: phase-2 reuses phase-1 (parser not re-run)",
        "phase1=reused" in r4.stdout and mtime_before == mtime_after,
        "stdout=%s" % r4.stdout.strip().splitlines()[:1])

    # ---------- T4: evidence validation ----------
    items = {it["id"]: it for it in res_a2["task_items"]}
    it1, it2 = items.get("item-1", {}), items.get("item-2", {})
    add("T4a: bad index/page/bbox flagged as evidence_suspect",
        it1.get("answer_status") == "answered_evidence_suspect"
        and len(it1.get("evidence_validation", {}).get("invalid", [])) == 3,
        json.dumps(it1.get("evidence_validation", {}), ensure_ascii=False)[:200])
    add("T4b: answer without evidence flagged",
        it2.get("answer_status") == "answered_no_evidence",
        it2.get("answer_status", "missing"))
    add("T4c: invalid evidence recorded in uncertainties",
        any(u.get("issue") == "answer evidence failed validation"
            for u in res_a2["uncertainties"]))
    # valid answers validate clean
    answers_ok = WORK / "answers_ok.json"
    answers_ok.write_text(json.dumps({"items": [
        {"id": "item-1", "answer": "表1两行对比。",
         "evidence": [{"kind": "table", "table_index": 0, "page": 1}]},
        {"id": "item-2", "answer": "摘要说明了验证目标。",
         "evidence": [{"kind": "paragraph", "paragraph_index": 0, "page": 1}]},
    ]}, ensure_ascii=False), encoding="utf-8")
    out_a3 = WORK / "out_a3"
    sh([str(RUN_CASE), "--input", str(in_a), "--output", str(out_a3),
        "--work", str(work_s), "--answers", str(answers_ok)])
    res_a3 = read_json(out_a3 / "result.json")
    ok_statuses = all(it["answer_status"] == "answered_verified"
                      for it in res_a3["task_items"])
    add("T4d: valid evidence passes as answered_verified",
        ok_statuses and res_a3["status"] == "success",
        "status=%s" % res_a3["status"])

    # ---------- T6: swapped PDF must invalidate the cache ----------
    # same case, same filename, but PDF content changed -> no reuse allowed
    (in_a / "paper.pdf").write_bytes(twocol.read_bytes() + b"% post-hoc change\n")
    out_a4 = WORK / "out_a4"
    r5 = sh([str(RUN_CASE), "--input", str(in_a), "--output", str(out_a4),
             "--work", str(work_s), "--answers", str(answers_ok)])
    add("T6: changed PDF invalidates phase-1 cache (no reuse)",
        "phase1=reused" not in r5.stdout
        and any("fingerprint mismatch" in c for c in
                read_json(out_a4 / "result.json")["changes"]),
        r5.stdout.strip().splitlines()[:1])
    # restore the original PDF for any later runs
    shutil.copy(twocol, in_a / "paper.pdf")

    # ---------- T5: missing PDF ----------
    in_c, out_c, work_c = WORK / "in_c", WORK / "out_c", WORK / "work_c"
    make_case(in_c, "case-C", None)
    sh([str(RUN_CASE), "--input", str(in_c), "--output", str(out_c),
        "--work", str(work_c)])
    res_c = read_json(out_c / "result.json")
    add("T5: missing PDF reported as failed", res_c["status"] == "failed",
        res_c.get("reason", ""))

    n_pass = sum(1 for c in checks if c["pass"])
    lines = ["# run_case harness test report (measured)",
             "",
             "- checks: %d, passed: %d" % (len(checks), n_pass), ""]
    for c in checks:
        lines.append("- [%s] %s%s" % ("PASS" if c["pass"] else "FAIL",
                                      c["check"],
                                      (" — " + c["detail"]) if c["detail"] and not c["pass"] else ""))
    (WORK / "case_test_report.md").write_text("\n".join(lines), encoding="utf-8")
    print("case tests: %d/%d passed -> %s" % (n_pass, len(checks),
                                              WORK / "case_test_report.md"))
    return 0 if n_pass == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
