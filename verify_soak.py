"""Separate sample verification of the OCR values from the small-claims extension (2026-11-18), kept apart from the
existing 295-cell sample (manual_sample.csv).

Target: court_panel_long.csv rows with table=='민사본안_1심_소액' (civil main cases, first instance, small claims) &
  source_type=='ocr' (2006/2011/2016 PDF editions, 2002–2014).
Sample: edition (3) × unit type (main court / branch / si-gun court / total or area total) = 12 strata × 5 cells = 60
  (seed 20261118) + all cells with value 0.
Stage 1 (`python verify_soak.py`): in the PDF text layer (PyMuPDF word coordinates → rebuilt rows), find the number in
  the same parent-court block, row label and year column and compare it with the OCR value
  → tl_pages, tl_value, tl_status (match/mismatch/not_found).
  Cells other than match go to data/validation/visual_queue_soak.csv (with page image paths) → Claude visual reading
  (without seeing the OCR value).
Stage 2 (`python verify_soak.py merge`): apply visual_reads_soak.csv (id, visual_value, visual_note)
  → verified_value, verifier, error rate.
Output: data/validation/soak_sample.csv
"""
import glob
import re
import sys
from pathlib import Path

import fitz
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from vision_util import page_png  # noqa: E402

BASE = Path(__file__).parent / "data"
VAL = BASE / "validation"
OUT = VAL / "soak_sample.csv"
TABLE = "민사본안_1심_소액"
PAGES = (10, 11, 12, 13)  # the small-claims table is on pp. 10–13 in all of the 2006, 2011 and 2016 editions
SEED = 20261118
NUM = re.compile(r"^(-|\d{1,3}(?:,\d{3})+|\d+)$")


def nz(s):
    return re.sub(r"\s+", "", str(s or ""))


def fam(s):
    return re.sub(r"\(.*?\)", "", nz(s)).replace("가정법원", "지방법원")


def pdf_of(ed):
    return glob.glob(str(BASE / f"raw/{ed}/pdf/*추이*.pdf"))[0]


def page_rows(f, p):
    """Rebuild rows from word coordinates → [(label, [nums])]. A numbers-only row and a label-only row (misaligned
    line break) are merged."""
    pg = fitz.open(f)[p - 1]
    # Drop standalone `절` (section) words so the page-edge index tab (vertical `제2절`, "Section 2") does not attach
    # to labels (no court name contains `절`)
    ws = sorted((w for w in pg.get_text("words") if w[4] != "절"),
                key=lambda w: ((w[1] + w[3]) / 2, w[0]))
    lines, cur, cy = [], [], None
    for w in ws:
        y = (w[1] + w[3]) / 2
        if cy is None or abs(y - cy) > 2.5:
            if cur:
                lines.append(sorted(cur, key=lambda w: w[0]))
            cur, cy = [w], y
        else:
            cur.append(w)
    if cur:
        lines.append(sorted(cur, key=lambda w: w[0]))
    out = []
    for ln in lines:
        toks = [w[4] for w in ln]
        lab = nz("".join(t for t in toks if not NUM.match(t)))
        nums = [0 if t == "-" else int(t.replace(",", "")) for t in toks if NUM.match(t)]
        out.append([lab, nums])
    merged = []
    i = 0
    while i < len(out):
        lab, nums = out[i]
        if nums and not lab and i + 1 < len(out) and out[i + 1][0] and not out[i + 1][1]:
            merged.append([out[i + 1][0], nums]); i += 2; continue
        if lab and not nums and i + 1 < len(out) and out[i + 1][1] and not out[i + 1][0]:
            merged.append([lab, out[i + 1][1]]); i += 2; continue
        merged.append([lab, nums]); i += 1
    return merged


_tl = {}


def text_table(ed):
    """Read the whole edition (pp. 10–13) in order → [(page, district_ctx, label, {year: value})]."""
    if ed in _tl:
        return _tl[ed]
    import build_courts as bc
    f = pdf_of(ed)
    res, years, district = [], None, None
    for p in PAGES:
        for lab, nums in page_rows(f, p):
            ys = [n for n in nums if 1990 < n < 2100]
            if len(ys) >= 4 and len(ys) >= len(nums) - 1:
                years = ys
                continue
            if not lab or not years or len(nums) < len(years):
                continue
            lab = bc.fix_label(lab)
            if lab.endswith("관내합계"):
                district = lab[:-4]
            elif re.search(r"(지방법원|가정법원)$", lab):
                if district is None or fam(district) != fam(lab):
                    district = lab
            res.append((p, district, lab, dict(zip(years, nums))))
    _tl[ed] = res
    return res


def tl_check(r):
    ed = int(r.source[:4])
    want = nz(r.court)
    cands = []
    for p, dctx, lab, vals in text_table(ed):
        if int(r.year) not in vals:
            continue
        if r.unit_type == "national_total":
            ok = lab in ("총계", "합계")
        elif r.unit_type == "district_total":
            ok = lab.endswith("관내합계") and fam(lab[:-4]) == fam(r.district)
        elif r.unit_type == "main_court":
            ok = fam(lab) == fam(want)
        else:
            ok = lab == want and dctx is not None and fam(dctx) == fam(r.district)
        if ok:
            cands.append((vals[int(r.year)], p))
    if not cands:
        return None, None, "not_found"
    hit = [c for c in cands if abs(c[0] - r.value) < 0.5]
    v, p = hit[0] if hit else cands[0]
    return v, p, "match" if hit else "mismatch"


def draw():
    d = pd.read_csv(BASE / "series/court_panel_long.csv")
    s = d[(d.table == TABLE) & (d.source_type == "ocr")].copy()
    s["utype"] = s.unit_type.replace({"national_total": "total", "district_total": "total"})
    s["stratum"] = s.source.str[:4] + "|" + s.utype
    pick = s.groupby("stratum", group_keys=False).apply(lambda g: g.sample(min(5, len(g)), random_state=SEED))
    zeros = s[(s.value == 0) & ~s.index.isin(pick.index)]
    pick = pd.concat([pick, zeros])
    out = pd.DataFrame({
        "id": range(1, len(pick) + 1), "dataset": "court_panel_soak", "source": pick.source.values,
        "table": TABLE, "row": pick.court.values, "district": pick.district.values, "year": pick.year.values,
        "ocr_value": pick.value.values, "stratum": pick.stratum.values, "unit_type": pick.unit_type.values,
        "court_id_h": pick.court_id_h.values})
    print(f"모집단 {len(s)}셀 → 표본 {len(out)}셀 (0값 추가 {len(zeros)})")
    return out


def stage1():
    s = draw()
    res = [tl_check(r.rename({"row": "court", "ocr_value": "value"})) for _, r in s.iterrows()]
    s["tl_value"] = [x[0] for x in res]
    s["tl_pages"] = [f"p{x[1]}" if x[1] else "" for x in res]
    s["tl_status"] = [x[2] for x in res]
    s["page_ref"] = [f"{r.source[:4]}_p{int(x[1]):03d}.png" if x[1] else " ".join(f"{r.source[:4]}_p{p:03d}.png" for p in PAGES)
                     for (_, r), x in zip(s.iterrows(), res)]
    s.to_csv(OUT, index=False, encoding="utf-8-sig")
    print(s.groupby(["stratum", "tl_status"]).size().unstack(fill_value=0).to_string())
    q = s[s.tl_status != "match"].copy()
    pdir = VAL / "pages"
    names = []
    for _, r in q.iterrows():
        ed = int(r.source[:4])
        pp = [int(r.tl_pages[1:])] if r.tl_pages else list(PAGES)
        nm = []
        for p in pp:
            png = pdir / f"{ed}_ny_p{p:03d}.png"
            if not png.exists():
                png.write_bytes(page_png(pdf_of(ed), p))
            nm.append(png.name)
        names.append(" ".join(nm))
    q["visual_pages"] = names
    q.drop(columns=["ocr_value", "tl_value"]).to_csv(VAL / "visual_queue_soak.csv", index=False, encoding="utf-8-sig")
    print(f"\n시각 판독 대상 {len(q)}셀 → visual_queue_soak.csv (OCR 값·텍스트 값 제외, blind)")


def merge():
    from validate_ocr import wilson
    s = pd.read_csv(OUT)
    vf = VAL / "visual_reads_soak.csv"
    v = pd.read_csv(vf, encoding="utf-8-sig") if vf.exists() else pd.DataFrame(columns=["id", "visual_value", "visual_note"])
    s = s.drop(columns=[c for c in ("visual_value", "visual_note", "verified_value", "verifier") if c in s]).merge(v, on="id", how="left")
    s["verified_value"] = s.tl_value.where(s.tl_status == "match", s.visual_value)
    s["verifier"] = s.tl_status.map(lambda t: "pdf_text_layer" if t == "match" else None)
    s.loc[s.verifier.isna() & s.visual_value.notna(), "verifier"] = "claude_visual"
    # The row itself does not exist in the source (OCR recorded another row's value under a different label)
    # → counted separately as a cell-level error
    s["label_error"] = s.visual_note.fillna("").str.contains("라벨 오류")
    s.loc[s.label_error, "verifier"] = "claude_visual"
    s.to_csv(OUT, index=False, encoding="utf-8-sig")
    le = int(s.label_error.sum())
    done = s[s.verified_value.notna()]
    err = (done.verified_value - done.ocr_value).abs() >= 0.5
    p, lo, hi = wilson(int(err.sum()), len(done))
    print(s.groupby(["stratum", "verifier"], dropna=False).size().unstack(fill_value=0).to_string())
    print(f"\n값 검증 {len(done)}/{len(s)}셀, 숫자 오류 {int(err.sum())} → {p*100:.2f}% (95% Wilson CI {lo*100:.2f}–{hi*100:.2f}%)")
    p2, lo2, hi2 = wilson(int(err.sum()) + le, len(done) + le)
    print(f"셀 단위(숫자+행 라벨) 오류 {int(err.sum()) + le}/{len(done) + le} → {p2*100:.2f}% (95% CI {lo2*100:.2f}–{hi2*100:.2f}%)")
    for ed in ("2006", "2011", "2016"):
        m = done.source.str.startswith(ed)
        e = int(err[m].sum())
        p, lo, hi = wilson(e, int(m.sum()))
        print(f"  {ed}판: {e}/{int(m.sum())} (CI {lo*100:.2f}–{hi*100:.2f}%)")
    if err.any():
        print(done[err][["id", "source", "row", "district", "year", "ocr_value", "verified_value", "verifier"]].to_string())


if __name__ == "__main__":
    merge() if "merge" in sys.argv[1:] else stage1()
