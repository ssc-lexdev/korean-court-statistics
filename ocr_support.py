"""Per-value validation paths for every released OCR value (pipeline step after validation_blocks).

For each released value with source_type == 'ocr' in court_panel, detail, duration and pending_observed:
- second_source: 'agree' / 'disagree' if another edition reports the same cell (overlap files), else 'none';
- text_layer: 'zero' for zeros (printed as '-'), 'broken_text' for files with mis-encoded text layers,
  'present' if the value occurs as a numeric string in the PDF text layer of the page(s) it was read
  from, 'absent' if those pages have a text layer with numbers but not this one, 'no_text' if they have none;
  values below 10 are 'present_trivial' when present (a one-digit string occurs on almost any page);
- reread_sample: True if the cell was in a re-reading sample (C1 main or C2 small claims), linked on the full cell key;
- text_layer_position: 'agree' / 'disagree' if the table was rebuilt from the text-layer word coordinates and the
  word at the value's row and column was compared (court_position.py, detail_position.py,
  duration_pdf_position.py), else 'none'.
Presence in the text layer shows that the number is on the page, not its row or column position; the positional
check establishes the position.
Output: data/validation/ocr_value_support.csv (released as validation/ocr_value_support.csv), and
data/validation/title_unverified_blocks.csv: the six 2016-edition detail blocks without printed-title evidence in the
earlier title rule, with their text-layer, second-edition, total-row and positional checks and the title found from
the word coordinates.
"""
import re
from pathlib import Path

import fitz
import pandas as pd

ROOT = Path(__file__).parent
REL = Path(__import__("os").environ.get("SCOURT_RELEASE_OUT", ROOT / "release")) / "data"  # the release built by make_release.py
VAL = REL.parent / "validation"
POS = ROOT / "data" / "validation"
OUT = ROOT / "data" / "validation" / "ocr_value_support.csv"

_text = {}


def page_numbers(src, p0, p1):
    nums, has = set(), False
    for p in range(int(p0), int(p1) + 1):
        k = (src, p)
        if k not in _text:
            doc = fitz.open(ROOT / "data" / src)
            t = doc[p - 1].get_text() if p <= doc.page_count else ""
            _text[k] = set(int(x.replace(",", "")) for x in re.findall(r"\d{1,3}(?:,\d{3})+|\d+", t))
        nums |= _text[k]
        has |= bool(_text[k])
    return nums, has


MANIFEST = pd.read_csv(REL / "source_manifest.csv").set_index("file").text_layer


def tl_status(r):
    if pd.isna(r.page_start) or not str(r.source_file).endswith(".pdf"):
        return "no_text"
    if str(MANIFEST.get(r.source_file, "")).startswith("broken"):
        return "broken_text"  # characters of the text layer are mis-encoded (2015 file 1, 2017, 2019)
    if r.value == 0:
        return "zero"  # zeros are printed as '-' and cannot be matched as numbers
    nums, has = page_numbers(r.source_file, r.page_start, r.page_end if pd.notna(r.page_end) else r.page_start)
    if not has:
        return "no_text"
    if int(r.value) in nums:
        return "present_trivial" if r.value < 10 else "present"
    return "absent"


def second(o, keycols, rel, relkeys):
    """Compare each released value with the other editions' values for the same cell."""
    ed = [c for c in o.columns if c[:4].isdigit()]
    o = o.set_index(keycols)
    out = []
    for k, v, src in zip(rel[relkeys].itertuples(index=False, name=None), rel.value, rel.source):
        if k not in o.index:
            out.append("none"); continue
        row = o.loc[[k]].iloc[0]
        others = [row[c] for c in ed if c != src and pd.notna(row[c])]
        out.append("none" if not others else ("agree" if all(float(x) == float(v) for x in others) else "disagree"))
    return out


def main():
    tables = pd.read_csv(REL / "tables.csv").set_index("table_id").table_ko
    inst = pd.read_csv(REL / "instances.csv").set_index("instance_id").instance_ko
    bins = pd.read_csv(REL / "duration_bins.csv").set_index(["domain_id", "bin_id"]).bin_ko
    cats = pd.read_csv(REL / "categories.csv").set_index("category_id").category_ko
    mets = pd.read_csv(REL / "metrics.csv").set_index("metric_id").metric_ko
    dom_ko = {"civil_main": "민사본안", "family_litigation": "가사소송", "criminal_trial": "형사공판"}
    parts = []

    p = pd.read_csv(REL / "court_panel.csv")
    p = p[p.source_type == "ocr"].copy()
    p["table_ko"] = p.table_id.map(tables)
    p["second_source"] = second(pd.read_csv(VAL / "overlap_court_panel.csv"), ["table", "court_id", "year"],
                                p, ["table_ko", "source_court_id_ko", "year"])
    p["key"] = p.table_id + "|" + p.court_id_h
    parts.append(p.assign(file="court_panel.csv"))

    d = pd.read_csv(REL / "detail.csv")
    d = d[d.source_type == "ocr"].copy()
    d["t_ko"], d["m_ko"] = d.table_id.map(tables), d.metric_id.map(mets)
    od = pd.read_csv(VAL / "overlap_detail.csv")
    res = pd.Series("none", index=d.index)
    # row labels: case categories (총괄 tables) or instances (심급별 tables); the total row is printed 합계 or 총계
    for lab in (d.label_id.map(cats), d.label_id.map(inst), d.label_id.map({"total": "합계"}), d.label_id.map({"total": "총계"})):
        d["l_ko"] = lab
        r = pd.Series(second(od, ["table", "label", "metric", "year"], d, ["t_ko", "l_ko", "m_ko", "year"]), index=d.index)
        res = res.where(res != "none", r)
    d["second_source"] = res
    d["key"] = d.table_id + "|" + d.label_id + "|" + d.metric_id
    parts.append(d.assign(file="detail.csv"))

    u = pd.read_csv(REL / "duration.csv")
    u = u[u.source_type == "ocr"].copy()
    u["d_ko"] = u.domain_id.map(dom_ko)
    u["i_ko"] = u.instance_id.map(inst)
    u["b_ko"] = [bins.get((a, b), b) for a, b in zip(u.domain_id, u.bin_id)]
    u["second_source"] = second(pd.read_csv(VAL / "overlap_duration.csv"), ["domain", "level", "bin", "year"],
                                u, ["d_ko", "i_ko", "b_ko", "year"])
    u["key"] = u.domain_id + "|" + u.instance_id + "|" + u.bin_id
    parts.append(u.assign(file="duration.csv"))

    q = pd.read_csv(REL / "pending_observed.csv")
    q = q[q.source_type == "ocr"].copy()
    rows = []
    for m in ("filings", "dispositions", "pending"):
        x = q.assign(value=q[m], key=q.category_id + "|" + m)
        rows.append(x[x.value.notna()])
    q = pd.concat(rows)
    # overview tables are single-year; filings and dispositions of civil main cases and family litigation are compared
    # with the multi-year detailed tables of other volumes (validate_ocr.pending_vs_nunyeon): civil overall 'main cases'
    # and the sum of the family-litigation instances (Excel from 2016, OCR before)
    dd = pd.read_csv(REL / "detail.csv")
    ref = {("civil_main", y, m): v for y, m, v in
           dd[(dd.table_id == "civil_overall") & (dd.label_id == "main_cases")][["year", "metric_id", "value"]].itertuples(index=False)}
    fam = dd[dd.table_id == "family_litigation_by_instance"].groupby(["year", "metric_id"]).value.sum()
    ref.update({("family_litigation", y, m): v for (y, m), v in fam.items()})
    q["second_source"] = [("agree" if ref[(c, y, m)] == v else "disagree") if (c, y, m) in ref else "none"
                          for c, y, m, v in zip(q.category_id, q.year, q.key.str.split("|").str[1], q.value)]
    parts.append(q.assign(file="pending_observed.csv"))

    a = pd.concat(parts, ignore_index=True)
    a["text_layer"] = [tl_status(r) for r in a.itertuples()]

    # re-reading samples: link each sampled cell to a released value on the full cell key
    # (file, row key, year, source volume); a sampled cell read from a volume that is not the released source is not linked
    tid = {v: k for k, v in tables.items()}
    dom_id = {v: k for k, v in dom_ko.items()}
    inst_id = {v: k for k, v in inst.items()}
    bin_id = {(d, k): b for (d, b), k in bins.items()}
    cat_id = {v: k for k, v in cats.items()}
    met = {"접수": "filings", "처리": "dispositions", "미제": "pending"}
    cid = {}
    for r in p.itertuples():
        cid.setdefault((r.table_id, r.source_court_id_ko), r.court_id_h)
    keys = set()
    for src, df in (("main", pd.read_csv(VAL / "reread_sample_main.csv")),
                    ("small_claims", pd.read_csv(VAL / "reread_sample_small_claims.csv"))):
        for r in df.itertuples():
            ed, y = int(r.source[:4]), int(r.year)
            k = None
            if r.dataset.startswith("court_panel"):
                t = tid.get(r.table)
                c = cid.get((t, getattr(r, "court_id_h", None))) if src == "small_claims" else None  # source court ID (Korean)
                if not isinstance(c, str):
                    for name in ([f"{r.district}/{r.row}", r.row] if isinstance(r.district, str) else [r.row]):
                        c = cid.get((t, name))
                        if c:
                            break
                k = ("court_panel.csv", f"{t}|{c}") if t and c else None
            elif r.dataset == "duration":
                dk, ik = r.table.split("/", 1)
                d = dom_id.get(dk)
                k = ("duration.csv", f"{d}|{inst_id.get(ik)}|{bin_id.get((d, r.row))}") if d else None
            elif r.dataset.startswith("pending"):
                c = next((cat_id[w] for w in r.table.split()[:1] if w in cat_id), None)
                m = met.get(str(r.row).split("/")[-1])
                k = ("pending_observed.csv", f"{c}|{m}") if c and m else None
            if k:
                keys.add((k[0], k[1], y, ed))
    a["reread_sample"] = [(f, k, int(y), int(e)) in keys for f, k, y, e in zip(a.file, a.key, a.year, a.source_edition)]
    # positional checks against the text-layer word coordinates
    pos = {}
    for f, name, kc in (("court_panel.csv", "court_position_check.csv", ["table_id", "court_id_h"]),
                        ("detail.csv", "detail_position_check.csv", ["table_id", "label_id", "metric_id"]),
                        ("duration.csv", "duration_pdf_position_check.csv", ["domain_id", "instance_id", "bin_id"])):
        c = pd.read_csv(POS / name)
        for r in c.itertuples():
            k = "|".join(str(getattr(r, x)) for x in kc)
            pos[(f, k, int(r.year), int(r.source_edition))] = "agree" if r.position_agrees else "disagree"
    a["text_layer_position"] = [pos.get((f, k, int(y), int(e)), "none")
                                for f, k, y, e in zip(a.file, a.key, a.year, a.source_edition)]
    a["n_paths"] = ((a.second_source == "agree").astype(int) + (a.text_layer == "present").astype(int)
                    + a.reread_sample.astype(int) + (a.text_layer_position == "agree").astype(int))
    cols = ["file", "key", "year", "value", "source_edition", "source_file", "source_locator",
            "second_source", "text_layer", "reread_sample", "text_layer_position", "n_paths"]
    a = a[cols].sort_values(["file", "key", "year"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    a.to_csv(OUT, index=False, encoding="utf-8")
    print(f"ocr_value_support.csv: {len(a)} OCR values, "
          f"{int((a.second_source == 'agree').sum())} agree with another volume, "
          f"{int(a.reread_sample.sum())} re-read, {int((a.text_layer_position == 'agree').sum())} agree by position "
          f"({int((a.text_layer_position == 'disagree').sum())} disagree), {int((a.n_paths == 0).sum())} with no path")


PARTS = {"civil_overall": ["main_cases", "non_main_cases"],
         "family_overall": ["litigation", "non_contentious", "conciliation", "applications"],
         "criminal_overall": ["trial", "summary_order", "summary_trial", "other"],
         "civil_by_instance": ["first_instance", "appeal", "supreme_court"]}


def title_unverified_blocks():
    t = pd.read_csv(REL / "source_tables.csv")
    a = pd.read_csv(OUT)
    d = pd.read_csv(REL / "detail.csv")
    w = d[d.source_edition == 2016].pivot_table(index=["table_id", "metric_id", "year"], columns="label_id",
                                                values="value").reset_index()
    pc = pd.read_csv(POS / "detail_position_check.csv")
    rows = []
    for r in t[t.title_evidence == "title rule not matched in text layer"].itertuples():
        pp = pc[(pc.table_id == r.key) & (pc.source_edition == 2016)]
        x = a[(a.file == "detail.csv") & (a.source_edition == 2016) & a.key.str.startswith(r.key + "|")]
        o = t[(t.key == r.key) & (t.source_edition == 2011)].iloc[0]
        if r.key in PARTS:
            g = w[w.table_id == r.key]
            arith = f"total = sum of rows in {int((g[PARTS[r.key]].sum(axis=1) == g.total).sum())}/{len(g)} metric-years"
        else:
            arith = "no printed total row"
        rows.append(dict(table_id=r.key, source_edition=2016, source_file=r.source_file, location_span=r.location_span,
                         released_values=len(x), years=f"{x.year.min()}-{x.year.max()}",
                         text_layer_present=int((x.text_layer == "present").sum()),
                         second_edition_cells=int((x.second_source != "none").sum()),
                         second_edition_agree=int((x.second_source == "agree").sum()),
                         comparator="2011 edition (OCR), statistical years 2007-2011",
                         comparator_title_evidence=o.title_evidence, arithmetic_check=arith,
                         title_from_word_coordinates=pp.title_in_text_layer.iloc[0],
                         position_agree=int(pp.position_agrees.sum()),
                         note="the title and the row and column of every value were confirmed from the text-layer "
                              "word coordinates (detail_position.py); the earlier title rule failed because the "
                              "reading order of the text layer is scrambled"))
    pd.DataFrame(rows).to_csv(OUT.parent / "title_unverified_blocks.csv", index=False, encoding="utf-8")
    print(f"title_unverified_blocks.csv: {len(rows)} blocks")


if __name__ == "__main__":
    main()
    title_unverified_blocks()
