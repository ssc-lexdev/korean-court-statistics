"""Build 2002–2025 long-run time-series CSVs from the multi-year comparison tables.

Sources (for overlapping years the most recent source wins; overlaps are checked for agreement):
  - 2025 multi-year comparison Excel : 2016–2025
  - 2016 multi-year comparison PDF   : 2007–2016
  - 2011 multi-year comparison PDF   : 2002–2011
  - 2006 multi-year comparison PDF   : 1997–2006 (includes observed pending counts)
Outputs: data/series/
  - long_series.csv   (year, category, level, metric, value, source, derived)
  - wide_series.csv   (year × indicator)
  - overlap_check.csv (comparison of values for years covered by more than one source)
"""
import glob
import logging
import re
from pathlib import Path

import openpyxl
import pandas as pd
import pdfplumber

logging.disable(logging.WARNING)
BASE = Path(__file__).parent / "data"
OUT = BASE / "series"
OUT.mkdir(exist_ok=True)
Y0, Y1 = 2002, 2025

# section label (matched after removing whitespace) -> (category, level)
LABELS = {
    "총계": ("전체사건", "총계"),
    "본안사건": ("본안사건", "전심급"),
    "본안외사건": ("본안외사건", "전심급"),
    "비송사건": ("비송사건", "전심급"),
    "제1심": ("본안사건", "제1심"),
    "고등법원": ("본안사건", "항소심-고등법원"),
    "지방법원": ("본안사건", "항소심-지방법원"),
    "상고심": ("본안사건", "상고심"),
}
NUM = r"[\d,]+"


def norm(s):
    return re.sub(r"\s+", "", str(s or "")).replace("１", "1")


def rel(f):
    import os
    return os.path.relpath(str(f), str(BASE)).replace("\\", "/")


# ---------------- Excel (2025) ----------------
def from_excel():
    f = glob.glob(str(BASE / "xlsx/2025/*누년*/*01항.전체사건.xlsx"))[0]
    ws = openpyxl.load_workbook(f, data_only=True).worksheets[0]
    rows, cur = [], None
    for ri, r in enumerate(ws.iter_rows(values_only=True), 1):
        a = r[0]
        if isinstance(a, str) and norm(a) in LABELS:
            cur = LABELS[norm(a)]
        elif isinstance(a, (int, float)) and cur and r[1] is not None:
            for m, v in (("접수", r[1]), ("처리", r[2])):
                rows.append((int(a), *cur, m, float(v), "2025_xlsx", rel(f), f"{ws.title}!r{ri}"))
    return rows


# ---------------- PDF ----------------
def parse_text(text, src, with_pending=False, file="", page=""):
    rows, cur = [], None
    for line in text.splitlines():
        n = norm(line)
        hit = [k for k in LABELS if n == k or n.startswith(k) and not re.search(r"\d{4}", n)]
        if hit:
            cur = LABELS[max(hit, key=len)]
            continue
        m = re.match(rf"\s*((?:19|20)\d\d)\s+({NUM})\s+({NUM})(?:\s+({NUM}))?", line)
        if m and cur:
            y = int(m.group(1))
            vals = [m.group(2), m.group(3)] + ([m.group(4)] if with_pending and m.group(4) else [])
            for met, v in zip(("접수", "처리", "미제"), vals):
                rows.append((y, *cur, met, float(v.replace(",", "")), src, file, page))
    return rows


def from_pdf(year, with_pending=False):
    p = glob.glob(str(BASE / f"raw/{year}/pdf/*추이*.pdf"))[0]
    rows = []
    with pdfplumber.open(p) as pdf:
        for i in range(1, 5):
            pg = pdf.pages[i]
            t = pg.extract_text() or ""
            if "총" not in norm(t) or "괄" not in norm(t):
                continue
            # p1: summary table (single column). Next page: by instance (use the left column only)
            rows += parse_text(t, f"{year}_pdf", with_pending, rel(p), f"p{i + 1}")
            nxt = pdf.pages[i + 1]
            left = nxt.crop((0, 0, nxt.width / 2, nxt.height)).extract_text() or ""
            rows += parse_text(left, f"{year}_pdf", with_pending, rel(p), f"p{i + 2} (left column)")
            break
    return rows


def main():
    cols = ["year", "category", "level", "metric", "value", "source", "source_file", "source_page"]
    df = pd.DataFrame(from_excel() + from_pdf(2016) + from_pdf(2011) + from_pdf(2006, True), columns=cols)
    df = df.drop_duplicates(["year", "category", "level", "metric", "source"])

    # overlap check
    piv = df.pivot_table(index=["category", "level", "metric", "year"], columns="source", values="value")
    ov = piv[piv.notna().sum(axis=1) > 1].copy()
    ov["일치"] = ov.nunique(axis=1) == 1
    ov.to_csv(OUT / "overlap_check.csv", encoding="utf-8-sig")

    # priority: most recent source
    pri = {"2025_xlsx": 0, "2016_pdf": 1, "2011_pdf": 2, "2006_pdf": 3}
    df["p"] = df.source.map(pri)
    best = (df.sort_values("p").drop_duplicates(["year", "category", "level", "metric"])
              .drop(columns="p").query("@Y0 <= year <= @Y1"))
    best["derived"] = False

    # pending: derive 2007 onward from the observed 2006 value via the stock-flow identity
    # (pending_t = pending_{t-1} + filed_t - disposed_t)
    add = []
    for (c, l), g in best.groupby(["category", "level"]):
        w = g.pivot(index="year", columns="metric", values="value")
        if "미제" not in w.columns or 2006 not in w.index or pd.isna(w.loc[2006, "미제"]):
            continue
        stock = w.loc[2006, "미제"]
        for y in range(2007, Y1 + 1):
            if y not in w.index:
                break
            stock = stock + w.loc[y, "접수"] - w.loc[y, "처리"]
            add.append((y, c, l, "미제", stock, "산출(2006미제+누적순증)", "", "", True))
    best = pd.concat([best, pd.DataFrame(add, columns=cols + ["derived"])])
    best = best.sort_values(["category", "level", "metric", "year"])
    best["year"] = best.year.astype(int)
    best.to_csv(OUT / "long_series.csv", index=False, encoding="utf-8-sig")

    wide = best.pivot_table(index="year", columns=["category", "level", "metric"], values="value")
    wide.columns = ["_".join(c) for c in wide.columns]
    wide.to_csv(OUT / "wide_series.csv", encoding="utf-8-sig")

    print(best.groupby(["category", "level", "metric"]).year.agg(["min", "max", "count"]).to_string())
    print("\n겹침 검증:", int(ov["일치"].sum()), "/", len(ov), "일치")
    if (~ov["일치"]).any():
        print(ov[~ov["일치"]].to_string())


if __name__ == "__main__":
    main()
