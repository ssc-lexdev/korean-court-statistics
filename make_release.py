"""Build the public release package (release/) with a bilingual design (agreed in advisor review, Round 3).
- Fact tables: ASCII lowercase snake_case IDs + values + provenance/QC. Only the original Korean labels that vary by source are kept.
- Lookup tables: Korean (authoritative) + English labels. Court English names prefer the official names on the Supreme Court's
  English website; branch and si/gun courts follow the English terminology pattern of the Court Organization Act translation
  + the official romanization of the place name.
- Encoding: release/data/ = UTF-8 without BOM (canonical), release/csv_excel/ = UTF-8-SIG copies.
Run: python make_release.py  (after finalize_release.py). Stops with an error if any mapping is missing.
Working files (data/series/*) are not modified, because the build and validation scripts depend on the Korean values."""
import re
import json
import shutil
from pathlib import Path

import pandas as pd

import court_lineage as CL

ROOT = Path(__file__).parent
SER, VAL = ROOT / "data" / "series", ROOT / "data" / "validation"
OUT = Path(__import__("os").environ.get("SCOURT_RELEASE_OUT", ROOT / "release"))  # a local build folder can be set for speed
SCOURT = "https://eng.scourt.go.kr/eng/judiciary/organization/courts2.jsp|courts3.jsp|courts4.jsp (retrieved 2026-11-19)"

# ------------------------------------------------------------------ court English names
OFFICIAL = {  # official name on the Supreme Court English website → (slug, English)
    "서울고등법원": ("seoul_hc", "Seoul High Court"), "대전고등법원": ("daejeon_hc", "Daejeon High Court"),
    "대구고등법원": ("daegu_hc", "Daegu High Court"), "부산고등법원": ("busan_hc", "Busan High Court"),
    "광주고등법원": ("gwangju_hc", "Gwangju High Court"), "수원고등법원": ("suwon_hc", "Suwon High Court"),
    "특허법원": ("patent_court", "Patent Court"),
    "서울중앙지방법원": ("seoul_central_dc", "Seoul Central District Court"), "서울동부지방법원": ("seoul_eastern_dc", "Seoul Eastern District Court"),
    "서울남부지방법원": ("seoul_southern_dc", "Seoul Southern District Court"), "서울북부지방법원": ("seoul_northern_dc", "Seoul Northern District Court"),
    "서울서부지방법원": ("seoul_western_dc", "Seoul Western District Court"), "의정부지방법원": ("uijeongbu_dc", "Uijeongbu District Court"),
    "인천지방법원": ("incheon_dc", "Incheon District Court"), "수원지방법원": ("suwon_dc", "Suwon District Court"),
    "춘천지방법원": ("chuncheon_dc", "Chuncheon District Court"), "대전지방법원": ("daejeon_dc", "Daejeon District Court"),
    "청주지방법원": ("cheongju_dc", "Cheongju District Court"), "대구지방법원": ("daegu_dc", "Daegu District Court"),
    "부산지방법원": ("busan_dc", "Busan District Court"), "울산지방법원": ("ulsan_dc", "Ulsan District Court"),
    "창원지방법원": ("changwon_dc", "Changwon District Court"), "광주지방법원": ("gwangju_dc", "Gwangju District Court"),
    "전주지방법원": ("jeonju_dc", "Jeonju District Court"), "제주지방법원": ("jeju_dc", "Jeju District Court"),
    "서울가정법원": ("seoul_fc", "Seoul Family Court"), "대구가정법원": ("daegu_fc", "Daegu Family Court"),
    "부산가정법원": ("busan_fc", "Busan Family Court"), "광주가정법원": ("gwangju_fc", "Gwangju Family Court"),
    "대전가정법원": ("daejeon_fc", "Daejeon Family Court"), "인천가정법원": ("incheon_fc", "Incheon Family Court"),
    "울산가정법원": ("ulsan_fc", "Ulsan Family Court"), "수원가정법원": ("suwon_fc", "Suwon Family Court"),
    "서울회생법원": ("seoul_bankruptcy", "Seoul Bankruptcy Court"), "수원회생법원": ("suwon_bankruptcy", "Suwon Bankruptcy Court"),
    "부산회생법원": ("busan_bankruptcy", "Busan Bankruptcy Court"),
}
PLACE = {  # place name → official romanization of the city/county (Revised Romanization of Korean)
    "목포": "Mokpo", "순천": "Suncheon", "장흥": "Jangheung", "해남": "Haenam", "경주": "Gyeongju", "김천": "Gimcheon",
    "상주": "Sangju", "안동": "Andong", "영덕": "Yeongdeok", "의성": "Uiseong", "포항": "Pohang", "공주": "Gongju",
    "논산": "Nonsan", "서산": "Seosan", "천안": "Cheonan", "홍성": "Hongseong", "성남": "Seongnam", "안산": "Ansan",
    "안양": "Anyang", "여주": "Yeoju", "평택": "Pyeongtaek", "고양": "Goyang", "남양주": "Namyangju", "부천": "Bucheon",
    "군산": "Gunsan", "남원": "Namwon", "정읍": "Jeongeup", "거창": "Geochang", "마산": "Masan", "밀양": "Miryang",
    "진주": "Jinju", "통영": "Tongyeong", "영동": "Yeongdong", "제천": "Jecheon", "충주": "Chungju", "강릉": "Gangneung",
    "속초": "Sokcho", "영월": "Yeongwol", "원주": "Wonju",
    "강진": "Gangjin", "고흥": "Goheung", "곡성": "Gokseong", "광양": "Gwangyang", "구례": "Gurye", "나주": "Naju",
    "담양": "Damyang", "무안": "Muan", "보성": "Boseong", "여수": "Yeosu", "영광": "Yeonggwang", "영암": "Yeongam",
    "완도": "Wando", "장성": "Jangseong", "진도": "Jindo", "함평": "Hampyeong", "화순": "Hwasun", "경산": "Gyeongsan",
    "고령": "Goryeong", "구미": "Gumi", "군위": "Gunwi", "문경": "Mungyeong", "봉화": "Bonghwa", "성주": "Seongju",
    "영양": "Yeongyang", "영주": "Yeongju", "영천": "Yeongcheon", "예천": "Yecheon", "울진": "Uljin", "청도": "Cheongdo",
    "청송": "Cheongsong", "칠곡": "Chilgok", "금산": "Geumsan", "당진": "Dangjin", "보령": "Boryeong", "부여": "Buyeo",
    "서천": "Seocheon", "세종특별자치": "Sejong", "아산": "Asan", "예산": "Yesan", "청양": "Cheongyang", "태안": "Taean",
    "광명": "Gwangmyeong", "광주": "Gwangju", "안성": "Anseong", "양평": "Yangpyeong", "오산": "Osan", "용인": "Yongin",
    "이천": "Icheon", "양산": "Yangsan", "가평": "Gapyeong", "동두천": "Dongducheon", "연천": "Yeoncheon",
    "철원": "Cheorwon", "파주": "Paju", "포천": "Pocheon", "강화": "Ganghwa", "김포": "Gimpo", "고창": "Gochang",
    "김제": "Gimje", "무주": "Muju", "부안": "Buan", "순창": "Sunchang", "익산": "Iksan", "임실": "Imsil", "장수": "Jangsu",
    "진안": "Jinan", "서귀포": "Seogwipo", "거제": "Geoje", "고성": "Goseong", "김해": "Gimhae", "남해": "Namhae",
    "사천": "Sacheon", "산청": "Sancheong", "의령": "Uiryeong", "창녕": "Changnyeong", "창원남부": "Changwon-Nambu",
    "하동": "Hadong", "함안": "Haman", "함양": "Hamyang", "합천": "Hapcheon", "괴산": "Goesan", "단양": "Danyang",
    "보은": "Boeun", "옥천": "Okcheon", "음성": "Eumseong", "진천": "Jincheon", "동해": "Donghae", "삼척": "Samcheok",
    "양구": "Yanggu", "양양": "Yangyang", "인제": "Inje", "정선": "Jeongseon", "태백": "Taebaek", "평창": "Pyeongchang",
    "홍천": "Hongcheon", "화천": "Hwacheon", "횡성": "Hoengseong",
}
DIRECTION = {"동부": ("eastern", "Eastern"), "서부": ("western", "Western")}
GROUPS = {"전국": ("national_total", "National total"), "고등법원계": ("high_courts_total", "High courts total"),
          "지방법원계": ("district_courts_total", "District courts total")}
LEGAL_EVENT = {"설치": "established", "승격": "elevated_from_branch", "전환": "converted_to_family_court",
               "명칭변경": "renamed", "명칭변경(군→시 승격)": "renamed_county_to_city", "폐지(마산지원으로 흡수)": "abolished_absorbed",
               "폐지(지원으로 승계, 2022-03-01)": "abolished_succeeded_by_branch", "관할변경(2016-01-01)": "jurisdiction_added",
               "미확인": "unverified"}


def slug(s):
    s = re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")
    assert s.isascii() and "/" not in s
    return s


def court_entry(cid):
    """court_id_h (Korean) → slug, English name, name source, romanization, parent."""
    if cid in GROUPS:
        s, en = GROUPS[cid]
        return s, en, "author_label", "", ""
    if cid in OFFICIAL:
        s, en = OFFICIAL[cid]
        return s, en, "official_scourt_english_site", "", ""
    parent, child = cid.split("/", 1)
    ps, pen = OFFICIAL[parent]
    if child == "소계":
        return f"{ps}_subtotal", f"{pen}: subtotal (as printed)", "author_label", "", ps
    if child == "관내합계":
        return f"{ps}_area_total", f"{pen}: district-area total (as printed)", "author_label", "", ps
    m = re.fullmatch(r"(.+?)(지원|시법원|군법원)", child)
    stem, kind = m.group(1), m.group(2)
    if kind == "지원":
        if stem in DIRECTION:
            rs, ren = DIRECTION[stem]
        else:
            ren = PLACE[stem]; rs = slug(ren)
        return f"{ps}_{rs}_br", f"{ren} Branch Court of {pen}", "pattern_court_organization_act", ren, ps
    ren = PLACE[stem]
    k = "Si" if kind == "시법원" else "Gun"
    return f"{ps}_{slug(ren)}_{k.lower()}", f"{ren} {k} Court", "pattern_court_organization_act", ren, ps


# ------------------------------------------------------------------ category codes
TABLES = {  # court-level panel tables
    "민사본안_1심_합의": ("civil_main_1st_collegiate", "Civil contentious/main cases, first instance, collegiate panel", "cases"),
    "민사본안_1심_단독": ("civil_main_1st_single", "Civil contentious/main cases, first instance, single judge (excl. small claims)", "cases"),
    "민사본안_1심_소액": ("civil_main_1st_small_claims", "Civil contentious/main cases, first instance, small claims", "cases"),
    "민사본안_항소심": ("civil_main_appeal", "Civil contentious/main cases, appeal", "cases"),
    "가사소송_1심": ("family_litigation_1st", "Family litigation, first instance", "cases"),
    "가사소송_항소심": ("family_litigation_appeal", "Family litigation, appeal", "cases"),
    "형사공판_1심": ("criminal_trial_1st_total", "Criminal trials, first instance, total", "persons"),
    "형사공판_1심_합의": ("criminal_trial_1st_collegiate", "Criminal trials, first instance, collegiate panel", "persons"),
    "형사공판_1심_단독": ("criminal_trial_1st_single", "Criminal trials, first instance, single judge", "persons"),
    "형사공판_항소심": ("criminal_trial_appeal", "Criminal trials, appeal", "persons"),
    "민사본안_1심_계(산출)": (CL.CIVIL_TOTAL, "Civil contentious/main cases, first instance, total (derived: collegiate + single judge + small claims)", "cases"),
    # detailed tables
    "민사_총괄": ("civil_overall", "Civil cases, overall", "cases"),
    "민사_심급별": ("civil_by_instance", "Civil cases, by instance", "cases"),
    "민사본안_심급별": ("civil_main_by_instance", "Civil contentious/main cases, by instance", "cases"),
    "가사_총괄": ("family_overall", "Family cases, overall", "cases"),
    "가사소송_심급별": ("family_litigation_by_instance", "Family litigation, by instance", "cases"),
    "형사_총괄": ("criminal_overall", "Criminal cases, overall", "persons"),
    "형사공판_심급별": ("criminal_trial_by_instance", "Criminal trials, by instance", "persons"),
}
CATEGORIES = {
    "전체사건": ("all_cases", "All cases"), "본안사건": ("main_cases", "Main (merits) cases"),
    "본안외사건": ("non_main_cases", "Non-main/ancillary cases"), "비송사건": ("non_contentious", "Non-contentious cases"),
    "민사본안": ("civil_main", "Civil contentious/main cases"), "가사소송": ("family_litigation", "Family litigation"),
    "행정소송": ("administrative", "Administrative litigation"), "특허·지식재산": ("patent_ip", "Patent and intellectual property cases"),
    "형사공판": ("criminal_trial", "Criminal trials"), "치료감호": ("medical_custody", "Medical Treatment and Custody cases"),
    "총계": ("total", "Total"), "합계": ("total", "Total"), "소송사건": ("litigation", "Litigation cases"),
    "신청사건": ("applications", "Application cases"), "조정사건": ("conciliation", "Conciliation cases"),
    "공판사건": ("trial", "Trial cases"), "약식사건": ("summary_order", "Summary order cases"),
    "즉결사건": ("summary_trial", "Summary trial cases (minor-offense immediate proceedings)"), "기타사건": ("other", "Other cases"),
}
TRANSLATION_NOTE = {  # advisor review, Round 5: translation notes for English labels that involve interpretation (category/table/domain ID → note)
    "main_cases": "본안사건: cases on the merits (lawsuits and other principal proceedings) as classified by the Judicial Yearbook. 'Main (merits)' is a functional translation; read it with the Korean label. Includes criminal trials, counted as cases in the overview tables",
    "non_main_cases": "본안외사건: matters the Yearbook counts outside 본안사건 (e.g. applications and enforcement-related matters). Not the same category as non_contentious (비송사건)",
    "non_contentious": "비송사건: non-contentious matters; a separate Yearbook category, not identical to non_main_cases",
    "civil_main": "민사본안: civil cases on the merits (first instance incl. small claims, appeals and final appeals), as opposed to civil applications, enforcement etc.",
    "criminal_trial": "형사공판: criminal cases tried in court after indictment; counted in persons (defendants)",
    "summary_order": "약식사건: summary-order route (약식명령): a fine imposed on the prosecutor's written request without a trial. Distinct from summary_trial",
    "summary_trial": "즉결사건: immediate summary trial (즉결심판) of minor offences on a police chief's request, heard by Si/Gun court or designated judges. Distinct from summary_order",
    "patent_ip": "특허·지식재산: one ID across editions; earlier editions print 특허",
    "medical_custody": "치료감호: cases under the Medical Treatment and Custody Act",
    "civil_main_1st_collegiate": "The split between collegiate, single-judge and small-claims tables is set by monetary jurisdiction thresholds that changed in 2015, 2017 and 2022 (structural_breaks.csv); use civil_main_1st_total for a split-free series",
    "civil_main_1st_single": "Excludes small claims. Affected by the 2015, 2017 and 2022 threshold changes (structural_breaks.csv); use civil_main_1st_total for a split-free series",
    "civil_main_1st_small_claims": "Small-claims ceiling KRW 20 million to 2016, KRW 30 million from 2017 (structural_breaks.csv)",
    "civil_main_1st_total": "Derived in this dataset as the sum of the three first-instance tables for each court and year; nationally it equals the printed first-instance filings of civil main cases (detail.csv) in every year",
    "civil_main_appeal": "From 2016 includes the Patent Court (appeals in IP-infringement civil cases; structural_breaks.csv)",
    "criminal_trial_1st_collegiate": "Split set by Court Organization Act Art. 32(1) (offence-based); see structural_breaks.csv. Use criminal_trial_1st_total for a split-free series",
    "criminal_trial_1st_single": "Split set by Court Organization Act Art. 32(1) (offence-based); see structural_breaks.csv. Use criminal_trial_1st_total for a split-free series",
}
INSTANCES = {
    "총계": ("total", "Total"), "전심급": ("all_instances", "All instances"), "합계": ("total", "Total"),
    "제1심": ("first_instance", "First instance"), "제1심-합의": ("first_collegiate", "First instance, collegiate panel"),
    "제1심-단독": ("first_single", "First instance, single judge"), "항소심": ("appeal", "Appeal"),
    "항소심-고등법원": ("appeal_high_court", "Appeal, high court"), "항소심-지방법원": ("appeal_district_court", "Appeal, district court appellate division"),
    "상고심": ("supreme_court", "Final appeal (Supreme Court)"), "상고심-합의": ("supreme_from_collegiate", "Final appeal, from collegiate first instance"),
    "상고심-단독": ("supreme_from_single", "Final appeal, from single-judge first instance"),
}
METRICS = {"접수": ("filings", "Filings (cases received)"), "처리": ("dispositions", "Dispositions"),
           "미제": ("pending", "Pending at year end"), "미제(산출)": ("pending_computed", "Pending, computed (2006 pending + cumulative net inflow)"),
           "미제(누년표)": ("pending_multiyear_table", "Pending, from multi-year comparison table")}
DOMAINS = {"민사": ("civil", "Civil"), "가사": ("family", "Family"), "형사": ("criminal", "Criminal"),
           "민사본안": ("civil_main", "Civil contentious/main cases"), "가사소송": ("family_litigation", "Family litigation"),
           "형사공판": ("criminal_trial", "Criminal trials")}
BINS = [  # (ko, id, en, upper_month, type)
    ("1월이내", "le_1m", "≤1 month", 1, "count"), ("2월이내", "le_2m", "1–2 months", 2, "count"),
    ("3월이내", "le_3m", "2–3 months", 3, "count"), ("4월이내", "le_4m", "3–4 months", 4, "count"),
    ("5월이내", "le_5m", "4–5 months", 5, "count"), ("6월이내", "le_6m", "5–6 months", 6, "count"),
    ("9월이내", "le_9m", "6–9 months (criminal only)", 9, "count"), ("1년이내", "le_12m", "up to 12 months (after preceding bin)", 12, "count"),
    ("2년이내", "le_24m", "12–24 months", 24, "count"), ("2년초과", "gt_24m", ">24 months", None, "count"),
    ("합계", "total", "Total disposed", None, "total"), ("평균처리기간(월)", "mean_months", "Mean disposition time (months, as printed)", None, "mean"),
]


def need(mapping, values, what):
    miss = sorted(set(values) - set(mapping))
    assert not miss, f"unmapped {what}: {miss}"


# ---- split the source-location column + unify source_type (advisor review, Round 4 Q2 and #57)
_PAGE_TOKENS = {}


def _page_tokens(rel_file, page):
    """Set of numeric tokens (commas removed) in the text layer of one PDF page."""
    k = (rel_file, page)
    if k not in _PAGE_TOKENS:
        import fitz
        doc = fitz.open(ROOT / "data" / rel_file)
        txt = doc[page - 1].get_text() if page <= len(doc) else ""
        _PAGE_TOKENS[k] = {t.replace(",", "") for t in re.findall(r"\d[\d,]*(?:\.\d+)?", txt)}
    return _PAGE_TOKENS[k]


def _num_forms(v):
    if pd.isna(v):
        return set()
    v = float(v)
    if v.is_integer():
        return {str(int(v))}
    return {f"{v:.1f}", f"{v:.2f}", f"{v:g}"}


def split_locator(df):
    """source_page → source_locator + page_start/page_end/exact_page/locator_note.
    For values read from several pages at once, if the number appears in the text layer of exactly one page in the range,
    that page is taken as the exact page."""
    loc = df.source_page.fillna("").astype(str)
    ps, pe, ex, note = [], [], [], []
    for f, l, v in zip(df.source_file.fillna(""), loc, df["value"] if "value" in df else [None] * len(df)):
        m1 = re.fullmatch(r"p(\d+)(?: \(left column\))?", l)
        m2 = re.fullmatch(r"p(\d+)-(\d+) \(pages sent together\)", l)
        if m1:
            p = int(m1.group(1)); ps.append(p); pe.append(p); ex.append(True); note.append("exact page")
        elif m2:
            a, b = int(m2.group(1)), int(m2.group(2))
            forms = _num_forms(v)
            hits = [p for p in range(a, b + 1) if forms & _page_tokens(f, p)] if forms and str(f).endswith(".pdf") else []
            if len(hits) == 1:
                ps.append(hits[0]); pe.append(hits[0]); ex.append(True)
                note.append(f"exact page located in text layer within request pages {a}-{b}")
            else:
                ps.append(a); pe.append(b); ex.append(False)
                note.append(f"page range = pages sent in one model request; value found on {len(hits)} of them in text layer")
        else:
            ps.append(pd.NA); pe.append(pd.NA); ex.append(pd.NA)
            note.append("Excel sheet!row" if "!" in l else ("derived" if not l else "other"))
    out = df.copy()
    i = list(out.columns).index("source_page")
    out = out.rename(columns={"source_page": "source_locator"})
    for k, (name, vals) in enumerate([("page_start", ps), ("page_end", pe), ("exact_page", ex), ("locator_note", note)]):
        out.insert(i + 1 + k, name, vals)
    out["page_start"] = out.page_start.astype("Int64"); out["page_end"] = out.page_end.astype("Int64")
    return out


ST = {"excel": "digital", "excel_llm_structured": "digital", "pdf_text_layer": "digital", "pdf_image_vlm": "ocr", "derived": "derived"}


def add_source_type(df):
    st = df.extraction_method.map(ST)
    assert st.notna().all(), set(df.extraction_method[st.isna()])
    if "source_type" in df:
        assert (df.source_type.fillna("") == st).all(), "source_type inconsistent with extraction_method"
        df = df.drop(columns="source_type")
    df.insert(list(df.columns).index("extraction_method") + 1, "source_type", st)
    return df


def write(df, name):
    if "source_page" in df.columns and "extraction_method" in df.columns:
        df = split_locator(add_source_type(df))
        if name in PAGE_STATS_FOR:
            PAGE_STATS[name] = df.exact_page.value_counts(dropna=False).to_dict()
    (OUT / "data").mkdir(parents=True, exist_ok=True)
    (OUT / "csv_excel").mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT / "data" / name, index=False, encoding="utf-8")
    df.to_csv(OUT / "csv_excel" / name, index=False, encoding="utf-8-sig")
    print(f"  {name}: {len(df)} rows × {df.shape[1]} cols")


PAGE_STATS, PAGE_STATS_FOR = {}, {"court_panel.csv", "national_series.csv", "pending_observed.csv", "detail.csv", "duration.csv"}
PROV = ["source", "source_edition", "source_file", "source_page", "extraction_method", "correction_status"]


def main():
    if OUT.exists():  # keep the folder itself and delete only its contents (safe even if the folder is someone's current working directory)
        for c in OUT.iterdir():
            shutil.rmtree(c) if c.is_dir() else c.unlink()
    OUT.mkdir(exist_ok=True)
    # ---- courts lookup
    cw = pd.read_csv(SER / "court_crosswalk.csv")
    notes = pd.read_csv(SER / "court_crosswalk_notes.csv").set_index("court_id_h")  # merge statutory annotations (Korean and English) directly
    nget = lambda cid, c: (notes.at[cid, c] if cid in notes.index and pd.notna(notes.at[cid, c]) else "")  # noqa: E731
    rows = []
    for _, r in cw.iterrows():
        s, en, src, rom, parent = court_entry(r.court_id_h)
        ev = nget(r.court_id_h, "legal_event")
        if ev:
            assert ev in LEGAL_EVENT, f"unmapped legal_event: {ev}"
        rows.append(dict(court_id_h=s, court_ko=r.court_id_h, court_en=en, court_en_source=src, romanization=rom,
                         unit_type=r.unit_type, parent_court_id_h=parent, first_year_in_data=r.first_year, last_year_in_data=r.last_year,
                         legal_start=nget(r.court_id_h, "legal_start"), legal_event=LEGAL_EVENT.get(ev, ""),
                         predecessor_en=nget(r.court_id_h, "predecessor_en"), legal_basis_en=nget(r.court_id_h, "legal_basis_en"),
                         data_note_en=nget(r.court_id_h, "data_note_en"),
                         predecessor_ko=nget(r.court_id_h, "predecessor"), legal_basis_ko=nget(r.court_id_h, "legal_basis"),
                         data_note_ko=nget(r.court_id_h, "data_note"),
                         harmonized_from_ko=r.source_ids, tables_ko=r.tables))
    courts = pd.DataFrame(rows)
    cpk = pd.read_csv(SER / "court_panel_long.csv", usecols=["court_id_h", "year", "value"])
    nz = cpk[cpk.value.ne(0)].groupby("court_id_h").year.agg(["min", "max"])
    courts["first_year_in_data"] = courts.court_ko.map(nz["min"]).astype("Int64")
    courts["last_year_in_data"] = courts.court_ko.map(nz["max"]).astype("Int64")
    assert courts.court_id_h.is_unique, courts[courts.court_id_h.duplicated(keep=False)]
    order = {"national_total": 0, "group_total": 1, "high_court": 2, "main_court": 3, "district_total": 4, "branch": 5, "si_gun_court": 6}
    courts = courts.sort_values(by=["unit_type", "court_id_h"], key=lambda c: c.map(order) if c.name == "unit_type" else c)
    courts.insert(1, "court_code", range(1, len(courts) + 1))
    ko2id = dict(zip(courts.court_ko, courts.court_id_h))
    code = dict(zip(courts.court_id_h, courts.court_code))
    print("release/ lookups")
    write(courts, "courts.csv")
    # ---- other lookups
    panel_tables = set(pd.read_csv(SER / "court_panel_long.csv", usecols=["table"]).table)
    tables = pd.DataFrame([dict(table_id=v[0], table_ko=k, table_en=v[1], unit=v[2],
                                used_in="court_panel.csv" if (k in panel_tables or v[0] == CL.CIVIL_TOTAL) else "detail.csv",
                                translation_note_en=TRANSLATION_NOTE.get(v[0], ""))
                           for k, v in TABLES.items()])
    write(tables, "tables.csv")
    cat = pd.DataFrame([dict(category_id=v[0], category_ko=k, category_en=v[1], translation_note_en=TRANSLATION_NOTE.get(v[0], ""))
                        for k, v in CATEGORIES.items()]).drop_duplicates("category_id")
    write(cat, "categories.csv")
    ins = pd.DataFrame([dict(instance_id=v[0], instance_ko=k, instance_en=v[1]) for k, v in INSTANCES.items()]).drop_duplicates("instance_id")
    write(ins, "instances.csv")
    met = pd.DataFrame([dict(metric_id=v[0], metric_ko=k, metric_en=v[1]) for k, v in METRICS.items()])
    write(met, "metrics.csv")
    dom = pd.DataFrame([dict(domain_id=v[0], domain_ko=k, domain_en=v[1], translation_note_en=TRANSLATION_NOTE.get(v[0], ""))
                        for k, v in DOMAINS.items()])
    write(dom, "domains.csv")
    # bins per domain (only criminal has the `9월이내` (within 9 months) bin), with explicit lower/upper bounds and inclusiveness
    # (advisor review, Round 4 #20)
    brow = []
    for dom in ("civil_main", "family_litigation", "criminal_trial"):
        lo, order = 0, 0
        for k, b, e, u, t in BINS:
            if b == "le_9m" and dom != "criminal_trial":
                continue
            order += 1
            if t == "count":
                en = (f"{lo}–{u} months" if lo else f"≤{u} month" + ("s" if u > 1 else "")) if u else f">{lo} months"
                brow.append(dict(domain_id=dom, bin_id=b, bin_ko=k, bin_en=en, bin_type=t, lower_month=lo, upper_month=u,
                                 lower_inclusive=False, upper_inclusive=bool(u), open_ended=u is None, sort_order=order))
                lo = u if u else lo
            else:
                brow.append(dict(domain_id=dom, bin_id=b, bin_ko=k, bin_en=e, bin_type=t, lower_month=None, upper_month=None,
                                 lower_inclusive=None, upper_inclusive=None, open_ended=None, sort_order=order))
    bins = pd.DataFrame(brow)
    bins["lower_month"] = bins.lower_month.astype("Int64"); bins["upper_month"] = bins.upper_month.astype("Int64")
    write(bins, "duration_bins.csv")

    print("release/ fact tables")
    # ---- court panel
    cp = pd.read_csv(SER / "court_panel_long.csv")
    need(ko2id, cp.court_id_h, "court_id_h"); need(TABLES, cp.table, "table")
    out = pd.DataFrame({"year": cp.year, "court_id_h": cp.court_id_h.map(ko2id), "table_id": cp.table.map(lambda t: TABLES[t][0]),
                        "value": cp.value.round().astype("Int64"), "unit": cp.table.map(lambda t: TABLES[t][2]),
                        "unit_type": cp.unit_type, "source_court_id_ko": cp.court_id, "source_court_label_ko": cp.court})
    out.insert(2, "court_code", out.court_id_h.map(code))
    for c in PROV + ["source_type", "qc_flag", "partial_year", "dup_flag"]:
        out[c] = cp[c]
    out["qc_flag"] = out.qc_flag.fillna(""); out["dup_flag"] = out.dup_flag.fillna("")
    assert out.value.notna().all()
    out["pre_establishment"] = CL.pre_establishment(out, courts)
    out = pd.concat([out, CL.civil_total_rows(out)], ignore_index=True)
    out["dup_flag"] = out.dup_flag.fillna("")
    out = CL.add_break_flags(out, "court_panel.csv")
    write(out.sort_values(["table_id", "court_code", "year"]), "court_panel.csv")
    write(coverage(out, courts), "coverage.csv")
    write(CL.court_events(courts, out), "court_events.csv")
    # ---- national series
    ls = pd.read_csv(SER / "long_series.csv")
    need(CATEGORIES, ls.category, "category"); need(INSTANCES, ls.level, "level"); need(METRICS, ls.metric, "metric")
    ns = pd.DataFrame({"year": ls.year, "category_id": ls.category.map(lambda x: CATEGORIES[x][0]),
                       "instance_id": ls.level.map(lambda x: INSTANCES[x][0]), "metric_id": ls.metric.map(lambda x: METRICS[x][0]),
                       "value": ls.value, "unit": "cases", "derived": ls.derived})
    for c in PROV + ["break_flag"]:
        ns[c] = ls[c]
    ns["break_flag"] = ns.break_flag.fillna("")
    ns = CL.add_break_flags(ns, "national_series.csv")
    write(ns, "national_series.csv")
    wide = ns[~ns.metric_id.isin(["pending_computed", "pending_multiyear_table"])].pivot_table(
        index="year", columns=["category_id", "instance_id", "metric_id"], values="value", aggfunc="first")
    wide.columns = ["__".join(c) for c in wide.columns]
    write(wide.reset_index(), "national_series_wide.csv")
    # ---- pending (observed)
    pa = pd.read_csv(SER / "pending_actual.csv")
    need(CATEGORIES, pa.category, "pending category")
    po = pd.DataFrame({"year": pa.year, "category_id": pa.category.map(lambda x: CATEGORIES[x][0]),
                       "filings": pa["접수"], "dispositions": pa["처리"], "pending": pa["미제"],
                       "identity_gap": pa.identity_gap, "identity_gap_pct": pa.identity_gap_pct,
                       "unit": "cases", "source_table_ko": pa.table})
    for c in PROV + ["break_flag"]:
        po[c] = pa[c]
    po["break_flag"] = po.break_flag.fillna("")
    write(po, "pending_observed.csv")
    # ---- detail
    dl = pd.read_csv(SER / "detail_long.csv")
    lab = {**CATEGORIES, **INSTANCES}
    need(TABLES, dl.table, "detail table"); need(lab, dl.label, "detail label"); need(DOMAINS, dl.domain, "domain")
    de = pd.DataFrame({"year": dl.year, "domain_id": dl.domain.map(lambda x: DOMAINS[x][0]), "table_id": dl.table.map(lambda x: TABLES[x][0]),
                       "label_id": dl.label.map(lambda x: lab[x][0]), "metric_id": dl.metric.map(lambda x: METRICS[x][0]),
                       "value": dl.value, "unit": dl.table.map(lambda x: TABLES[x][2])})
    for c in PROV + ["break_flag"]:
        de[c] = dl[c]
    de["break_flag"] = de.break_flag.fillna("")
    de = CL.add_break_flags(de, "detail.csv")
    write(de, "detail.csv")
    # ---- duration
    du = pd.read_csv(SER / "duration_long.csv")
    bmap = {k: b for k, b, *_ in BINS}
    need(DOMAINS, du.domain, "duration domain"); need(INSTANCES, du.level, "duration level"); need(bmap, du.bin, "bin")
    dd = pd.DataFrame({"year": du.year, "domain_id": du.domain.map(lambda x: DOMAINS[x][0]), "instance_id": du.level.map(lambda x: INSTANCES[x][0]),
                       "bin_id": du.bin.map(bmap), "value": du.value,
                       "unit": ["months" if b == "평균처리기간(월)" else ("persons" if d == "형사공판" else "cases") for b, d in zip(du.bin, du.domain)]})
    for c in PROV + ["break_flag"]:
        dd[c] = du[c]
    dd["break_flag"] = dd.break_flag.fillna("")
    dd = CL.add_break_flags(dd, "duration.csv")
    write(dd, "duration.csv")
    source_tables()
    # ---- registries
    sb = pd.read_csv(SER / "structural_breaks.csv")
    sb["filter"] = sb.code.map({
        "civil_single_incl_small_claims_2010": "duration.csv: domain_id=civil_main & instance_id=first_single",
        "mean_months_bin_midpoint_2002_2006": "duration.csv: bin_id=mean_months & year<=2006",
        "stock_flow_gap_2007": "pending_observed.csv: year=2007 & category_id in (civil_main, family_litigation)",
        "overview_receipts_current_year_2004_2006": "pending_observed.csv: year in 2004–2006",
        "pending_spliced_2002_2003": "national_series.csv: metric_id=pending & derived=True",
        "court_new_or_converted": "court_panel.csv: partial_year; courts.csv: legal_start, legal_event"})
    sb["file"] = sb["filter"].str.split(":").str[0]
    sb["filter"] = sb["filter"].replace({"court_panel.csv: partial_year; courts.csv: legal_start, legal_event":
                                         "court_panel.csv: partial_year, pre_establishment; court_events.csv; courts.csv: legal_start, legal_event"})
    meta = {  # code → (break_type, confidence)
        "civil_single_incl_small_claims_2010": ("definition_change", "verified"),
        "mean_months_bin_midpoint_2002_2006": ("method_change", "verified"),
        "stock_flow_gap_2007": ("counting_rule", "suspected"),
        "overview_receipts_current_year_2004_2006": ("table_layout", "verified"),
        "pending_spliced_2002_2003": ("derived_splice", "verified"),
        "court_new_or_converted": ("unbalanced_panel", "verified")}
    sb["break_type"] = sb.code.map(lambda c: meta[c][0]); sb["confidence"] = sb.code.map(lambda c: meta[c][1])
    sb = pd.concat([sb, pd.DataFrame(CL.THRESHOLD_BREAKS)], ignore_index=True)
    for c in ("effective_date", "old_rule", "new_rule", "legal_basis_ko", "legal_basis_en", "expected_effect", "unaffected_alternative"):
        sb[c] = sb[c].fillna("") if c in sb else ""
    sb["row_flagged"] = sb.code.isin(CL.flagged_codes() | {"civil_single_incl_small_claims_2010", "mean_months_bin_midpoint_2002_2006",
                                                          "stock_flow_gap_2007", "overview_receipts_current_year_2004_2006", "pending_spliced_2002_2003"})
    sb = sb[["code", "file", "filter", "from_year", "to_year", "break_type", "confidence", "row_flagged", "effective_date", "old_rule", "new_rule",
             "legal_basis_ko", "legal_basis_en", "expected_effect", "unaffected_alternative", "description", "basis"]]
    assert sb.code.is_unique
    write(sb, "structural_breaks.csv")
    shutil.copyfile(VAL / "correction_log.csv", OUT / "data" / "correction_log.csv")
    shutil.copyfile(ROOT / "data" / "source_manifest.csv", OUT / "data" / "source_manifest.csv")
    for f in ("correction_log.csv", "source_manifest.csv"):  # canonical copies are without BOM
        p = OUT / "data" / f
        p.write_text(p.read_text(encoding="utf-8-sig"), encoding="utf-8")
        shutil.copyfile(p, OUT / "csv_excel" / f)
        (OUT / "csv_excel" / f).write_text(p.read_text(encoding="utf-8"), encoding="utf-8-sig")
    print("  correction_log.csv, source_manifest.csv copied")
    # ---- data dictionary (generated from the actual file columns → error if any column is undocumented)
    D = {
        "year": ("int", "Statistical year (= Yearbook edition year; verified against the tables)"),
        "court_id_h": ("str", "Harmonized court-unit ID (ASCII slug, stable across releases); join key to courts.csv"),
        "court_code": ("int", "Integer surrogate for court_id_h"),
        "court_ko": ("str", "Korean name of the harmonized unit as printed (authoritative)"),
        "court_en": ("str", "English name; see court_en_source"),
        "court_en_source": ("str", "official_scourt_english_site | pattern_court_organization_act (branch/si/gun courts: place name + 'Branch Court of …' / 'Si Court' / 'Gun Court') | author_label (totals)"),
        "romanization": ("str", "Place name in Revised Romanization (branch and si/gun courts)"),
        "unit_type": ("str", "national_total | group_total | high_court | main_court | district_total | branch | si_gun_court — totals coexist with courts; filter before summing"),
        "parent_court_id_h": ("str", "Parent district/family court of a branch, si/gun court or subtotal"),
        "first_year_in_data": ("int", "First year with a non-zero value in court_panel.csv"), "last_year_in_data": ("int", "Last year with a non-zero value in court_panel.csv"),
        "legal_start": ("date", "Statutory effective date of establishment/renaming (YYYY-MM-DD), where annotated"),
        "legal_event": ("str", "established | elevated_from_branch | converted_to_family_court | renamed | renamed_county_to_city | abolished_* | jurisdiction_added | unverified"),
        "predecessor_ko": ("str", "Predecessor court(s), Korean (authoritative)"), "legal_basis_ko": ("str", "Statute and Addenda provision, Korean (authoritative)"),
        "data_note_ko": ("str", "Data caveat (partial year, retroactive relabelling, duplication), Korean"),
        "predecessor_en": ("str", "Predecessor court(s), English"),
        "legal_basis_en": ("str", "Statute and Addenda provision, English. 'Court Organization Act' is the KLRI English title; other act titles are author translations"),
        "data_note_en": ("str", "Data caveat, English"),
        "harmonized_from_ko": ("str", "Source court IDs merged into this unit (Korean, ';'-separated)"),
        "tables_ko": ("str", "Tables in which the unit appears (Korean table codes)"),
        "table_id": ("str", "Table ID; join to tables.csv"), "table_ko": ("str", "Korean table code"), "table_en": ("str", "English table label"),
        "used_in": ("str", "File using the table ID"),
        "value": ("number", "Count (see unit); duration mean_months is in months. Duration bins: time from the filing date at each instance, suspension periods excluded; applying the rule to each instance separately (for appeals, from the date the appeal was filed rather than the date the record reached the appellate court) is the authors' reading of the Yearbook notes"),
        "unit": ("str", "cases | persons (criminal tables count persons/defendants) | months"),
        "source_court_id_ko": ("str", "Court ID as constructed from the source table before harmonization (Korean)"),
        "source_court_label_ko": ("str", "Row label as printed in the source table (Korean, after logged label fixes)"),
        "source": ("str", "Source edition and type as recorded by the build (e.g., 2025_xlsx, 2016_pdf_vision, 2011_pdf) or derivation rule"),
        "source_edition": ("int", "Statistical year of the Yearbook volume the value was taken from, as labelled on the Judicial Statistics Portal; the printed Yearbook carrying it has the following year on its cover (e.g. 2024 = 2025 사법연감). NA for derived values"),
        "source_file": ("str", "Source file, path relative to the dataset's data/ folder as in source_manifest.csv. PDFs: raw/<edition>/pdf/…; "
                               "Excel: xlsx/<edition>/<volume>/… = workbook extracted from the zip archive raw/<edition>/excel/… listed in source_manifest.csv. Empty for derived values"),
        "source_page": ("str", "Location within source_file. PDF: 'p<n>' = 1-based page of that file (exact page, one model call per page or text-layer parsing); "
                               "'p<a>-<b> (pages sent together)' = page range when several pages were read in one model call (detail and duration PDF tables). "
                               "Excel: '<sheet>!r<row>' (1-based row) or '<sheet>!r<a>-r<b>' (table block). Empty for derived values"),
        "source_locator": ("str", "Location within source_file as recorded at extraction: 'p<n>' (PDF page), 'p<n> (left column)', 'p<a>-<b> (pages sent together)' (pages sent in one model request), '<sheet>!r<row>' or '<sheet>!r<a>-r<b>' (Excel). Empty for derived values"),
        "page_start": ("int", "First PDF page (1-based) that may contain the value; empty for Excel and derived values"),
        "page_end": ("int", "Last PDF page that may contain the value; equals page_start when the page is exact"),
        "exact_page": ("bool", "True if the value's page is known exactly (one page per request, or located uniquely in the text layer within a multi-page request); False if only the request's page range is known; empty for Excel/derived"),
        "locator_note": ("str", "How page_start/page_end were determined"),
        "extraction_method": ("str", "excel (cells parsed by rule) | excel_llm_structured (duration tables 2019–2025 eds.: the Excel cell grid was passed as text to a language model, which returned the table structure; every value was checked to occur in the source cell block) | pdf_text_layer | pdf_image_vlm (page image read by a vision-language model) | derived"),
        "correction_status": ("str", "none | corrected_value | corrected_label (see correction_log.csv). No released value is left with an unresolved validation warning"),
        "source_type": ("str", "digital (excel, excel_llm_structured, pdf_text_layer: the value comes from machine-readable source content) | ocr (pdf_image_vlm: the value depends on reading a page image) | derived (computed)"),
        "qc_flag": ("str", "ocr_corrected_manual (value corrected after reading the source page; see correction_log.csv) | empty. "
                              "The build would set district_sum_mismatch / national_sum_mismatch on OCR values in a block failing the subtotal check after corrections; none remain"),
        "partial_year": ("bool", "True in the establishment year of a court established on a date other than 1 January"),
        "dup_flag": ("str", "duplicates_namyangju_si_court: Namyangju branch small claims 2018–2021 restate the Namyangju si court row"),
        "break_flag": ("str", "Codes (';'-separated) of every structural break whose affected rows include this row; see structural_breaks.csv. Empty = no break applies"),
        "pre_establishment": ("bool", "True if the row is for a year before the unit existed (or, for appellate and IP tables, before it had that jurisdiction). "
                                      "The Yearbook's 10-year tables print such years as 0, which means 'not yet existing', not 'no filings'. "
                                      "Exceptions with non-zero values restate a predecessor's caseload (Namyangju, Masan; see courts.csv data_note_en)"),
        "translation_note_en": ("str", "Translation note for labels whose English is a functional translation, or usage note for tables affected by jurisdiction changes"),
        "event_id": ("str", "Event ID (ev001, …), ordered by date"), "event_date": ("date", "Effective date (YYYY-MM-DD)"),
        "event_year": ("int", "Year of event_date"), "in_data_period": ("bool", "True if the event took effect in 2002–2025"),
        "event_type": ("str", "high_court_jurisdiction_split | branch_created_from_parent | bankruptcy_court_created | converted_to_family_court | "
                              "elevated_from_branch | renamed | abolished_absorbed | jurisdiction_added"),
        "from_court_id_h": ("str", "Unit(s) the jurisdiction or caseload came from (';'-separated court_id_h); equals to_court_id_h for renaming; empty if not a single unit"),
        "to_court_id_h": ("str", "Unit receiving the jurisdiction or caseload (for abolition: the absorbing unit)"),
        "affected_parent_court_id_h": ("str", "Unit whose series falls at the event (empty if no released series is affected)"),
        "case_scope": ("str", "Case types concerned by the event"),
        "tables_affected": ("str", "Tables (table_id, ';'-separated) in which to_court_id_h has non-zero values"),
        "affects_parent_series": ("bool", "True if the event moves caseload out of a unit that remains in the panel (a break in that unit's series)"),
        "recommended_user_action": ("str", "How to obtain a comparable series across the event"),
        "note_en": ("str", "Data note on the receiving unit (courts.csv data_note_en)"),
        "break_type": ("str", "jurisdiction_threshold | jurisdiction_transfer | jurisdiction_rule | definition_change | method_change | counting_rule | "
                              "table_layout | derived_splice | unbalanced_panel | unexplained_level_shift | statutory_case_type_addition | case_mix_change"),
        "confidence": ("str", "verified (statute text or Yearbook note checked) | suspected (cause inferred, legal basis not fully confirmed) | observed_only (level shift; no cause found)"),
        "row_flagged": ("bool", "True if the code is written into break_flag of the affected rows; False = registry/context entry only (no row flag)"),
        "effective_date": ("str", "Effective date(s) of the rule change, ';'-separated (empty if none)"),
        "old_rule": ("str", "Rule before the change"), "new_rule": ("str", "Rule after the change"),
        "legal_basis_ko": ("str", "Legal basis, Korean (authoritative)"),
        "expected_effect": ("str", "Expected or observed effect on the released series"),
        "unaffected_alternative": ("str", "Series not affected by the break"),
        "category_id": ("str", "Case category; join to categories.csv"), "category_ko": ("str", "Korean label"), "category_en": ("str", "English label"),
        "instance_id": ("str", "Instance level; join to instances.csv"), "instance_ko": ("str", "Korean label"), "instance_en": ("str", "English label"),
        "metric_id": ("str", "filings | dispositions | pending | pending_computed | pending_multiyear_table; join to metrics.csv"),
        "metric_ko": ("str", "Korean label"), "metric_en": ("str", "English label"),
        "derived": ("bool", "True if the value is computed rather than read from a table"),
        "filings": ("int", "Filings (current-year receipts)"), "dispositions": ("int", "Dispositions"), "pending": ("int", "Pending at year end (observed)"),
        "identity_gap": ("number", "pending_t − (pending_{t−1} + filings_t − dispositions_t)"), "identity_gap_pct": ("number", "identity_gap as a percentage of pending_t, in percentage points (-2.7 = -2.7%)"),
        "source_table_ko": ("str", "Title of the source overview table as printed (Korean)"),
        "domain_id": ("str", "Case domain; join to domains.csv"), "domain_ko": ("str", "Korean label"), "domain_en": ("str", "English label"),
        "label_id": ("str", "Row label (category or instance) of the detailed table"),
        "bin_id": ("str", "Duration bin; join to duration_bins.csv on (domain_id, bin_id)"), "bin_ko": ("str", "Korean label"), "bin_en": ("str", "English label"),
        "upper_month": ("int", "Upper bound in months (empty for the open-ended bin and for total/mean)"), "bin_type": ("str", "count | total | mean"),
        "sort_order": ("int", "Display order within the domain"),
        "lower_month": ("int", "Lower bound in months (exclusive; 0 for the first bin). '1년이내' starts at 6 months for civil/family and at 9 months for criminal tables"),
        "lower_inclusive": ("bool", "False: a case at exactly the lower bound belongs to the preceding bin"),
        "upper_inclusive": ("bool", "True: '…이내' (within) includes the upper bound"), "open_ended": ("bool", "True for '2년초과' (more than 24 months)"),
        "dataset": ("str", "Release fact table"), "key_column": ("str", "Column identifying the table/series in that file"), "key": ("str", "Value of key_column"),
        "location_span": ("str", "PDF pages (first-last) or Excel sheet(s) holding the values"), "n_values": ("int", "Released values from this source block"),
        "title_rule": ("str", "Regular expression (on whitespace-stripped text) that identifies the table title; the same rule the build used to locate the table"),
        "printed_title_ko": ("str", "Title text matched by title_rule in the source (PDF text layer, whitespace removed; or Excel title cell); ' ; ' separates several matches (e.g. continued tables)"),
        "title_evidence": ("str", "Where printed_title_ko was read"),
        "title_seen_by_model": ("str", "Title the model reported seeing on the page (court panel: title guard; overview tables); empty if not requested"),
        "continuation_pages": ("str", "Untitled continuation pages accepted by rule (small-claims 4-page tables)"),
        "present": ("bool", "True if court_panel.csv has a row for this court unit, table and year"),
        "coverage_status": ("str", "present | present_before_establishment (row is a printed zero for a year before the unit existed; pre_establishment=True) | "
                                   "predecessor_reported_under_successor (row holds a predecessor court's caseload that a later edition restates under this unit; pre_establishment=True; see courts.csv data_note_en) | unit_not_in_table (the unit is never a row of this table) | before_establishment (year before the statutory establishment, or before the unit acquired the jurisdiction of the table, e.g. the Patent Court in civil_main_appeal before 2016) | "
                                   "not_yet_reported (unit and jurisdiction exist but the table has no row for it yet; no rows in this release) | after_abolition | "
                                   "reported_under_other_unit (caseload printed under another row; see courts.csv data_note_en). No row is missing because of extraction failure"),
        "note": ("str", "Statutory event and date, or first/last year of the unit in the table"),
        "code": ("str", "Break/issue code"), "file": ("str", "Affected file"), "filter": ("str", "Rows affected"),
        "from_year": ("int", "First affected year"), "to_year": ("int", "Last affected year"),
        "description": ("str", "Description"), "basis": ("str", "Evidence"),
    }
    dd_rows = []
    for f in sorted((OUT / "data").glob("*.csv")):
        if f.name in ("correction_log.csv", "source_manifest.csv"):
            continue
        cols = pd.read_csv(f, nrows=0).columns
        if f.name == "national_series_wide.csv":
            dd_rows.append(dict(file=f.name, column="year", type="int", description=D["year"][1]))
            dd_rows.append(dict(file=f.name, column="<category_id>__<instance_id>__<metric_id>", type="number",
                                description="Wide view of national_series.csv (pending_computed/multiyear excluded)"))
            continue
        for c in cols:
            assert c in D, f"undocumented column {f.name}:{c}"
            dd_rows.append(dict(file=f.name, column=c, type=D[c][0], description=D[c][1]))
    for fname in ("correction_log.csv", "source_manifest.csv"):
        cols = DOC_COLS[fname]
        actual = list(pd.read_csv(OUT / "data" / fname, nrows=0).columns)
        assert actual == list(cols), (fname, actual)
        for c, (t, d) in cols.items():
            dd_rows.append(dict(file=fname, column=c, type=t, description=d))
    for c, d in {"file": "File (validation files prefixed validation/)", "column": "Column name", "type": "int | number | str | bool | date",
                 "description": "Meaning, codes and units"}.items():
        dd_rows.append(dict(file="data_dictionary.csv", column=c, type="str", description=d))
    for c, d in INV_COLS.items():
        dd_rows.append(dict(file="file_inventory.csv", column=c, type="int" if c in ("rows", "columns") else "str", description=d))
    copy_supporting()
    for f in sorted((OUT / "validation").glob("*.csv")):
        for c in pd.read_csv(f, nrows=0).columns:
            t, d = vdesc(c)
            dd_rows.append(dict(file="validation/" + f.name, column=c, type=t, description=d))
    write(pd.DataFrame(dd_rows), "data_dictionary.csv")

    # ---- checks
    for f in (OUT / "data").glob("*.csv"):
        b = f.read_bytes()
        assert not b.startswith(b"\xef\xbb\xbf"), f
    for name, df in [("court_panel", out), ("national_series", ns), ("detail", de), ("duration", dd), ("pending_observed", po)]:
        idcols = [c for c in df.columns if c.endswith("_id") or c == "court_id_h"]
        for c in idcols:
            bad = df[c].dropna().astype(str)
            assert bad.map(str.isascii).all(), (name, c)
    write_readme_with_schema()
    for f in ("CHANGELOG.md", "KNOWN_ISSUES.md", "CITATION.cff", "LICENSE_DATA.md", "LICENSE_CODE"):
        shutil.copyfile(ROOT / "release_template" / f, OUT / f)
    release_checks()
    print("checks: no BOM in release/data, all ID columns ASCII, row counts preserved; README copied")


def coverage(panel, courts):
    """Reason each row is absent in the full court-panel grid (unit × table × year) (advisor review, Round 4 #16)."""
    g = pd.MultiIndex.from_product([courts.court_id_h, sorted(panel.table_id.unique()), range(2002, 2026)],
                                   names=["court_id_h", "table_id", "year"]).to_frame(index=False)
    g = g.merge(panel[["court_id_h", "table_id", "year", "pre_establishment", "value"]].assign(present=True), how="left")
    g["present"] = g.present.fillna(False).astype(bool)
    span = panel.groupby(["court_id_h", "table_id"]).year.agg(t0="min", t1="max").reset_index()
    g = g.merge(span, how="left")
    leg = courts.set_index("court_id_h")
    ly = pd.to_numeric(leg.legal_start.astype(str).str[:4], errors="coerce")
    st, note = [], []
    for r in g.itertuples(index=False):
        ev = leg.at[r.court_id_h, "legal_event"] if r.court_id_h in leg.index else ""
        y0 = ly.get(r.court_id_h)
        if r.present and r.pre_establishment is True and r.value == 0:
            st.append("present_before_establishment"); note.append("printed zero for a year before the unit (or its jurisdiction) existed")
        elif r.present and r.pre_establishment is True:
            st.append("predecessor_reported_under_successor")
            note.append(CL.RESTATED_NONZERO.get((r.court_id_h, r.table_id)) or CL.RESTATED_NONZERO.get(
                next(((c, t) for c, t in CL.RESTATED_NONZERO if c == r.court_id_h), None), "predecessor caseload restated under this unit"))
        elif r.present:
            st.append("present"); note.append("")
        elif pd.isna(r.t0):
            st.append("unit_not_in_table"); note.append("the unit is never a row of this table (e.g., si/gun courts appear only in small claims; appellate tables list courts with appellate divisions)")
        elif r.year < r.t0:
            jd = CL.JURISDICTION_START.get((r.court_id_h, r.table_id))
            if jd and r.year < int(jd[:4]):
                st.append("before_establishment"); note.append(f"before the unit acquired the jurisdiction of this table ({jd}); court established {leg.at[r.court_id_h, 'legal_start']}")
            elif pd.notna(y0) and r.year < y0 and str(ev).startswith(("established", "elevated")):
                st.append("before_establishment"); note.append(f"{ev} {leg.at[r.court_id_h, 'legal_start']}")
            else:
                st.append("not_yet_reported"); note.append(f"first row in this table {int(r.t0)}" + (f"; {ev} {leg.at[r.court_id_h, 'legal_start']}" if ev else ""))
        elif r.year > r.t1:
            if str(ev).startswith("abolished") and (pd.isna(y0) or r.year >= y0):
                st.append("after_abolition"); note.append(f"{ev} {leg.at[r.court_id_h, 'legal_start']}")
            else:
                st.append("reported_under_other_unit"); note.append(f"last row in this table {int(r.t1)}; see courts.csv data_note_en")
        else:
            raise AssertionError(f"inner gap {r}")
    g["coverage_status"], g["note"] = st, note
    out = g[["court_id_h", "table_id", "year", "present", "coverage_status", "note"]]
    print("  coverage:", out.coverage_status.value_counts().to_dict())
    return out


# ---- source_tables.csv: metadata per source edition × table (advisor review, Round 4 #14)
OVERVIEW_RX = r"[가-힣()·∙ㆍ]{2,30}접수[·∙ㆍ,]?처리[·∙ㆍ,]?미제(?:건수|상황|인원)\(표\d+\)"


def _title_rule(fname, key):
    import build_courts as bc_
    import build_detail as bdet
    import build_duration as bdur
    if fname == "court_panel.csv":
        ko = next(k for k, v in TABLES.items() if v[0] == key)
        return bc_.TABLES[ko][2]
    if fname == "detail.csv":
        ko = next(k for k, v in TABLES.items() if v[0] == key)
        return bdet.TABLES[ko][5]
    if fname == "duration.csv":
        ko = next(k for k, v in DOMAINS.items() if v[0] == key)
        return bdur.TABLES[ko][1]
    if fname == "pending_observed.csv":
        return OVERVIEW_RX
    return r"전체사건(?:누년비교)?(?:1\.)?총괄|1\.총괄"


def _nz(t):
    return re.sub(r"\s+", "", t or "")


def _pdf_titles(rel_file, pages, rx):
    import fitz
    doc = fitz.open(ROOT / "data" / rel_file)
    hits, pg = [], []
    for p in pages:
        if p <= len(doc):
            for m in re.finditer(rx, _nz(doc[p - 1].get_text())):
                hits.append(m.group(0)); pg.append(p)
    return list(dict.fromkeys(hits)), sorted(set(pg))


def _xlsx_titles(rel_file, sheets, rx):
    import openpyxl
    wb = openpyxl.load_workbook(ROOT / "data" / rel_file, read_only=True, data_only=True)
    hits = []
    for sh in sheets:
        for row in wb[sh].iter_rows(max_col=4, values_only=True):
            for c in row:
                if isinstance(c, str) and re.search(rx, _nz(c)):
                    hits.append(re.sub(r"\s+", " ", c.strip()))
    return list(dict.fromkeys(hits))


def _model_titles():
    """(pdf, page) → title_seen / title returned by the model (court panel, overview tables)."""
    out = {}
    cache = ROOT / "data" / "ocr_cache_backup"
    for line in (ROOT / "data" / "validation" / "model_calls.jsonl").read_text(encoding="utf-8").splitlines():
        x = json.loads(line)
        if x["model"] != "gpt-5.5" or len(x["images"]) != 1:
            continue
        r = json.loads((cache / f"{x['cache_key']}.json").read_text(encoding="utf-8"))
        t = r.get("title_seen") or r.get("title") or ""
        if t:
            im = x["images"][0]
            out.setdefault((im["pdf"], im["page"]), set()).add(re.sub(r"\s+", " ", t.strip()))
    return out


def source_tables():
    MT = _model_titles()
    specs = [("court_panel.csv", "table_id"), ("national_series.csv", "category_id"), ("pending_observed.csv", "category_id"),
             ("detail.csv", "table_id"), ("duration.csv", "domain_id")]
    rows = []
    for fname, key in specs:
        d = pd.read_csv(OUT / "data" / fname, dtype=str, keep_default_na=False)
        d = d[d.extraction_method != "derived"]
        for (k, ed, f, em), g in d.groupby([key, "source_edition", "source_file", "extraction_method"]):
            rx = _title_rule(fname, k)
            if fname == "pending_observed.csv":
                cat_rx = next(v for kk, v in __import__("build_detail").CATS.items() if CATEGORIES.get(kk, ("",))[0] == k)[0]
                rx_use = rf"(?:{cat_rx})[가-힣()·∙ㆍ]{{0,20}}접수[·∙ㆍ,]?처리[·∙ㆍ,]?미제(?:건수|상황|인원)\(표\d+\)"
            else:
                rx_use = rx.replace("-", "[-－–]")  # the source text mixes in full-width hyphens
            locs = sorted(set(g.source_locator))
            if f.endswith(".pdf"):
                pages = sorted({int(p) for a, b in zip(g.page_start, g.page_end) if a for p in range(int(a), int(b) + 1)})
                span = f"p{pages[0]}-{pages[-1]}" if len(pages) > 1 else f"p{pages[0]}"
                hits, hp = _pdf_titles(f, pages, rx_use)
                seen = " ; ".join(sorted(set().union(*[MT.get((f, p), set()) for p in pages]))) if em == "pdf_image_vlm" and fname in ("court_panel.csv", "pending_observed.csv") else ""
                ev = (f"title rule matched in PDF text layer on {', '.join(f'p{p}' for p in hp)}" if hits else
                      ("title rule not matched in text layer (scrambled or missing); model-reported title" if seen else "title rule not matched in text layer"))
                cont = "p11, p13 (untitled; accepted by continuation rule)" if fname == "court_panel.csv" and k == "civil_main_1st_small_claims" else ""
                printed = " ; ".join(hits)
            else:
                sheets = sorted({l.split("!")[0] for l in locs})
                span = "; ".join(f"sheet {s}" for s in sheets)
                hits = _xlsx_titles(f, sheets, rx_use)
                printed, seen, cont = " ; ".join(hits), "", ""
                ev = "title rule matched in Excel cell" if hits else "title rule not matched in sheet"
            rows.append(dict(dataset=fname, key_column=key, key=k, source_edition=ed, source_file=f, extraction_method=em,
                             location_span=span, n_values=len(g), title_rule=rx_use, printed_title_ko=printed, title_evidence=ev,
                             title_seen_by_model=seen, continuation_pages=cont))
    st = pd.DataFrame(rows)
    write(st, "source_tables.csv")
    print("  source_tables: printed title matched", int((st.printed_title_ko != "").sum()), "/", len(st),
          "; model title only", int(((st.printed_title_ko == "") & (st.title_seen_by_model != "")).sum()))
    return st

# ---- column dictionary for documentation and validation files (advisor review, Round 4 #4: one row per column)
DOC_COLS = {
    "correction_log.csv": {
        "log_id": ("int", "Entry number"),
        "log_type": ("str", "released_data_correction (a released value or label was changed) | harmonization_decision (two source names mapped to one court unit) | "
                            "pipeline_configuration (a build rule: page override, continuation pages, re-running a check) | superseded_ocr_error (OCR error in a cell whose released value comes from a digital source) | "
                            "source_to_source_discrepancy (two official sources print different values) | "
                            "official_source_table_error (an official table prints a value shown to be wrong by the same edition's other tables and later editions; the corrected value is released)"),
        "file": ("str", "Working file the entry applies to (court_panel_long.csv = release court_panel.csv; detail_long.csv = detail.csv; pending_actual.csv = pending_observed.csv; long_series.csv = national_series.csv)"),
        "table": ("str", "Korean table code as in tables.csv table_ko, or '(all)' / '(any)'"),
        "court_id": ("str", "Source court ID (Korean, district/court) where applicable"),
        "year": ("int", "Statistical year, if the entry concerns one year"),
        "field": ("str", "What was changed: value, court (label), court_id_h, source page(s), qc_flag"),
        "action": ("str", "corrected_value | corrected_label | harmonized_id | page_override | continuation_pages | qc_recheck | ocr_error_superseded | source_difference"),
        "original": ("str", "Value or label before the decision"),
        "corrected": ("str", "Value or label after the decision (for superseded OCR errors: the digital value used)"),
        "evidence": ("str", "Evidence (source page, text layer, identity, statute)"),
        "detected_by": ("str", "Check that found the issue (see validation/validation_protocol.md)"),
        "applied_in": ("str", "Script and rule implementing the decision"),
        "date": ("date", "Date of the decision (YYYY-MM-DD)"),
        "affects_released": ("bool", "True if released rows differ from what the extraction alone would give (changed values or labels, merged IDs, pages read, flags). "
                                     "False for superseded OCR errors and source-to-source discrepancies, where the released value comes from a digital source"),
    },
    "source_manifest.csv": {
        "edition": ("int", "Yearbook edition (= statistical year)"),
        "title": ("str", "Volume title as listed on the Judicial Statistics Portal (Korean)"),
        "kind": ("str", "pdf | excel (zip archive of Excel workbooks) | dscr (Excel workbook downloaded separately)"),
        "file": ("str", "Path relative to the dataset's data/ folder; source_file in fact tables refers to these paths (Excel: workbook extracted from the zip)"),
        "bytes": ("int", "File size in bytes"),
        "sha256": ("str", "SHA-256 checksum of the downloaded file"),
        "downloaded": ("date", "Download date (YYYY-MM-DD)"),
        "pdf_pages": ("int", "Number of PDF pages (empty for non-PDF files)"),
        "pages_text_ok": ("int", "Pages whose text layer is readable: at least 20 characters, more than 90% of them Hangul/ASCII/CJK/full-width/common symbols. Every page is classified. ok means the characters are valid; it does not guarantee reading order (e.g. 2016 edition text is emitted column by column; validation/text_layer_handcheck.csv)"),
        "pages_broken": ("int", "Pages with text but broken encoding (allowed-character share 90% or less)"),
        "pages_no_text": ("int", "Pages with fewer than 20 text characters (scanned images, blank or figure pages)"),
        "text_layer": ("str", "File status from the page counts: text_layer (90% or more pages ok) | no_text_layer(scanned) (50% or more pages without text) | broken_encoding (50% or more pages broken) | mixed | n/a (not a PDF)"),
        "portal": ("str", "Portal page listing the file"),
        "retrieval": ("str", "How the file was obtained: listing row title and download button on the portal page; the listing is loaded by a POST request; scrape_scourt.py automates it"),
    },
}
EDITION_COL = re.compile(r"^(\d{4})_(xlsx|pdf_vision|pdf)$")
EDITION_KIND = {"xlsx": "Excel", "pdf_vision": "PDF page image, model-read", "pdf": "PDF text layer"}
VCOLS = {
    "table": ("str", "Korean table code (tables.csv table_ko) or domain/level"),
    "court_id": ("str", "Source court ID (Korean, district/court)"),
    "year": ("int", "Statistical year"),
    "pair": ("str", "The two editions compared"),
    "n_cells": ("int", "Cells compared"),
    "disagree": ("int", "Cells whose values differ"),
    "rate_%": ("number", "disagree / n_cells, percent"),
    "ci95_lo_%": ("number", "Wilson 95% interval, lower bound, percent"),
    "ci95_hi_%": ("number", "Wilson 95% interval, upper bound, percent"),
    "ocr_source": ("str", "Edition and method of the OCR value"),
    "ocr": ("number", "OCR value"),
    "ref": ("number", "Digital comparator value (Excel)"),
    "kind": ("str", "Discrepancy type: digit_1 (one digit) | transposition | other"),
    "dataset": ("str", "court_panel | duration | pending(개황) (overview totals) | detail"),
    "domain": ("str", "Case domain (Korean)"),
    "level": ("str", "Instance level (Korean) or check level: district | group | national"),
    "bin": ("str", "Duration bin (Korean)"),
    "metric": ("str", "Metric (Korean)"),
    "edition": ("int", "Edition of the OCR value"),
    "pdf_type": ("str", "Text-layer status of the PDF page"),
    "error": ("bool", "True = values differ by 0.5 or more"),
    "group": ("str", "Subset summarized; in the census file, printed group total the court belongs to"),
    "errors": ("int", "Discrepancies"),
    "error_rate_%": ("number", "errors / n_cells, percent"),
    "n_digit_1": ("int", "Discrepancies differing in one digit"),
    "n_transposition": ("int", "Discrepancies with transposed digits"),
    "n_other": ("int", "Other discrepancies"),
    "source": ("str", "Source edition and method, e.g. 2011_pdf_vision, 2025_xlsx"),
    "sum_bins": ("number", "Sum of duration bin counts"),
    "total": ("number", "Printed total"),
    "ok": ("bool", "True if the check passes (|difference| < 0.5)"),
    "value": ("number", "Released or extracted value"),
    "source_file": ("str", "Source file (relative to data/)"),
    "source_page": ("str", "Location in source file"),
    "found_in_source_block": ("bool", "True if the value occurs among the numbers of the source Excel cell block"),
    "printed_mean_months": ("number", "Mean disposition time as printed (months)"),
    "midpoint_mean_months": ("number", "Mean recomputed from the bins with the Yearbook's representative values"),
    "diff": ("number", "Printed minus recomputed, or reported minus sum of parts"),
    "match_midpoint": ("bool", "|diff| < 0.15"),
    "source_edition": ("int", "Edition of the value"),
    "check": ("str", "Check name"),
    "subset": ("str", "Source and level checked"),
    "pass": ("int", "Checks passed"),
    "n": ("int", "Checks run"),
    "pass_%": ("number", "pass / n, percent"),
    "label": ("str", "Row label (Korean)"),
    "category": ("str", "Case category (Korean)"),
    "agree": ("bool", "True if all editions reporting the cell give the same value"),
    "id": ("int", "Sample cell ID"),
    "row": ("str", "Row label as extracted (Korean)"),
    "district": ("str", "Parent district court (Korean)"),
    "ocr_value": ("number", "Extracted value under check"),
    "stratum": ("str", "Sampling stratum"),
    "page_ref": ("str", "Page images / location given to readers"),
    "note": ("str", "Note"),
    "pdf_page": ("int", "PDF page number (viewer page, not printed page number)"),
    "auto_page_label": ("str", "Automatic text-layer page label: ok | broken | none (source_manifest.csv rule)"),
    "human_page_label": ("str", "Label given by a person after copying text from the PDF viewer: ok | broken | none"),
    "human_agrees": ("str", "Y if the human label equals the automatic label, else N"),
    "observation": ("str", "What the copied text looked like (e.g. reading order)"),
    "checked_on": ("date", "Date of the hand check"),
    "check_method": ("str", "How the page was checked"),
    "tl_pages": ("str", "PDF pages searched by the text-layer parser"),
    "tl_value": ("number", "Value found in the PDF text layer"),
    "tl_status": ("str", "match | mismatch | not_found | no_text_layer"),
    "visual_value": ("number", "Independent model (Claude) reading, blind to the extracted value"),
    "visual_note": ("str", "Page/table where the model reading was made"),
    "verified_value": ("number", "Text-layer value if it matched, otherwise the model reading"),
    "verifier": ("str", "pdf_text_layer | claude_visual"),
    "human_value": ("number", "Blind human reading"),
    "unreadable": ("str", "'O' = human marked the cell unreadable or not found"),
    "human_note": ("str", "Human reader's note"),
    "unit_type": ("str", "Court unit type (see court_panel.csv)"),
    "court_id_h": ("str", "Harmonized court ID (Korean form used at extraction time)"),
    "label_error": ("bool", "True if the extracted row label does not exist on the page"),
    "court": ("str", "Court label (Korean)"),
    "source_type": ("str", "digital | ocr"),
    "qc_flag": ("str", "QC flag at the time of the census"),
    "fix_note": ("str", "Manual correction note"),
    "harmonize_note": ("str", "Harmonization note"),
    "reported": ("number", "Printed subtotal or total"),
    "sum_of_parts": ("number", "Sum of member rows"),
    "cells": ("int", "Cells or checks covered"), "source_pages": ("int", "Distinct source PDF pages covered (edition × page)"),
    "blocks": ("int", "Edition × table blocks covered"), "blocks_with_discrepancy": ("int", "Blocks with at least one discrepancy or failed check"),
    "discrepancies": ("int", "Discrepancies or failed checks"), "corrected_in_release": ("int", "Values corrected in the release as a result"),
    "released_values_affected": ("int", "Released values that differ because of the finding"), "block": ("str", "Edition × table (or edition pair × table)"),
    "pages": ("int", "Source pages of the block (model-read pages, or pages of the sampled cells)"),
    # ocr_value_support.csv and title_unverified_blocks.csv (review panel, Round 1)
    "file": ("str", "Fact table of the value (court_panel.csv | detail.csv | duration.csv | pending_observed.csv)"),
    "key": ("str", "Row key within the file, '|'-joined: table_id|court_id_h (court panel), table_id|label_id|metric_id (detail), domain_id|instance_id|bin_id (duration), category_id|metric (pending_observed)"),
    "source_locator": ("str", "Location within source_file as in the fact table"),
    "second_source": ("str", "agree | disagree: another edition reports the same cell (overlap files) and its value agrees or not | none: no other edition reports it"),
    "text_layer": ("str", "present: the value occurs as a numeric string in the PDF text layer of its page(s) | present_trivial: present, but a one-digit value | zero: printed as '-', not testable | broken_text: the file's text layer is mis-encoded | no_text: no text layer. Presence does not establish row or column position"),
    "reread_sample": ("bool", "True if the cell was in a re-reading sample (linked on file, row key, year and source edition)"),
    "text_layer_position": ("str", "agree | disagree: the table was rebuilt from the PDF text-layer word coordinates and the word at the value's row and column equals the value or not (positional check) | none: not checked (overview tables)"),
    "n_paths": ("int", "Number of independent paths passed: second_source = agree, text_layer = present, reread_sample, text_layer_position = agree"),
    "table_id": ("str", "Table ID; join to tables.csv"),
    "location_span": ("str", "Pages of the source block"),
    "released_values": ("int", "Released values from the block"),
    "years": ("str", "Statistical years of the released values"),
    "text_layer_present": ("int", "Released values found in the text layer of the pages sent"),
    "second_edition_cells": ("int", "Released values that another edition also reports"),
    "second_edition_agree": ("int", "Of these, values that agree"),
    "comparator": ("str", "Edition used as the second source"),
    "comparator_title_evidence": ("str", "Printed-title evidence of the comparator's table"),
    "arithmetic_check": ("str", "Result of the printed total-row identity, if the table has a total row"),
    "title_from_word_coordinates": ("str", "Printed table title recovered from the text-layer word coordinates"),
    "position_agree": ("int", "Released values of the block whose row and column position agrees with the text layer"),
    # positional checks (review, 2026-11-20)
    "domain_id": ("str", "Duration domain; join to domains.csv"), "instance_id": ("str", "Instance; join to instances.csv"),
    "bin_id": ("str", "Duration bin; join to duration_bins.csv"), "label_id": ("str", "Row label of the detailed table"),
    "metric_id": ("str", "Metric; join to metrics.csv"), "source_court_id_ko": ("str", "Source court identifier (Korean) as in court_panel.csv"),
    "page": ("int", "Source page"), "correction_status": ("str", "correction_status of the released value"),
    "rule_cell": ("str", "Excel cell (row and column) at the released value's position, found by rules from the row and column headers"),
    "rule_value": ("number", "Value of that cell"),
    "title_in_text_layer": ("str", "Printed table title found in the text layer by word coordinates"),
    "text_layer_value": ("number", "Text-layer word at the released value's row and column ('-' read as 0); empty if no word was found there"),
    "position_agrees": ("bool", "True if the value at the released position equals the released value"),
    "printed_table": ("str", "Printed table number on the page"), "printed_value": ("number", "Value printed in the cell, read from the page image"),
    "instance_rows": ("str", "Printed instance rows of the same column, whose sum is the cell"),
    "agrees": ("bool", "True if the released value equals the printed value"),
    "instance_rows_sum_equals": ("bool", "True if the printed instance rows sum to the printed value"),
    "reader": ("str", "Who read the page image, when and how"),
}


def vdesc(c):
    m = EDITION_COL.match(c)
    if m:
        return "number", f"Value read from the {m.group(1)} edition ({EDITION_KIND[m.group(2)]})"
    assert c in VCOLS, f"undocumented validation column {c}"
    return VCOLS[c]


# ---- per-file schema (inserted into README + file_inventory.csv)
SCHEMA = {  # file: (role, grain, primary key, unit, values, caveats)
    "national_series.csv": ("fact", "category × instance × metric × year", "category_id, instance_id, metric_id, year", "cases (criminal: persons)", "observed + derived (`derived`)", "pending 2002–03 spliced"),
    "national_series_wide.csv": ("convenience", "year", "year", "as national_series", "view of national_series", "generated view; not authoritative"),
    "pending_observed.csv": ("fact", "category × year", "category_id, year", "cases (criminal: persons)", "observed; identity_gap derived", "2004–06 receipts = current-year"),
    "detail.csv": ("fact", "table × label × metric × year", "table_id, label_id, metric_id, year", "cases (criminal: persons)", "observed", "family total level shift 2016"),
    "court_panel.csv": ("fact", "court unit × table × year", "court_id_h, table_id, year", "cases (criminal: persons)", "observed; civil_main_1st_total derived",
                        "filings only; totals coexist with courts; unbalanced; collegiate/single/small-claims split changes with jurisdiction thresholds (break_flag); printed zeros before establishment (pre_establishment)"),
    "court_events.csv": ("documentation", "court establishment, split, conversion, renaming or abolition", "event_id", "", "", "links units by court_id_h; see recommended_user_action"),
    "duration.csv": ("fact", "domain × instance × bin × year", "domain_id, instance_id, bin_id, year", "cases/persons; mean in months", "observed (mean as printed)", "mean method changes 2007; single-judge incl. small claims from 2010"),
    "courts.csv": ("lookup", "harmonized court unit", "court_id_h", "", "", "legal dates only for units changed 2002–2025"),
    "tables.csv": ("lookup", "table", "table_id", "", "", ""),
    "categories.csv": ("lookup", "case category", "category_id", "", "", ""),
    "instances.csv": ("lookup", "instance level", "instance_id", "", "", ""),
    "metrics.csv": ("lookup", "metric", "metric_id", "", "", ""),
    "domains.csv": ("lookup", "case domain", "domain_id", "", "", ""),
    "duration_bins.csv": ("lookup", "domain × duration bin", "domain_id, bin_id", "months", "", "bin sets differ by domain; join on domain_id and bin_id"),
    "structural_breaks.csv": ("documentation", "break or definition issue", "code", "", "", "referenced by break_flag"),
    "correction_log.csv": ("documentation", "logged decision", "log_id", "", "", "not all entries are data errors (see log_type)"),
    "source_manifest.csv": ("documentation", "downloaded source file", "file", "", "", "source files are not redistributed"),
    "data_dictionary.csv": ("documentation", "file × column", "file, column", "", "", ""),
    "source_tables.csv": ("documentation", "dataset × key × source edition × source file × method", "dataset, key, source_edition, source_file, extraction_method", "", "", "printed table titles and title-check evidence"),
    "coverage.csv": ("documentation", "court unit × table × year (full grid)", "court_id_h, table_id, year", "", "", "explains every absent court_panel row"),
    "file_inventory.csv": ("documentation", "file", "file", "", "", "this table"),
}


INV_COLS = {"file": "Path within the release", "role": "fact | lookup | documentation | convenience",
            "rows": "Number of data rows", "columns": "Number of columns", "grain": "What one row represents",
            "primary_key": "Columns that uniquely identify a row (checked)", "years": "Range of `year` (fact and convenience tables)",
            "unit": "Unit of the values", "values": "Observed vs derived values", "caveats": "Main caveats"}


def file_inventory():
    rows = []
    for f in sorted((OUT / "data").glob("*.csv")):
        if f.name == "file_inventory.csv":
            continue
        d = pd.read_csv(f, dtype=str, keep_default_na=False)
        role, grain, pk, unit, obs, cav = SCHEMA[f.name]
        keys = [k.strip() for k in pk.split(",")]
        assert not d.duplicated(keys).any(), f"primary key not unique: {f.name}"
        yrs = pd.to_numeric(d["year"], errors="coerce") if "year" in d else pd.Series(dtype=float)
        rows.append(dict(file="data/" + f.name, role=role, rows=len(d), columns=d.shape[1], grain=grain, primary_key=pk,
                         years=f"{int(yrs.min())}–{int(yrs.max())}" if role in ("fact", "convenience") and yrs.notna().any() else "", unit=unit, values=obs, caveats=cav))
    rows.append(dict(file="data/file_inventory.csv", role="documentation", rows=len(rows) + 1, columns=10, grain="file",
                     primary_key="file", years="", unit="", values="", caveats="this table"))
    inv = pd.DataFrame(rows)
    write(inv, "file_inventory.csv")
    return inv


def write_readme_with_schema():
    inv = file_inventory()
    md = ["| File | Role | Rows | Cols | Grain (one row =) | Primary key | Years | Caveats |",
          "|---|---|---|---|---|---|---|---|"]
    for _, r in inv.iterrows():
        md.append(f"| `{r.file.split('/')[-1]}` | {r.role} | {r.rows:,} | {r.columns} | {r.grain} | {r.primary_key} | {r.years} | {r.caveats} |")
    txt = (ROOT / "release_template" / "README.md").read_text(encoding="utf-8")
    assert "<!-- FILE_SCHEMA -->" in txt
    (OUT / "README.md").write_text(txt.replace("<!-- FILE_SCHEMA -->", "\n".join(md)), encoding="utf-8")


# Validation evidence, model documentation and response cache (advisor review, Round 4 #8 and #25).
# File names are kept intuitive so they map onto the claims in the manuscript.
VALIDATION_FILES = {  # public name: original path (relative to ROOT)
    "digital_comparator_summary.csv": "data/validation/ocr_accuracy.csv",
    "digital_comparator_discrepancies.csv": "data/validation/ocr_mismatches.csv",
    "cross_edition_summary.csv": "data/validation/ocr_cross_edition.csv",
    "cross_edition_discrepancies.csv": "data/validation/ocr_cross_edition_mismatches.csv",
    "internal_consistency_summary.csv": "data/validation/internal_consistency.csv",
    "subtotal_checks_extracted.csv": "data/series/court_checks.csv",
    "subtotal_checks_after_corrections.csv": "data/series/court_checks_after_fixes.csv",
    "duration_bin_sum_checks.csv": "data/series/duration_checks.csv",
    "overlap_court_panel.csv": "data/series/court_overlap_check.csv",
    "overlap_duration.csv": "data/series/duration_overlap_check.csv",
    "overlap_detail.csv": "data/series/detail_overlap_check.csv",
    "overlap_national_series.csv": "data/series/overlap_check.csv",
    "reread_sample_main.csv": "data/validation/manual_sample_scored.csv",
    "reread_sample_main_model_reads.csv": "data/validation/visual_reads.csv",
    "reread_sample_main_human_disagreements.csv": "data/validation/human_errors.csv",
    "reread_sample_small_claims.csv": "data/validation/soak_sample_scored.csv",
    "reread_sample_small_claims_model_reads.csv": "data/validation/visual_reads_soak.csv",
    "reread_sample_small_claims_human_disagreements.csv": "data/validation/human_errors_soak.csv",
    "small_claims_text_layer_census.csv": "data/validation/soak_population_tl.csv",
    "duration_mean_method_check.csv": "data/validation/duration_mean_method_check.csv",
    "duration_excel_cell_check.csv": "data/validation/duration_excel_cell_check.csv",
    "model_calls.jsonl": "data/validation/model_calls.jsonl",
    "validation_blocks.csv": "data/validation/validation_blocks.csv",
    "validation_blocks_detail.csv": "data/validation/validation_blocks_detail.csv",
    "text_layer_handcheck.csv": "data/validation/text_layer_handcheck.csv",
    "ocr_value_support.csv": "data/validation/ocr_value_support.csv",
    "title_unverified_blocks.csv": "data/validation/title_unverified_blocks.csv",
    "duration_excel_position_check.csv": "data/validation/duration_excel_position_check.csv",
    "duration_pdf_position_check.csv": "data/validation/duration_pdf_position_check.csv",
    "detail_position_check.csv": "data/validation/detail_position_check.csv",
    "court_position_check.csv": "data/validation/court_position_check.csv",
    "overview_no_path_reread.csv": "data/validation/overview_no_path_reread.csv",
}
COL_EN = {"일치": "agree"}


def copy_supporting():
    vdir = OUT / "validation"
    vdir.mkdir(parents=True, exist_ok=True)
    for name, src in VALIDATION_FILES.items():
        sp = ROOT / src
        assert sp.exists(), f"missing validation source {src}"
        if name.endswith(".csv"):
            d = pd.read_csv(sp, encoding="utf-8-sig", dtype=str, keep_default_na=False).rename(columns=COL_EN)
            d.to_csv(vdir / name, index=False, encoding="utf-8")  # canonical copy without BOM
        else:
            shutil.copyfile(sp, vdir / name)
    for sub in ("validation", "docs"):
        for f in (ROOT / "release_template" / sub).glob("*.md"):
            (OUT / sub).mkdir(exist_ok=True)
            shutil.copyfile(f, OUT / sub / f.name)
    # model response cache (normalized JSON output); data/ocr_cache_backup is a copy kept in sync with the local cache
    rdir = OUT / "model_responses"
    rdir.mkdir(exist_ok=True)
    keys = {json.loads(l)["cache_key"] for l in (ROOT / VALIDATION_FILES["model_calls.jsonl"]).read_text(encoding="utf-8").splitlines() if l}
    allc = sorted((ROOT / "data" / "ocr_cache_backup").glob("*.json"))
    cache = [f for f in allc if f.stem in keys]  # only responses used by the current pipeline (development-stage responses excluded)
    for f in cache:
        shutil.copyfile(f, rdir / f.name)
    have = {f.stem for f in allc}
    assert keys <= have, "logged call without archived response"
    print(f"  validation/: {len(VALIDATION_FILES)} files; model_responses/: {len(cache)} JSON; "
          f"calls logged {len(keys)}, responses without a logged call {len(have - keys)}, logged calls without response {len(keys - have)}")
    for f in vdir.glob("*.csv"):
        assert not f.read_bytes().startswith(b"\xef\xbb\xbf"), f


def release_checks():
    """release_checks.txt (check results) + checksums.sha256 (all released files)."""
    import hashlib
    from datetime import datetime
    L = [f"Release checks — generated by make_release.py on {datetime.now():%Y-%m-%d %H:%M}", ""]
    ok = lambda c, msg: L.append(("PASS  " if c else "FAIL  ") + msg)  # noqa: E731
    inv = pd.read_csv(OUT / "data" / "file_inventory.csv", dtype=str, keep_default_na=False)
    for _, r in inv.iterrows():
        d = pd.read_csv(OUT / r.file, dtype=str, keep_default_na=False)
        keys = [k.strip() for k in r.primary_key.split(",")]
        ok(not d.duplicated(keys).any() and len(d) == int(r.rows), f"{r.file}: {len(d):,} rows, primary key ({r.primary_key}) unique")
    for f in ("court_panel", "national_series", "pending_observed", "detail", "duration"):
        d = pd.read_csv(OUT / "data" / f"{f}.csv", dtype=str, keep_default_na=False)
        vcols = ["value"] if "value" in d else ["filings", "dispositions", "pending"]
        ok((d[vcols] != "").all().all(), f"data/{f}.csv: no blank values in {', '.join(vcols)}")
        ok(((d.source_locator != "") | (d.extraction_method == "derived")).all(), f"data/{f}.csv: every non-derived value has a source locator")
        ids = [c for c in d.columns if c.endswith("_id") or c == "court_id_h"]
        ok(all(d[c].map(str.isascii).all() for c in ids), f"data/{f}.csv: identifier columns ASCII ({', '.join(ids)})")
    lk = {"court_id_h": "courts.csv", "table_id": "tables.csv", "category_id": "categories.csv", "instance_id": "instances.csv",
          "metric_id": "metrics.csv", "domain_id": "domains.csv"}
    for f in ("court_panel", "national_series", "pending_observed", "detail", "duration", "coverage"):
        d = pd.read_csv(OUT / "data" / f"{f}.csv", dtype=str, keep_default_na=False)
        for c, lf in lk.items():
            if c in d:
                ref = set(pd.read_csv(OUT / "data" / lf, dtype=str)[c])
                ok(set(d[c]) <= ref, f"data/{f}.csv: all {c} values found in {lf}")
    du = pd.read_csv(OUT / "data" / "duration.csv", dtype=str); bins = pd.read_csv(OUT / "data" / "duration_bins.csv", dtype=str)
    ok(set(zip(du.domain_id, du.bin_id)) <= set(zip(bins.domain_id, bins.bin_id)), "data/duration.csv: all (domain_id, bin_id) found in duration_bins.csv")
    cp = pd.read_csv(OUT / "data" / "court_panel.csv", dtype=str, keep_default_na=False)
    ok(not cp.correction_status.eq("unresolved_warning").any() and not cp.qc_flag.str.contains("mismatch").any(), "data/court_panel.csv: no unresolved validation warnings")
    cpn = pd.read_csv(OUT / "data" / "court_panel.csv"); cn = pd.read_csv(OUT / "data" / "courts.csv", dtype=str, keep_default_na=False)
    leafs = cpn[cpn.unit_type.isin(["high_court", "main_court", "branch", "si_gun_court"]) & cpn.dup_flag.isna()].groupby(["table_id", "year"]).value.sum()
    nat = cpn[cpn.unit_type.eq("national_total")].set_index(["table_id", "year"]).value
    ok(leafs.reindex(nat.index).eq(nat).all(), f"data/court_panel.csv: high, main, branch and si/gun court rows (excl. dup_flag) sum to the national total in every table and year ({len(nat)} cells)")
    det = pd.read_csv(OUT / "data" / "detail.csv")
    d1 = det[(det.table_id == "civil_main_by_instance") & (det.label_id == "first_instance") & (det.metric_id == "filings")].set_index("year").value
    t1 = cpn[(cpn.table_id == CL.CIVIL_TOTAL) & (cpn.court_id_h == "national_total")].set_index("year").value
    ok(len(t1) == 24 and t1.eq(d1.reindex(t1.index)).all(), "data/court_panel.csv: national civil_main_1st_total equals printed civil main first-instance filings (detail.csv) in all 24 years")
    pre = cpn[cpn.pre_establishment]
    exc = pre[pre.value.ne(0)]
    allowed = set(CL.RESTATED_NONZERO) | {(c, CL.CIVIL_TOTAL) for c, t in CL.RESTATED_NONZERO if t in CL.CIVIL_PARTS}
    ok(set(zip(exc.court_id_h, exc.table_id)) <= allowed, f"data/court_panel.csv: pre_establishment rows are printed zeros ({len(pre) - len(exc)}) except restated predecessor values ({len(exc)})")
    evf = pd.read_csv(OUT / "data" / "court_events.csv", dtype=str, keep_default_na=False)
    evids = {x for c in ("from_court_id_h", "to_court_id_h", "affected_parent_court_id_h") for v in evf[c] for x in v.split(";") if x}
    ok(evids <= set(cn.court_id_h), f"data/court_events.csv: all {len(evids)} referenced units found in courts.csv")
    sbc = set(pd.read_csv(OUT / "data" / "structural_breaks.csv", dtype=str).code)
    used = {x for f in ("court_panel", "national_series", "pending_observed", "detail", "duration")
            for v in pd.read_csv(OUT / "data" / f"{f}.csv", dtype=str, keep_default_na=False).break_flag for x in v.split(";") if x}
    ok(used <= sbc, f"break_flag codes ({len(used)}) all defined in structural_breaks.csv")
    cov = pd.read_csv(OUT / "data" / "coverage.csv", dtype=str)
    ok(int((cov.present == "True").sum()) == len(cp), f"data/coverage.csv: present cells = court_panel rows ({len(cp):,})")
    dd = pd.read_csv(OUT / "data" / "data_dictionary.csv", dtype=str)
    documented = set(zip(dd.file, dd.column))
    miss = [(k, c) for folder, pre in (("data", ""), ("validation", "validation/")) for f in sorted((OUT / folder).glob("*.csv"))
            if f.name != "national_series_wide.csv" for k in [pre + f.name] for c in pd.read_csv(f, nrows=0).columns if (k, c) not in documented]
    ok(not miss, f"data_dictionary.csv documents every column of data/ and validation/ ({len(dd)} rows){'' if not miss else ' — missing ' + str(miss[:5])}")
    boms = [f.name for folder in ("data", "validation") for f in (OUT / folder).glob("*.csv") if f.read_bytes().startswith(b"\xef\xbb\xbf")]
    ok(not boms, "canonical CSVs (data/, validation/) are UTF-8 without BOM")
    xl = [f.name for f in (OUT / "csv_excel").glob("*.csv") if not f.read_bytes().startswith(b"\xef\xbb\xbf")]
    ok(not xl and {f.name for f in (OUT / "csv_excel").glob("*.csv")} == {f.name for f in (OUT / "data").glob("*.csv")}, "csv_excel/ mirrors data/ with BOM")
    # positional checks: built from this release's values (second pass), every value at its row and column
    for vf, df_, sel in (("duration_excel_position_check.csv", du, du.extraction_method == "excel_llm_structured"),
                         ("duration_pdf_position_check.csv", du, du.source_type == "ocr"),
                         ("detail_position_check.csv", det, det.source_type == "ocr"),
                         ("court_position_check.csv", cpn, cpn.source_type == "ocr")):
        pv = pd.read_csv(OUT / "validation" / vf)
        cur = df_[sel].value.astype(float).sort_values().tolist() == pv.value.astype(float).sort_values().tolist()
        ok(cur and pv.position_agrees.all(), f"validation/{vf}: all {len(pv)} released values checked against the current release agree by row and column position")
    keys = {json.loads(l)["cache_key"] for l in (OUT / "validation" / "model_calls.jsonl").read_text(encoding="utf-8").splitlines() if l}
    have = {f.stem for f in (OUT / "model_responses").glob("*.json")}
    ok(keys == have, f"model_responses/ ({len(have)}) = cache keys in validation/model_calls.jsonl ({len(keys)})")
    for f in ("validation/validation_protocol.md", "docs/model_extraction.md", "README.md", "CHANGELOG.md", "KNOWN_ISSUES.md", "CITATION.cff",
              "LICENSE_DATA.md", "LICENSE_CODE"):
        ok((OUT / f).exists(), f"{f} present")
    nfail = sum(l.startswith("FAIL") for l in L)
    L += ["", f"{sum(l.startswith((chr(80) + chr(65), chr(70) + chr(65))) for l in L)} checks, {nfail} failed. File checksums: checksums.sha256"]
    (OUT / "release_checks.txt").write_text("\n".join(L) + "\n", encoding="utf-8")
    sums = []
    for f in sorted(p for p in OUT.rglob("*") if p.is_file() and p.name != "checksums.sha256"):
        sums.append(f"{hashlib.sha256(f.read_bytes()).hexdigest()}  {f.relative_to(OUT).as_posix()}")
    (OUT / "checksums.sha256").write_text("\n".join(sums) + "\n", encoding="utf-8", newline="\n")  # LF, so `sha256sum -c` works
    print(f"  release_checks.txt: {nfail} failed; checksums.sha256: {len(sums)} files")
    assert nfail == 0, "release checks failed — see release_checks.txt"


if __name__ == "__main__":
    main()
