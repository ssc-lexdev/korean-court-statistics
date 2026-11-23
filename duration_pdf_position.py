"""Positional check of the OCR values of the PDF duration tables against the PDF text layer.

The duration tables of the 2006, 2011 and 2016 editions were read from page images (build_duration.py). Their
text layers are readable but scrambled in reading order, so this script rebuilds each table from word coordinates:
the column header gives the total, bin ('이내'/'초과') and mean columns; section headings (제1심, 항소심, 상고심) and
level labels (합의, 단독, 고법, 지법, ...) at the left give the instance; the year of a row is its own year label or,
where the year cell is merged over several rows, the nearest year label of the same section (earlier on ties), as
in duration_position.py for the Excel tables. Integers are assigned to the total or bin column with the nearest
horizontal centre; decimals are the printed mean. Rows labelled 평균 (average) and parenthesized share rows are
skipped. A released value passes only if the text-layer word at its (year, instance, bin) position equals it.
Output: data/validation/duration_pdf_position_check.csv (one row per released OCR value of duration.csv).
"""
import re
import sys
from pathlib import Path

import fitz
import pandas as pd

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
from build_courts import nz  # noqa: E402
from detail_position import lines, TITLE  # noqa: E402
from duration_position import INSTANCE  # noqa: E402

REL = Path(__import__("os").environ.get("SCOURT_RELEASE_OUT", ROOT / "release")) / "data"  # the release built by make_release.py
OUT = ROOT / "data" / "validation" / "duration_pdf_position_check.csv"
NUM = re.compile(r"^(\d{1,3}(,\d{3})*|-|－)$")
DEC = re.compile(r"^\d+\.\d+$")
TITLES = {"civil_main": r"민사본안사건처리기간별누년비교표", "family_litigation": r"가사(소송)?사건처리기간별누년비교표",
          "criminal_trial": r"형사공판사건처리기간별누년비교표"}
SECTION = [(r"제1?심", "first"), (r"항소심", "appeal"), (r"상고심", "supreme")]
LEVEL = [(r"합의", "collegiate"), (r"단독", "single"), (r"고법|고등법원", "high"), (r"지법|지방법원", "district")]


def header_cols(hl, nbins):
    """Column centres from the header lines: [('total', x), (bin index, x)..., ('mean', x)]."""
    bins, tot, mean = [], None, None
    pairs = []
    for _, g in hl:  # pair split characters within the same line only
        ws = sorted(g, key=lambda w: w[0])
        pairs += [(w, ws[i + 1] if i + 1 < len(ws) else None) for i, w in enumerate(ws)]
    for w, nxt in pairs:
        t = w[4]
        if t in ("이내", "초과"):
            bins.append((w[0] + w[2]) / 2)
        elif t in ("이", "초") and nxt and nxt[4] in ("내", "과") and nxt[0] - w[2] < 15:
            bins.append((w[0] + nxt[2]) / 2)
        elif t in ("합계", "합") and tot is None:
            end = nxt[2] if t == "합" and nxt and nxt[4] == "계" else w[2]
            tot = (w[0] + end) / 2
        elif "평균" in t:
            mean = (w[0] + w[2]) / 2
    bins = sorted(set(round(b, 1) for b in bins))
    if len(bins) != nbins or tot is None:
        return None
    return [("total", tot)] + [(k, x) for k, x in enumerate(bins)] + [("mean_months", mean)]


def parse(doc, pages, dom, bin_ids):
    vals, probs = {}, []
    cols, active, section, sub = None, False, None, None
    rows, years, orphans = [], [], []  # rows: (page, y, section, level, year or None, words)
    for pn in pages:
        ls = lines(doc[pn - 1])
        hdr_lines = []
        for y, g in ls:
            if y < 62:  # running page header (page number, chapter and section titles)
                continue
            text = nz("".join(w[4] for w in g))
            if re.search(TITLES[dom], text):
                active = True
                continue
            if TITLE.match(nz(g[0][4])) and active:
                active = False  # next table
                break
            if not active:
                continue
            # label area: left of the total column (all words before the header is known)
            bound = cols[0][1] - 25 if cols else 999
            first_x = bound
            left = nz("".join(w[4] for w in g if w[0] < bound))
            if cols is None or (not any(NUM.match(w[4]) for w in g) and ("이내" in text or "이내" in left)):
                hdr_lines.append((y, g))
                c = header_cols(hdr_lines, len(bin_ids))
                if c:
                    cols = c
                continue
            for rx, s in SECTION:
                if re.search(rx, left):
                    section, sub = s, None
            lvl = next((v for rx, v in LEVEL if re.search(rx, left)), None)
            m = re.search(r"(19|20)\d\d", left)
            yr = int(m.group(0)) if m else None
            if yr:
                years.append((pn, y, section, yr))
            nums = [w for w in g if w[0] >= first_x and (NUM.match(w[4]) or DEC.match(w[4]))]
            if "평균" in left or "평" in left and "균" in left:
                # the average rows: their label is placed like a merged year label, so it competes with the years
                years.append((pn, y, section, "average"))
                continue
            if not nums:
                if lvl in ("high", "district") and not yr:
                    sub = lvl  # a sub-heading such as 고등법원
                elif lvl:
                    orphans.append((pn, y, lvl))  # 합의/단독 printed slightly off its number row
                continue
            rows.append((pn, y, section, lvl or sub, yr, nums))
    if cols is None:
        return vals, ["no header"]
    ints = [c for c in cols if c[0] != "mean_months"]
    tol = 0.45 * min(b[1] - a[1] for a, b in zip(ints, ints[1:]))
    for pn, y, sec, lvl, yr, nums in rows:
        if lvl is None:
            near = [o for o in orphans if o[0] == pn and abs(o[1] - y) <= 4.5]
            if near:
                lvl = near[0][2]
        if yr is None:
            cand = [(abs(y - yy_y) + (0 if p == pn else 1000), yy_y, yv) for p, yy_y, s, yv in years if s == sec]
            if not cand:
                probs.append(f"p{pn} y{y:.0f}: no year")
                continue
            yr = min(cand)[2]
        if yr == "average":
            continue
        inst = INSTANCE.get((sec, lvl))
        if inst is None:
            probs.append(f"p{pn} y{y:.0f}: instance {(sec, lvl)}")
            continue
        for w in nums:
            if DEC.match(w[4]):
                vals[(yr, inst, "mean_months")] = float(w[4])
                continue
            xc = (w[0] + w[2]) / 2
            c = min(ints, key=lambda c: abs(c[1] - xc))
            if abs(c[1] - xc) > tol:
                probs.append(f"p{pn} {yr} {inst}: {w[4]} at x={xc:.0f} has no column")
                continue
            b = "total" if c[0] == "total" else bin_ids[c[0]]
            vals[(yr, inst, b)] = 0.0 if w[4] in "-－" else float(w[4].replace(",", ""))
    return vals, probs


def main():
    d = pd.read_csv(REL / "duration.csv")
    bins = pd.read_csv(REL / "duration_bins.csv")
    x = d[d.source_type == "ocr"]
    rows = []
    for (ed, dom, f, loc), g in x.groupby(["source_edition", "domain_id", "source_file", "source_locator"]):
        p0, p1 = (list(map(int, re.findall(r"\d+", loc.split("(")[0]))) * 2)[:2]
        bid = bins[(bins.domain_id == dom) & (bins.bin_type == "count")].sort_values("sort_order").bin_id.tolist()
        vals, probs = parse(fitz.open(ROOT / "data" / f), range(int(p0), int(p1) + 1), dom, bid)
        for pr in probs[:8]:
            print(f"  {ed} {dom}: {pr}")
        for r in g.itertuples():
            tv = vals.get((int(r.year), r.instance_id, r.bin_id))
            ok = tv is not None and (abs(tv - r.value) < 0.05 if r.bin_id == "mean_months" else tv == r.value)
            rows.append(dict(year=r.year, domain_id=dom, instance_id=r.instance_id, bin_id=r.bin_id, value=r.value,
                             source_edition=ed, source_file=f, source_locator=r.source_locator,
                             text_layer_value=tv, position_agrees=bool(ok)))
    o = pd.DataFrame(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    o.to_csv(OUT, index=False, encoding="utf-8")
    print(f"duration_pdf_position_check.csv: {len(o)} values, {int(o.position_agrees.sum())} agree by position, "
          f"{int(o.text_layer_value.isna().sum())} not located")
    print(o.groupby(["source_edition", "domain_id"]).agg(n=("value", "size"), agree=("position_agrees", "sum"),
                                                        located=("text_layer_value", "count")).to_string())
    bad = o[~o.position_agrees & o.text_layer_value.notna()]
    if len(bad):
        print(bad.to_string())


if __name__ == "__main__":
    main()
