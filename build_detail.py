"""(1) Observed pending-case series + (2) civil / family / criminal multi-year series.

(1) Total and per-instance rows of the case-overview tables `○○사건 접수·처리·미제 건수(표 N)`
    ("filed / disposed / pending counts for ○○ cases (Table N)")
    - 2019–2025: parsed directly from Excel
    - 2007–2018: PDF page -> GPT vision (for the 2015 scanned edition and the 2017 edition with broken
      fonts, pages are located by vision classification)
    - 2002–2006: observed pending counts from the 2006 multi-year comparison table (output of build_series.py)
(2) Filed / disposed counts from 7 multi-year comparison tables
    - 2016–2025: 2025 Excel / 2007–2016: 2016 PDF vision / 2002–2011: 2011 PDF vision
Outputs: data/series/pending_actual.csv, detail_long.csv, detail_wide.csv, detail_overlap_check.csv,
         long_series.csv (version with observed pending counts), wide_series.csv
"""
import glob
import re
import sys
from pathlib import Path

import openpyxl
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from vision_util import TEXT_CACHE, ask, n_pages, page_png, page_text  # noqa: E402
import fitz  # noqa: E402


def fitz_text(f, p):
    return page_text(f, p, engine="fitz")

BASE = Path(__file__).parent / "data"
OUT = BASE / "series"
MINI = "gpt-5.4-mini"


def nz(s):
    return re.sub(r"\s+", "", str(s or "")).replace("１", "1").replace("∙", "·").replace("ㆍ", "·").replace("‧", "·").replace("･", "·")


def to_int(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return int(round(v))
    s = re.sub(r"[^\d\-]", "", str(v))
    return int(s) if s not in ("", "-") else None


# =====================================================================
# (1) Observed pending cases
# =====================================================================
CATS = {  # key: (title regex, description)
    "민사본안": (r"민사본안", "민사본안사건 접수·처리·미제 건수"),
    "가사소송": (r"가사소송", "가사소송사건 접수·처리·미제 건수"),
    "행정소송": (r"행정소송|행정\(본안\)", "행정소송사건 접수·처리·미제 건수"),
    "특허·지식재산": (r"특허소송|지식재산소송|특허사건|지식재산사건", "특허(지식재산)소송사건 접수·처리·미제 건수"),
    "형사공판": (r"형사공판", "형사공판사건 접수·처리·미제 상황"),
    "치료감호": (r"치료감호", "치료감호사건 접수·처리·미제 인원"),
}
TITLE_RX = r"([가-힣()]{2,25})접수[·,]?처리[·,]?미제(?:건수|상황|인원)?\(표(\d+)\)"


def gaehwang_pdfs(y):
    return [f for f in sorted(glob.glob(str(BASE / f"raw/{y}/pdf/*.pdf"))) if "개황" in f]


def locate_by_text(y):
    found = {}
    for f in gaehwang_pdfs(y):
        for p in range(1, n_pages(f) + 1):
            t = nz(page_text(f, p)) + "|" + nz(fitz_text(f, p))
            for m in re.finditer(TITLE_RX, t):
                for c, (rx, _) in CATS.items():
                    if re.search(rx, m.group(1)) and c not in found:
                        found[c] = (f, p)
    return found


def locate_by_vision(y, ref, win=6):
    """Years without usable text: classify pages within ±win of the reference year's page with a low-cost model."""
    f = gaehwang_pdfs(y)[0]
    N = n_pages(f)
    found = {}
    for c, (rf, rp) in ref.items():
        for p in sorted(range(max(1, rp - win), min(N, rp + win) + 1), key=lambda p: abs(p - rp)):
            # Prompt (English translation; the Korean string below is the text actually sent):
            #   List every table title on this page (Korean Judicial Yearbook) as JSON {"titles": [..]}.
            #   Titles usually take the form '...(Table 12)'.
            r = ask("이 페이지(대한민국 사법연감)에 있는 모든 표 제목을 JSON {\"titles\": [..]} 로 나열하라. "
                    "제목은 보통 '...(표 12)' 형태다.", [page_png(f, p, dpi=110)], model=MINI, detail="low")
            if any(re.search(CATS[c][0], nz(t)) and "미제" in nz(t) and "접수" in nz(t) and "기간" not in nz(t)
                   for t in r.get("titles", [])):
                found[c] = (f, p)
                break
    return found


def extract_pdf(f, p, cat):
    # Prompt (English translation; the Korean string below is the text actually sent):
    #   The image is a page of the Korean Judicial Yearbook (case overview). Find the table
    #   '{CATS[cat][1]}(Table N)' whose title contains all of 'filed', 'disposed' and 'pending', and extract all its
    #   rows. Only this table, even if other tables are on the same page.
    #   JSON: {"found": bool, "title": str, "rows": [{"label": str, "접수": int, "처리": int, "미제": int}]}
    #   (keys 접수 = filed, 처리 = disposed, 미제 = pending)
    #   - label is the row name as written in the table (e.g. total, first-instance subtotal, panel, single judge,
    #     appellate subtotal, supreme court)
    #   - Numbers as integers without commas. Ignore auxiliary numbers inside brackets [ ] or parentheses ( );
    #     use only the main number.
    #   - Use 'filed this year' as filed. If disposals are broken down, use the disposal total. If unreadable, null.
    prompt = (
        "이미지는 대한민국 사법연감(사건개황) 페이지다. 제목에 '접수', '처리', '미제'가 모두 들어간 "
        f"'{CATS[cat][1]}(표 N)' 표를 찾아 모든 행을 추출하라. 같은 페이지에 다른 표가 있어도 이 표만.\n"
        "JSON: {\"found\": bool, \"title\": str, \"rows\": [{\"label\": str, \"접수\": int, \"처리\": int, \"미제\": int}]}\n"
        "- label은 표에 적힌 행 이름(예: 총계, 제1심계, 합의, 단독, 항소심계, 상고심)\n"
        "- 숫자는 쉼표 없는 정수. 대괄호 [ ] 또는 괄호 ( ) 안 보조 숫자는 무시하고 주 숫자만.\n"
        "- '금년접수'를 접수로. 처리가 세분되어 있으면 처리 합계. 읽을 수 없으면 null.")
    imgs = [page_png(f, p)]
    r = ask(prompt, imgs)
    if not r.get("found") and p < n_pages(f):  # table continues on the next page
        r = ask(prompt, [page_png(f, p + 1)])
    return r


def total_row(rows):
    for r in rows or []:
        if re.match(r"^(총계|합계|계)$", nz(r.get("label"))):
            return r
    return (rows or [None])[0]


def rel(f):
    import os
    return os.path.relpath(str(f), str(BASE)).replace("\\", "/")


def pending_from_excel(y):
    """Cache the Excel parse result in data/text_cache/ (keyed on source file size and mtime). Full openpyxl loads are slow on the Z: drive."""
    import json
    files = sorted(glob.glob(str(BASE / f"xlsx/{y}/*개황/*.xlsx")))
    sig = "|".join(f"{Path(f).name}:{Path(f).stat().st_size}:{Path(f).stat().st_mtime_ns}" for f in files)
    cf = TEXT_CACHE / f"pending_xlsx_v2_{y}.json"  # v2: includes source_file/source_page
    if cf.exists():
        c = json.loads(cf.read_text(encoding="utf-8"))
        if c.get("sig") == sig:
            return c["rows"]
    out = _pending_from_excel(y)
    cf.write_text(json.dumps({"sig": sig, "rows": out}, ensure_ascii=False), encoding="utf-8")
    return out


def _pending_from_excel(y):
    out = []
    for f in sorted(glob.glob(str(BASE / f"xlsx/{y}/*개황/*.xlsx"))):
        wb = openpyxl.load_workbook(f, data_only=True)
        for ws in wb.worksheets:
            rows = list(ws.iter_rows(values_only=True))
            for i, r in enumerate(rows):
                cell = next((x for x in r if isinstance(x, str) and "(표" in x.replace(" ", "")), None)
                if not cell:
                    continue
                m = re.search(TITLE_RX, nz(cell))
                if not m:
                    continue
                cat = next((c for c, (rx, _) in CATS.items() if re.search(rx, m.group(1))), None)
                if not cat:
                    continue
                # find the header row
                for j in range(i + 1, i + 5):
                    h = [nz(x) for x in rows[j]]
                    if any("미제" in x for x in h) and any("접수" in x for x in h):
                        ci = {k: next(n for n, x in enumerate(h) if k in x) for k in ("접수", "처리", "미제")}
                        break
                else:
                    continue
                for k, rr in enumerate(rows[j + 1:j + 20]):
                    lab = nz(rr[0]) or nz(rr[1])
                    if re.match(r"^(총계|합계)$", lab):
                        out.append(dict(year=y, category=cat, table=f"표{m.group(2)}", 접수=to_int(rr[ci["접수"]]),
                                        처리=to_int(rr[ci["처리"]]), 미제=to_int(rr[ci["미제"]]), source=f"{y}_xlsx",
                                        source_file=rel(f), source_page=f"{ws.title}!r{j + 2 + k}"))
                        break
    return out


def build_pending():
    recs = []
    for y in range(2019, 2026):
        recs += pending_from_excel(y)
    YRS = range(2004, 2019)
    loc = {y: locate_by_text(y) for y in YRS}
    core = [c for c in CATS if c != "치료감호"]
    for y in YRS:  # categories not found via text: vision-classify pages within ±window of the nearest year's page position
        miss = [c for c in core if c not in loc[y]]
        if not miss:
            continue
        refy = min((r for r in YRS if r != y and all(c in loc[r] for c in miss)), key=lambda r: abs(r - y))
        ref = {c: (gaehwang_pdfs(y)[0], loc[refy][c][1]) for c in miss}
        loc[y].update(locate_by_vision(y, ref, win=6 if abs(refy - y) <= 2 else 12))
        print(f"  {y} vision-located {miss} (ref {refy}) -> {[c for c in miss if c in loc[y]]}")
    # locations confirmed manually after both text and vision search failed
    LOC_OVERRIDE = {(2014, "민사본안"): 18}
    for (y, c), p in LOC_OVERRIDE.items():
        loc[y].setdefault(c, (gaehwang_pdfs(y)[0], p))
    for y in YRS:
        for c, (f, p) in loc[y].items():
            r = extract_pdf(f, p, c)
            t = total_row(r.get("rows")) if r.get("found") else None
            print(f"  {y} {c:8s} p{p:<3d} {'OK' if t else 'NOT FOUND'} {t or ''}")
            if t:
                recs.append(dict(year=y, category=c, table=r.get("title", ""), 접수=to_int(t.get("접수")),
                                 처리=to_int(t.get("처리")), 미제=to_int(t.get("미제")), source=f"{y}_pdf_vision",
                                 source_file=rel(f), source_page=f"p{p}"))
    df = pd.DataFrame(recs).drop_duplicates(["year", "category"])
    # stock-flow check: pending_{t-1} + filed_t - disposed_t vs pending_t
    df = df.sort_values(["category", "year"])
    prev = df.groupby("category").미제.shift()
    consecutive = df.groupby("category").year.diff().eq(1)
    df["identity_gap"] = (df.미제 - (prev + df.접수 - df.처리)).where(consecutive)
    df["identity_gap_pct"] = (df.identity_gap / df.미제 * 100).round(2)
    df.to_csv(OUT / "pending_actual.csv", index=False, encoding="utf-8-sig")
    return df


# =====================================================================
# (2) Seven multi-year comparison tables
# =====================================================================
TABLES = {  # key: (domain, title, label list, Excel file key, sheet, title regex, layout)
    "민사_총괄": ("민사", "민사사건 누년비교표(총괄표)-전심급", ["총계", "본안사건", "본안외사건"], "02항.민사", "1", r"민사사건누년비교표\(총괄", "block"),
    "민사_심급별": ("민사", "민사사건 누년비교표-심급별", ["합계", "상고심", "항소심", "제1심"], "02항.민사", "2", r"민사사건누년비교표-심급", "wide"),
    "민사본안_심급별": ("민사", "민사본안사건 누년비교표-심급별", ["제1심", "항소심-고등법원", "항소심-지방법원", "상고심"], "02항.민사", "2", r"민사본안사건누년비교표-심급", "block"),
    "가사소송_심급별": ("가사", "가사소송사건 누년비교표-심급별", ["제1심", "항소심", "상고심"], "03항.가사", "1", r"가사소송사건누년비교표-심급", "block"),
    "가사_총괄": ("가사", "가사사건 누년비교표(총괄)", ["합계", "소송사건", "비송사건", "조정사건", "신청사건"], "03항.가사", "2", r"가사사건누년비교표\(총괄", "wide"),
    "형사_총괄": ("형사", "형사사건 누년비교표(총괄표)-전심급 [인원수]", ["합계", "공판사건", "약식사건", "즉결사건", "기타사건"], "06항.형사", "1", r"형사사건누년비교표\(총괄", "block"),
    "형사공판_심급별": ("형사", "형사공판사건 누년비교표(총괄표)-심급별 [인원수]", ["제1심", "항소심-고등법원", "항소심-지방법원", "상고심"], "06항.형사", "2", r"형사공판사건누년비교표", "block"),
}
BLOCK_ALIAS = {"고등법원": "항소심-고등법원", "지방법원": "항소심-지방법원", "총계": "총계", "합계": "합계"}


def detail_from_excel():
    out = []
    for key, (dom, _, labels, fk, sheet, trx, kind) in TABLES.items():
        f = glob.glob(str(BASE / f"xlsx/2025/*누년*/*{fk}*.xlsx"))[0]
        rows = list(openpyxl.load_workbook(f, data_only=True)[sheet].iter_rows(values_only=True))
        start = next(i for i, r in enumerate(rows) if any(isinstance(x, str) and re.search(trx, nz(x)) for x in r))
        cur, groups = None, None
        for ri, r in enumerate(rows[start + 1:], start + 2):  # ri = Excel row number (1-based)
            loc = (rel(f), f"{sheet}!r{ri}")
            v = [x for x in r if x is not None]
            if not v:
                continue
            if isinstance(v[0], str) and re.match(r"^\d+\.", nz(v[0])) and not re.search(trx, nz(v[0])):
                break  # next table
            if kind == "block":
                if isinstance(v[0], str):
                    lab = BLOCK_ALIAS.get(nz(v[0]), nz(v[0]))
                    cur = lab if lab in labels else (None if lab != "항소심" else cur)
                elif isinstance(v[0], (int, float)) and cur and 2000 <= v[0] <= 2030:
                    out.append((int(v[0]), dom, key, cur, int(v[1]), int(v[2]), "2025_xlsx", *loc))
            else:  # wide: group header row -> year rows
                if isinstance(v[0], str) and nz(v[0]) == "구분":
                    groups = [nz(x).replace("사건", "사건") for x in v[1:]]
                    groups = [g if g in labels else g + "사건" if g + "사건" in labels else g for g in groups]
                elif isinstance(v[0], (int, float)) and groups and 2000 <= v[0] <= 2030:
                    nums = v[1:]
                    step = 3 if key == "가사_총괄" else 2
                    for gi, g in enumerate(groups):
                        if g in labels and gi * step + 1 < len(nums):
                            out.append((int(v[0]), dom, key, g, int(nums[gi * step]), int(nums[gi * step + 1]), "2025_xlsx", *loc))
    return out


def detail_from_pdf(year):
    f = glob.glob(str(BASE / f"raw/{year}/pdf/*추이*.pdf"))[0]
    N = n_pages(f)
    texts = {p: nz(page_text(f, p)) for p in range(1, N + 1)}
    out = []
    for key, (dom, title, labels, *_r) in TABLES.items():
        trx = TABLES[key][5]
        hits = [p for p in texts if re.search(trx, texts[p])]
        # title page + next page (if the table continues). If the title text is not detected, search around
        # tables of the same domain
        if not hits:
            dom_hits = [p for k2, v2 in TABLES.items() if v2[0] == dom for p in texts if re.search(v2[5], texts[p])]
            hits = sorted(set(q for p in dom_hits for q in (p - 1, p, p + 1, p + 2) if 1 <= q <= N))
        pages = sorted(set(q for p in hits for q in (p, p + 1) if q <= N))[:4]
        # Prompt (English translation; the Korean string below is the text actually sent):
        #   The images are 'Case trends (multi-year comparison)' pages of the Korean Judicial Yearbook. Find the
        #   table '{title}' among them. A page may be laid out in two columns (left/right), so read only that
        #   table's area.
        #   Categories (labels): {labels} — if the table has 'High Court' and 'District Court' under 'appellate',
        #   use '항소심-고등법원' and '항소심-지방법원' (appellate-High Court, appellate-District Court).
        #   Extract the 'filed' and 'disposed' values for each label and year (exclude index, disposal-rate and
        #   change-rate columns).
        #   JSON: {"found": bool, "page_index": int, "data": {"<label>": {"<4-digit year>": [filed, disposed]}}}
        #   Numbers as integers without commas; null if missing. Omit labels not in the table.
        prompt = (
            f"이미지들은 대한민국 사법연감 '사건의 추이(누년비교)' 페이지들이다. 이 중 '{title}' 표를 찾아라. "
            "한 페이지가 좌우 2단으로 되어 있을 수 있으니 해당 표 영역만 읽어라.\n"
            f"구분(라벨): {labels}  — 표에 '항소심' 아래 '고등법원','지방법원'이 있으면 '항소심-고등법원','항소심-지방법원'으로.\n"
            "각 라벨·연도별 '접수'와 '처리' 값(지수·처리율·증감률 열은 제외)을 추출하라.\n"
            "JSON: {\"found\": bool, \"page_index\": int, \"data\": {\"<라벨>\": {\"<연도4자리>\": [접수, 처리]}}}\n"
            "숫자는 쉼표 없는 정수, 없으면 null. 표에 없는 라벨은 생략.")
        r = ask(prompt, [page_png(f, p) for p in pages])
        n = 0
        for lab, yrs in (r.get("data") or {}).items():
            for yy, pair in (yrs or {}).items():
                if pair and len(pair) >= 2 and pair[0] is not None:
                    out.append((int(yy), dom, key, lab, to_int(pair[0]), to_int(pair[1]), f"{year}_pdf_vision",
                                rel(f), f"p{pages[0]}-{pages[-1]} (pages sent together)"))
                    n += 1
        print(f"  {year} {key:12s} pages={pages} found={r.get('found')} values={n}")
    return out


def build_detail():
    cols = ["year", "domain", "table", "label", "접수", "처리", "source", "source_file", "source_page"]
    df = pd.DataFrame(detail_from_excel() + detail_from_pdf(2016) + detail_from_pdf(2011), columns=cols)
    long = df.melt(id_vars=["year", "domain", "table", "label", "source", "source_file", "source_page"], value_vars=["접수", "처리"],
                   var_name="metric", value_name="value")
    piv = long.pivot_table(index=["table", "label", "metric", "year"], columns="source", values="value")
    ov = piv[piv.notna().sum(axis=1) > 1].copy()
    ov["일치"] = ov.nunique(axis=1) == 1
    ov.to_csv(OUT / "detail_overlap_check.csv", encoding="utf-8-sig")
    pri = {"2025_xlsx": 0, "2016_pdf_vision": 1, "2011_pdf_vision": 2}
    long["p"] = long.source.map(pri)
    best = (long.sort_values("p").drop_duplicates(["year", "table", "label", "metric"]).drop(columns="p")
                .query("2002 <= year <= 2025").sort_values(["domain", "table", "label", "metric", "year"]))
    best.to_csv(OUT / "detail_long.csv", index=False, encoding="utf-8-sig")
    wide = best.pivot_table(index="year", columns=["table", "label", "metric"], values="value")
    wide.columns = ["_".join(c) for c in wide.columns]
    wide.to_csv(OUT / "detail_wide.csv", encoding="utf-8-sig")
    print("\n누년 상세 겹침 검증:", int(ov["일치"].sum()), "/", len(ov), "일치")
    if (~ov["일치"]).any():
        print(ov[~ov["일치"]].to_string())
    print(best.groupby(["table", "label"]).year.agg(["min", "max", "count"]).to_string())
    return best, ov


def merge_pending(pend):
    """Build the all-instance pending count for main (merits) cases consistently from observed case-overview sums.
    - 2004–2025: sum of observed overview values (civil merits + family litigation + administrative +
      patent/IP + criminal trials)
    - 2002–2003: no overview available -> spliced (derived) as 2006 multi-year-table observed pending ×
      (observed-sum / multi-year-table ratio, 2004–2006 mean)
    - The earlier computed values (2006 pending + cumulative net inflow) are kept as '미제(산출)' (pending, computed)."""
    ls = pd.read_csv(OUT / "long_series.csv")
    ls = ls[~ls.source.astype(str).str.startswith(("개황 실측합", "접합"))]
    ls.loc[ls.derived.astype(str).eq("True") & (ls.metric == "미제"), "metric"] = "미제(산출)"
    is_bonan = (ls.category == "본안사건") & (ls.level == "전심급")
    # observed multi-year-table values (2002–2006) are kept as `미제(누년표)` (pending, multi-year table)
    nn = ls[is_bonan & ls.metric.isin(["미제", "미제(누년표)"])].set_index("year").value  # on re-runs the metric is already renamed
    ls.loc[is_bonan & (ls.metric == "미제"), "metric"] = "미제(누년표)"

    core = ["민사본안", "가사소송", "행정소송", "특허·지식재산", "형사공판"]
    s = pend[pend.category.isin(core)].groupby("year").agg(미제=("미제", "sum"), n=("category", "nunique"))
    s = s[s.n == len(core)].미제
    ratio = (s / nn).dropna()
    r = ratio.loc[[y for y in (2004, 2005, 2006) if y in ratio.index]].mean()
    print(f"\n실측합/누년표 비율(2004–2006): {ratio.round(4).to_dict()} → 접합계수 {r:.4f}")
    rows = [(y, v, "개황 실측합(민사본안+가사소송+행정+특허/지재+형사공판)", False) for y, v in s.items()]
    rows += [(y, round(nn[y] * r), f"접합: 누년표 미제×{r:.4f}", True) for y in (2002, 2003) if y in nn.index and y not in s.index]
    add = pd.DataFrame([dict(year=y, category="본안사건", level="전심급", metric="미제", value=v, source=src, derived=d)
                        for y, v, src, d in rows])
    ls = pd.concat([ls, add]).sort_values(["category", "level", "metric", "year"])
    ls.to_csv(OUT / "long_series.csv", index=False, encoding="utf-8-sig")
    wide = ls.pivot_table(index="year", columns=["category", "level", "metric"], values="value")
    wide.columns = ["_".join(c) for c in wide.columns]
    wide.to_csv(OUT / "wide_series.csv", encoding="utf-8-sig")
    cmp = ls[(ls.category == "본안사건") & (ls.level == "전심급") & ls.metric.str.startswith("미제")]
    print("\n본안 전심급 미제 비교")
    print(cmp.pivot_table(index="year", columns="metric", values="value").to_string())

if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    if what in ("all", "pending"):
        pend = build_pending()
        print(pend.pivot_table(index="year", columns="category", values="미제").to_string())
        print("\n재고-흐름 오차 >2%:")
        print(pend[pend.identity_gap_pct.abs() > 2][["year", "category", "접수", "처리", "미제", "identity_gap_pct", "source"]].to_string())
        merge_pending(pend)
    if what in ("all", "detail"):
        build_detail()
