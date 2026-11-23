"""Positional check of the Excel duration values (`excel_llm_structured`).

The model structured the Excel duration blocks (build_duration.py). This script re-reads the same cell blocks with
rules only, assigning each cell its year from the row label, its instance from the section and level labels and its
bin from the column header, and compares the result with every released value from an Excel edition.
A value passes only if the cell at the released (year, instance, bin) position holds the released value, so swapped
cells within a row, swapped rows or a wrong year would fail even when the value occurs in the block.
Output: data/validation/duration_excel_position_check.csv (one row per released Excel duration value).
"""
import re
import sys
from pathlib import Path

import openpyxl
import pandas as pd

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
from build_courts import nz  # noqa: E402

REL = Path(__import__("os").environ.get("SCOURT_RELEASE_OUT", ROOT / "release")) / "data"  # the release built by make_release.py
OUT = ROOT / "data" / "validation" / "duration_excel_position_check.csv"

BIN = {"1월이내": "le_1m", "2월이내": "le_2m", "3월이내": "le_3m", "4월이내": "le_4m", "5월이내": "le_5m",
       "6월이내": "le_6m", "9월이내": "le_9m", "1년이내": "le_12m", "2년이내": "le_24m", "2년초과": "gt_24m",
       "합계": "total", "평균처리기간(월)": "mean_months"}
SECTION = {"제1심": "first", "항소심": "appeal", "상고심": "supreme"}
LEVEL = {"합의": "collegiate", "단독": "single", "고법": "high", "고등법원": "high", "지법": "district",
         "지방법원": "district"}
INSTANCE = {("first", None): "first_instance", ("first", "collegiate"): "first_collegiate",
            ("first", "single"): "first_single", ("appeal", None): "appeal", ("appeal", "high"): "appeal_high_court",
            ("appeal", "district"): "appeal_district_court", ("supreme", None): "supreme_court",
            ("supreme", "collegiate"): "supreme_from_collegiate", ("supreme", "single"): "supreme_from_single"}
YEAR = re.compile(r"^(20\d\d)년?$")


def num(x):
    if isinstance(x, (int, float)):
        return float(x)
    s = nz(x).replace(",", "")
    if s in ("-", "－"):
        return 0.0
    try:
        return float(s)
    except ValueError:
        return None


def parse_block(ws, r0, r1):
    """Return {(year, instance_id, bin_id): (value, cell)} read by rules from rows r0..r1."""
    rows = {i: list(r) for i, r in enumerate(ws.iter_rows(min_row=r0, max_row=r1, values_only=True), start=r0)}
    hdr = next(i for i, r in rows.items() if any(nz(c) == "합계" for c in r) and any("이내" in nz(c) for c in r))
    cols = {j: BIN[nz(c)] for j, c in enumerate(rows[hdr]) if nz(c) in BIN}
    tcol = next(j for j, b in cols.items() if b == "total")
    section, sub = None, None
    main, years = [], []  # main: (row, section, level, year-in-row)
    for i in range(hdr + 1, r1 + 1):
        r = rows.get(i) or []
        cells = [nz(c) for c in r]
        lead = [c for c in cells[:2] if c]
        for c in lead:
            if c in SECTION:
                section, sub = SECTION[c], None
        y = next((int(YEAR.match(c).group(1)) for c in cells[:2] if YEAR.match(c)), None)
        lvl = next((LEVEL[c] for c in cells[:2] if c in LEVEL), None)
        has_total = tcol < len(r) and num(r[tcol]) is not None
        if not has_total:
            if lvl and not y:  # a sub-heading row (e.g. 고등법원) without values
                sub = lvl
            if y:
                years.append((i, section, y))
            continue
        if y:
            years.append((i, section, y))
        if lvl:
            main.append((i, section, lvl, y))
        elif y:
            main.append((i, section, sub, y))
        # numeric rows with neither a level nor a year label are auxiliary rows (the prompt also skipped them)
    out = {}
    for i, sec, lvl, y in main:
        if y is None:  # year label merged over several rows: nearest year label of the same section, earlier on ties
            cand = [(abs(i - j), j, yy) for j, s, yy in years if s == sec]
            y = min(cand)[2]
        inst = INSTANCE[(sec, lvl)]
        for j, b in cols.items():
            v = num(rows[i][j]) if j < len(rows[i]) else None
            if v is not None:
                out[(y, inst, b)] = (v, f"r{i}c{j + 1}")
    return out


def main():
    d = pd.read_csv(REL / "duration.csv")
    x = d[d.extraction_method == "excel_llm_structured"].copy()
    rows = []
    for (f, loc), g in x.groupby(["source_file", "source_locator"]):
        wb = openpyxl.load_workbook(ROOT / "data" / f, data_only=True)
        sh, rr = loc.split("!")
        r0, r1 = (int(v) for v in re.findall(r"\d+", rr))
        grid = parse_block(wb[sh], r0, r1)
        for r in g.itertuples():
            hit = grid.get((int(r.year), r.instance_id, r.bin_id))
            ok = hit is not None and (abs(hit[0] - r.value) < 0.005 if r.bin_id == "mean_months" else hit[0] == r.value)
            rows.append(dict(year=r.year, domain_id=r.domain_id, instance_id=r.instance_id, bin_id=r.bin_id,
                             value=r.value, source_edition=r.source_edition, source_file=f, source_locator=loc,
                             rule_cell=hit[1] if hit else "", rule_value=hit[0] if hit else None,
                             position_agrees=bool(ok)))
    o = pd.DataFrame(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    o.to_csv(OUT, index=False, encoding="utf-8")
    print(f"duration_excel_position_check.csv: {len(o)} values, {int(o.position_agrees.sum())} agree by position")
    bad = o[~o.position_agrees]
    if len(bad):
        print(bad.to_string())


if __name__ == "__main__":
    main()
