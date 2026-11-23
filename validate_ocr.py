"""Accuracy validation of the OCR (GPT vision).

A. Digital-source comparison: cell-by-cell comparison of OCR cells whose values also appear in the Excel editions
   (2019–2025) → error rate (95% Wilson CI)
   · court panel (court), disposition time (duration): 2016/2011/2006 PDF OCR vs Excel
   · filings/dispositions in the overview pending tables (pending): OCR vs multi-year comparison filings/dispositions
     (independent source)
B. Internal consistency: pass rate of sum checks on OCR-only values (subtotals, bin sums, stock–flow)
C. Manual verification sample: stratified random sample of OCR-only cells (no digital comparator)
   → data/validation/manual_sample.csv. After a human fills in human_value, `python validate_ocr.py score` computes
   the error rate.
A2. Cross-edition OCR comparison: disagreement rate on cells read by two PDF editions, without a digital source
Outputs: data/validation/ocr_accuracy.csv, ocr_mismatches.csv, ocr_cross_edition*.csv, internal_consistency.csv,
      manual_sample.csv, pages/*.png
Run: python validate_ocr.py            → A, A2, B (safe; keeps the sample)
     python validate_ocr.py c --force  → redraw sample C (⚠ overwrites manual_sample.csv)
"""
import glob
import math
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
BASE = Path(__file__).parent / "data"
SER = BASE / "series"
VAL = BASE / "validation"
VAL.mkdir(exist_ok=True)
SCAN_LIKE = {"2015", "2017"}  # no text layer (scanned) / broken font encoding


def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"),) * 3
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return p, max(0, c - h), min(1, c + h)


def classify(ocr, ref):
    if abs(ocr - ref) < 0.5:
        return "exact"
    so, sr = str(int(round(ocr))), str(int(round(ref)))
    if len(so) == len(sr) and sum(a != b for a, b in zip(so, sr)) == 1:
        return "digit_1"           # one digit misread (e.g. 0↔6)
    if sorted(so) == sorted(sr):
        return "transposition"     # digits transposed
    return "other"                 # row/column/table confusion, etc.


# ------------------------------------------------------------------ A. digital-source comparison
def compare_overlap(path, keys, ocr_tag="_pdf_vision", round_to=None):
    """Compare OCR columns vs Excel columns (latest edition) in an overlap_check.csv-style file (keys + one column per source)."""
    ov = pd.read_csv(path)
    xl = sorted([c for c in ov.columns if c.endswith("_xlsx")], reverse=True)
    oc = [c for c in ov.columns if c.endswith(ocr_tag)]
    rows = []
    for o in oc:
        sub = ov[ov[o].notna()].copy()
        sub["ref"] = sub[xl].bfill(axis=1).iloc[:, 0] if xl else float("nan")
        sub = sub[sub.ref.notna()]
        for _, r in sub.iterrows():
            a, b = r[o], r.ref
            if round_to is not None:
                a, b = round(a, round_to), round(b, round_to)
            rows.append({**{k: r[k] for k in keys}, "ocr_source": o, "ocr": a, "ref": b, "kind": classify(a, b)})
    return pd.DataFrame(rows)


def pending_vs_nunyeon():
    """Filings/dispositions in the OCR overview tables vs the multi-year comparison tables (Excel / multi-year OCR):
    totals for civil main cases and family litigation."""
    p = pd.read_csv(SER / "pending_actual.csv")
    d = pd.read_csv(SER / "detail_long.csv")
    ref = {}
    m = d[(d.table == "민사_총괄") & (d.label == "본안사건")]
    for _, r in m.iterrows():
        ref[("민사본안", r.year, r.metric)] = r.value
    g = d[d.table == "가사소송_심급별"].groupby(["year", "metric"]).value.sum()
    for (y, met), v in g.items():
        ref[("가사소송", y, met)] = v
    rows = []
    for _, r in p[p.source.str.contains("vision")].iterrows():
        for met in ("접수", "처리"):
            k = (r.category, r.year, met)
            if k in ref and pd.notna(r[met]):
                rows.append({"table": r.category, "year": r.year, "metric": met, "ocr_source": r.source,
                             "ocr": r[met], "ref": ref[k], "kind": classify(r[met], ref[k])})
    return pd.DataFrame(rows)


def part_a():
    parts = []
    if (SER / "court_overlap_check.csv").exists():
        c = compare_overlap(SER / "court_overlap_check.csv", ["table", "court_id", "year"])
        c["dataset"] = "court_panel"
        parts.append(c)
    if (SER / "duration_overlap_check.csv").exists():
        du = compare_overlap(SER / "duration_overlap_check.csv", ["domain", "level", "bin", "year"])
        du = du[du.bin != "평균처리기간(월)"]  # exclude decimal rounding differences
        du["dataset"] = "duration"
        parts.append(du)
    pv = pending_vs_nunyeon()
    if len(pv):
        pv["dataset"] = "pending(개황)"
        parts.append(pv)
    a = pd.concat(parts, ignore_index=True)
    a["edition"] = a.ocr_source.str.extract(r"(\d{4})")[0]
    a["pdf_type"] = a.edition.map(lambda e: "scan/broken" if e in SCAN_LIKE else "text-layer")
    a["error"] = a.kind != "exact"
    a[a.error].to_csv(VAL / "ocr_mismatches.csv", index=False, encoding="utf-8-sig")

    res = []
    for keys in (["dataset"], ["dataset", "ocr_source"], ["pdf_type"], []):
        grp = a.groupby(keys) if keys else [(("전체",), a)]
        for k, g in grp:
            k = k if isinstance(k, tuple) else (k,)
            n, e = len(g), int(g.error.sum())
            p, lo, hi = wilson(e, n)
            res.append({"group": " / ".join(map(str, k)) if keys else "전체", "n_cells": n, "errors": e,
                        "error_rate_%": round(p * 100, 3), "ci95_lo_%": round(lo * 100, 3), "ci95_hi_%": round(hi * 100, 3),
                        **{f"n_{t}": int((g.kind == t).sum()) for t in ("digit_1", "transposition", "other")}})
    out = pd.DataFrame(res)
    out.to_csv(VAL / "ocr_accuracy.csv", index=False, encoding="utf-8-sig")
    print("A. 디지털 원본 대조 (OCR 셀 오류율)")
    print(out.to_string(index=False))
    return a


# ------------------------------------------------------------------ B. internal consistency
def part_b():
    rows = []
    cc = pd.read_csv(SER / "court_checks.csv")
    for (s, lv), g in cc[cc.source.str.contains("vision")].groupby(["source", "level"]):
        rows.append(("court 합계검증", f"{s} {lv}", int(g.ok.sum()), len(g)))
    dc = pd.read_csv(SER / "duration_checks.csv")
    for s, g in dc[dc.source.str.contains("vision")].groupby("source"):
        rows.append(("duration 구간합=합계", s, int(g.ok.sum()), len(g)))
    pa = pd.read_csv(SER / "pending_actual.csv")
    core = pa[pa.category.isin(["민사본안", "가사소송", "행정소송", "특허·지식재산", "형사공판"]) & pa.identity_gap_pct.notna()]
    for s, g in core.groupby(core.source.str.contains("vision").map({True: "OCR", False: "Excel"})):
        rows.append(("pending 재고-흐름 |오차|≤2%", s, int((g.identity_gap_pct.abs() <= 2).sum()), len(g)))
    b = pd.DataFrame(rows, columns=["check", "subset", "pass", "n"])
    b["pass_%"] = (b["pass"] / b.n * 100).round(1)
    b.to_csv(VAL / "internal_consistency.csv", index=False, encoding="utf-8-sig")
    print("\nB. 내부 정합성 (OCR 값)")
    print(b.to_string(index=False))


# ------------------------------------------------------------------ C. manual verification sample
def part_c(n_total=300, seed=20261113):
    from build_courts import classify_pages
    from vision_util import page_png
    cp = pd.read_csv(SER / "court_panel_long.csv")
    du = pd.read_csv(SER / "duration_long.csv")
    pa = pd.read_csv(SER / "pending_actual.csv")
    pages = {}
    for ed in (2016, 2011):
        f, found = classify_pages(ed)  # uses the cache
        for k, ps in found.items():
            pages[(f"{ed}_pdf_vision", k)] = (f, sorted(set(ps)))
    frames = []
    o = cp[cp.source.str.contains("vision")]  # values still sourced from OCR in the final panel = no digital comparator
    frames.append(pd.DataFrame({"dataset": "court_panel", "source": o.source, "table": o.table, "row": o.court,
                                "district": o.district, "year": o.year, "ocr_value": o.value}))
    o = du[du.source.str.contains("vision") & (du.bin != "평균처리기간(월)")]
    frames.append(pd.DataFrame({"dataset": "duration", "source": o.source, "table": o.domain + "/" + o.level,
                                "row": o.bin, "district": "", "year": o.year, "ocr_value": o.value}))
    o = pa[pa.source.str.contains("vision")].melt(id_vars=["year", "category", "source", "table"],
                                                  value_vars=["접수", "처리", "미제"], var_name="col", value_name="v")
    frames.append(pd.DataFrame({"dataset": "pending(개황)", "source": o.source, "table": o.category + " " + o.table.fillna(""),
                                "row": "총계/" + o.col, "district": "", "year": o.year, "ocr_value": o.v}))
    pool = pd.concat(frames, ignore_index=True).dropna(subset=["ocr_value"])
    pool["stratum"] = pool.dataset + "|" + pool.source
    # Stratification: at least 10 cells per stratum, the rest proportional to size; scanned/broken editions (2015, 2017) weighted 2x
    w = pool.groupby("stratum").size().astype(float)
    w[w.index.str.contains("2015|2017")] *= 2
    alloc = (w / w.sum() * (n_total - 10 * len(w))).round().astype(int) + 10
    samp = pd.concat([g.sample(min(len(g), alloc[s]), random_state=seed) for s, g in pool.groupby("stratum")])
    samp = samp.sample(frac=1, random_state=seed).reset_index(drop=True)
    samp.insert(0, "id", range(1, len(samp) + 1))

    pdir = VAL / "pages"
    pdir.mkdir(exist_ok=True)
    refs = []
    for _, r in samp.iterrows():
        ed = re.search(r"(\d{4})", r.source).group(1)
        if r.dataset == "court_panel" and (r.source, r.table) in pages:
            f, ps = pages[(r.source, r.table)]
        else:
            f, ps = None, []
        ref = ""
        for p in ps:
            out = pdir / f"{ed}_p{p:03d}.png"
            if not out.exists():
                out.write_bytes(page_png(f, p))
            ref += f"{out.name} "
        refs.append(ref.strip() or f"{ed}년판 PDF — '{r.table}' 표 (data/raw/{ed}/pdf)")
    samp["page_ref"] = refs
    samp["human_value"] = ""
    samp["note"] = ""
    samp.to_csv(VAL / "manual_sample.csv", index=False, encoding="utf-8-sig")
    print(f"\nC. 수기 검증 표본 {len(samp)}셀 → data/validation/manual_sample.csv (쪽 이미지: data/validation/pages/)")
    print(samp.groupby("stratum" if "stratum" in samp else "dataset").size().to_string())


def score():
    s = pd.read_csv(VAL / "manual_sample.csv")
    s = s[s.human_value.notna() & (s.human_value.astype(str).str.strip() != "")]
    s["human_value"] = pd.to_numeric(s.human_value.astype(str).str.replace(",", ""), errors="coerce")
    s["error"] = (s.human_value - s.ocr_value).abs() >= 0.5
    p, lo, hi = wilson(int(s.error.sum()), len(s))
    print(f"수기 검증: {len(s)}셀 중 오류 {int(s.error.sum())} → {p*100:.2f}% (95% CI {lo*100:.2f}–{hi*100:.2f}%)")
    print(s.groupby("dataset").error.agg(["sum", "count"]).to_string())
    s[s.error].to_csv(VAL / "manual_errors.csv", index=False, encoding="utf-8-sig")


def part_a2():
    """A2. Cross-edition OCR comparison: court-panel cells with no digital source that were read by OCR in two PDF editions."""
    ov = pd.read_csv(SER / "court_overlap_check.csv")
    xl = [c for c in ov.columns if c.endswith("_xlsx")]
    oc = sorted(c for c in ov.columns if c.endswith("_pdf_vision"))
    rows, mism = [], []
    for i, a in enumerate(oc):
        for b in oc[i + 1:]:
            m = ov[a].notna() & ov[b].notna() & ov[xl].isna().all(axis=1)
            g = ov[m]
            bad = g[(g[a] - g[b]).abs() >= 0.5]
            p, lo, hi = wilson(len(bad), len(g))
            rows.append({"pair": f"{a} vs {b}", "n_cells": len(g), "disagree": len(bad),
                         "rate_%": round(p * 100, 3) if len(g) else None,
                         "ci95_lo_%": round(lo * 100, 3) if len(g) else None, "ci95_hi_%": round(hi * 100, 3) if len(g) else None})
            mism.append(bad[["table", "court_id", "year", a, b]].assign(pair=f"{a} vs {b}"))
    out = pd.DataFrame(rows)
    out.to_csv(VAL / "ocr_cross_edition.csv", index=False, encoding="utf-8-sig")
    pd.concat(mism, ignore_index=True).to_csv(VAL / "ocr_cross_edition_mismatches.csv", index=False, encoding="utf-8-sig")
    print("\nA2. OCR 판 간 교차 대조 (디지털 원본 없는 셀)")
    print(out.to_string(index=False))


if __name__ == "__main__":
    # Default (no argument) = A, A2, B only. C (redrawing the sample) overwrites manual_sample.csv (re-reading and
    # human-verification results), so it runs only via `python validate_ocr.py c --force`.
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "score":
        score()
    elif arg == "c":
        if "--force" not in sys.argv:
            sys.exit("C는 manual_sample.csv(재판독·사람검증 결과)를 덮어씁니다. 정말 실행하려면: python validate_ocr.py c --force")
        part_c()
    else:
        part_a()
        part_a2()
        part_b()
