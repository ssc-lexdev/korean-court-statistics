"""Court-level filings panel (2002–2025) + court crosswalk.

Sources: the 10 multi-year comparison tables titled '…누년비교표-법원별 접수' (multi-year comparison table,
filings by court)
  - 2016–2025: 2025 Excel
  - 2007–2016: 2016 PDF (GPT vision)
  - 2002–2011: 2011 PDF (GPT vision)
  - Small claims only: the 2011-edition PDF covers 2007–2011 (5-year window) → 2002–2006 from the 2006 PDF (GPT vision)
Outputs (data/series/):
  court_panel_long.csv   year, table, court_id, court, district, unit_type, value, source
  court_crosswalk.csv    per-court period of appearance, unit type and tables (+ merged with the hand-written
                         notes in court_crosswalk_notes.csv)
  court_checks.csv       subtotal checks (sum of courts in a district = subtotal/district total,
                         sum of district courts = grand total)
  court_overlap_check.csv comparison of overlapping years across sources
"""
import glob
import re
import sys
from pathlib import Path

import openpyxl
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from vision_util import TEXT_CACHE, ask, n_pages, page_png, page_text  # noqa: E402

BASE = Path(__file__).parent / "data"
OUT = BASE / "series"
MINI = "gpt-5.4-mini"

# key: (domain, Excel file key, title regex (applied after removing whitespace), display title)
TABLES = {
    "민사본안_1심_합의": ("민사", "02항.민사", r"제1심민사본안합의사건누년비교표.{0,3}법원별", "제1심 민사본안 합의사건 누년비교표-법원별 접수"),
    "민사본안_1심_단독": ("민사", "02항.민사", r"제1심민사본안단독사건.{0,12}누년비교표.{0,3}법원별", "제1심 민사본안 단독사건(소액사건 제외) 누년비교표-법원별 접수"),
    "민사본안_1심_소액": ("민사", "02항.민사", r"(제1심민사본안)?소액사건누년비교표.{0,3}법원별", "제1심 민사본안 소액사건 누년비교표-법원별 접수"),
    "민사본안_항소심": ("민사", "02항.민사", r"항소심민사본안사건누년비교표.{0,3}법원별", "항소심 민사본안사건 누년비교표-법원별 접수"),
    "가사소송_1심": ("가사", "03항.가사", r"제1심가사소송사건누년비교표.{0,3}법원별", "제1심 가사소송사건 누년비교표-법원별 접수"),
    "가사소송_항소심": ("가사", "03항.가사", r"항소심가사소송사건누년비교표.{0,3}법원별", "항소심 가사소송사건 누년비교표-법원별 접수"),
    "형사공판_1심": ("형사", "06항.형사", r"제1심형사공판사건누년비교표(\(총괄\))?.{0,3}법원별", "제1심 형사공판사건 누년비교표(총괄)-법원별 접수 [인원수]"),
    "형사공판_1심_합의": ("형사", "06항.형사", r"제1심형사공판합의사건누년비교표.{0,3}법원별", "제1심 형사공판 합의사건 누년비교표-법원별 접수 [인원수]"),
    "형사공판_1심_단독": ("형사", "06항.형사", r"제1심형사공판단독사건누년비교표.{0,3}법원별", "제1심 형사공판 단독사건 누년비교표-법원별 접수 [인원수]"),
    "형사공판_항소심": ("형사", "06항.형사", r"항소심형사공판사건누년비교표.{0,3}법원별", "항소심 형사공판사건 누년비교표-법원별 접수 [인원수]"),
}


def nz(s):
    return re.sub(r"\s+", "", str(s or "")).replace("１", "1").replace("ㆍ", "·")


# Typo fixes in the source data (where each was found is noted). Fixes are documented in HANDOFF and the
# paper's Usage Notes.
LABEL_FIXES = {
    "지밥법원": "지방법원",  # 2019 & 2020 editions, civil first-instance small claims: typo `제주지밥법원관내합계` (Jeju district total)
    "서울의정부지방법원": "의정부지방법원",  # 2011 edition OCR misread (criminal first-instance single-judge)
    "부산지법동부지원": "동부지원",          # spelling variant in some editions
    "부산지법서부지원": "서부지원",
    "과천시법원": "광명시법원",  # 2016 edition small claims p10 OCR misread (source reads `광명시법원` (Gwangmyeong); no `과천시법원` (Gwacheon) court exists) — sample check 2026-11-18
}


def fix_label(lab):
    for a, b in LABEL_FIXES.items():
        lab = lab.replace(a, b)
    return lab


def num(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = re.sub(r"[^\d.\-]", "", str(v))
    return float(s) if s not in ("", "-", ".") else (0.0 if str(v).strip() in ("-", "–", "—") else None)


# ---------------------------------------------------------------- hierarchy assignment
def rel(f):
    """Path relative to data/ (forward slashes) — same format as source_manifest.csv."""
    import os
    return os.path.relpath(str(f), str(BASE)).replace("\\", "/")


def assign_hierarchy(rows):
    """rows: [(label, {year: value}[, loc])] in table order. loc = page ('p10') or sheet & row ('Sheet!r23').
    → [(court_id, label, district, unit_type, group, {year: v}, loc)]
    group: in appellate tables, the high-court-total / district-court-total block ('' if none)."""
    out, district, group = [], None, ""
    for label, vals, *loc in rows:
        n0 = len(out)
        _hier_step(out, label, vals, district, group)
        if len(out) > n0:
            district, group = out[-1][-2], out[-1][-1]  # retrieve the updated state
            out[-1] = (*out[-1][:6], loc[0] if loc else "")
    return out


def _hier_step(out, label, vals, district, group):
    """Classify one row in the hierarchy. Appends (cid, lab, district, unit_type, group, vals, new_district,
    new_group) to out."""
    def push(t):
        out.append((*t, district, group))
    lab = fix_label(nz(label))
    if not lab or lab in ("평균", "구분", "법원", "연도"):
        return
    if re.fullmatch(r"(총계|합계|계|전국)", lab):
        push(("전국", lab, "전국", "national_total", "", vals))
    elif re.fullmatch(r"(고등법원|지방법원)(계|합계)", lab):
        group = lab[:4]
        push((f"{group}계", lab, group, "group_total", group, vals))
    elif lab.endswith("관내합계") or lab.endswith("관내계"):
        d = re.sub(r"관내(합)?계$", "", lab)
        district = d
        push((f"{d}/관내합계", lab, d, "district_total", group, vals))
    elif re.fullmatch(r"소계|계\(.*\)", lab):
        push((f"{district}/소계", lab, district, "district_total", group, vals))
    elif re.search(r"고등법원", lab) or (lab == "특허법원" and group == "고등법원"):
        push((lab, lab, lab, "high_court", group, vals))
    elif re.search(r"(지방법원|가정법원|회생법원|행정법원|특허법원)(본원)?(\(.*\))?$", lab):
        district = re.sub(r"(본원)?(\(.*\))?$", "", lab)  # e.g. `광주지방법원(가정지원)` → `광주지방법원` (Gwangju District Court)
        push((district, lab, district, "main_court", group, vals))
    elif lab.endswith("지원"):
        push((f"{district}/{lab}", lab, district, "branch", group, vals))
    elif re.search(r"(시|군)법원$", lab):
        push((f"{district}/{lab}", lab, district, "si_gun_court", group, vals))
    else:
        push((f"{district}/{lab}", lab, district, "other", group, vals))


def _assign_hierarchy_legacy(rows):
    """(Reference only, unused) Original implementation before source locations were added — used to verify that
    results are identical."""
    out, district, group = [], None, ""
    for label, vals, *_ in rows:
        lab = fix_label(nz(label))
        if not lab or lab in ("평균", "구분", "법원", "연도"):
            continue
        if re.fullmatch(r"(총계|합계|계|전국)", lab):
            out.append(("전국", lab, "전국", "national_total", "", vals))
        elif re.fullmatch(r"(고등법원|지방법원)(계|합계)", lab):
            group = lab[:4]
            out.append((f"{group}계", lab, group, "group_total", group, vals))
        elif lab.endswith("관내합계") or lab.endswith("관내계"):
            d = re.sub(r"관내(합)?계$", "", lab)
            district = d
            out.append((f"{d}/관내합계", lab, d, "district_total", group, vals))
        elif re.fullmatch(r"소계|계\(.*\)", lab):
            out.append((f"{district}/소계", lab, district, "district_total", group, vals))
        elif re.search(r"고등법원", lab) or (lab == "특허법원" and group == "고등법원"):
            out.append((lab, lab, lab, "high_court", group, vals))
        elif re.search(r"(지방법원|가정법원|회생법원|행정법원|특허법원)(본원)?(\(.*\))?$", lab):
            district = re.sub(r"(본원)?(\(.*\))?$", "", lab)  # e.g. `광주지방법원(가정지원)` → `광주지방법원` (Gwangju District Court)
            out.append((district, lab, district, "main_court", group, vals))
        elif lab.endswith("지원"):
            out.append((f"{district}/{lab}", lab, district, "branch", group, vals))
        elif re.search(r"(시|군)법원$", lab):
            out.append((f"{district}/{lab}", lab, district, "si_gun_court", group, vals))
        else:
            out.append((f"{district}/{lab}", lab, district, "other", group, vals))
    return out

# ---------------------------------------------------------------- Excel
def as_year(x):
    """Header cell → year. Accepts 2016, 2016.0, '2016년' ('2016 year'), "'16"."""
    if isinstance(x, (int, float)) and 1990 < x < 2100:
        return int(x)
    m = re.fullmatch(r"(\d{4})년?", nz(x)) if isinstance(x, str) else None
    return int(m.group(1)) if m and 1990 < int(m.group(1)) < 2100 else None

def xlsx_file(ed, fk):
    """The multi-year comparison file of edition ed matching the key (e.g. '02항.민사', section 02 civil).
    Tolerates differing filename separators (., space, _)."""
    rx = re.escape(fk).replace(r"\.", r"[.\s_]?")
    fs = [f for f in glob.glob(str(BASE / f"xlsx/{ed}/*누년*/*.xlsx")) if re.search(rx, Path(f).name)]
    return fs[0] if fs else None


def from_excel(ed=2025):
    recs = []
    for key, (dom, fk, trx, _) in TABLES.items():
        f = xlsx_file(ed, fk)
        if not f:
            print(f"  {ed} {key}: Excel 파일 없음")
            continue
        wb = openpyxl.load_workbook(f, data_only=True)
        rows_out, years, active = [], None, False
        for ws in wb.worksheets:
            for ri, r in enumerate(ws.iter_rows(values_only=True), 1):
                v = [x for x in r if x is not None]
                if not v:
                    continue
                first = nz(v[0]) if isinstance(v[0], str) else ""
                if isinstance(v[0], str) and re.match(r"^\d+\.", first):
                    active = bool(re.search(trx, first))  # keep going on a "(continued)" of the same table; stop at a different table
                    continue
                if not active:
                    continue
                hdr = [as_year(x) for x in v[1:]]
                if first in ("연도", "구분") and any(hdr):
                    years = [y for y in hdr if y]
                    continue
                if years and isinstance(v[0], str) and first not in ("법원", "평균"):
                    nums = [num(x) for x in v[1:1 + len(years)]]
                    rows_out.append((v[0], dict(zip(years, nums)), f"{ws.title}!r{ri}"))
        # The same court can appear twice, once per year block (small claims split into 5-year blocks)
        # → merge after assigning the hierarchy
        n = 0
        for cid, lab, dist, ut, grp, vals, loc in assign_hierarchy(rows_out):
            for y, val in vals.items():
                if val is not None:
                    recs.append((y, key, cid, lab, dist, ut, grp, val, f"{ed}_xlsx", rel(f), loc))
                    n += 1
        if n == 0:
            print(f"  {ed} {key}: 표를 찾지 못함")
    return recs


# ---------------------------------------------------------------- PDF (vision)
SECTION_PAGES = {  # page range to scan per domain (page numbers of the multi-year PDF); exact pages found by title classification
    2016: {"민사": range(6, 20), "가사": range(40, 48), "형사": range(50, 62)},
    2011: {"민사": range(4, 20), "가사": range(38, 48), "형사": range(48, 62)},
    2006: {"민사": range(10, 14)},  # small claims 2002–2006 only (the 2011 edition covers 2002–2011 for the other tables)
}
# Continuation pages with no printed title (right-hand pages of a 4-page table). Confirmed via the text layer:
# in the 2006, 2011 and 2016 editions alike, p10 (title), p11 (no title), p12 (continued), p13 (no title); the first
# row of each page continues from the last court on the previous page.
CONT_PAGES = {(ed, "민사본안_1심_소액"): {11, 13} for ed in (2006, 2011, 2016)}
PDF_KEYS = {2006: {"민사본안_1심_소액"}}  # restrict which tables are extracted per edition (all if absent)


def classify_pages(year):
    f = glob.glob(str(BASE / f"raw/{year}/pdf/*추이*.pdf"))[0]
    found = {k: [] for k in TABLES}
    for dom, pages in SECTION_PAGES[year].items():
        for p in pages:
            if p > n_pages(f):
                continue
            t = nz(page_text(f, p))
            hits = [k for k, v in TABLES.items() if v[0] == dom and re.search(v[2], t)]
            if not hits:  # if the text layer does not reveal the title, classify titles with a low-cost model
                # Prompt (English translation; the Korean string below is the text actually sent):
                #   List every table title on this page (Republic of Korea Judicial Yearbook, multi-year comparison) as
                #   JSON {"titles": [..]}. Include '(계속)' ("continued") markers too.
                r = ask("이 페이지(대한민국 사법연감 누년비교)에 있는 모든 표 제목을 JSON {\"titles\": [..]} 로 나열하라. "
                        "'(계속)' 표기도 포함.", [page_png(f, p, dpi=110)], model=MINI, detail="low")
                tt = nz(" ".join(r.get("titles", [])))
                hits = [k for k, v in TABLES.items() if v[0] == dom and re.search(v[2], tt)]
            for k in hits:
                found[k].append(p)
    for (ed, k), ps in CONT_PAGES.items():
        if ed == year:
            found[k] = sorted(set(found[k]) | ps)
    return f, found


def extract_pdf_page(f, p, key, cont=False):
    title = TABLES[key][3]
    if cont:  # untitled continuation page: only court rows with the same column layout continue here
        # Prompt (English translation; the Korean string below is the text actually sent):
        #   The image is a page of the Republic of Korea Judicial Yearbook 'Trends in cases (multi-year comparison)';
        #   it is the continuation of the '{title}' table from the previous page (no title is printed). Read the
        #   table on this page. Keep the row (court) order exactly as in the table, and include all total, subtotal,
        #   district-total and si/gun (municipal) court rows. Exclude the 'average' column.
        #   JSON: {"found": bool, "title_seen": "", "years": [4-digit years...],
        #   "rows": [{"label": "court name", "values": [integers or null, in year order]}]}
        #   Numbers are integers without commas. '-' is 0. If unreadable, null.
        prompt = (
            f"이미지는 대한민국 사법연감 '사건의 추이(누년비교)' 페이지로, 앞 쪽 '{title}' 표의 이어지는 부분이다(제목이 인쇄되지 않음). "
            "이 페이지의 표를 읽어라. 행(법원) 순서를 표에 나온 그대로 유지하고, 합계·소계·관내합계·시군법원 행도 모두 포함하라. '평균' 열은 제외.\n"
            "JSON: {\"found\": bool, \"title_seen\": \"\", \"years\": [연도4자리...], "
            "\"rows\": [{\"label\": \"법원명\", \"values\": [연도 순서대로 정수 또는 null]}]}\n"
            "숫자는 쉼표 없는 정수. '-'는 0. 읽을 수 없으면 null.")
        return ask(prompt, [page_png(f, p)])
    # Prompt (English translation; the Korean string below is the text actually sent):
    #   The image is a page of the Republic of Korea Judicial Yearbook 'Trends in cases (multi-year comparison)'.
    #   Read only the '{title}' table (or its '(continued)' part). Ignore other tables on the same page. If the page
    #   has two columns, read the left column top→bottom, then the right column top→bottom.
    #   Keep the row (court) order exactly as in the table, and include all total, subtotal, district-total and
    #   si/gun (municipal) court rows. Exclude the 'average' column.
    #   JSON: {"found": bool, "title_seen": "the title text of this table exactly as actually printed on this page
    #   (including its number; empty string if none)", "years": [4-digit years...],
    #   "rows": [{"label": "court name", "values": [integers or null, in year order]}]}
    #   - If the requested table's title is not actually on this page, do not read another table instead; found=false.
    #   Numbers are integers without commas. '-' is 0. If unreadable, null. If a page has two year blocks, the same
    #   court may appear twice in rows; in that case put a separate "years" key in each row.
    prompt = (
        f"이미지는 대한민국 사법연감 '사건의 추이(누년비교)' 페이지다. '{title}' 표(또는 그 '(계속)' 부분)만 읽어라. "
        "같은 페이지의 다른 표는 무시. 페이지가 좌우 2단이면 왼쪽 단 위→아래, 그다음 오른쪽 단 위→아래 순서.\n"
        "행(법원) 순서를 표에 나온 그대로 유지하고, 합계·소계·관내합계·시군법원 행도 모두 포함하라. '평균' 열은 제외.\n"
        "JSON: {\"found\": bool, \"title_seen\": \"이 페이지에 실제로 인쇄된 해당 표 제목 텍스트 그대로(번호 포함, 없으면 빈 문자열)\", "
        "\"years\": [연도4자리...], \"rows\": [{\"label\": \"법원명\", \"values\": [연도 순서대로 정수 또는 null]}]}\n"
        "- 요청한 표의 제목이 이 페이지에 실제로 없으면 다른 표를 대신 읽지 말고 found=false.\n"
        "숫자는 쉼표 없는 정수. '-'는 0. 읽을 수 없으면 null. 한 페이지에 연도 블록이 2개면 rows에 같은 법원이 두 번 나와도 되며 "
        "그 경우 각 행에 \"years\" 키를 따로 넣어라.")
    return ask(prompt, [page_png(f, p)])


def from_pdf(year):
    f, found = classify_pages(year)
    recs = []
    for key, pages in found.items():
        if year in PDF_KEYS and key not in PDF_KEYS[year]:
            continue
        rows = []
        for p in sorted(set(pages)):
            cont = p in CONT_PAGES.get((year, key), set())
            r = extract_pdf_page(f, p, key, cont)
            seen = nz(r.get("title_seen"))
            if cont:
                t = nz(page_text(f, p))  # continuation-page safeguard: discard if another table's title is printed
                if not r.get("found") or re.search(r"\d+\.[^\d]{2,40}누년비교표", t):
                    print(f"    skip cont p{p} {key}")
                    continue
            elif not r.get("found") or not re.search(TABLES[key][2], seen):
                print(f"    skip p{p} {key}: title_seen='{seen[:40]}'")
                continue
            yrs = r.get("years") or []
            for row in r.get("rows", []):
                ys = row.get("years") or yrs
                vals = {int(y): num(v) for y, v in zip(ys, row.get("values") or []) if v is not None}
                rows.append((row.get("label"), vals, f"p{p}"))
        n = 0
        for cid, lab, dist, ut, grp, vals, loc in assign_hierarchy(rows):
            for y, val in vals.items():
                recs.append((y, key, cid, lab, dist, ut, grp, val, f"{year}_pdf_vision", rel(f), loc))
                n += 1
        print(f"  {year} {key:16s} pages={sorted(set(pages))} values={n}")
    return recs


# ---------------------------------------------------------------- checks & output
def checks(df):
    """Internal total checks.
    district: sum of courts in the district (main court + branches + si/gun courts) = subtotal/district total
    group   : high-court total / district-court total = sum of member courts (appellate tables)
    national: national total = sum of group totals (if present) or sum over district-court units"""
    res = []
    for (src, key, y), g in df.groupby(["source", "table", "year"]):
        for d, gd in g[g.unit_type != "group_total"].groupby("district"):
            tot = gd[gd.unit_type == "district_total"].value
            if tot.empty:
                continue
            parts = gd[gd.unit_type.isin(["main_court", "branch", "si_gun_court", "other"])].value.sum()
            res.append((src, key, y, d, "district", tot.iloc[0], parts))
        gt = g[g.unit_type == "group_total"]
        for _, r in gt.iterrows():
            parts = g[(g.group == r.group) & g.unit_type.isin(["high_court", "main_court"])].value.sum()
            res.append((src, key, y, r.court_id, "group", r.value, parts))
        nat = g[g.unit_type == "national_total"].value
        if not nat.empty:
            if not gt.empty:
                s = gt.value.sum()
            else:
                dt = g[g.unit_type == "district_total"].groupby("district").value.first()
                s = dt.sum() + g[g.unit_type.isin(["main_court", "high_court"]) & ~g.district.isin(dt.index)].value.sum()
            res.append((src, key, y, "전국", "national", nat.iloc[0], s))
    c = pd.DataFrame(res, columns=["source", "table", "year", "district", "level", "reported", "sum_of_parts"])
    c["diff"] = c.reported - c.sum_of_parts
    c["ok"] = c["diff"].abs() < 0.5
    return c

def repair_hierarchy(df):
    """Fix OCR rows assigned to the wrong parent court. Reference: digital (Excel) data, where a branch or si/gun
    court name maps to a unique parent court. First choice: digital data of the same table; second: all tables of
    the same domain (family / non-family). Names under several parent courts (e.g. `서부지원`, "West Branch") are left
    as is."""
    dig = df[~df.source.str.contains("vision") & df.unit_type.isin(["branch", "si_gun_court"])]
    is_gasa = df.table.str.startswith("가사")
    def uniq_map(sub):
        m = sub.groupby("court").district.unique()
        return {k: v[0] for k, v in m.items() if len(v) == 1}
    by_table = {t: uniq_map(g) for t, g in dig.groupby("table")}
    by_dom = {True: uniq_map(dig[dig.table.str.startswith("가사")]), False: uniq_map(dig[~dig.table.str.startswith("가사")])}
    ocr = df.source.str.contains("vision") & df.unit_type.isin(["branch", "si_gun_court"])
    tgt = [by_table.get(t, {}).get(c) or by_dom[g].get(c) for t, c, g in zip(df.table, df.court, is_gasa)]
    tgt = pd.Series(tgt, index=df.index)
    # `X지방법원` (district court) ↔ `X가정법원` (family court) is a name succession (merged in harmonize), so do not reassign
    same_family = pd.Series([isinstance(t, str) and isinstance(d, str) and t.replace("가정법원", "지방법원") == d.replace("가정법원", "지방법원")
                             for t, d in zip(tgt, df.district)], index=df.index)
    fix = ocr & tgt.notna() & (tgt != df.district) & ~same_family
    df.loc[fix, "district"] = tgt[fix]
    df.loc[fix, "court_id"] = df.loc[fix, "district"] + "/" + df.loc[fix, "court"]
    print(f"  계층 교정: OCR 지원·시군법원 {int(fix.sum())}개 값의 상위 법원 재배정")
    return df


SI_GUN_RENAMES = {
    "대전지방법원/당진군법원": "대전지방법원/당진시법원",
    "대전지방법원/연기군법원": "대전지방법원/세종특별자치시법원",
    "수원지방법원/광주군법원": "수원지방법원/광주시법원",
    "수원지방법원/안성군법원": "수원지방법원/안성시법원",
    "의정부지방법원/포천군법원": "의정부지방법원/포천시법원",
    "인천지방법원/김포군법원": "인천지방법원/김포시법원",
    "창원지방법원/진해시법원": "창원지방법원/창원남부시법원",  # Act No. 10536 (2011-04-05), Annex 2: located in Jinhae-gu, Changwon
}

# OCR errors corrected by checking against the source (2026-11-18). Cells where the 2016- and 2011-edition OCR
# disagree and no digital original exists were read from the source page image and text layer.
# (table, court_id, year): (corrected value, evidence)
VALUE_FIXES = {
    ("민사본안_1심_단독", "수원지방법원/안산지원", 2007): (5948, "2016판 OCR 5,748 → 원문 5,948 (2016판 추이 p9, 2011판 일치, 소계 26,947 정합)"),
    ("민사본안_1심_단독", "수원지방법원/안양지원", 2007): (0, "2016판 OCR 200 → 원문 '-' (안양지원 2009.3.1 설치; 안산지원 값 분할 오독)"),
    ("형사공판_1심_단독", "창원지방법원/진주지원", 2009): (2945, "2016판 OCR 2,745 → 원문 2,945 (2016판 추이 p56·2011판 p56 텍스트 레이어)"),
    # 2026-11-19 re-read of an unresolved warning (district_sum_mismatch): text layer + visual check of the 200 dpi
    # page image; subtotal reconciles after the fix
    ("민사본안_1심_단독", "광주지방법원", 2005): (9566, "2011판 OCR 9,560 → 원문 9,566 (2011판 추이 p9 텍스트 레이어·쪽 이미지, 소계 15,504 정합)"),
    # 2026-11-20 positional check of every OCR value against the text-layer word coordinates (court_position.py):
    # two cells of one column were misread so that their sum, and hence the subtotal check, was unchanged
    ("민사본안_1심_합의", "대전지방법원/천안지원", 2006): (536, "2011판 OCR 530 → 원문 536 (2011판 추이 p8 텍스트 레이어 좌표·쪽 이미지; 홍성지원 171과 합 707 동일해 소계 검사 통과)"),
    ("민사본안_1심_합의", "대전지방법원/홍성지원", 2006): (171, "2011판 OCR 177 → 원문 171 (2011판 추이 p8 텍스트 레이어 좌표·쪽 이미지; 천안지원 536과 합 707 동일해 소계 검사 통과)"),
}


def apply_fixes(best):
    best = best.copy()
    best["fix_note"] = ""
    for (t, cid, y), (v, why) in VALUE_FIXES.items():
        m = (best.table == t) & (best.court_id == cid) & (best.year == y)
        assert m.sum() == 1, (t, cid, y, int(m.sum()))
        best.loc[m, "value"] = v
        best.loc[m, "qc_flag"] = "ocr_corrected_manual"
        best.loc[m, "fix_note"] = why
    print(f"  수동 정정: {len(VALUE_FIXES)}개 값")
    return best


def harmonize(best):
    """court_id_h: unify the same court appearing under different names in different periods.
    Family tables: `X지방법원` (district court; before a family court was established, or labeled as a family branch)
    → `X가정법원` (family court) if the same table contains `X가정법원` (branches included)."""
    best = best.copy()
    best["court_id_h"] = best.court_id
    best["harmonize_note"] = ""
    for t in [t for t in best.table.unique() if t.startswith("가사")]:
        m = best.table == t
        fam = set(best.loc[m, "district"])
        for d in sorted(fam):
            if d.endswith("지방법원") and d.replace("지방법원", "가정법원") in fam:
                h = d.replace("지방법원", "가정법원")
                mm = m & (best.district == d)
                best.loc[mm, "court_id_h"] = best.loc[mm, "court_id"].str.replace(d, h, n=1, regex=False)
                best.loc[mm, "harmonize_note"] = f"{d}→{h} (가사 관할 승계)"
    # si/gun court renames (same jurisdiction) — evidence in court_crosswalk_notes.csv
    for old, new in SI_GUN_RENAMES.items():
        mm = best.court_id == old
        best.loc[mm, "court_id_h"] = new
        best.loc[mm, "harmonize_note"] = f"{old.split('/')[1]}→{new.split('/')[1]} (명칭 변경)"
    # If the same (table, year, court_id_h) appears under two source names, keep the higher-priority (earlier) one
    best["_p"] = best.source.map(lambda s: 0 if "xlsx" in s else 1)
    best = best.sort_values("_p").drop_duplicates(["table", "year", "court_id_h"]).drop(columns="_p")
    return best

def add_qc(best, c):
    """Quality flags: source_type (digital/ocr), qc_flag (set when the subtotal or national-total check containing an
    OCR value fails)."""
    best = best.copy()
    best["source_type"] = best.source.str.contains("vision").map({True: "ocr", False: "digital"})
    # Total checks are per source (edition) block. c = check results on extracted values with the source-verified
    # corrections (VALUE_FIXES) applied
    bad = c[~c.ok]
    bad_d = set(zip(bad.source, bad.table, bad.year, bad.district))
    if "qc_flag" not in best:
        best["qc_flag"] = ""
    keep = best.qc_flag.eq("ocr_corrected_manual")
    is_ocr = best.source_type == "ocr"
    in_bad_d = pd.Series([(s_, t, y, d) in bad_d for s_, t, y, d in zip(best.source, best.table, best.year, best.district)], index=best.index)
    best.loc[~keep, "qc_flag"] = ""
    best.loc[~keep & is_ocr & in_bad_d & (best.unit_type != "national_total"), "qc_flag"] = "district_sum_mismatch"
    nb = bad[bad.level == "national"]
    bad_n = set(zip(nb.source, nb.table, nb.year))
    in_bad_n = pd.Series([(s_, t, y) in bad_n for s_, t, y in zip(best.source, best.table, best.year)], index=best.index)
    best.loc[~keep & is_ocr & in_bad_n & (best.unit_type == "national_total"), "qc_flag"] = "national_sum_mismatch"
    return best


def main():
    cols = ["year", "table", "court_id", "court", "district", "unit_type", "group", "value", "source", "source_file", "source_page"]
    parts = [from_excel(ed) for ed in range(2025, 2018, -1)]
    for y in (2016, 2011, 2006):
        parts.append(from_pdf(y))
    df = pd.DataFrame([r for p in parts for r in p], columns=cols)
    df = repair_hierarchy(df)
    df = df.drop_duplicates(["year", "table", "court_id", "source"])

    c = checks(df)
    c.to_csv(OUT / "court_checks.csv", index=False, encoding="utf-8-sig")
    print("\n소계 검증 통과율(출처별):")
    print(c.groupby(["source", "level"]).ok.agg(["sum", "count"]).to_string())

    piv = df.pivot_table(index=["table", "court_id", "year"], columns="source", values="value")
    ov = piv[piv.notna().sum(axis=1) > 1].copy()
    ov["일치"] = ov.nunique(axis=1) == 1
    ov.to_csv(OUT / "court_overlap_check.csv", encoding="utf-8-sig")
    print("\n출처 간 겹침 일치:", int(ov["일치"].sum()), "/", len(ov))

    pri = {f"{ed}_xlsx": 2025 - ed for ed in range(2019, 2026)} | {"2016_pdf_vision": 10, "2011_pdf_vision": 11, "2006_pdf_vision": 12}
    df["p"] = df.source.map(pri)
    best = (df.sort_values("p").drop_duplicates(["year", "table", "court_id"]).drop(columns="p")
              .query("2002 <= year <= 2025").sort_values(["table", "court_id", "year"]))
    best = apply_fixes(best)
    # Re-check after corrections: separately from court_checks.csv (raw extracted values), apply VALUE_FIXES to the
    # same cell in every source and re-run the total checks
    dfx = df.copy()
    for (t, cid, y), (v, _) in VALUE_FIXES.items():
        dfx.loc[(dfx.table == t) & (dfx.court_id == cid) & (dfx.year == y) & dfx.source.str.contains("vision"), "value"] = v
    cr = checks(dfx)
    cr.to_csv(OUT / "court_checks_after_fixes.csv", index=False, encoding="utf-8-sig")
    print("정정 반영 후 합계 검증:", int(cr.ok.sum()), "/", len(cr), "(정정 전", int(c.ok.sum()), ")")
    best = add_qc(best, cr)
    best = harmonize(best)
    best.to_csv(OUT / "court_panel_long.csv", index=False, encoding="utf-8-sig")

    # Crosswalk (automatic part): period of appearance per court
    nzv = best[best.value > 0]
    cw = (nzv.groupby(["court_id_h", "unit_type"])
              .agg(first_year=("year", "min"), last_year=("year", "max"), n_years=("year", "nunique"),
                   source_ids=("court_id", lambda s: " ; ".join(sorted(set(s)))),
                   source_labels=("court", lambda s: " ; ".join(sorted(set(s)))),
                   harmonize_note=("harmonize_note", lambda s: " ; ".join(sorted(set(x for x in s if x)))),
                   tables=("table", lambda s: ",".join(sorted(set(s)))))
              .reset_index().sort_values(["court_id_h"]))
    cw["coverage_note"] = [
        ("자료상 최초 등장 %d" % f if f > 2002 else "") + (" / 자료상 마지막 %d" % l if l < 2025 else "")
        for f, l in zip(cw.first_year, cw.last_year)]
    notes = OUT / "court_crosswalk_notes.csv"
    if notes.exists():
        cw = cw.merge(pd.read_csv(notes), on="court_id_h", how="left")
    cw.to_csv(OUT / "court_crosswalk.csv", index=False, encoding="utf-8-sig")
    print(f"\n패널: {best.court_id.nunique()}개 법원 단위 × {best.table.nunique()}개 표, {len(best):,}개 값")


if __name__ == "__main__":
    main()
