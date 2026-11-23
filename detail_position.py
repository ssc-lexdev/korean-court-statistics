"""Positional check of the OCR values of the detailed tables against the PDF text layer.

The detailed tables of the 2011 and 2016 editions were read from page images (build_detail.py). Their PDF text
layers are readable, but the reading order is scrambled, so the earlier checks could only establish that each value
occurs on the pages sent. This script rebuilds each table from the word coordinates of the text layer instead:
the printed title is located on the page, year rows are identified by the year labels at the left margin, section
headings (vertical layout) or column-group headers (wide layout) assign the row label, and the integers of each
year row are assigned to (label, filings/dispositions) in left-to-right order. A released value passes only if the
text-layer word at its (title, label, metric, year) position equals it.
Output: data/validation/detail_position_check.csv (one row per released OCR value of detail.csv).
"""
import re
import sys
from pathlib import Path

import fitz
import pandas as pd

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
from build_courts import nz  # noqa: E402

REL = Path(__import__("os").environ.get("SCOURT_RELEASE_OUT", ROOT / "release")) / "data"  # the release built by make_release.py
OUT = ROOT / "data" / "validation" / "detail_position_check.csv"

# title regex (spaces removed); heading -> labels in left-to-right order. A heading is matched against the text of a
# line without a year label; vertical tables have one label per heading, wide tables several.
SPEC = {
    "civil_overall": (r"민사사건누년비교표\(?총괄표", [(r"합계", ["total"]), (r"본안사건", ["main_cases"]),
                                                     (r"본안외사건", ["non_main_cases"])]),
    "civil_by_instance": (r"민사사건누년비교표[－-]심급별",
                          [(r"합계상고심항소심제1심", ["total", "supreme_court", "appeal", "first_instance"])]),
    "civil_main_by_instance": (r"민사본안사건누년비교표[－-]심급별",
                               [(r"제1?심", ["first_instance"]), (r"고등법원", ["appeal_high_court"]),
                                (r"지방법원", ["appeal_district_court"]), (r"상고심", ["supreme_court"])]),
    "family_litigation_by_instance": (r"^(1\.)?가사소송사건누년비교표[－-]심급별",
                                      [(r"제1?심", ["first_instance"]), (r"항소심", ["appeal"]),
                                       (r"상고심", ["supreme_court"])]),
    "family_overall": (r"가사사건누년비교표\(?총괄",
                       [(r"합계(가사)?소송사건", ["total", "litigation"]),
                        (r"(가사)?비송사건조정사건신청사건", ["non_contentious", "conciliation", "applications"])]),
    "criminal_overall": (r"형사사건누년비교표\(?총괄표", [(r"합계", ["total"]), (r"공판사건", ["trial"]),
                                                       (r"약식사건", ["summary_order"]), (r"즉결사건", ["summary_trial"]),
                                                       (r"기타사건", ["other"])]),
    "criminal_trial_by_instance": (r"형사공판사건누년비교표\(?총괄표\(?\)?[－-]심급별",
                                   [(r"제1?심", ["first_instance"]), (r"고등법원", ["appeal_high_court"]),
                                    (r"지방법원", ["appeal_district_court"]), (r"상고심", ["supreme_court"])]),
}
INT = re.compile(r"^(\d{1,3}(,\d{3})*|-|－)$")
YEAR = re.compile(r"^(19|20)\d\d$")
TITLE = re.compile(r"^\d+\.(\D|$)")  # a table number such as "4." as the first word


def lines(page, tol=3):
    """Words of a page grouped into lines (|dy| <= tol), margins excluded; ideographic spaces stripped."""
    ws = [w[:4] + (w[4].strip("　 "),) + tuple(w[5:]) for w in page.get_text("words") if 45 < w[0] < 505]
    ws = sorted((w for w in ws if w[4]), key=lambda w: (w[1], w[0]))
    out = []
    for w in ws:
        if out and abs(w[1] - out[-1][0]) <= tol:
            out[-1][1].append(w)
        else:
            out.append([w[1], [w]])
    return [(y, sorted(g)) for y, g in out]


def parse(doc, pages, title_rx, heads):
    """Return ({(label, metric, year): value}, title line text, problems)."""
    vals, title, probs, active, groups = {}, None, [], False, None
    for pn in pages:
        ls = lines(doc[pn - 1])
        years = [(w[1], int(w[4])) for _, g in ls for w in g if YEAR.match(w[4]) and w[0] < 100]
        ints = [w for _, g in ls for w in g if INT.match(w[4]) and w[0] > 100]
        rowints = {}
        for w in ints:
            near = min(years, key=lambda t: abs(t[0] - w[1]), default=None)
            if near and abs(near[0] - w[1]) <= 5:
                rowints.setdefault(near, []).append(w)
        for y, g in ls:
            text = nz("".join(w[4] for w in g))
            if TITLE.match(nz(g[0][4])) or re.search(title_rx, text):
                if re.search(title_rx, text):
                    active, title = True, text
                    continue
                if active:
                    return vals, title, probs  # next table begins
            if not active:
                continue
            yr = [w for w in g if YEAR.match(w[4]) and w[0] < 100]
            if not yr:
                left = nz("".join(w[4] for w in g if w[0] < 140))
                for rx, labs in heads:
                    if re.fullmatch(rx, left) or (len(labs) > 1 and re.search(rx, text)):
                        groups = labs
                continue
            key = (yr[0][1], int(yr[0][4]))
            nums = sorted(rowints.get(key, []))
            if groups is None:
                probs.append(f"p{pn} {key[1]}: no heading")
                continue
            if len(nums) != 2 * len(groups):
                probs.append(f"p{pn} {key[1]}: {len(nums)} integers for {groups}")
                continue
            for k, w in enumerate(nums):
                v = 0.0 if w[4] in "-－" else float(w[4].replace(",", ""))
                vals[(groups[k // 2], ("filings", "dispositions")[k % 2], key[1])] = v
    return vals, title, probs


def main():
    d = pd.read_csv(REL / "detail.csv")
    x = d[d.source_type == "ocr"]
    rows = []
    for (ed, t, f, p0, p1), g in x.groupby(["source_edition", "table_id", "source_file", "page_start", "page_end"]):
        doc = fitz.open(ROOT / "data" / f)
        vals, title, probs = parse(doc, range(int(p0), int(p1) + 1), *SPEC[t])
        for pr in probs:
            print(f"  {ed} {t}: {pr}")
        for r in g.itertuples():
            tv = vals.get((r.label_id, r.metric_id, int(r.year)))
            rows.append(dict(table_id=t, label_id=r.label_id, metric_id=r.metric_id, year=r.year, value=r.value,
                             source_edition=ed, source_file=f, source_locator=r.source_locator,
                             title_in_text_layer=title or "", text_layer_value=tv,
                             position_agrees=tv is not None and tv == r.value))
    o = pd.DataFrame(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    o.to_csv(OUT, index=False, encoding="utf-8")
    print(f"detail_position_check.csv: {len(o)} values, {int(o.position_agrees.sum())} agree by position")
    print(o.groupby(["source_edition", "table_id"]).agg(n=("value", "size"), agree=("position_agrees", "sum"),
                                                       title=("title_in_text_layer", "first")).to_string())
    bad = o[~o.position_agrees]
    if len(bad):
        print(bad[["source_edition", "table_id", "label_id", "metric_id", "year", "value", "text_layer_value"]].to_string())


if __name__ == "__main__":
    main()
