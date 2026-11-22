"""run_regression.py — Regression test harness for scientific-pdf-parser.

Generates fixtures (if missing), runs the real parser on each, compares
against ground truth known by construction, and writes a measured report.
No accuracy number is invented: every value below is computed from an actual
run in the environment recorded in the report header. Checks that cannot run
(e.g. OCR without tesseract) are reported as NOT RUN, never as passed.

Usage:
    python run_regression.py [--work <dir>]   # default: <tests>/../testdata_regression
"""
import argparse
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
SKILL_DIR = TESTS_DIR.parent


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def norm(t):
    t = unicodedata.normalize("NFKC", t).lower()
    return re.sub(r"\s+", " ", t).strip()


# Ground truth per fixture (known by construction in make_fixtures.py)
GT = {
    "singlecol": {
        "must_contain": ["deep parsing of single column articles",
                         "alice example, bob sample",
                         "keywords: layout; parsing; metadata",
                         "doi: 10.1234/jscs.2024.0001",
                         "3 results reported below illustrate this requirement"],
        "order": ["single column articles are the simplest",
                  "1 introduction", "2 discussion", "references"],
        "sections": ["Abstract", "1 Introduction", "2 Discussion", "References"],
        "forbid_sections": ["3 results reported below illustrate this requirement in detail"],
        "refs": 2, "tables": 0, "equations": 0,
        "metadata": {"title_contains": "Deep Parsing of Single Column",
                     "doi": "10.1234/jscs.2024.0001",
                     "keywords_contains": "layout"},
    },
    "twocol": {
        "must_contain": ["a study of synthetic layout parsing",
                         "jane doe, john smith",
                         "department of testing, example university"],
        "order": ["we present a synthetic two column",
                  "parsing scientific pdfs requires",
                  "2 method", "2.1 layout extraction", "word boxes are extracted",
                  "2.2 structure recognition", "table 1: parsing accuracy",
                  "figure 1: overview", "3 results", "4 conclusion", "references",
                  "[1] a. author"],
        "sections": ["Abstract", "1 Introduction", "2 Method", "2.1 Layout extraction",
                     "2.2 Structure recognition", "3 Results", "4 Conclusion",
                     "References"],
        "refs": 3, "tables": 1, "figures": 1, "equations": 1,
        "running_removed": ["journal of synthetic tests, vol. 7"],
        "metadata": {"title_contains": "Synthetic Layout Parsing",
                     "authors_contains": "Jane Doe"},
    },
    "threecol": {
        "order": ["column one introduces", "2 middle column",
                  "the middle column continues", "3 final column",
                  "the final column closes", "[1] t. three"],
        "sections": ["1 Introduction", "2 Middle Column", "3 Final Column",
                     "References"],
        "refs": 1,
    },
    "mixedlayout": {
        "order": ["left column text before the wide table",
                  "right column text before the wide band",
                  "table 2: wide results table",
                  "left column text after the wide band",
                  "[1] w. wide"],
        "sections": ["1 Introduction", "2 Early Right", "3 After Band"],
        "refs": 1, "tables": 1,
    },
    "table": {
        "tables": 1,
        "table_cells": ["91.2", "88.4", "93.5", "90.1", "news", "wiki",
                        "acc", "f1"],
        "order": ["the table below has a two row header",
                  "table 1: benchmark results",
                  "the numbers in the grid are deliberately simple"],
    },
    "equations": {
        "equations": 2,
        "equation_numbers": ["1", "2"],
        "forbid_equation_text": ["see also the earlier review"],
        "order": ["we define the energy", "e = sum_i alpha_i x_i + beta",
                  "see also the earlier review"],
    },
    "scanned": {"expect_status": ["unreadable", "partial"]},
    "mixedlayer": {
        "expect_status": ["partial", "success"],
        "must_contain": ["this page has a normal text layer"],
        "expect_flagged_page": 2,
    },
    "crosspage_table": {
        "tables": 2,
        "order": ["the table begins on this page",
                  "table 1: rows split across two pages",
                  "table 1 (continued)", "closing prose after the continued table"],
    },
}


def check_result(name, pdf_path, pp, tmp_out):
    """Run the real parser in-process and compute measured checks."""
    t0 = time.time()
    result, md, fatal = pp.parse_document(pdf_path, [])
    elapsed = time.time() - t0
    gt = GT[name]
    checks = []
    if fatal:
        return {"fixture": name, "fatal": fatal, "seconds": elapsed, "checks": []}
    fulltext = norm(md or "")

    def add(check, ok, detail=""):
        checks.append({"check": check, "pass": bool(ok), "detail": detail})

    # --- text completeness
    for phrase in gt.get("must_contain", []):
        add("text contains: %s" % phrase[:50],
            norm(phrase) in fulltext, "")

    # --- reading order
    order = gt.get("order", [])
    pos, ok_order, first_bad = [], True, None
    for phrase in order:
        i = fulltext.find(norm(phrase))
        pos.append(i)
        if i < 0:
            ok_order, first_bad = False, phrase
    if ok_order:
        for a, b in zip(pos, pos[1:]):
            if a >= b:
                ok_order = False
                first_bad = "sequence broken near position %d" % b
                break
    if order:
        add("reading order (%d anchors)" % len(order), ok_order,
            first_bad or "all anchors found in ascending order")

    # --- sections
    secs = [s["title"] for s in result["sections"]]
    for title in gt.get("sections", []):
        add("section found: %s" % title, title in secs)
    for bad in gt.get("forbid_sections", []):
        add("no false heading: %s" % bad[:40],
            not any(norm(bad) == norm(s) for s in secs))

    # --- counts
    for key, arr in (("refs", "references"), ("tables", "tables"),
                     ("figures", "figures"), ("equations", "equations")):
        if key in gt:
            add("%s count == %d" % (key, gt[key]),
                len(result[arr]) == gt[key],
                "got %d" % len(result[arr]))

    # --- equations detail
    for num in gt.get("equation_numbers", []):
        add("equation number %s found" % num,
            any(e.get("number") == num for e in result["equations"]))
    for bad in gt.get("forbid_equation_text", []):
        add("prose not misread as equation: %s" % bad[:40],
            not any(norm(bad) in norm(e["text"]) for e in result["equations"]))

    # --- tables
    if "table_cells" in gt and result["tables"]:
        grid_md = norm(" ".join(t.get("markdown", "") for t in result["tables"]))
        for cell in gt["table_cells"]:
            add("table cell present: %s" % cell, norm(cell) in grid_md)

    # --- cross-page table: per-page grids + explicit continuation link
    if name == "crosspage_table" and len(result["tables"]) >= 2:
        t1, t2 = result["tables"][0], result["tables"][1]
        md1 = norm(t1.get("markdown", ""))
        md2 = norm(t2.get("markdown", ""))
        add("page-1 grid has no page-2 rows", "b1" not in md1 and "30" not in md1,
            md1[:80])
        add("page-2 grid has no page-1 rows", "a1" not in md2 and "10" not in md2,
            md2[:80])
        add("continuation link recorded",
            t2.get("continued") is True
            and "continuation_of" in t2,
            "t2.continued=%r continuation_of=%r" % (t2.get("continued"),
                                                    t2.get("continuation_of")))

    # --- running matter
    for rm in gt.get("running_removed", []):
        add("running matter removed: %s" % rm[:40],
            any(norm(rm) in norm(r["text"]) for r in result["removed_running_matter"]))
        add("running matter absent from body: %s" % rm[:30],
            norm(rm) not in fulltext)

    # --- metadata
    mdexp = gt.get("metadata", {})
    meta = result["metadata"]
    if "title_contains" in mdexp:
        v = (meta.get("title") or {}).get("value") or ""
        add("metadata title", mdexp["title_contains"].lower() in v.lower(),
            repr(v[:60]))
    if "authors_contains" in mdexp:
        v = (meta.get("authors") or {}).get("value") or ""
        add("metadata authors", mdexp["authors_contains"].lower() in v.lower(),
            repr(v[:60]))
    if "doi" in mdexp:
        v = (meta.get("doi") or {}).get("value") or ""
        add("metadata doi", v == mdexp["doi"], repr(v))
    if "keywords_contains" in mdexp:
        v = (meta.get("keywords") or {}).get("value") or ""
        add("metadata keywords", mdexp["keywords_contains"].lower() in v.lower(),
            repr(v[:60]))

    # --- status expectations
    if "expect_status" in gt:
        add("status in %s" % gt["expect_status"],
            result["status"] in gt["expect_status"], result["status"])
    if "expect_flagged_page" in gt:
        flagged = set(result["stats"].get("empty_pages", [])) | {
            u.get("page") for u in result["uncertainties"] if u.get("page")}
        add("image page %d flagged" % gt["expect_flagged_page"],
            gt["expect_flagged_page"] in flagged
            or gt["expect_flagged_page"] in result["stats"].get("ocr_pages", []),
            "empty=%s ocr=%s" % (result["stats"].get("empty_pages"),
                                 result["stats"].get("ocr_pages")))

    # --- bbox validity for every located item
    bad_bbox = 0
    total_bbox = 0

    def check_box(b, pw=595.5, ph=841.9):
        nonlocal bad_bbox, total_bbox
        total_bbox += 1
        if not b or not (0 <= b["x0"] < b["x1"] <= pw + 20
                         and 0 <= b["y0"] < b["y1"] <= ph + 20):
            bad_bbox += 1

    for coll in ("paragraphs", "sections", "tables", "figures", "equations",
                 "references"):
        for it in result[coll]:
            check_box(it.get("bbox"))
    add("bbox validity (%d boxes)" % total_bbox, bad_bbox == 0,
        "%d invalid" % bad_bbox)

    n_pass = sum(1 for c in checks if c["pass"])
    return {"fixture": name, "seconds": round(elapsed, 2),
            "status": result["status"], "n_checks": len(checks),
            "n_pass": n_pass, "checks": checks}


def check_ocr_tsv_math(pp):
    """Unit checks of Tesseract-TSV parsing (no tesseract needed)."""
    out = []
    tsv = ("level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\t"
           "width\theight\tconf\ttext\n"
           "5\t1\t1\t1\t1\t1\t300\t600\t150\t60\t96.0\tHello\n")
    blocks = pp.parse_tesseract_tsv(tsv, 595.0, 842.0, dpi=300)
    if not blocks:
        out.append({"check": "ocr tsv conversion", "pass": False,
                    "detail": "no blocks"})
    else:
        w = blocks[0].lines[0].words[0]
        ok = (abs(w.x0 - 72.0) < 0.01 and abs(w.y0 - 144.0) < 0.01
              and abs(w.x1 - 108.0) < 0.01 and abs(w.y1 - 158.4) < 0.01)
        out.append({"check": "ocr tsv conversion (300dpi px -> pt)",
                    "pass": ok,
                    "detail": "got (%.1f, %.1f, %.1f, %.1f), want (72, 144, 108, 158.4)"
                              % (w.x0, w.y0, w.x1, w.y1)})
    # confidence aggregation
    tsv2 = ("level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\t"
            "width\theight\tconf\ttext\n"
            "5\t1\t1\t1\t1\t1\t0\t0\t100\t24\t80.0\tFoo\n"
            "5\t1\t1\t1\t1\t2\t120\t0\t100\t24\t60.0\tBar\n")
    blocks2, stats = pp.parse_tesseract_tsv(tsv2, 595.0, 842.0, dpi=300,
                                            with_conf=True)
    ok2 = (stats["words"] == 2 and abs(stats["mean_conf"] - 70.0) < 0.01)
    out.append({"check": "ocr tsv confidence aggregation",
                "pass": ok2, "detail": "got %s" % stats})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", default=str(TESTS_DIR / "regression_work"))
    args = ap.parse_args()
    work = Path(args.work)
    work.mkdir(parents=True, exist_ok=True)

    pp = load_module("parse_pdf", SKILL_DIR / "scripts" / "parse_pdf.py")

    # fixtures
    mk = load_module("make_fixtures", TESTS_DIR / "make_fixtures.py")
    for name, fn in mk.ALL.items():
        pdf = work / ("%s.pdf" % name)
        if not pdf.is_file():
            fn(work)

    env = {"python": sys.version.split()[0],
           "pdftotext": shutil.which("pdftotext") or "MISSING",
           "pdftoppm": shutil.which("pdftoppm") or "MISSING",
           "tesseract": shutil.which("tesseract") or "MISSING (OCR paths NOT RUN)"}

    reports = []
    for name in mk.ALL:
        pdf = work / ("%s.pdf" % name)
        reports.append(check_result(name, pdf, pp, work))

    ocr_checks = check_ocr_tsv_math(pp)

    # ---- aggregate measured metrics
    all_checks = [c for r in reports for c in r["checks"]] + ocr_checks
    n_pass = sum(1 for c in all_checks if c["pass"])

    lines = ["# Regression report (measured, not estimated)",
             "",
             "- environment: python %s; pdftotext=%s; pdftoppm=%s; tesseract=%s"
             % (env["python"], "yes" if "MISSING" not in env["pdftotext"] else "no",
                "yes" if "MISSING" not in env["pdftoppm"] else "no", env["tesseract"]),
             "- total checks: %d, passed: %d, failed: %d"
             % (len(all_checks), n_pass, len(all_checks) - n_pass),
             "- OCR end-to-end: %s"
             % ("NOT RUN (tesseract missing) — TSV coordinate conversion "
                "unit-checked instead" if "MISSING" in env["tesseract"] else "available"),
             ""]
    for r in reports:
        if "fatal" in r:
            lines.append("## %s — FATAL: %s" % (r["fixture"], r["fatal"]))
            continue
        lines.append("## %s — %d/%d checks passed, %.2fs, status=%s"
                     % (r["fixture"], r["n_pass"], r["n_checks"],
                        r["seconds"], r["status"]))
        for c in r["checks"]:
            mark = "PASS" if c["pass"] else "FAIL"
            lines.append("- [%s] %s%s" % (mark, c["check"],
                                          (" — " + c["detail"]) if c["detail"] and not c["pass"] else ""))
        lines.append("")
    mark_all = {True: "PASS", False: "FAIL"}
    lines.append("## unit checks")
    for c in ocr_checks:
        lines.append("- [%s] %s — %s" % (mark_all[c["pass"]], c["check"],
                                           c["detail"]))

    (work / "regression_report.md").write_text("\n".join(lines), encoding="utf-8")
    (work / "regression_results.json").write_text(json.dumps(
        {"env": env, "reports": reports, "ocr_unit_checks": ocr_checks,
         "summary": {"checks": len(all_checks), "passed": n_pass}},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print("checks: %d passed / %d total -> %s" % (n_pass, len(all_checks),
                                                work / "regression_report.md"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
