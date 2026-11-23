"""Finalize the public release (run after the build_* scripts; idempotent).
1) data/source_manifest.csv      228 source files: edition, kind, path, size, SHA-256, download date (file mtime), PDF text-layer status
2) data/validation/correction_log.csv   manual value corrections, label fixes, page overrides, digital-vs-OCR mismatches (machine-readable)
   data/series/structural_breaks.csv    register of structural breaks and definition changes
3) Add provenance/status/flag columns to the series files
   all files: source_edition, extraction_method(excel/pdf_text_layer/pdf_image_vlm/derived), correction_status
   court_panel_long: partial_year, dup_flag      all others: break_flag
Run: python finalize_release.py   (about 1–3 min including the PDF text-layer check)
"""
import hashlib
import re
from datetime import datetime
from pathlib import Path

import fitz
import pandas as pd

BASE = Path(__file__).parent / "data"
SER, VAL = BASE / "series", BASE / "validation"
PORTAL = "https://portal.scourt.go.kr/pgp/index.on?m=PGP442M02&l=N&c=900"
ADDED = ["source_edition", "extraction_method", "correction_status", "partial_year", "dup_flag", "break_flag"]


# ---------------------------------------------------------------- 1. manifest
_OKCH = re.compile(r"[ -~가-힣㄰-㆏　-〿 -⁯←-⋿■-◿＀-￯·一-鿿]")


def text_layer_pages(path):
    """Classify every page (all pages since 2026-11-19; previously a 5-page sample). Per page: fewer than 20 text
    characters = none; share of allowed characters (Hangul, ASCII, CJK, full-width, common symbols) > 0.9 = ok; else broken."""
    try:
        d = fitz.open(path)
    except Exception:
        return dict(pdf_pages=0, pages_text_ok=0, pages_broken=0, pages_no_text=0, text_layer="unreadable")
    c = {"ok": 0, "broken": 0, "none": 0}
    for pg in d:
        ch = re.sub(r"\s", "", pg.get_text())
        c["none" if len(ch) < 20 else ("ok" if len(_OKCH.findall(ch)) / len(ch) > 0.9 else "broken")] += 1
    n = d.page_count
    st = ("text_layer" if c["ok"] >= 0.9 * n else "no_text_layer(scanned)" if c["none"] >= 0.5 * n
          else "broken_encoding" if c["broken"] >= 0.5 * n else "mixed")
    return dict(pdf_pages=n, pages_text_ok=c["ok"], pages_broken=c["broken"], pages_no_text=c["none"], text_layer=st)


def manifest():
    cat = pd.read_csv(BASE / "catalog.csv")
    cat = cat[cat.status == "ok"].copy()
    rows = []
    for _, r in cat.iterrows():
        p = BASE / r.file
        if not p.exists():
            continue
        b = p.read_bytes()
        rows.append({"edition": r.year, "title": r.title, "kind": r.kind, "file": r.file.replace("\\", "/"),
                     "bytes": len(b), "sha256": hashlib.sha256(b).hexdigest(),
                     "downloaded": datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d"),
                     **(text_layer_pages(p) if p.suffix.lower() == ".pdf" else
                        dict(pdf_pages=pd.NA, pages_text_ok=pd.NA, pages_broken=pd.NA, pages_no_text=pd.NA, text_layer="n/a")),
                     "portal": PORTAL,
                     "retrieval": f"portal listing row '{r.title}' → '{r.kind}' download button (listing via POST pgp442/selectAojAlmnLst.on; scrape_scourt.py)"})
    m = pd.DataFrame(rows).sort_values(["edition", "kind", "file"])
    m.to_csv(BASE / "source_manifest.csv", index=False, encoding="utf-8-sig")
    print(f"manifest: {len(m)} files, {m.bytes.sum()/1e6:.0f} MB")
    print(m[m.kind == "pdf"].groupby("text_layer").edition.agg(lambda s: sorted(set(s))).to_string())
    return m


# ---------------------------------------------------------------- helpers
def edition(src):
    m = re.match(r"(\d{4})_", str(src))
    return int(m.group(1)) if m else pd.NA


def method(src):
    s = str(src)
    if s.endswith("_xlsx"):
        return "excel"
    if s.endswith("_pdf_vision"):
        return "pdf_image_vlm"
    if s.endswith("_pdf"):
        return "pdf_text_layer"
    return "derived"


def base_cols(d):
    d = d.drop(columns=[c for c in ADDED if c in d.columns])
    d["source_edition"] = d.source.map(edition).astype("Int64")
    d["extraction_method"] = d.source.map(method)
    d["correction_status"] = "none"
    return d


# ---------------------------------------------------------------- 2. correction log + breaks
def corrections():
    import build_courts as bc
    log = []
    now = "2026-11-18"
    det = {("민사본안_1심_단독", "수원지방법원/안산지원", 2007): ("cross-edition OCR comparison", "2026-11-18"),
           ("민사본안_1심_단독", "수원지방법원/안양지원", 2007): ("statutory-date plausibility check", "2026-11-18"),
           ("형사공판_1심_단독", "창원지방법원/진주지원", 2009): ("cross-edition OCR comparison", "2026-11-18"),
           ("민사본안_1심_단독", "광주지방법원", 2005): ("internal subtotal check (district_sum_mismatch) → re-reading of text layer and page image", "2026-11-19"),
           ("민사본안_1심_합의", "대전지방법원/천안지원", 2006): ("positional check against text-layer word coordinates (court_position.py) → page image", "2026-11-20"),
           ("민사본안_1심_합의", "대전지방법원/홍성지원", 2006): ("positional check against text-layer word coordinates (court_position.py) → page image", "2026-11-20")}
    for (t, cid, y), (v, why) in bc.VALUE_FIXES.items():
        how, dt = det[(t, cid, y)]
        log.append(dict(file="court_panel_long.csv", table=t, court_id=cid, year=y, field="value",
                        action="corrected_value", original=re.search(r"OCR ([\d,]+|\d+)", why).group(1).replace(",", ""),
                        corrected=v, evidence=why, detected_by=how,
                        applied_in="build_courts.py VALUE_FIXES", date=dt, affects_released=True))
    import build_duration as bd
    for (dom, lvl, y, b), (v, why) in bd.DURATION_FIXES.items():
        log.append(dict(file="duration_long.csv", table=dom, court_id=lvl, year=y, field=f"value ({b})",
                        action="corrected_value", original=re.search(r"OCR ([\d,]+|\d+)", why).group(1).replace(",", ""),
                        corrected=v, evidence=why,
                        detected_by="positional check against text-layer word coordinates (duration_pdf_position.py) → page image; "
                                    "the bin-sum check had failed for this series-year (17,417 vs 17,437)",
                        applied_in="build_duration.py DURATION_FIXES", date="2026-11-20", affects_released=True))
    log.append(dict(file="court_panel_long.csv", table="형사공판_1심_단독", court_id="창원지방법원 (district block)", year=2009,
                    field="qc_flag", action="qc_recheck", original="district_sum_mismatch on 6 rows (check ran before manual corrections)",
                    corrected="no flag: subtotal 16,773 = sum of parts after the 진주지원 correction",
                    evidence="court_checks_after_fixes.csv", detected_by="review of unresolved warnings",
                    applied_in="build_courts.py main (subtotal check re-run after VALUE_FIXES)", date="2026-11-19", affects_released=True))
    label_scope = {
        "과천시법원": ("민사본안_1심_소액", "수원지방법원/광명시법원", "2016_pdf_vision", "2016 ed. p10 small-claims table; model misread row label", "small-claims extension sample (text layer + visual + human)"),
        "서울의정부지방법원": ("형사공판_1심_단독", "의정부지방법원", "2011_pdf_vision", "2011 ed. criminal single-judge table; model output label variant", "label harmonization against digital names"),
        "지밥법원": ("민사본안_1심_소액", "제주지방법원/관내합계", "2019_xlsx|2020_xlsx", "typo printed in 2019/2020 Excel editions ('제주지밥법원')", "label harmonization"),
        "부산지법동부지원": ("(any)", "부산지방법원/동부지원", "(various)", "label variant in some editions", "label harmonization"),
        "부산지법서부지원": ("(any)", "부산지방법원/서부지원", "(various)", "label variant in some editions", "label harmonization"),
    }
    for a, b in bc.LABEL_FIXES.items():
        t, cid, src, ev, det = label_scope[a]
        log.append(dict(file="court_panel_long.csv", table=t, court_id=cid, year=pd.NA, field="court (label)",
                        action="corrected_label", original=a, corrected=b, evidence=f"{ev}; source={src}", detected_by=det,
                        applied_in="build_courts.py LABEL_FIXES", date=now, affects_released=True))
    for old, new in bc.SI_GUN_RENAMES.items():
        log.append(dict(file="court_panel_long.csv", table="(all)", court_id=old, year=pd.NA, field="court_id_h",
                        action="harmonized_id", original=old, corrected=new, evidence="name change of the same si/gun court; see court_crosswalk_notes.csv",
                        detected_by="statutory records", applied_in="build_courts.py SI_GUN_RENAMES", date=now, affects_released=True))
    log.append(dict(file="detail_long.csv / pending_actual.csv", table="민사본안 (2014 ed. overview)", court_id=pd.NA, year=2014,
                    field="source page", action="page_override", original="auto page detection failed", corrected="page 18",
                    evidence="manual page location", detected_by="extraction failure", applied_in="build_detail.py LOC_OVERRIDE",
                    date="2026-11-13", affects_released=True))
    for ed in (2006, 2011, 2016):
        log.append(dict(file="court_panel_long.csv", table="민사본안_1심_소액", court_id=pd.NA, year=pd.NA, field="source pages",
                        action="continuation_pages", original="untitled pages rejected by title check", corrected="pp. 11, 13 accepted as continuation",
                        evidence=f"{ed} ed. 4-page small-claims table, titles printed on pp.10,12 only", detected_by="coverage gap",
                        applied_in="build_courts.py CONT_PAGES", date="2026-11-18", affects_released=True))
    # Advisor review, Round 6: an error in the official source table (not a structural break)
    log.append(dict(file="detail_long.csv", table="가사_총괄", court_id=pd.NA, year=2016, field="value (소송사건·합계 접수/처리)",
                    action="official_source_error", original="56,057 / 55,712 (litigation); 163,651 / 159,649 (total)",
                    corrected="53,040 / 52,782; 160,634 / 156,719 (released, 2025 ed.)",
                    evidence="The 2016 ed. (p41) and 2018 ed. (p21) year-by-year family overall tables print values for 2016 that exceed the "
                             "released ones by exactly the 2016 appeal filings/dispositions (3,017 / 2,930; same edition's by-instance table p40): the appeal row is "
                             "double-counted. The values are printed in the PDF text layer (not an extraction error). The 2016 ed. by-instance sum and overview table, "
                             "the 2019–2024 Excel editions and the 2025 ed. all give 53,040 / 52,782; stock–flow identity gap −24",
                    detected_by="cross-edition overlap check; source review 2026-11-19", applied_in="source priority (latest edition used)",
                    date="2026-11-19", affects_released=False))
    # Review panel, Round 1 (2026-11-20): detailed-table cross-edition comparison, 2016 vs the 2025 Excel edition
    for lab, o, c in (("제1심 처리", 4645399, 4645402), ("합계 처리", 4746992, 4746995)):
        log.append(dict(file="detail_long.csv", table="민사_심급별", court_id=pd.NA, year=2016, field=f"value ({lab})",
                        action="source_difference", original=o, corrected=c,
                        evidence="2016 ed. p6 text layer prints the OCR value; the same edition's civil overall table (p5) prints "
                                 "the total as 4,746,995 → difference between official sources (and within the 2016 ed.)",
                        detected_by="cross-edition overlap check (detailed tables)",
                        applied_in="source priority (2025 Excel edition used)", date="2026-11-20", affects_released=False))
    mm = pd.read_csv(VAL / "ocr_mismatches.csv")
    srcdiff = {("court_panel", "민사본안_1심_소액", 2016): "PDF text layer also reads the OCR value → source-to-source difference",
               ("pending(개황)", "민사본안", 2006): "OCR value satisfies the overview table's stock–flow identity → source-to-source difference"}
    for _, r in mm.iterrows():
        sd = srcdiff.get((r.dataset, r.table, int(r.year)))
        log.append(dict(file=r.dataset, table=r.table, court_id=r.get("court_id", pd.NA), year=int(r.year), field="value",
                        action="source_difference" if sd else "ocr_error_superseded",
                        original=r.ocr, corrected=r.ref, evidence=sd or f"OCR {r.kind} vs digital comparator ({r.ocr_source})",
                        detected_by="digital-comparator check", applied_in="source priority (digital edition used)",
                        date="2026-11-14", affects_released=False))
    cl = pd.DataFrame(log)
    cl.insert(0, "log_id", range(1, len(cl) + 1))
    # Classify entries by type so 'correction' is not read as 25 data errors (advisor review, Round 3)
    cl.insert(1, "log_type", cl.action.map({
        "corrected_value": "released_data_correction", "corrected_label": "released_data_correction",
        "harmonized_id": "harmonization_decision", "page_override": "pipeline_configuration",
        "continuation_pages": "pipeline_configuration", "ocr_error_superseded": "superseded_ocr_error",
        "source_difference": "source_to_source_discrepancy", "qc_recheck": "pipeline_configuration",
        "official_source_error": "official_source_table_error"}))
    cl.to_csv(VAL / "correction_log.csv", index=False, encoding="utf-8-sig")
    print(f"correction_log: {len(cl)} entries", cl.action.value_counts().to_dict())

    br = pd.DataFrame([
        dict(code="civil_single_incl_small_claims_2010", file="duration_long.csv", filter="domain=민사본안 & level=제1심-단독",
             from_year=2010, to_year=2025, description="From 2010 the single-judge row includes small-claims cases (2009 234,780 → 2010 937,971); 2006 ed. note says small claims excluded",
             basis="2006 edition table note; level jump"),
        dict(code="mean_months_bin_midpoint_2002_2006", file="duration_long.csv", filter="bin=평균처리기간(월) & year<=2006",
             from_year=2002, to_year=2006,
             description="Printed mean disposition time for 2002–2006 is an approximation from bin representative values (≤1m 0.5, ≤2m 1.5, … ≤6m 5.5, ≤9m 7.5, "
                         "≤1y 9 or 10.5 where a 9-month bin exists, ≤2y 18, >2y 30); from 2007 it is the mean of case-level disposition days ÷ 30. "
                         "Recomputing from the bins reproduces every 2002–2006 printed mean (|diff| < 0.15) but not later years",
             basis="2004 ed. 사건개황 p19, 2006 ed. 사건개황 p20/p33 (midpoint note); 2007 ed. 사건개황 p24 ('평균처리일수를 30으로 나눈 수치'); validation/duration_mean_method_check.csv"),
        dict(code="stock_flow_gap_2007", file="pending_actual.csv", filter="year=2007 & category in (민사본안, 가사소송)",
             from_year=2007, to_year=2007, description="Stock–flow identity gap −2.7% (civil main) and −3.3% (family litigation); counting-rule change suspected",
             basis="identity_gap_pct"),
        dict(code="overview_receipts_current_year_2004_2006", file="pending_actual.csv", filter="year in 2004–2006",
             from_year=2004, to_year=2006, description="2004–2006 overview tables split receipts into total (incl. carried-over)/carried-over/current-year; dataset uses current-year filings",
             basis="table layout"),
        dict(code="pending_spliced_2002_2003", file="long_series.csv", filter="metric=미제 & derived=True",
             from_year=2002, to_year=2003, description="National pending 2002–2003 = multi-year-table pending × 0.9991 (ratio to observed sum in 2004–2006)",
             basis="derived"),
        dict(code="court_new_or_converted", file="court_panel_long.csv", filter="see partial_year and court_crosswalk.csv",
             from_year=2002, to_year=2025, description="Unbalanced panel: courts established/converted during period; first-year values partial (partial_year=True)",
             basis="statutory records"),
    ])
    br.to_csv(SER / "structural_breaks.csv", index=False, encoding="utf-8-sig")
    print(f"structural_breaks: {len(br)}")
    return cl


# ---------------------------------------------------------------- 3. columns & flags
def court_panel(cl):
    f = SER / "court_panel_long.csv"
    d = base_cols(pd.read_csv(f))
    d.loc[d.qc_flag.eq("ocr_corrected_manual"), "correction_status"] = "corrected_value"
    d.loc[d.qc_flag.eq("district_sum_mismatch"), "correction_status"] = "unresolved_warning"
    lab = {  # (table, court_id, source) rows to mark as label-corrected
        ("민사본안_1심_소액", "수원지방법원/광명시법원", "2016_pdf_vision"),
        ("형사공판_1심_단독", "의정부지방법원", "2011_pdf_vision"),
    }
    m = pd.Series([(t, c, s) in lab for t, c, s in zip(d.table, d.court_id, d.source)], index=d.index)
    m |= d.court_id.eq("제주지방법원/관내합계") & d.table.eq("민사본안_1심_소액") & d.source.isin(["2019_xlsx", "2020_xlsx"])
    d.loc[m & d.correction_status.eq("none"), "correction_status"] = "corrected_label"
    # partial_year: establishment year of courts 'established' (`설치`) during the period (effective on a date other than Jan 1)
    n = pd.read_csv(SER / "court_crosswalk_notes.csv")
    n = n[n.legal_event.eq("설치") & n.legal_start.notna()].copy()
    n["y"] = n.legal_start.str[:4].astype(int)
    n = n[(n.y >= 2002) & ~n.legal_start.str.endswith("-01-01")]
    py = set(zip(n.court_id_h, n.y))
    d["partial_year"] = [(c, y) in py for c, y in zip(d.court_id_h, d.year)]
    d["dup_flag"] = ""
    d.loc[d.court_id_h.eq("의정부지방법원/남양주지원") & d.table.eq("민사본안_1심_소액") & d.year.between(2018, 2021),
          "dup_flag"] = "duplicates_namyangju_si_court"
    d.to_csv(f, index=False, encoding="utf-8-sig")
    print("court_panel:", d.correction_status.value_counts().to_dict(), "partial_year", int(d.partial_year.sum()),
          "dup", int(d.dup_flag.ne("").sum()), "| partial units:", sorted(py))


def simple(name, flagger):
    f = SER / name
    d = base_cols(pd.read_csv(f))
    if name == "duration_long.csv":  # GPT structured the Excel cell-grid text into tables (build_duration.from_excel); values verified against the source cells
        d.loc[d.extraction_method.eq("excel"), "extraction_method"] = "excel_llm_structured"
        import build_duration as bd
        for (dom, lvl, y, b), _ in bd.DURATION_FIXES.items():  # manual OCR corrections (correction_log.csv)
            m = (d.domain == dom) & (d.level == lvl) & (d.year == y) & (d.bin == b)
            assert m.sum() == 1, (dom, lvl, y, b, int(m.sum()))
            d.loc[m, "correction_status"] = "corrected_value"
    d["break_flag"] = flagger(d)
    d.to_csv(f, index=False, encoding="utf-8-sig")
    print(name, d.extraction_method.value_counts().to_dict(), "break rows", int(d.break_flag.ne("").sum()))


def none(d):
    return ""


def dur_flag(d):
    return ["mean_months_bin_midpoint_2002_2006" if (b == "평균처리기간(월)" and y <= 2006) else
            "civil_single_incl_small_claims_2010" if (dm == "민사본안" and lv == "제1심-단독" and y >= 2010) else ""
            for dm, lv, y, b in zip(d.domain, d.level, d.year, d.bin)]


def duration_excel_cell_check():
    """Deterministic check that each excel_llm_structured value (disposition time, 2019–2025 editions) actually appears
    in the source Excel cell block (the source_page range)."""
    import openpyxl
    d = pd.read_csv(SER / "duration_long.csv")
    x = d[d.extraction_method.eq("excel_llm_structured")]
    rows = []
    for (f, loc), g in x.groupby(["source_file", "source_page"]):
        sh, rng = loc.split("!")
        a, b = [int(v) for v in re.findall(r"r(\d+)", rng)]
        ws = openpyxl.load_workbook(BASE / f, data_only=True, read_only=True)[sh]
        nums = []
        for r in ws.iter_rows(min_row=a, max_row=b, values_only=True):
            for c in r:
                if isinstance(c, (int, float)):
                    nums.append(float(c))
                elif isinstance(c, str):
                    nums += [float(t.replace(",", "")) for t in re.findall(r"\d[\d,]*\.?\d*", c)]
        for _, r in g.iterrows():
            v = r.value
            hit = pd.notna(v) and (v == 0 or any(abs(v - n) < 0.051 for n in nums))
            rows.append(dict(domain=r.domain, level=r.level, year=r.year, bin=r.bin, value=v, source_file=f,
                             source_page=loc, found_in_source_block=bool(hit)))
    out = pd.DataFrame(rows)
    out.to_csv(VAL / "duration_excel_cell_check.csv", index=False, encoding="utf-8-sig")
    print(f"duration_excel_cell_check: {int(out.found_in_source_block.sum())}/{len(out)} values found in source cell block")


MID = {"1월이내": .5, "2월이내": 1.5, "3월이내": 2.5, "4월이내": 3.5, "5월이내": 4.5, "6월이내": 5.5, "9월이내": 7.5,
       "2년이내": 18, "2년초과": 30}  # `1년이내` (within 1 year) = 9, or 10.5 if a `9월이내` (within 9 months) bin exists (overview table notes, 2004 and 2006 eds.)


def duration_mean_check():
    """Printed mean disposition time vs the mean recomputed from bin representative values -> confirms the 2002–2006
    calculation method (bin representative values)."""
    d = pd.read_csv(SER / "duration_long.csv")
    rows = []
    for (dm, lv, y), g in d.groupby(["domain", "level", "year"]):
        v = dict(zip(g.bin, g.value))
        tot, mm = v.get("합계"), v.get("평균처리기간(월)")
        if not tot or pd.isna(mm):
            continue
        y1 = 10.5 if "9월이내" in v else 9
        est = (sum(v[b] * w for b, w in MID.items() if b in v) + v.get("1년이내", 0) * y1) / tot
        rows.append(dict(domain=dm, level=lv, year=y, printed_mean_months=mm, midpoint_mean_months=round(est, 3),
                         diff=round(mm - est, 3), match_midpoint=abs(mm - est) < 0.15,
                         source_edition=g.source_edition.iloc[0]))
    r = pd.DataFrame(rows)
    r.to_csv(VAL / "duration_mean_method_check.csv", index=False, encoding="utf-8-sig")
    a = r.year <= 2006
    print(f"duration_mean_method_check: 2002–2006 match {int(r[a].match_midpoint.sum())}/{int(a.sum())}, "
          f"2007– match {int(r[~a].match_midpoint.sum())}/{int((~a).sum())}")


def detail_flag(d):  # The 2016 'level shift' in `가사_총괄` (family overall table) turned out to be a source-table error (advisor review, Round 6) -> not a break, no flag
    return ["" for _ in range(len(d))]


def pending_flag(d):
    out = []
    for c, y in zip(d.category, d.year):
        if y == 2007 and c in ("민사본안", "가사소송"):
            out.append("stock_flow_gap_2007")
        elif 2004 <= y <= 2006:
            out.append("overview_receipts_current_year_2004_2006")
        else:
            out.append("")
    return out


def long_flag(d):
    return ["pending_spliced_2002_2003" if (str(dv) == "True" and m == "미제") else "" for dv, m in zip(d.derived, d.metric)]


if __name__ == "__main__":
    manifest()
    cl = corrections()
    court_panel(cl)
    simple("duration_long.csv", dur_flag)
    duration_mean_check()
    duration_excel_cell_check()
    simple("detail_long.csv", detail_flag)
    simple("pending_actual.csv", pending_flag)
    simple("long_series.csv", long_flag)
