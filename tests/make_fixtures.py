"""make_fixtures.py — Generate synthetic regression-test PDFs.

All fixtures are synthetic (matplotlib-rendered real text layers, except the
scanned/mixed ones which embed raster images). Ground truth is known by
construction and consumed by run_regression.py. Nothing here is an official
test case of the challenge.

Requires: matplotlib. Output: PDFs next to this script's --out directory.
"""
import argparse
import textwrap
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

SERIF = "serif"


def wrap(t, w=58):
    return textwrap.wrap(t, w)


class PageWriter:
    """Draw text into explicit columns; coordinates in figure fraction."""

    def __init__(self, fig, headers=None, footer_num=None):
        self.fig = fig
        if headers:
            fig.text(0.5, 0.975, headers, ha="center", fontsize=7, family=SERIF)
        if footer_num is not None:
            fig.text(0.5, 0.015, str(footer_num), ha="center", fontsize=8, family=SERIF)

    def text(self, x, y, s, size=8, weight="normal"):
        self.fig.text(x, y, s, fontsize=size, fontweight=weight, family=SERIF)

    def col(self, x, y, lines, dy=0.016, size=8, weight="normal"):
        for ln in lines:
            self.text(x, y, ln, size=size, weight=weight)
            y -= dy
        return y


def new_page(pdf, header=None, num=None):
    fig = plt.figure(figsize=(8.27, 11.69))
    w = PageWriter(fig, header, num)
    return fig, w


# ---------------------------------------------------------------- fixtures

def fx_singlecol(out):
    """Single column, headings, keywords, DOI, references."""
    with PdfPages(out / "singlecol.pdf") as pdf:
        fig, w = new_page(pdf, "Journal of Single Column Studies 2024", 1)
        w.text(0.5, 0.94, "Deep Parsing of Single Column Articles", size=14,
               weight="bold") if False else None
        fig.text(0.5, 0.94, "Deep Parsing of Single Column Articles",
                 ha="center", fontsize=14, fontweight="bold", family=SERIF)
        fig.text(0.5, 0.92, "Alice Example, Bob Sample", ha="center",
                 fontsize=10, family=SERIF)
        fig.text(0.5, 0.905, "Department of Layout Science, Example University",
                 ha="center", fontsize=9, family=SERIF)
        w.text(0.1, 0.87, "Abstract", size=10, weight="bold")
        y = w.col(0.1, 0.852, wrap("Single column articles are the simplest case for "
                                   "reading order restoration. This fixture verifies "
                                   "metadata extraction and heading detection.", 80),
                  size=9)
        y = w.col(0.1, y - 0.01, ["Keywords: layout; parsing; metadata"], size=9)
        y = w.col(0.1, y - 0.01, ["DOI: 10.1234/jscs.2024.0001"], size=9)
        w.text(0.1, y - 0.02, "1 Introduction", size=11, weight="bold")
        y = w.col(0.1, y - 0.04, wrap("A robust parser must not mistake a numbered "
                                      "sentence for a heading. 3 results reported "
                                      "below illustrate this requirement in detail.", 80))
        w.text(0.1, y - 0.02, "2 Discussion", size=11, weight="bold")
        y = w.col(0.1, y - 0.04, wrap("The discussion closes the article and leads "
                                      "into the reference list.", 80))
        w.text(0.1, y - 0.02, "References", size=11, weight="bold")
        w.col(0.1, y - 0.04, ["[1] D. One. Single columns forever. J. Layout, 2020.",
                              "[2] E. Two. Metadata matters. Doc. Eng., 2022."])
        pdf.savefig(fig)
        plt.close(fig)


def fx_twocol(out):
    """Two columns, header/footer, equation, table, figure, references."""
    LX, RX = 0.06, 0.54
    with PdfPages(out / "twocol.pdf") as pdf:
        fig, w = new_page(pdf, "Journal of Synthetic Tests, Vol. 7", 1)
        fig.text(0.5, 0.965, "A Study of Synthetic Layout Parsing for Test Fixtures",
                 ha="center", fontsize=13, fontweight="bold", family=SERIF)
        fig.text(0.5, 0.945, "Jane Doe, John Smith", ha="center", fontsize=10, family=SERIF)
        fig.text(0.5, 0.930, "Department of Testing, Example University",
                 ha="center", fontsize=9, family=SERIF)
        w.text(LX, 0.905, "Abstract", size=10, weight="bold")
        w.col(LX, 0.888, wrap("We present a synthetic two column document used to verify "
                              "reading order restoration, header removal, section detection "
                              "and reference splitting in an automated PDF parsing pipeline.", 70))
        w.text(LX, 0.815, "1 Introduction", size=10, weight="bold")
        y = w.col(LX, 0.795, wrap("Parsing scientific PDFs requires correct reading order. "
                                  "Double column layouts are common in journals and conference "
                                  "proceedings. A naive extraction interleaves lines from "
                                  "adjacent columns and corrupts every downstream task."))
        y = w.col(LX, y - 0.008, wrap("Our pipeline instead recovers column geometry from word "
                                      "bounding boxes and restores the original reading order "
                                      "before any structural analysis is attempted."))
        y = w.col(LX, y - 0.014, ["2 Method"], size=10, weight="bold")
        y = w.col(LX, y - 0.010, ["2.1 Layout extraction"], size=9, weight="bold")
        y = w.col(LX, y - 0.006, wrap("Word boxes are extracted per page. Blocks wider than a "
                                      "threshold split the page into horizontal bands. Within a "
                                      "band the left column precedes the right column."))
        y = w.col(LX, y - 0.008, ["The scoring objective is",
                                  "L = sum_i log p(x_i) + E_0    (1)",
                                  "where p denotes the page model."])
        w.text(RX, 0.815, "2.2 Structure recognition", size=9, weight="bold")
        y = w.col(RX, 0.795, wrap("Numbered headings define the section hierarchy. Captions "
                                  "beginning with Figure or Table are located with regular "
                                  "expressions and recorded with their page and bounding box."))
        y = w.col(RX, y - 0.008, ["Table 1: Parsing accuracy on synthetic data.",
                                  "Method   Order   Structure",
                                  "Naive    0.41    0.55",
                                  "Ours     0.97    0.93"])
        y = w.col(RX, y - 0.008, wrap("Table 1 summarises the comparison. The naive baseline "
                                      "loses nearly half of the reading order decisions."))
        w.col(RX, y - 0.012, ["Figure 1: Overview of the proposed parsing pipeline."])
        fig.text(0.5, 0.03, "Journal of Synthetic Tests, Vol. 7", ha="center", fontsize=7)
        pdf.savefig(fig)
        plt.close(fig)

        fig, w = new_page(pdf, "Journal of Synthetic Tests, Vol. 7", 2)
        w.text(LX, 0.945, "3 Results", size=10, weight="bold")
        y = w.col(LX, 0.925, wrap("On the held out fixture set the pipeline reproduces the "
                                  "original reading order on all double column pages. Headers "
                                  "and footers repeated across pages are removed without "
                                  "touching body text."))
        w.text(LX, y - 0.014, "4 Conclusion", size=10, weight="bold")
        w.col(LX, y - 0.034, wrap("Geometry driven ordering is sufficient for the fixture corpus. "
                                  "Scanned pages are reported as unreadable when no OCR engine is "
                                  "available instead of being filled with guessed text."))
        w.text(RX, 0.945, "References", size=10, weight="bold")
        w.col(RX, 0.925, ["[1] A. Author. Reading order matters. J. Layout, 2019.",
                          "[2] B. Writer. Tables in the wild. Proc. Docs, 2021. "
                          "Extended version with appendices.",
                          "[3] C. Tester. Synthetic fixtures for parsers. Test Press, 2023."])
        pdf.savefig(fig)
        plt.close(fig)


def fx_threecol(out):
    """Three columns of unequal width."""
    C1, C2, C3 = 0.04, 0.37, 0.68
    with PdfPages(out / "threecol.pdf") as pdf:
        fig, w = new_page(pdf, "Transactions on Narrow Columns 2023", 1)
        fig.text(0.5, 0.955, "Three Column Layout Restoration", ha="center",
                 fontsize=13, fontweight="bold", family=SERIF)
        w.text(C1, 0.92, "Abstract", size=9, weight="bold")
        w.col(C1, 0.905, wrap("Narrow three column proceedings are common.", 34), size=7)
        w.text(C1, 0.855, "1 Introduction", size=9, weight="bold")
        w.col(C1, 0.84, wrap("Column one introduces the fixture and its purpose for "
                             "regression testing of multi column reading order.", 34), size=7)
        w.text(C2, 0.92, "2 Middle Column", size=9, weight="bold")
        w.col(C2, 0.905, wrap("The middle column continues the article body with more "
                              "text so that ordering can be checked precisely.", 34), size=7)
        w.text(C3, 0.92, "3 Final Column", size=9, weight="bold")
        w.col(C3, 0.905, wrap("The final column closes the page and lists references.", 34), size=7)
        w.text(C3, 0.80, "References", size=9, weight="bold")
        w.col(C3, 0.785, ["[1] T. Three. Narrow columns. TNC, 2023."], size=7)
        pdf.savefig(fig)
        plt.close(fig)


def fx_mixed_layout(out):
    """Full-width band (big table) interrupting a two-column page."""
    LX, RX = 0.06, 0.54
    with PdfPages(out / "mixedlayout.pdf") as pdf:
        fig, w = new_page(pdf, None, 1)
        fig.text(0.5, 0.955, "Mixed Layout With A Wide Table", ha="center",
                 fontsize=13, fontweight="bold", family=SERIF)
        w.text(LX, 0.925, "1 Introduction", size=10, weight="bold")
        w.col(LX, 0.905, wrap("Left column text before the wide table band.", 52))
        w.text(RX, 0.925, "2 Early Right", size=10, weight="bold")
        w.col(RX, 0.905, wrap("Right column text before the wide band appears here.", 52))
        # full-width band
        y0 = 0.76
        fig.text(0.5, y0, "Table 2: Wide results table spanning both columns.",
                 ha="center", fontsize=9, family=SERIF)
        w.col(0.2, y0 - 0.02, ["Model      Accuracy      Latency",
                               "Alpha      0.91          12ms",
                               "Beta       0.88          9ms"], size=9)
        w.text(LX, y0 - 0.11, "3 After Band", size=10, weight="bold")
        w.col(LX, y0 - 0.13, wrap("Left column text after the wide band resumes here.", 52))
        w.text(RX, y0 - 0.11, "References", size=10, weight="bold")
        w.col(RX, y0 - 0.13, ["[1] W. Wide. Bands and columns. MixPress, 2022."])
        pdf.savefig(fig)
        plt.close(fig)


def fx_table(out):
    """Complex table: two-row header, a spanning row, numeric grid."""
    LX = 0.06
    with PdfPages(out / "table.pdf") as pdf:
        fig, w = new_page(pdf, None, 1)
        fig.text(0.5, 0.95, "Complex Table Fixture", ha="center",
                 fontsize=13, fontweight="bold", family=SERIF)
        w.text(LX, 0.92, "1 Data", size=10, weight="bold")
        y = w.col(LX, 0.90, wrap("The table below has a two row header and a "
                                 "spanning separator row.", 52))
        y = w.col(LX, y - 0.01, ["Table 1: Benchmark results by dataset.",
                                 "Dataset        Metric       Value     Delta",
                                 "               Name         (%)       (pp)",
                                 "News           Acc          91.2      +1.0",
                                 "News           F1           88.4      +0.7",
                                 "All datasets combined",
                                 "Wiki           Acc          93.5      +2.1",
                                 "Wiki           F1           90.1      +1.9"])
        w.col(LX, y - 0.01, wrap("The numbers in the grid are deliberately simple so "
                                 "that cell level accuracy can be measured exactly.", 52))
        w.text(LX, 0.5, "References", size=10, weight="bold")
        w.col(LX, 0.48, ["[1] G. Grid. Tables in print. TabJ, 2021."])
        pdf.savefig(fig)
        plt.close(fig)


def fx_equations(out):
    """Numbered equations incl. multi-line and greek; plus a trap line."""
    LX = 0.06
    with PdfPages(out / "equations.pdf") as pdf:
        fig, w = new_page(pdf, None, 1)
        fig.text(0.5, 0.95, "Equation Extraction Fixture", ha="center",
                 fontsize=13, fontweight="bold", family=SERIF)
        w.text(LX, 0.92, "1 Model", size=10, weight="bold")
        y = w.col(LX, 0.90, wrap("We define the energy as a sum over sites with "
                                 "greek coefficients alpha and beta.", 52))
        y = w.col(LX, y - 0.01, ["E = sum_i alpha_i x_i + beta    (1)"])
        y = w.col(LX, y - 0.01, ["and the coupled system",
                                 "F = G + H",
                                 "G = x^2 - y_0    (2)"])
        y = w.col(LX, y - 0.01, wrap("See also the earlier review (3) for background; "
                                     "this line is prose and must not become an equation.", 52))
        w.text(LX, 0.5, "References", size=10, weight="bold")
        w.col(LX, 0.48, ["[1] Q. Equations. Numbering rituals. MathJ, 2020."])
        pdf.savefig(fig)
        plt.close(fig)


def fx_scanned(out):
    """Image-only page (no text layer)."""
    fig = plt.figure(figsize=(8.27, 11.69), dpi=150)
    fig.text(0.1, 0.9, "Scanned page simulation", fontsize=14)
    fig.text(0.1, 0.85, "This page has no text layer at all.", fontsize=10)
    png = out / "_scan_tmp.png"
    fig.savefig(png)
    plt.close(fig)
    img = plt.imread(png)
    fig = plt.figure(figsize=(8.27, 11.69))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.imshow(img)
    ax.axis("off")
    fig.savefig(out / "scanned.pdf", format="pdf")
    plt.close(fig)
    png.unlink()


def fx_mixedlayer(out):
    """Page 1 text layer, page 2 image-only."""
    with PdfPages(out / "mixedlayer.pdf") as pdf:
        fig, w = new_page(pdf, None, 1)
        fig.text(0.5, 0.95, "Mixed Layer Fixture", ha="center",
                 fontsize=13, fontweight="bold", family=SERIF)
        w.text(0.06, 0.92, "1 Only Text Page", size=10, weight="bold")
        w.col(0.06, 0.90, wrap("This page has a normal text layer. The next page is "
                               "a pure image and must be flagged, while this page "
                               "still parses normally.", 60))
        pdf.savefig(fig)
        plt.close(fig)
        fig = plt.figure(figsize=(8.27, 11.69), dpi=150)
        fig.text(0.1, 0.9, "Image only page", fontsize=14)
        png = out / "_mix_tmp.png"
        fig.savefig(png)
        plt.close(fig)
        img = plt.imread(png)
        fig = plt.figure(figsize=(8.27, 11.69))
        ax = fig.add_axes([0, 0, 1, 1])
        ax.imshow(img)
        ax.axis("off")
        pdf.savefig(fig)
        plt.close(fig)
        png.unlink()


ALL = {
    "singlecol": fx_singlecol,
    "twocol": fx_twocol,
    "threecol": fx_threecol,
    "mixedlayout": fx_mixed_layout,
    "table": fx_table,
    "equations": fx_equations,
    "scanned": fx_scanned,
    "mixedlayer": fx_mixedlayer,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(Path(__file__).parent))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, fn in ALL.items():
        fn(out)
        print("wrote %s.pdf" % name)


if __name__ == "__main__":
    main()
