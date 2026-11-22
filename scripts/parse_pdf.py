#!/usr/bin/env python3
"""parse_pdf.py — Parse a scientific paper PDF into verifiable structured output.

Dependencies: pdftotext (Poppler). Optional: pdftoppm + tesseract (scanned pages).
Python >= 3.9, standard library only.

Outputs:
  <out>/result.json   structured result with per-item page/bbox evidence
  <out>/fulltext.md   full text in restored reading order with [p.N] anchors

Exit codes: 0 success/partial (see status field), 1 hard failure (no result).
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

WORD_MIN_TEXT_PAGE = 20        # fewer words than this => candidate scanned page
WIDE_BLOCK_FRAC = 0.62         # block width fraction of page => spans all columns
HEADER_TOP_FRAC = 0.085        # y-center above this => header candidate
FOOTER_BOT_FRAC = 0.925        # y-center below this => footer candidate
RUNNING_MIN_PAGE_FRAC = 0.4    # repeated on >= this fraction of pages => running matter

SEC_NUM_RE = re.compile(r"^(\d+(?:\.\d+)*)\.?\s+(\S.{0,90})$")
SEC_NAME_RE = re.compile(
    r"^(abstract|摘要|introduction|引言|conclusions?|结论|references|bibliography|"
    r"参考文献|acknowledg(e)?ments?|致谢|appendix|附录|keywords?|关键词)\b\.?:?\s*$",
    re.IGNORECASE,
)
FIG_CAP_RE = re.compile(
    r"^\s*((?:figure|fig\.?)\s*[0-9IVX]+\s*[:.：]|图\s*[0-9IVX]+)",
    re.IGNORECASE)
TAB_CAP_RE = re.compile(
    r"^\s*((?:table|tab\.?)\s*[0-9IVX]+\s*[:.：]|表\s*[0-9IVX]+)",
    re.IGNORECASE)
EQN_NUM_RE = re.compile(r"[（(]\s*\d+(?:\.\d+)?\s*[)）]\s*$")
REF_ITEM_RE = re.compile(r"^\s*(\[\d+\]|\d+\s*[.)])\s+")


@dataclass
class Word:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float


@dataclass
class Line:
    words: list = field(default_factory=list)

    @property
    def text(self):
        return " ".join(w.text for w in self.words)

    @property
    def bbox(self):
        return (min(w.x0 for w in self.words), min(w.y0 for w in self.words),
                max(w.x1 for w in self.words), max(w.y1 for w in self.words))


@dataclass
class Block:
    lines: list = field(default_factory=list)
    page: int = 0

    @property
    def bbox(self):
        bs = [ln.bbox for ln in self.lines]
        return (min(b[0] for b in bs), min(b[1] for b in bs),
                max(b[2] for b in bs), max(b[3] for b in bs))

    @property
    def text_lines(self):
        return [ln.text for ln in self.lines if ln.text.strip()]


def ascii_safe_tmpdir():
    """Return a writable temp directory whose path is pure ASCII.

    Poppler builds on some platforms cannot open output files under non-ASCII
    paths, so intermediate files must live in an ASCII-only directory."""
    cands = [tempfile.gettempdir(),
             os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "Temp"),
             r"C:\Windows\Temp", "/tmp", "."]
    for c in cands:
        try:
            if c and os.path.isdir(c):
                c.encode("ascii")
                return c
        except (UnicodeEncodeError, OSError):
            continue
    return tempfile.gettempdir()


def stage_ascii(path):
    """If *path* contains non-ASCII characters, copy it into the ASCII temp dir
    and return (ascii_path, cleanup_fn); otherwise return (path, noop)."""
    import shutil as _sh
    try:
        str(path).encode("ascii")
        return Path(path), (lambda: None)
    except UnicodeEncodeError:
        pass
    tmp = Path(tempfile.mkdtemp(prefix="pdfstage_", dir=ascii_safe_tmpdir()))
    dst = tmp / ("input%s" % Path(path).suffix)
    _sh.copy2(path, dst)
    return dst, (lambda: _sh.rmtree(tmp, ignore_errors=True))


def run_tool(cmd):
    """Run an external tool, return (ok, stdout, stderr).

    stdout/stderr are captured via anonymous temp files rather than pipes so
    the script also works in sandboxes that forbid named-pipe creation."""
    try:
        with tempfile.TemporaryFile(mode="w+t", encoding="utf-8", errors="replace") as out_f, \
                tempfile.TemporaryFile(mode="w+t", encoding="utf-8", errors="replace") as err_f:
            rc = subprocess.run(cmd, stdout=out_f, stderr=err_f, timeout=300).returncode
            out_f.seek(0)
            err_f.seek(0)
            return rc == 0, out_f.read(), err_f.read()
    except FileNotFoundError:
        return False, "", "tool not found: %s" % cmd[0]
    except subprocess.TimeoutExpired:
        return False, "", "timeout running: %s" % cmd[0]


def pdf_page_count(pdf):
    ok, out, err = run_tool(["pdfinfo", str(pdf)])
    if ok:
        m = re.search(r"^Pages:\s+(\d+)", out, re.MULTILINE)
        if m:
            return int(m.group(1)), None
    if "not found" in err:
        # fall back: probe pages with pdftotext
        n = 0
        while n < 2000:
            ok2, out2, _ = run_tool(["pdftotext", "-f", str(n + 1), "-l", str(n + 1),
                                     str(pdf), "-"])
            if not ok2:
                break
            n += 1
        if n:
            return n, None
    return None, err.strip() or "pdfinfo failed"


def extract_page_blocks(pdf, page_no):
    """Return (page_width, page_height, [Block]) for one page via pdftotext -bbox-layout."""
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False,
                                     dir=ascii_safe_tmpdir()) as tf:
        tmp = tf.name
    try:
        ok, _, err = run_tool(["pdftotext", "-bbox-layout", "-f", str(page_no),
                               "-l", str(page_no), str(pdf), tmp])
        if not ok:
            return None, None, None, err.strip()
        raw = Path(tmp).read_text(encoding="utf-8", errors="replace")
    finally:
        Path(tmp).unlink(missing_ok=True)
    raw = re.sub(r"<!DOCTYPE[^>]*>", "", raw)
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        return None, None, None, "bbox XML parse error: %s" % e

    def lname(tag):
        return tag.rsplit("}", 1)[-1]  # strip XHTML namespace if present

    page_el = None
    for el in root.iter():
        if lname(el.tag) == "page":
            page_el = el
            break
    if page_el is None:
        return None, None, None, "no <page> element in bbox output"
    pw = float(page_el.get("width"))
    ph = float(page_el.get("height"))
    blocks = []
    for b_el in page_el.iter():
        if lname(b_el.tag) != "block":
            continue
        blk = Block(page=page_no)
        for l_el in b_el:
            if lname(l_el.tag) != "line":
                continue
            ln = Line()
            for w_el in l_el:
                if lname(w_el.tag) != "word":
                    continue
                ln.words.append(Word(
                    text=w_el.text or "",
                    x0=float(w_el.get("xMin")), y0=float(w_el.get("yMin")),
                    x1=float(w_el.get("xMax")), y1=float(w_el.get("yMax")),
                ))
            if ln.words:
                ln.words.sort(key=lambda w: w.x0)
                blk.lines.append(ln)
        if blk.lines:
            blk.lines.sort(key=lambda ln: (ln.bbox[1], ln.bbox[0]))
            blocks.append(blk)
    return pw, ph, blocks, None


def normalize_running(text):
    t = unicodedata.normalize("NFKC", text).strip().lower()
    return re.sub(r"\d+", "#", t)


def detect_running_matter(pages_blocks, page_heights, npages):
    """Return set of id() of lines to drop as header/footer."""
    seen = {}
    for pi, blocks in enumerate(pages_blocks):
        ph = page_heights[pi]
        for blk in blocks:
            for ln in blk.lines:
                yc = (ln.bbox[1] + ln.bbox[3]) / 2.0
                if yc < HEADER_TOP_FRAC * ph or yc > FOOTER_BOT_FRAC * ph:
                    key = normalize_running(ln.text)
                    if key:
                        seen.setdefault(key, []).append((pi, ln))
    drop = set()
    removed = []
    thresh = max(2, int(round(RUNNING_MIN_PAGE_FRAC * npages)))
    for key, occ in seen.items():
        pages_hit = len({pi for pi, _ in occ})
        if pages_hit >= thresh:
            for pi, ln in occ:
                drop.add(id(ln))
            removed.append({"text": occ[0][1].text, "pages": sorted({pi + 1 for pi, _ in occ})})
    return drop, removed


def order_page_blocks(blocks, pw, ph):
    """Restore reading order: split into horizontal bands at full-width blocks,
    order bands top-down; within a band, left column then right column."""
    wide, narrow = [], []
    for b in blocks:
        x0, y0, x1, y1 = b.bbox
        (wide if (x1 - x0) > WIDE_BLOCK_FRAC * pw else narrow).append(b)
    if not narrow:
        return sorted(wide, key=lambda b: b.bbox[1])
    # detect columns by clustering block left edges (x0): real columns share
    # a left edge; page-centered blocks (title/authors) match neither cluster
    tol = 0.05 * pw
    clusters = []  # list of [x0_sum, count, [blocks]]
    for b in sorted(narrow, key=lambda b: b.bbox[0]):
        if clusters and abs(b.bbox[0] - clusters[-1][0] / clusters[-1][1]) <= tol:
            clusters[-1][0] += b.bbox[0]
            clusters[-1][1] += 1
            clusters[-1][2].append(b)
        else:
            clusters.append([b.bbox[0], 1, [b]])
    clusters.sort(key=lambda c: -c[1])
    col_intervals = []
    col_x0means = []
    for x0sum, cnt, cblocks in clusters[:2]:
        col_intervals.append((min(b.bbox[0] for b in cblocks),
                              max(b.bbox[2] for b in cblocks)))
        col_x0means.append(x0sum / cnt)
    order_idx = sorted(range(len(col_intervals)), key=lambda i: col_x0means[i])
    col_intervals = [col_intervals[i] for i in order_idx]
    col_x0means = [col_x0means[i] for i in order_idx]
    two_col = (len(col_intervals) == 2
               and col_x0means[1] - col_x0means[0] > 0.15 * pw
               and clusters[1][1] >= max(1, 0.2 * clusters[0][1]))
    centered = []
    if two_col:
        split = (col_intervals[0][1] + col_intervals[1][0]) / 2.0
        rest = []
        for b in narrow:
            xc = (b.bbox[0] + b.bbox[2]) / 2.0
            in_l = col_intervals[0][0] - tol <= xc <= col_intervals[0][1] + tol
            in_r = col_intervals[1][0] - tol <= xc <= col_intervals[1][1] + tol
            if in_l or in_r:
                rest.append(b)
            else:
                centered.append(b)
        narrow = rest
        # page-centered blocks on a two-column page (title, authors) span or
        # centre across the columns => treat as full-width band breakers
        wide.extend(centered)
    else:
        split = pw / 2.0
    bands = []  # (y0, y1)
    cuts = sorted({0.0, ph} | {w.bbox[1] for w in wide} | {w.bbox[3] for w in wide})
    for a, b_ in zip(cuts, cuts[1:]):
        if b_ - a > 1e-6:
            bands.append((a, b_))
    band_items = []
    for (a, b_) in bands:
        in_band = [n for n in narrow
                   if a - 1e-6 <= (n.bbox[1] + n.bbox[3]) / 2.0 < b_ - 1e-6]
        if not in_band:
            continue
        if two_col:
            left = sorted((n for n in in_band if (n.bbox[0] + n.bbox[2]) / 2.0 < split),
                          key=lambda n: n.bbox[1])
            right = sorted((n for n in in_band if (n.bbox[0] + n.bbox[2]) / 2.0 >= split),
                           key=lambda n: n.bbox[1])
            band_items.append((a, left + right))
        else:
            band_items.append((a, sorted(in_band, key=lambda n: n.bbox[1])))
    # merge wide blocks and bands by vertical position
    events = [(w.bbox[1], 0, w) for w in wide] + [(a, 1, items) for a, items in band_items]
    events.sort(key=lambda e: (e[0], e[1]))
    ordered = []
    for _, kind, obj in events:
        ordered.extend([obj] if kind == 0 else obj)
    for n in narrow:
        if id(n) not in {id(b) for b in ordered}:
            ordered.append(n)
    return ordered


def dehyphenate_join(lines):
    """Join text lines into a paragraph, removing end-of-line hyphenation."""
    out = ""
    for ln in lines:
        t = ln.strip()
        if not t:
            continue
        if out.endswith("-") and t[:1].islower():
            out = out[:-1] + t
        else:
            out = (out + " " + t) if out else t
    return out.strip()


def bbox_dict(b):
    return {"x0": round(b[0], 1), "y0": round(b[1], 1),
            "x1": round(b[2], 1), "y1": round(b[3], 1)}


def ocr_page(pdf, page_no, pw, ph):
    """OCR one scanned page: pdftoppm render at 300 dpi, then tesseract.
    Returns a list with one Block per OCR text line, or None on failure."""
    tmpdir = Path(tempfile.mkdtemp(prefix="ocr_", dir=ascii_safe_tmpdir()))
    try:
        imgbase = tmpdir / "page"
        ok, _, err = run_tool(["pdftoppm", "-f", str(page_no), "-l", str(page_no),
                               "-r", "300", "-png", "-singlefile",
                               str(pdf), str(imgbase)])
        img = Path(str(imgbase) + ".png")
        if not ok or not img.is_file():
            return None
        ok, out, err = run_tool(["tesseract", str(img), "stdout", "--psm", "3"])
        if not ok or not out.strip():
            return None
        blk = Block(page=page_no)
        n_lines = max(1, len([ln for ln in out.splitlines() if ln.strip()]))
        for k, raw in enumerate(out.splitlines()):
            t = raw.strip()
            if not t:
                continue
            y0 = ph * k / n_lines
            ln = Line()
            x = 0.0
            for tok in t.split():
                w = max(10.0, len(tok) * 6.0)
                ln.words.append(Word(text=tok, x0=x, y0=y0, x1=x + w, y1=y0 + 12.0))
                x += w + 6.0
            if ln.words:
                blk.lines.append(ln)
        return [blk] if blk.lines else None
    finally:
        import shutil as _sh
        _sh.rmtree(tmpdir, ignore_errors=True)


def parse_document(pdf, log):
    """Full pipeline. Returns (result_dict, markdown_text, fatal_error)."""
    uncertainties = []
    pdf, cleanup = stage_ascii(pdf)
    try:
        return _parse_document_staged(pdf, uncertainties)
    finally:
        cleanup()


def _parse_document_staged(pdf, uncertainties):
    npages, err = pdf_page_count(pdf)
    if npages is None:
        return None, None, "cannot read PDF (encrypted or corrupt?): %s" % err

    pages_blocks, page_heights, page_widths = [], [], []
    scanned_pages = []
    for p in range(1, npages + 1):
        pw, ph, blocks, perr = extract_page_blocks(pdf, p)
        if blocks is None:
            uncertainties.append({"page": p, "issue": "page extraction failed",
                                  "detail": perr or ""})
            pages_blocks.append([])
            page_heights.append(1.0)
            page_widths.append(1.0)
            continue
        nwords = sum(len(blk.lines) and sum(len(ln.words) for ln in blk.lines)
                     for blk in blocks)
        if nwords < WORD_MIN_TEXT_PAGE:
            scanned_pages.append(p)
        pages_blocks.append(blocks)
        page_heights.append(ph)
        page_widths.append(pw)

    if scanned_pages:
        ocr_ok = (shutil.which("pdftoppm") is not None
                  and shutil.which("tesseract") is not None)
        if ocr_ok:
            ocr_pages = []
            for p in scanned_pages:
                blocks = ocr_page(pdf, p, page_widths[p - 1], page_heights[p - 1])
                if blocks:
                    pages_blocks[p - 1] = blocks
                    ocr_pages.append(p)
            if ocr_pages:
                uncertainties.append({
                    "issue": "pages recovered by OCR (300 dpi + tesseract); "
                             "text unverified — spot-check against the original",
                    "pages": ocr_pages})
                scanned_pages = [p for p in scanned_pages if p not in ocr_pages]
        if scanned_pages:
            if len(scanned_pages) == npages:
                uncertainties.append({
                    "issue": "no text layer on any page (scanned PDF)",
                    "action": "needs OCR (pdftoppm + tesseract); marked unreadable, "
                              "no text fabricated"})
            else:
                uncertainties.append({
                    "issue": "pages without text layer (scanned or figure-only)",
                    "pages": scanned_pages,
                    "action": "these pages not OCRed; figure-only pages may be normal"})

    drop_lines, removed_running = detect_running_matter(
        pages_blocks, page_heights, npages)

    # Flatten blocks into reading order
    ordered = []  # (page, block)
    for pi, blocks in enumerate(pages_blocks):
        kept = []
        for blk in blocks:
            blk.lines = [ln for ln in blk.lines if id(ln) not in drop_lines]
            if blk.lines:
                kept.append(blk)
        for blk in order_page_blocks(kept, page_widths[pi], page_heights[pi]):
            ordered.append((pi + 1, blk))

    # Assemble paragraphs with structure recognition
    sections, paragraphs, tables, figures, equations, references = [], [], [], [], [], []
    in_refs = False
    cur_ref = None
    sec_stack = []
    md_parts = []
    last_page = [0]

    def emit_page_anchor(p):
        if p != last_page[0]:
            md_parts.append("\n[p.%d]\n" % p)
            last_page[0] = p

    def open_section(title, level, page, bbox):
        while sec_stack and sec_stack[-1]["level"] >= level:
            sec_stack.pop()
        sec = {"title": title, "level": level, "page": page, "bbox": bbox_dict(bbox),
               "path": [s["title"] for s in sec_stack] + [title]}
        sections.append(sec)
        sec_stack.append(sec)
        md_parts.append("\n%s %s\n" % ("#" * min(level + 1, 6), title))

    def flush_paragraph(pending, page, blk):
        text = dehyphenate_join(pending)
        if not text:
            return
        emit_page_anchor(page)
        paragraphs.append({"text": text, "page": page,
                           "bbox": bbox_dict(blk.bbox),
                           "section": sec_stack[-1]["title"] if sec_stack else None})
        md_parts.append(text + "\n")

    for page, blk in ordered:
        lines = blk.text_lines
        if not lines:
            continue

        if in_refs:
            emit_page_anchor(page)
            for raw_ln in lines:
                t = raw_ln.strip()
                if not t:
                    continue
                m = REF_ITEM_RE.match(t)
                if m:
                    cur_ref = {"index": m.group(1).strip(" .)[]"), "text": t,
                               "page": page, "bbox": bbox_dict(blk.bbox)}
                    references.append(cur_ref)
                elif cur_ref is not None:
                    cur_ref["text"] += " " + t
                else:
                    cur_ref = {"index": None, "text": t, "page": page,
                               "bbox": bbox_dict(blk.bbox)}
                    references.append(cur_ref)
                md_parts.append(t + "\n")
            continue

        pending = []  # paragraph lines under accumulation
        i = 0
        while i < len(lines):
            t = lines[i].strip()
            i += 1
            if not t:
                continue
            # heading number split onto its own line ("2.1" / "Layout extraction")
            if re.fullmatch(r"\d+(?:\.\d+)*\.?", t) and i < len(lines) \
                    and lines[i].strip():
                t = "%s %s" % (t, lines[i].strip())
                i += 1

            m = SEC_NUM_RE.match(t)
            name_m = SEC_NAME_RE.match(t)
            if m and len(t) < 100 and not t.rstrip().endswith("."):
                flush_paragraph(pending, page, blk)
                pending = []
                level = m.group(1).count(".") + 1
                emit_page_anchor(page)
                open_section(t, level, page, blk.bbox)
                continue
            if name_m:
                flush_paragraph(pending, page, blk)
                pending = []
                emit_page_anchor(page)
                open_section(t, 1, page, blk.bbox)
                if name_m.group(1).lower() in ("references", "bibliography", "参考文献"):
                    in_refs = True
                continue

            fm = FIG_CAP_RE.match(t)
            tm = TAB_CAP_RE.match(t)
            if fm or tm:
                flush_paragraph(pending, page, blk)
                pending = []
                # caption continues over the remaining lines of this block
                rest = [ln.strip() for ln in lines[i:] if ln.strip()]
                cap = dehyphenate_join([t] + rest) if rest else t
                i = len(lines)
                entry = {"label": (fm or tm).group(1), "caption": cap,
                         "page": page, "bbox": bbox_dict(blk.bbox)}
                if fm:
                    figures.append(entry)
                else:
                    entry["note"] = ("caption located; grid content preserved as "
                                     "paragraph lines unless adjacent blocks match")
                    tables.append(entry)
                emit_page_anchor(page)
                md_parts.append("**%s**\n" % cap)
                continue

            if EQN_NUM_RE.search(t) and len(t) < 200:
                flush_paragraph(pending, page, blk)
                pending = []
                equations.append({"text": t, "page": page,
                                  "bbox": bbox_dict(blk.bbox),
                                  "uncertain": False})
                emit_page_anchor(page)
                md_parts.append("$$\n%s\n$$\n" % t)
                continue

            pending.append(t)
        flush_paragraph(pending, page, blk)

    n_words = sum(len(p["text"].split()) for p in paragraphs)
    status = "success"
    if len(scanned_pages) == npages and npages > 0:
        status = "unreadable"
    elif uncertainties or not paragraphs:
        status = "partial"

    result = {
        "status": status,
        "input": {"file": str(pdf), "pages": npages},
        "metadata": {
            "title_guess": paragraphs[0]["text"][:200] if paragraphs else None,
            "title_confidence": "low — derived from first text block, verify on page 1",
        },
        "sections": sections,
        "paragraphs": paragraphs,
        "tables": tables,
        "figures": figures,
        "equations": equations,
        "references": references,
        "removed_running_matter": removed_running,
        "uncertainties": uncertainties,
        "stats": {"pages": npages, "paragraphs": len(paragraphs),
                  "sections": len(sections), "tables": len(tables),
                  "figures": len(figures), "equations": len(equations),
                  "references": len(references), "body_words": n_words},
        "changes": [],
    }
    return result, "\n".join(md_parts), None


def main():
    ap = argparse.ArgumentParser(description="Parse a scientific PDF into structured JSON + Markdown")
    ap.add_argument("pdf", help="path to input PDF")
    ap.add_argument("--out", default=".", help="output directory")
    ap.add_argument("--case-id", default=None, help="case id to embed in result.json")
    args = ap.parse_args()

    pdf = Path(args.pdf)
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    if not pdf.is_file():
        print("error: input not found: %s" % pdf, file=sys.stderr)
        return 1
    if shutil.which("pdftotext") is None:
        print("error: pdftotext (Poppler) not found on PATH; install poppler-utils",
              file=sys.stderr)
        return 1

    log = []
    result, md, fatal = parse_document(pdf, log)
    if fatal:
        print("error: %s" % fatal, file=sys.stderr)
        return 1

    result["runtime"] = {"tool": "pdftotext -bbox-layout (Poppler)",
                         "seconds": round(time.time() - t0, 2)}
    if args.case_id:
        result["case_id"] = args.case_id

    (outdir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (outdir / "fulltext.md").write_text(md or "", encoding="utf-8")
    print("status=%s pages=%s paragraphs=%s sections=%s refs=%s -> %s" % (
        result["status"], result["stats"]["pages"], result["stats"]["paragraphs"],
        result["stats"]["sections"], result["stats"]["references"], outdir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
