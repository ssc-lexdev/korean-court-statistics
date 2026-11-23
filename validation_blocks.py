"""Aggregate validation results by cell, page and block (edition × table) (advisor review, Round 1 #16 and Round 4 #10).

Block = source edition × table. Page = a PDF page sent to the model to read that block (validation/model_calls.jsonl), or
the source page of a sampled cell (the page used for the text-layer comparison or for the re-reading).
Output: data/validation/validation_blocks.csv (summary per check), data/validation/validation_blocks_detail.csv (check × block)
"""
import json
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
VAL, SER = ROOT / "data" / "validation", ROOT / "data" / "series"
import build_courts as bc  # noqa: E402
import build_duration as bd  # noqa: E402
import validate_ocr as vo  # noqa: E402

COURT_TITLE = {v[3]: k for k, v in bc.TABLES.items()}
DUR_TITLE = {v[2]: k for k, v in bd.TABLES.items()}


def block_pages():
    """(edition, table key) → model-read PDF pages, from the call log."""
    pages = {}
    for line in (VAL / "model_calls.jsonl").read_text(encoding="utf-8").splitlines():
        x = json.loads(line)
        if x["model"] != "gpt-5.5" or not x["images"]:
            continue
        q = re.findall(r"'([^']+)'", x["prompt"])
        key = next((COURT_TITLE.get(t) or DUR_TITLE.get(t) for t in q if t in COURT_TITLE or t in DUR_TITLE), None)
        if key is None:
            key = next((t for t in q if "(표" in t), None)  # overview tables
        ed = int(re.search(r"raw/(\d{4})/", x["images"][0]["pdf"]).group(1))
        for im in x["images"]:
            pages.setdefault((ed, key), set()).add(im["page"])
    return pages


def summarize(check, df, block_cols, pages_of, disc_col=None, corrected=0, affected=0, note=""):
    blocks = df.groupby(block_cols)
    det = []
    for b, g in blocks:
        b = b if isinstance(b, tuple) else (b,)
        pg = pages_of(b, g)
        det.append(dict(check=check, block=" | ".join(map(str, b)), cells=len(g), pages=len(pg) if pg is not None else pd.NA,
                        discrepancies=int(g[disc_col].sum()) if disc_col else 0))
    det = pd.DataFrame(det)
    allpages = set()
    for b, g in blocks:
        b = b if isinstance(b, tuple) else (b,)
        pg = pages_of(b, g)
        if pg is not None:
            allpages |= {(b[0], p) for p in pg}
    summ = dict(check=check, cells=len(df), source_pages=len(allpages) or pd.NA, blocks=len(det),
                blocks_with_discrepancy=int((det.discrepancies > 0).sum()), discrepancies=int(det.discrepancies.sum()),
                corrected_in_release=corrected, released_values_affected=affected, note=note)
    return summ, det


def main():
    BP = block_pages()
    ed_of = lambda s: int(re.search(r"(\d{4})", str(s)).group(1))  # noqa: E731
    rows, dets = [], []

    # A. digital comparator (rebuilt with the same function)
    parts = []
    c = vo.compare_overlap(SER / "court_overlap_check.csv", ["table", "court_id", "year"]); c["dataset"] = "court_panel"; c["tkey"] = c.table
    parts.append(c)
    du = vo.compare_overlap(SER / "duration_overlap_check.csv", ["domain", "level", "bin", "year"])
    du = du[du.bin != "평균처리기간(월)"]; du["dataset"] = "duration"; du["tkey"] = du.domain
    parts.append(du)
    pv = vo.pending_vs_nunyeon(); pv["dataset"] = "pending(개황)"; pv["tkey"] = pv.table
    parts.append(pv)
    a = pd.concat(parts, ignore_index=True)
    a["edition"] = a.ocr_source.map(ed_of)
    a["disc"] = a.kind != "exact"

    def pages_bp(b, g):
        ed, ds, key = b
        if ds == "pending(개황)":
            return {p for (e, k), ps in BP.items() if e == ed and k and "(표" in str(k) for p in ps} or None
        return BP.get((ed, key))
    s, d = summarize("A digital comparator", a, ["edition", "dataset", "tkey"], pages_bp, "disc", 0, 0,
                     "6 discrepancies = 4 OCR errors + 2 source-to-source differences; released values come from digital sources")
    rows.append(s); dets.append(d)

    # A2. cross-edition OCR (2011 vs 2016, no digital comparator)
    ov = pd.read_csv(SER / "court_overlap_check.csv")
    xl = [x for x in ov.columns if x.endswith("_xlsx")]
    m = ov["2011_pdf_vision"].notna() & ov["2016_pdf_vision"].notna() & ov[xl].isna().all(axis=1)
    x2 = ov[m].copy()
    x2["disc"] = (x2["2011_pdf_vision"] - x2["2016_pdf_vision"]).abs() >= 0.5
    x2["pair"] = "2011vs2016"
    s, d = summarize("A2 cross-edition OCR", x2, ["pair", "table"],
                     lambda b, g: (BP.get((2011, b[1]), set()) | {p + 10000 for p in BP.get((2016, b[1]), set())}), "disc", 2, 2,
                     "pages = pages of both editions; both discrepancies were 2016 OCR errors, corrected")
    rows.append(s); dets.append(d)

    # B. internal arithmetic (after corrections): block = edition × table; unit of check = subtotal / group / national
    cc = pd.read_csv(SER / "court_checks_after_fixes.csv")
    cc = cc[cc.source.str.contains("vision")].copy()
    cc["edition"] = cc.source.map(ed_of); cc["disc"] = ~cc.ok
    s, d = summarize("B subtotal/group/national checks (OCR, after corrections)", cc, ["edition", "table"],
                     lambda b, g: BP.get((b[0], b[1])), "disc", 0, 0,
                     "unit = one check; failing blocks have their released values from another source (no released value flagged)")
    rows.append(s); dets.append(d)

    # C1 / C2 re-reading samples
    def sample_pages(g):
        out = set()
        for tp, ref in zip(g.tl_pages.fillna(""), g.page_ref.fillna("")):
            out |= {int(p) for p in re.findall(r"p(\d+)", str(tp))}
            out |= {int(p) for p in re.findall(r"_p(\d+)\.png", str(ref))}
        return out
    for check, f in (("C1 re-reading sample (main)", "manual_sample_scored.csv"), ("C2 re-reading sample (small claims)", "soak_sample_scored.csv")):
        sm = pd.read_csv(VAL / f)
        sm["edition"] = sm.source.map(ed_of)
        sm["disc"] = (pd.to_numeric(sm.verified_value, errors="coerce") - sm.ocr_value).abs() >= 0.5
        s, d = summarize(check, sm, ["edition", "table"], lambda b, g: sample_pages(g), "disc", 0, 0,
                         "discrepancy = extracted vs verified value; C2 row-label error (1 cell) counted separately in the protocol")
        rows.append(s); dets.append(d)

    out = pd.DataFrame(rows)
    out.to_csv(VAL / "validation_blocks.csv", index=False, encoding="utf-8-sig")
    pd.concat(dets, ignore_index=True).to_csv(VAL / "validation_blocks_detail.csv", index=False, encoding="utf-8-sig")
    print(out.drop(columns="note").to_string(index=False))


if __name__ == "__main__":
    main()
