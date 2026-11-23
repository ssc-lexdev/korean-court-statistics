"""Positional check of the OCR values of the court panel against the PDF text layer.

Each court-panel table of the 2006, 2011 and 2016 editions prints one court per row and one year per column. The
text layer of these editions is readable but its reading order is scrambled, so this script rebuilds the table
from word coordinates: the year header gives the columns (each number is assigned to the header whose horizontal
centre is nearest, within 45% of the column spacing), the words left of the first column give the row label, and
the district context of branch, subtotal and Si/Gun rows is the last district court or district-area total printed
above them (carried over from the previous page of the same table), as in the source court identifier of the
release (`source_court_id_ko`). Parsing of a page stops at the title of the next table.
A released value passes only if the text-layer word in its row and year column equals it ('-' read as 0).
Output: data/validation/court_position_check.csv (one row per released OCR value of court_panel.csv).
"""
import re
import sys
from pathlib import Path

import fitz
import pandas as pd

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
from build_courts import nz  # noqa: E402
from detail_position import lines, INT, TITLE  # noqa: E402

REL = Path(__import__("os").environ.get("SCOURT_RELEASE_OUT", ROOT / "release")) / "data"  # the release built by make_release.py
OUT = ROOT / "data" / "validation" / "court_position_check.csv"
YEAR = re.compile(r"^20\d\d$")
DISTRICT = re.compile(r".+(지방법원|가정법원)(\(가정지원\))?$")


def row_id(label, district):
    """Source court identifier of a printed row label, given the current district context."""
    if label in ("합계", "총계"):
        return "전국", district
    if label.endswith("관내합계"):
        d = label[: -len("관내합계")]
        return f"{d}/관내합계", d
    if label.endswith("고등법원") or label == "특허법원" or label.endswith("계") and not label.endswith("소계"):
        return label, district
    if DISTRICT.fullmatch(label):
        d = label.replace("(가정지원)", "")  # family tables print "대전지방법원(가정지원)" for the district court row
        return d, d
    return f"{district}/{label}", district


def parse_page(page, district=None):
    """Return ({(source_court_id_ko, year): value}, problems, district context at the end of the page)."""
    ls = lines(page)
    hdr = next(((y, g) for y, g in ls if sum(bool(YEAR.match(w[4])) for w in g) >= 3), None)
    if hdr is None:
        return {}, ["no year header"], district
    cols = [((w[0] + w[2]) / 2, int(w[4])) for w in hdr[1] if YEAR.match(w[4])]
    avg = [w for w in hdr[1] if w[4].startswith(("평", "균"))]
    if avg:
        cols.append(((avg[0][0] + avg[-1][2]) / 2, None))  # the average column (평균 / 평 균); not released
    tol = 0.45 * min(b[0] - a[0] for a, b in zip(cols, cols[1:]))
    x0 = min(w[0] for w in hdr[1] if YEAR.match(w[4])) - 5
    out, probs = {}, []
    for y, g in ls:
        if y <= hdr[0]:
            continue
        if TITLE.match(nz(g[0][4])):  # the next table on the page begins
            break
        label = nz("".join(w[4] for w in g if w[0] < x0 and not INT.match(w[4])))
        nums = [w for w in g if w[0] >= x0 and INT.match(w[4])]
        if not label or not nums:
            continue
        rid, district = row_id(label, district)
        for w in nums:
            xc = (w[0] + w[2]) / 2
            c = min(cols, key=lambda c: abs(c[0] - xc))
            if abs(c[0] - xc) > tol:
                probs.append(f"{label}: {w[4]} at x={xc:.0f} has no column")
                continue
            if c[1] is not None:
                out[(rid, c[1])] = 0.0 if w[4] in "-－" else float(w[4].replace(",", ""))
    return out, probs, district


def main():
    c = pd.read_csv(REL / "court_panel.csv")
    x = c[c.source_type == "ocr"]
    rows, district = [], {}
    for (ed, f, t, p), g in x.groupby(["source_edition", "source_file", "table_id", "page_start"]):
        page = fitz.open(ROOT / "data" / f)[int(p) - 1]
        # continuation pages of a table start inside the district printed last on the previous page
        vals, probs, district[(ed, t)] = parse_page(page, district.get((ed, t)))
        for pr in probs[:5]:
            print(f"  {int(ed)} p{int(p)}: {pr}")
        for r in g.itertuples():
            tv = vals.get((r.source_court_id_ko, int(r.year)))
            rows.append(dict(table_id=r.table_id, court_id_h=r.court_id_h, source_court_id_ko=r.source_court_id_ko,
                             year=r.year, value=r.value, source_edition=int(ed), source_file=f, page=int(p),
                             correction_status=r.correction_status, text_layer_value=tv,
                             position_agrees=tv is not None and tv == r.value))
    o = pd.DataFrame(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    o.to_csv(OUT, index=False, encoding="utf-8")
    print(f"court_position_check.csv: {len(o)} values, {int(o.position_agrees.sum())} agree by position, "
          f"{int(o.text_layer_value.isna().sum())} not located")
    print(o.groupby(["source_edition", "table_id"]).agg(n=("value", "size"), agree=("position_agrees", "sum"),
                                                       located=("text_layer_value", "count")).to_string())
    bad = o[~o.position_agrees]
    if len(bad):
        print(bad[["source_edition", "table_id", "source_court_id_ko", "year", "value", "text_layer_value",
                   "page"]].to_string())


if __name__ == "__main__":
    main()
