"""Supplementary release information that makes court history and jurisdiction-rule changes machine-readable
(advisor review, Round 5).

Called by make_release.py after the ID conversion.
  court_events(courts, panel)      → court_events.csv (list of court establishment, split, conversion, renaming and abolition events)
  pre_establishment(panel, courts) → court_panel.pre_establishment (printed zeros in years before a court was established)
  add_break_flags(df, file)        → adds jurisdiction-rule change codes to break_flag (';'-separated)
  civil_total_rows(panel)          → derived table civil_main_1st_total (collegiate + single-judge + small claims)
"""
import pandas as pd

# ------------------------------------------------------------------ jurisdiction-rule changes (statute text checked: korean-law, 2026-11-19)
THRESHOLD_BREAKS = [
    dict(code="civil_collegiate_threshold_2015", file="court_panel.csv; duration.csv",
         filter="court_panel.csv: table_id in (civil_main_1st_collegiate, civil_main_1st_single) & year>=2015; "
                "duration.csv: domain_id=civil_main & instance_id in (first_collegiate, first_single) & year>=2015",
         from_year=2015, to_year=2025, break_type="jurisdiction_threshold", confidence="verified", effective_date="2015-02-13",
         old_rule="Collegiate panel hears first-instance civil cases with a claim value above KRW 100 million",
         new_rule="Collegiate panel hears first-instance civil cases with a claim value above KRW 200 million",
         legal_basis_ko="민사 및 가사소송의 사물관할에 관한 규칙 제2조(2015.1.28 개정, 2015.2.13 시행). 직전 기준 1억원(2001.3.1 시행본)",
         legal_basis_en="Supreme Court Rules on the Subject-Matter Jurisdiction over Civil and Family Cases, Art. 2 (amended 2015-01-28, effective 2015-02-13); previous threshold KRW 100 million (version effective 2001-03-01)",
         expected_effect="Cases of KRW 100–200 million move from collegiate to single-judge tables: collegiate filings fall (national 61,564 in 2014 → 41,589 in 2015), single-judge filings rise; 2015 is a mixed year (Addenda Art. 2: the new rule does not apply to cases filed before 2015-02-13)",
         unaffected_alternative="court_panel.csv table_id=civil_main_1st_total; detail.csv civil_main_by_instance first_instance",
         description="Monetary threshold between collegiate and single-judge civil first instance raised from KRW 100 million to 200 million",
         basis="statute text (law.go.kr article history and versions); level shift in national series"),
    dict(code="small_claims_threshold_2017", file="court_panel.csv",
         filter="court_panel.csv: table_id in (civil_main_1st_single, civil_main_1st_small_claims) & year>=2017",
         from_year=2017, to_year=2025, break_type="jurisdiction_threshold", confidence="verified", effective_date="2017-01-01",
         old_rule="Small claims: claim value not above KRW 20 million",
         new_rule="Small claims: claim value not above KRW 30 million",
         legal_basis_ko="소액사건심판규칙 제1조의2(2016.11.29 개정, 2017.1.1 시행). 직전 기준 2,000만원(1997.12.31 개정본부터, 2002–2016 전 기간)",
         legal_basis_en="Small Claims Adjudication Rules, Art. 1-2 (amended 2016-11-29, effective 2017-01-01); previous ceiling KRW 20 million (from the 1997-12-31 amendment, in force throughout 2002–2016)",
         expected_effect="Cases of KRW 20–30 million move from single-judge to small-claims tables: single-judge filings fall (246,651 in 2016 → 200,196 in 2017), small claims rise (686,407 → 774,440). Addenda Art. 2: cases pending on 2017-01-01 continue under the old rule; the change starts with a calendar year, so filings are not mixed",
         unaffected_alternative="court_panel.csv table_id=civil_main_1st_total",
         description="Small-claims ceiling raised from KRW 20 million to 30 million",
         basis="statute text (old/new comparison of the 2016-11-29 amendment); level shift in national series"),
    dict(code="civil_collegiate_threshold_2022", file="court_panel.csv; duration.csv",
         filter="court_panel.csv: table_id in (civil_main_1st_collegiate, civil_main_1st_single) & year>=2022; "
                "duration.csv: domain_id=civil_main & instance_id in (first_collegiate, first_single) & year>=2022",
         from_year=2022, to_year=2025, break_type="jurisdiction_threshold", confidence="verified", effective_date="2022-03-01",
         old_rule="Collegiate panel hears first-instance civil cases with a claim value above KRW 200 million",
         new_rule="Collegiate panel hears first-instance civil cases with a claim value above KRW 500 million",
         legal_basis_ko="민사 및 가사소송의 사물관할에 관한 규칙 제2조(2022.1.28 개정, 2022.3.1 시행)",
         legal_basis_en="Supreme Court Rules on the Subject-Matter Jurisdiction over Civil and Family Cases, Art. 2 (amended 2022-01-28, effective 2022-03-01)",
         expected_effect="Cases of KRW 200–500 million move from collegiate to single-judge tables (collegiate 43,679 in 2021 → 27,726 in 2022); 2022 is a mixed year (Addenda Art. 2: the new rule does not apply to cases filed before 2022-03-01)",
         unaffected_alternative="court_panel.csv table_id=civil_main_1st_total; detail.csv civil_main_by_instance first_instance",
         description="Monetary threshold between collegiate and single-judge civil first instance raised from KRW 200 million to 500 million",
         basis="statute text (law.go.kr article history and versions); level shift in national series"),
    dict(code="patent_court_ip_appeals_2016", file="court_panel.csv",
         filter="court_panel.csv: table_id=civil_main_appeal & court_id_h=patent_court & year>=2016",
         from_year=2016, to_year=2025, break_type="jurisdiction_transfer", confidence="verified", effective_date="2016-01-01",
         old_rule="Appeals in IP-infringement civil cases heard by high courts / district court appellate divisions",
         new_rule="Appeals in IP-infringement civil cases (Civil Procedure Act Art. 24(2)–(3)) heard by the Patent Court",
         legal_basis_ko="법원조직법 제28조의4제2호(법률 제13522호, 2015.12.1 공포, 2016.1.1 시행; 부칙 제2조: 시행 후 1심 판결이 선고된 사건부터 적용)",
         legal_basis_en="Court Organization Act, Art. 28-4(2) (Act No. 13522, promulgated 2015-12-01, effective 2016-01-01; Addenda Art. 2: applies where the first-instance judgment is delivered on or after that date)",
         expected_effect="The Patent Court appears in the civil appeal table from 2016 (112–184 filings a year); a matching small share leaves the other appellate courts",
         unaffected_alternative="sum of all appellate units (national_total) is unaffected",
         description="Patent Court acquires appellate jurisdiction over IP-infringement civil cases",
         basis="statute text; courts.csv data_note_en"),
    dict(code="criminal_single_judge_exceptions", file="court_panel.csv",
         filter="court_panel.csv: table_id in (criminal_trial_1st_collegiate, criminal_trial_1st_single) (registry only; rows not flagged)",
         from_year=2016, to_year=2025, break_type="jurisdiction_rule", confidence="verified", effective_date="2016-01-06; 2019-06-25; 2021-12-21; 2022-01-27",
         old_rule="Court Organization Act Art. 32(1)(3): offences punishable by death, life or a minimum of one year go to collegiate panels, with listed exceptions",
         new_rule="Art. 32(1) amended four times (in force on the dates given); the current text lists offence-specific exceptions (items 3(a)–(ja)) heard by single judges",
         legal_basis_ko="법원조직법 제32조제1항(조문 연혁: 2016.1.6, 2019.6.25, 2021.12.21, 2022.1.27 시행 개정)",
         legal_basis_en="Court Organization Act, Art. 32(1) (article history: amendments in force 2016-01-06, 2019-06-25, 2021-12-21, 2022-01-27)",
         expected_effect="Offence-specific reallocations between collegiate and single-judge criminal tables, mostly re-citations after the cited statutes were rewritten. Substantive changes: aggravated injury and extortion (Criminal Act Arts. 258-2, 350-2) to single judges (2016); drunk-driving items widened with the 2019 penalty increase; Art. 258-2(2) returned to collegiate panels (2021); Serious Accidents Punishment Act offences to single judges (2022). No visible level shift at these dates in the national series, so rows are not flagged",
         unaffected_alternative="court_panel.csv table_id=criminal_trial_1st_total",
         description="Offence-specific changes to criminal collegiate jurisdiction (registry entry; not used as a row flag)",
         basis="statute article history"),
    dict(code="criminal_collegiate_rise_2024_2025", file="court_panel.csv",
         filter="court_panel.csv: table_id=criminal_trial_1st_collegiate & year>=2024 (registry only; rows not flagged)",
         from_year=2024, to_year=2025, break_type="unexplained_level_shift", confidence="observed_only", effective_date="",
         old_rule="", new_rule="",
         legal_basis_ko="", legal_basis_en="No amendment of Court Organization Act Art. 32(1) took effect in 2023–2025 (article history)",
         expected_effect="National collegiate criminal filings 21,656 (2023) → 28,057 (2024) → 32,618 (2025) while single-judge filings fall; the first-instance total is stable",
         unaffected_alternative="court_panel.csv table_id=criminal_trial_1st_total",
         description="Rise in collegiate criminal first-instance filings; cause not identified (no jurisdiction-rule change found)",
         basis="national series; statute article history"),
    dict(code="criminal_collegiate_spike_2012", file="court_panel.csv",
         filter="court_panel.csv: table_id=criminal_trial_1st_collegiate & year=2012 (registry only; rows not flagged)",
         from_year=2012, to_year=2012, break_type="unexplained_level_shift", confidence="observed_only", effective_date="",
         old_rule="", new_rule="", legal_basis_ko="", legal_basis_en="",
         expected_effect="National collegiate criminal filings 19,689 (2011) → 31,278 (2012) → 20,330 (2013); the 2012 value is identical in the 2016, 2019, 2020 and 2021 editions",
         unaffected_alternative="court_panel.csv table_id=criminal_trial_1st_total",
         description="One-year spike in collegiate criminal first-instance filings; cause not identified",
         basis="national series; validation/overlap_court_panel.csv"),
]
THRESHOLD_BREAKS += [  # Advisor review, Round 6: family non-litigation cases; registry only (no row flag)
    dict(code="family_noncontentious_categories_2013_2018", file="detail.csv",
         filter="detail.csv: table_id=family_overall & label_id=non_contentious & year>=2013 (registry only; rows not flagged)",
         from_year=2013, to_year=2025, break_type="statutory_case_type_addition", confidence="verified",
         effective_date="2013-07-01; 2013-07-30; 2015-10-16; 2017-06-03; 2018-02-01",
         old_rule="Family non-litigation (라·마류) case list of Family Litigation Act Art. 2(1)(2)",
         new_rule="Case types added: adult/limited/specific guardianship (2013-07-01), adoption permits (2013-07-30), suspension or partial restriction of parental authority (2015-10-16), paternity-denial and acknowledgment permits (2018-02-01)",
         legal_basis_ko="가사소송법 제2조제1항제2호(조문 연혁: 2013.7.1, 2013.7.30, 2015.10.16, 2017.6.3, 2018.2.1 시행 개정)",
         legal_basis_en="Family Litigation Act, Art. 2(1)(2) (article history: amendments in force 2013-07-01, 2013-07-30, 2015-10-16, 2017-06-03, 2018-02-01)",
         expected_effect="Non-litigation filings grow steadily (62,003 in 2013 → 114,549 in 2025) with no single-year jump; part of the growth reflects new case types, not only demand",
         unaffected_alternative="family_overall litigation (the 2013–2018 amendments add only non-litigation case types)",
         description="New family non-litigation case types added by statute (context; the Yearbook category itself did not change)",
         basis="statute article history and text (law.go.kr); detail.csv"),
    dict(code="family_noncontentious_2008", file="detail.csv",
         filter="detail.csv: table_id=family_overall & label_id=non_contentious & year>=2008 (registry only; rows not flagged)",
         from_year=2008, to_year=2025, break_type="statutory_case_type_addition", confidence="verified", effective_date="2008-01-01",
         old_rule="Family non-litigation case list before the abolition of the family-head system",
         new_rule="Case types added: child surname/clan change permit (Civil Act Art. 781(6); 라류 item 4-3) and full-adoption (친양자) permit (라류 item 7-3); full-adoption annulment and dissolution added as litigation (나류 items 13-14)",
         legal_basis_ko="민법(법률 제7427호, 2005.3.31 공포) 부칙 제1조 단서: 제781조 등 2008.1.1 시행, 부칙 제7조제1항으로 가사소송법 제2조 라류 4의3 신설. 가사소송법(법률 제8715호, 2007.12.21 공포) 부칙 제1항: 친양자 관련 사건 2008.1.1 시행",
         legal_basis_en="Civil Act amendment No. 7427 (promulgated 2005-03-31), Addenda Art. 1 proviso: Art. 781 and related provisions effective 2008-01-01; its Addenda Art. 7(1) added Family Litigation Act Art. 2, 라류 item 4-3. Family Litigation Act amendment No. 8715 (promulgated 2007-12-21), Addenda para. 1: full-adoption case types effective 2008-01-01",
         expected_effect="Non-litigation filings 45,448 (2007) → 64,350 (2008) → 56,041 (2009); identical in the 2011 and 2016 editions. The new case types start in 2008; that the one-year peak consists of initial surname-change petitions is plausible but not verified. Consider a 2008 indicator or sensitivity check",
         unaffected_alternative="family_overall litigation (largely; the full-adoption litigation types added in 2008 are small)",
         description="New family case types from 2008-01-01 (family-law reform abolishing the family-head system); coincides with the 2008 peak in non-litigation filings",
         basis="statute texts and addenda (law.go.kr); detail.csv; validation/overlap_detail.csv"),
    dict(code="civil_appeal_routing_art4", file="court_panel.csv; duration.csv; detail.csv; national_series.csv",
         filter="court_panel.csv: table_id=civil_main_appeal & court_id_h!=patent_court & year>=2008; duration.csv: domain_id=civil_main & instance_id in (appeal_high_court, appeal_district_court) & year>=2008; detail.csv: table_id=civil_main_by_instance & label_id in (appeal_high_court, appeal_district_court) & year>=2008; national_series.csv: category_id=main_cases & instance_id in (appeal_high_court, appeal_district_court) & year>=2008",
         from_year=2008, to_year=2025, break_type="jurisdiction_threshold", confidence="verified",
         effective_date="2008-03-01; 2011-01-01; 2015-02-13; 2016-10-01; 2022-03-01",
         old_rule="Appeals from single-judge civil cases with a claim value above KRW 50 million go to the high court; other single-judge appeals go to the district-court appellate division (in force 2001-03-01 to 2008-02-29)",
         new_rule="Threshold KRW 80 million from 2008-03-01; provision deleted 2011-01-01 (all single-judge appeals to district appellate divisions); re-inserted at KRW 100 million 2015-02-13; deleted 2016-10-01; re-inserted at KRW 200 million 2022-03-01 (Art. 4(1) from 2023-03-01)",
         legal_basis_ko="민사 및 가사소송의 사물관할에 관한 규칙 제4조(대법원규칙 제2163호 2008.3.1 시행; 제2310호 2011.1.1 시행 삭제; 제2584호 2015.2.13 시행 신설; 제2674호 2016.10.1 시행 삭제; 제3028호 2022.3.1 시행 신설). 각 부칙: 시행 후 제기된 항소 또는 시행 후 접수된 사건부터 적용",
         legal_basis_en="Rules on the Subject-Matter Jurisdiction over Civil and Family Cases, Art. 4 (Supreme Court Rule No. 2163, effective 2008-03-01; No. 2310, deleted effective 2011-01-01; No. 2584, re-inserted effective 2015-02-13; No. 2674, deleted effective 2016-10-01; No. 3028, re-inserted effective 2022-03-01). Addenda: the 2008, 2011 and 2016 changes apply to appeals filed on or after the effective date (immediate effect); the 2015 change (Rules No. 2584 and No. 2591) and the 2022 change (No. 3028, Addenda Art. 2) do not apply to cases filed at first instance before the effective date, so they phase in over the following years",
         expected_effect="Civil appeals move between high courts and district-court appellate divisions; the 2008, 2011 and 2016 changes take effect at once (mixed years 2008 and 2016), while the 2015 and 2022 changes phase in as cases filed after the effective date reach appeal. Totals over a high-court circuit (the high court and the district courts of its circuit) and the national total are unaffected",
         unaffected_alternative="circuit-level or national civil appeal total (national_total of civil_main_appeal; detail.csv civil_main_by_instance appeal_high_court + appeal_district_court)",
         description="Routing of appeals from single-judge civil cases between high courts and district appellate divisions by claim value",
         basis="statute texts, version history and addenda (law.go.kr)"),
    dict(code="family_appeal_routing_2023", file="court_panel.csv; national_series.csv",
         filter="court_panel.csv: table_id=family_litigation_appeal & year>=2023; national_series.csv: category_id=main_cases & instance_id in (appeal_high_court, appeal_district_court) & year>=2023 (detail.csv family_litigation_by_instance has a single appeal row and is unaffected)",
         from_year=2023, to_year=2025, break_type="jurisdiction_threshold", confidence="verified", effective_date="2023-03-01",
         old_rule="Appeals from single-judge family cases heard by the family-court appellate division",
         new_rule="Appeals from single-judge family cases with a claim value above KRW 200 million go to the high court (Art. 4(2))",
         legal_basis_ko="민사 및 가사소송의 사물관할에 관한 규칙 제4조제2항(대법원규칙 제3088호, 2023.3.1 시행; 부칙: 시행 전 접수 사건에는 적용하지 아니함)",
         legal_basis_en="Rules on the Subject-Matter Jurisdiction over Civil and Family Cases, Art. 4(2) (Supreme Court Rule No. 3088, effective 2023-03-01; Addenda: not applied to cases filed before that date)",
         expected_effect="A small share of family appeals moves from family-court appellate divisions to high courts; the rule does not apply to cases filed before 2023-03-01, so it phases in from 2023",
         unaffected_alternative="circuit-level or national family appeal total (national_total of family_litigation_appeal)",
         description="Value-based routing of appeals from single-judge family cases to the high court",
         basis="statute text and addenda (law.go.kr)"),
    dict(code="ip_first_instance_concentration_2016", file="court_panel.csv",
         filter="court_panel.csv: table_id in (civil_main_1st_collegiate, civil_main_1st_single) & year>=2016 (registry only; rows not flagged)",
         from_year=2016, to_year=2025, break_type="jurisdiction_transfer", confidence="verified", effective_date="2016-01-01",
         old_rule="First-instance suits on patent and other IP rights could be filed at any competent district court",
         new_rule="Exclusive first-instance jurisdiction of the district courts at the seats of the high courts (in Seoul, the Seoul Central District Court), with optional filing at the Seoul Central District Court",
         legal_basis_ko="민사소송법 제24조제2항·제3항(법률 제13521호, 2015.12.1 공포, 2016.1.1 시행; 부칙 제2조: 시행 후 최초로 소장이 접수된 사건부터 적용)",
         legal_basis_en="Civil Procedure Act, Art. 24(2)-(3) (Act No. 13521, promulgated 2015-12-01, effective 2016-01-01; Addenda Art. 2: applies to suits filed on or after that date)",
         expected_effect="A small number of IP suits move from other district courts and branches to the five courts at high-court seats; national totals are unaffected",
         unaffected_alternative="national or high-court-district totals of civil first-instance filings",
         description="Concentration of first-instance IP-infringement suits (companion of the Patent Court's appellate jurisdiction)",
         basis="statute text and addenda (law.go.kr)"),
]


def flagged_codes():
    return {c for rules in ROW_FLAGS.values() for c, _ in rules}


# Row flags: (code, file, condition); jurisdiction-rule changes only (advisor review: flag only when exact)
ROW_FLAGS = {
    "court_panel.csv": [
        ("civil_collegiate_threshold_2015", lambda d: d.table_id.isin(["civil_main_1st_collegiate", "civil_main_1st_single"]) & (d.year >= 2015)),
        ("small_claims_threshold_2017", lambda d: d.table_id.isin(["civil_main_1st_single", "civil_main_1st_small_claims"]) & (d.year >= 2017)),
        ("civil_collegiate_threshold_2022", lambda d: d.table_id.isin(["civil_main_1st_collegiate", "civil_main_1st_single"]) & (d.year >= 2022)),
        ("patent_court_ip_appeals_2016", lambda d: d.table_id.eq("civil_main_appeal") & d.court_id_h.eq("patent_court") & (d.year >= 2016)),
        ("civil_appeal_routing_art4", lambda d: d.table_id.eq("civil_main_appeal") & d.court_id_h.ne("patent_court") & (d.year >= 2008)),
        ("family_appeal_routing_2023", lambda d: d.table_id.eq("family_litigation_appeal") & (d.year >= 2023)),
    ],
    "detail.csv": [
        ("civil_appeal_routing_art4", lambda d: d.table_id.eq("civil_main_by_instance") & d.label_id.isin(["appeal_high_court", "appeal_district_court"]) & (d.year >= 2008)),
    ],
    "national_series.csv": [
        ("civil_appeal_routing_art4", lambda d: d.category_id.eq("main_cases") & d.instance_id.isin(["appeal_high_court", "appeal_district_court"]) & (d.year >= 2008)),
        ("family_appeal_routing_2023", lambda d: d.category_id.eq("main_cases") & d.instance_id.isin(["appeal_high_court", "appeal_district_court"]) & (d.year >= 2023)),
    ],
    "duration.csv": [
        ("civil_collegiate_threshold_2015", lambda d: d.domain_id.eq("civil_main") & d.instance_id.isin(["first_collegiate", "first_single"]) & (d.year >= 2015)),
        ("civil_collegiate_threshold_2022", lambda d: d.domain_id.eq("civil_main") & d.instance_id.isin(["first_collegiate", "first_single"]) & (d.year >= 2022)),
        ("civil_appeal_routing_art4", lambda d: d.domain_id.eq("civil_main") & d.instance_id.isin(["appeal_high_court", "appeal_district_court"]) & (d.year >= 2008)),
    ],
}


def add_break_flags(df, file):
    """break_flag = all structural-break codes that apply to the row (';'-separated)."""
    df = df.copy()
    cur = df["break_flag"].fillna("") if "break_flag" in df else pd.Series("", index=df.index)
    codes = [[c] if c else [] for c in cur]
    for code, pred in ROW_FLAGS.get(file, []):
        for i, hit in enumerate(pred(df).to_numpy()):
            if hit:
                codes[i].append(code)
    df["break_flag"] = [";".join(c) for c in codes]
    return df


# ------------------------------------------------------------------ printed zeros in years before establishment
# From the 2016 edition on, the 10-year comparison tables print past years using the current court structure,
# so zeros appear in years before a court was established.
START_OVERRIDE = {("patent_court", "civil_main_appeal"): 2016}  # year the jurisdiction was added
# Effective date of the jurisdiction behind START_OVERRIDE (used by coverage.csv for years before the jurisdiction existed)
JURISDICTION_START = {("patent_court", "civil_main_appeal"): "2016-01-01"}
APPEAL_TABLES = {"civil_main_appeal", "criminal_trial_appeal", "family_litigation_appeal"}
RESTATED_NONZERO = {  # non-zero values before establishment: the predecessor court's cases are restated in the new court's row (courts.csv data_note_en)
    ("uijeongbu_dc_namyangju_br", "civil_main_1st_small_claims"): "restates the Namyangju Si Court row (dup_flag)",
    ("changwon_dc_masan_br", "civil_main_1st_small_claims"): "restates the predecessor Masan Si Court caseload (2007–2010)",
    ("uijeongbu_dc_goyang_br", "civil_main_1st_small_claims"): "2002 value printed under the branch in the 2006 edition; equals the Goyang Si Court row of the 2002 edition (2002 ed. 2절 p8: 5,790)",
}


def start_years(courts):
    """(court_id_h, table_id or None) → first year of existence."""
    s = {}
    c = courts[courts.legal_start.astype(str).str.len() >= 4]
    for r in c.itertuples():
        y = int(str(r.legal_start)[:4])
        if r.legal_event == "established":
            s[(r.court_id_h, None)] = y
        elif r.legal_event == "elevated_from_branch" and r.court_id_h != "seoul_central_dc":  # branch → district court: appellate division only after elevation (Seoul Central = former main court)
            for t in APPEAL_TABLES:
                s[(r.court_id_h, t)] = y
    s.update(START_OVERRIDE)
    return s


def pre_establishment(panel, courts):
    s = start_years(courts)
    y0 = [s.get((c, t), s.get((c, None))) for c, t in zip(panel.court_id_h, panel.table_id)]
    pre = pd.Series([y is not None and yr < y for y, yr in zip(y0, panel.year)], index=panel.index)
    bad = panel[pre & panel.value.ne(0) & ~pd.Series(list(zip(panel.court_id_h, panel.table_id)), index=panel.index).isin(RESTATED_NONZERO)]
    assert bad.empty, f"non-zero value before establishment: {bad[['court_id_h', 'table_id', 'year', 'value']].head()}"
    return pre


# ------------------------------------------------------------------ derived table: civil main cases, first-instance total
CIVIL_PARTS = ["civil_main_1st_collegiate", "civil_main_1st_single", "civil_main_1st_small_claims"]
CIVIL_TOTAL = "civil_main_1st_total"


def civil_total_rows(panel):
    """Collegiate + single-judge + small-claims sum per court × year (a first-instance series unaffected by
    jurisdiction-threshold changes). Only the component tables that are present are summed."""
    # Printed subtotals and area totals are different units in each table (subtotal: collegiate/single-judge tables;
    # area total: small-claims table), so summing them per unit would give partial sums -> excluded
    p = panel[panel.table_id.isin(CIVIL_PARTS) & panel.unit_type.isin(["national_total", "high_court", "main_court", "branch", "si_gun_court"])]
    agg = p.groupby(["court_id_h", "year"], as_index=False).agg(
        value=("value", "sum"), court_code=("court_code", "first"), unit_type=("unit_type", "first"),
        source_court_id_ko=("source_court_id_ko", "first"), n_parts=("table_id", "nunique"),
        partial_year=("partial_year", "any"), pre_establishment=("pre_establishment", "all"),
        dup_flag=("dup_flag", lambda s: ";".join(sorted({x for x in s if x}))))
    out = pd.DataFrame({"year": agg.year, "court_id_h": agg.court_id_h, "court_code": agg.court_code, "table_id": CIVIL_TOTAL,
                        "value": agg.value.astype("Int64"), "unit": "cases", "unit_type": agg.unit_type,
                        "source_court_id_ko": agg.source_court_id_ko, "source_court_label_ko": "",
                        "source": "derived: " + " + ".join(CIVIL_PARTS) + " (components present for this court and year)",
                        "source_edition": pd.NA, "source_file": "", "source_page": "", "extraction_method": "derived", "source_type": "derived",
                        "correction_status": "none", "qc_flag": "", "partial_year": agg.partial_year, "dup_flag": agg.dup_flag,
                        "pre_establishment": agg.pre_establishment, "break_flag": ""})
    return out


# ------------------------------------------------------------------ court_events.csv
# target court (to) → (from courts, event type, case scope, affects parent-court series, recommended user action)
_BR = "branch_created_from_parent"
EVENT_SPEC = {
    "suwon_hc": ("seoul_hc", "high_court_jurisdiction_split", "appeals (civil, family, criminal)", True,
                 "Seoul High Court appeal series fall from 2019. For a stable territory compare seoul_hc (to 2018) with seoul_hc + suwon_hc (from 2019)."),
    "seoul_bankruptcy": ("seoul_central_dc", "bankruptcy_court_created", "bankruptcy/rehabilitation; a small number of civil main cases", True,
                         "District: the whole of Seoul (Act No. 14469, Annex 10). Pending cases of the Seoul Central District Court, which had heard insolvency cases for all of Seoul since 2004 (Act No. 7082, Addenda Art. 3), were transferred; bankruptcy cases pending at the other Seoul district courts stayed there. Bankruptcy courts appear in civil main tables with small counts: for civil series add the court to seoul_central_dc, or use a Seoul-wide sum; do not merge it for other case types."),
    "suwon_bankruptcy": ("suwon_dc;suwon_dc_ansan_br;suwon_dc_anyang_br;suwon_dc_pyeongtaek_br;suwon_dc_seongnam_br;suwon_dc_yeoju_br", "bankruptcy_court_created", "bankruptcy/rehabilitation; a small number of civil main cases", True,
                         "District: the area of the Suwon District Court and all its branches (Act No. 19149, Annex 10). For civil series add it to the district-wide sum of suwon_dc (main court and all units with parent_court_id_h = suwon_dc); pending cases of the main court were transferred."),
    "busan_bankruptcy": ("busan_dc;busan_dc_eastern_br;busan_dc_western_br", "bankruptcy_court_created", "bankruptcy/rehabilitation; a small number of civil main cases", True,
                         "District: Busan Metropolitan City, i.e. the Busan District Court with its Eastern and Western branches (Act No. 19149, Annex 10). For civil series add it to the district-wide sum of busan_dc; pending cases of the main court were transferred."),
    "busan_dc_western_br": ("busan_dc", _BR, "all case types", True,
                            "busan_dc (main court) series fall from 2017. For a stable territory sum busan_dc and all units with parent_court_id_h = busan_dc (district-wide), or busan_dc + busan_dc_western_br."),
    "changwon_dc_masan_br": ("changwon_dc;changwon_dc_masan_si", _BR, "all case types", True,
                             "changwon_dc series fall from 2011. For a stable territory sum changwon_dc and all units with parent_court_id_h = changwon_dc (district-wide). Masan Si Court small claims continue under this branch."),
    "daegu_dc_western_br": ("daegu_dc", _BR, "all case types", True,
                            "daegu_dc series fall from 2007. For a stable territory sum daegu_dc and all units with parent_court_id_h = daegu_dc (district-wide), or daegu_dc + daegu_dc_western_br."),
    "suwon_dc_ansan_br": ("suwon_dc;suwon_dc_gwangmyeong_si", _BR, "all case types", True,
                          "Established 2002-09-01 (2002 partial). For a stable territory sum suwon_dc and all units with parent_court_id_h = suwon_dc (district-wide)."),
    "suwon_dc_anyang_br": ("suwon_dc", _BR, "all case types", True,
                           "suwon_dc series fall from 2009. For a stable territory sum suwon_dc and all units with parent_court_id_h = suwon_dc (district-wide), or suwon_dc + suwon_dc_anyang_br."),
    "uijeongbu_dc_goyang_br": ("uijeongbu_dc", _BR, "all case types (small claims: from the Goyang Si Court)", True,
                               "The 2002 small-claims row under this branch is the predecessor Goyang Si Court (2002 ed. prints 고양시법원 5,790; 2006 ed. restates it under 고양지원; area total unchanged). uijeongbu_dc series fall from 2003. For a stable territory sum uijeongbu_dc and all units with parent_court_id_h = uijeongbu_dc (district-wide)."),
    "uijeongbu_dc_namyangju_br": ("uijeongbu_dc;uijeongbu_dc_namyangju_si", _BR, "all case types", True,
                                  "uijeongbu_dc series fall from 2022. Small claims 2018–2021 under this branch restate the Namyangju Si Court (dup_flag): count them once. For a stable territory sum uijeongbu_dc and all units with parent_court_id_h = uijeongbu_dc (district-wide)."),
    "changwon_dc_masan_si": ("changwon_dc_masan_si", "abolished_absorbed", "small claims", False,
                             "Last separate row 2006; caseload continues under changwon_dc_masan_br."),
    "uijeongbu_dc_namyangju_si": ("uijeongbu_dc_namyangju_si", "abolished_absorbed", "small claims", False,
                                  "Last row 2021; pending cases transferred to uijeongbu_dc_namyangju_br on 2022-03-01, whose small claims 2018–2021 restate this court (dup_flag)."),
    "patent_court": ("", "jurisdiction_added", "IP-infringement civil appeals", False,
                     "Appears in civil_main_appeal from 2016; earlier printed zeros are flagged pre_establishment. National appeal totals are unaffected."),
}
_EVENT_TO = {"changwon_dc_masan_si": "changwon_dc_masan_br", "uijeongbu_dc_namyangju_si": "uijeongbu_dc_namyangju_br"}  # abolished/absorbed: to = the absorbing court
_DATE = {"patent_court": "2016-01-01", "uijeongbu_dc_namyangju_si": "2022-03-01"}  # event effective dates that differ from courts.legal_start
EXTRA_EVENTS = [  # events not expressible as a single per-unit legal_event in courts.csv
    dict(event_date="2014-03-01", event_type="jurisdiction_transfer", from_court_id_h="seoul_central_dc;seoul_fc", to_court_id_h="seoul_northern_dc",
         affected_parent_court_id_h="seoul_central_dc", case_scope="all case types (territorial transfer)", affects_parent_series=True,
         recommended_user_action="Possible level shift in seoul_northern_dc and seoul_central_dc from 2014; for a stable territory sum the Seoul district courts.",
         legal_basis_ko="각급법원설치법 법률 제11623호(2013.1.23)", legal_basis_en="Act on the Establishment and Jurisdictional Districts of Courts at All Levels, Act No. 11623 (2013-01-23)",
         note_en="Parts of the Seoul Central District Court and Seoul Family Court jurisdictions transferred to the Seoul Northern District Court (courts.csv data_note_en)"),
]


def _spec(r):
    cid, ev = r.court_id_h, r.legal_event
    if cid in EVENT_SPEC:
        return EVENT_SPEC[cid]
    if ev == "converted_to_family_court":
        src = cid.replace("_fc_", "_dc_").replace("_fc", "_dc") if cid.endswith("_fc") else cid.replace("_fc_", "_dc_")
        return (src, ev, "family cases", False,
                "Family tables use this unit for all years: rows before the conversion (printed under the district court or its branch) are harmonized into it. "
                "It is an analytical unit bridging the conversion, not the legal institution in every year.")
    if ev in ("renamed", "renamed_county_to_city"):
        return (cid, "renamed", "all case types", False, "Same unit and ID before and after renaming; no action needed.")
    if ev == "elevated_from_branch":
        return ("seoul_central_dc" if cid != "seoul_central_dc" else "", ev, "all case types", False,
                "Reported as a separate row before and after 2004-02-01; appellate divisions start in 2004 (printed zeros in 2002–2003 appeal tables are flagged pre_establishment).")
    raise AssertionError(f"no event spec for {cid} ({ev})")


def court_events(courts, panel):
    ids = set(courts.court_id_h)
    tabs = panel[panel.value.ne(0)].groupby("court_id_h").table_id.agg(lambda s: ";".join(sorted(set(s))))
    c = courts[courts.legal_event.astype(str) != ""].copy()
    rows = []
    for r in c.itertuples():
        frm, etype, scope, aff, action = _spec(r)
        date = _DATE.get(r.court_id_h, str(r.legal_start))
        to = _EVENT_TO.get(r.court_id_h, r.court_id_h)
        for f in filter(None, frm.split(";")):
            assert f in ids, (r.court_id_h, f)
        parent = frm.split(";")[0] if aff else ""
        rows.append(dict(event_date=date, event_year=int(date[:4]), in_data_period=2002 <= int(date[:4]) <= 2025,
                         event_type=etype, from_court_id_h=frm, to_court_id_h=to, affected_parent_court_id_h=parent,
                         case_scope=scope, tables_affected=tabs.get(to, ""), affects_parent_series=aff,
                         recommended_user_action=action, legal_basis_ko=r.legal_basis_ko, legal_basis_en=r.legal_basis_en,
                         note_en=r.data_note_en))
    for e in EXTRA_EVENTS:
        rows.append(dict(e, event_year=int(e["event_date"][:4]), in_data_period=True, tables_affected=tabs.get(e["to_court_id_h"], "")))
    ev = pd.DataFrame(rows).sort_values(["event_date", "to_court_id_h"]).reset_index(drop=True)
    ev.insert(0, "event_id", [f"ev{i:03d}" for i in range(1, len(ev) + 1)])
    return ev
