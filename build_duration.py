"""Multi-year comparison tables by disposition time -> time series of the disposition-time distribution (2002–2025).

Tables: civil merits No. 29 / family litigation No. 7 / criminal trials No. 29,
  `…처리기간별 누년비교표-심급별` (multi-year comparison by disposition time, by instance)
  - Excel editions 2019–2025: the cell grid is passed to GPT as text (a rule-based parser is fragile because
    of merged cells and auxiliary rows)
  - PDF editions 2016, 2011, 2006: GPT vision
  Civil and criminal tables cover a 5-year window per edition, family a 10-year window -> editions are overlapped
  to build 2002–2025, and overlapping years are checked for agreement.
Checks: sum of bins = total, agreement across sources, plausible range of mean disposition time.
Outputs (data/series/): duration_long.csv, duration_checks.csv, duration_overlap_check.csv
"""
import glob
import json
import re
import sys
from pathlib import Path

import openpyxl
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from build_courts import xlsx_file, nz  # noqa: E402
from vision_util import ask, n_pages, page_png, page_text  # noqa: E402

BASE = Path(__file__).parent / "data"
OUT = BASE / "series"

TABLES = {  # key: (Excel file key, title regex (whitespace removed), display title, unit)
    "민사본안": ("02항.민사", r"민사본안사건처리기간별누년비교표", "민사본안사건 처리기간별 누년비교표-심급별", "건"),
    "가사소송": ("03항.가사", r"가사(소송)?사건처리기간별누년비교표", "가사소송사건 처리기간별 누년비교표-심급별", "건"),
    "형사공판": ("06항.형사", r"형사공판사건처리기간별누년비교표", "형사공판사건 처리기간별 누년비교표-심급별", "인원"),
}
# LEVELS and SCHEMA are fragments of the LLM prompts below (they are part of the cache key; do not edit).
# LEVELS (English translation; the Korean string below is the text actually sent):
#   first instance-panel, first instance-single judge, first instance-small claims, first instance (if not
#   broken down), appellate-High Court, appellate-District Court, appellate (if not broken down),
#   supreme court-panel, supreme court-single judge (when the lower court's panel/single split is given),
#   supreme court (if not broken down)
LEVELS = ("제1심-합의, 제1심-단독, 제1심-소액, 제1심(구분 없으면), 항소심-고등법원, 항소심-지방법원, 항소심(구분 없으면), "
          "상고심-합의, 상고심-단독(원심 합의·단독 구분이 있을 때), 상고심(구분 없으면)")
# SCHEMA (English translation; the Korean string below is the text actually sent):
#   JSON: {"found": bool, "bins": [bin names in order, e.g. "within 1 month",…,"over 2 years"],
#   "records": [{"year": 4-digit year, "level": instance, "total": total, "counts": [integers in bins order],
#   "avg_months": mean disposition time (months) or null}]}
#   - Standardize level to one of: {LEVELS}
#   - If an item has two numeric rows (main row + parenthesized/auxiliary row), use only the **upper main row**.
#   - If a year cell is merged across several rows, apply that year to all of those rows.
#   - Numbers as integers without commas (only mean disposition time may be decimal). '-' is 0. Exclude
#     percentage-share (%) rows and columns.
SCHEMA = (
    "JSON: {\"found\": bool, \"bins\": [구간명 순서대로 예: \"1월이내\",…,\"2년초과\"], "
    "\"records\": [{\"year\": 연도4자리, \"level\": 심급, \"total\": 합계, \"counts\": [bins 순서대로 정수], "
    "\"avg_months\": 평균처리기간(월) 또는 null}]}\n"
    f"- level은 다음 중 하나로 표준화: {LEVELS}\n"
    "- 한 항목에 수치 행이 두 줄(주 행 + 괄호·보조 행)이면 **위쪽 주 행**만 사용.\n"
    "- 연도 칸이 병합되어 여러 행에 걸쳐 있으면 그 연도를 해당 행들 모두에 적용.\n"
    "- 숫자는 쉼표 없는 정수(평균처리기간만 소수). '-'는 0. 구성비(%) 행·열은 제외.")


# OCR errors corrected by checking against the source (2026-11-20): positional check of every PDF value against the
# text-layer word coordinates (duration_pdf_position.py), confirmed on the page image.
# (domain, level, year, bin): (corrected value, evidence). Applied after the checks, so duration_checks.csv keeps the
# extracted values.
DURATION_FIXES = {
    ("형사공판", "상고심-단독", 2010, "2년초과"): (133, "2011판 OCR 113 → 원문 133 (2011판 추이 p69 텍스트 레이어 좌표·쪽 이미지; 구간합 17,417 → 17,437 = 합계)"),
}


def rel(f):
    import os
    return os.path.relpath(str(f), str(BASE)).replace("\\", "/")


def grid_text(ws, r0, r1):
    lines = []
    for i, r in enumerate(ws.iter_rows(min_row=r0, max_row=r1, values_only=True), start=r0):
        cells = ["" if x is None else (f"{x:g}" if isinstance(x, float) else str(x)) for x in r]
        while cells and cells[-1] == "":
            cells.pop()
        if cells:
            lines.append(f"r{i}: " + " | ".join(c.replace("\n", " ") for c in cells))
    return "\n".join(lines)


def from_excel(ed):
    recs = []
    for key, (fk, trx, title, _) in TABLES.items():
        f = xlsx_file(ed, fk)
        if not f:
            continue
        wb = openpyxl.load_workbook(f, data_only=True)
        block = None
        for ws in wb.worksheets:
            rows = list(ws.iter_rows(values_only=True))
            starts = [i for i, r in enumerate(rows, 1) if isinstance(r[0], str) and re.search(trx, nz(r[0]))]
            if not starts:
                continue
            s = starts[0]
            e = next((i for i, r in enumerate(rows, 1) if i > s and isinstance(r[0], str)
                      and re.match(r"^\d+\.", nz(r[0])) and not re.search(trx, nz(r[0]))), len(rows) + 1) - 1
            block = grid_text(ws, s, e)
            loc = f"{ws.title}!r{s}-r{e}"
            break
        if not block:
            print(f"  {ed} {key}: 표 없음")
            continue
        # Prompt (English translation; the Korean string below is the text actually sent):
        #   Below is the cell grid of a Korean Judicial Yearbook Excel sheet (row number r, cells separated by |,
        #   empty cells blank). Structure the table '{title}'.
        #   {SCHEMA}
        #
        #   {block}
        r = ask(f"아래는 대한민국 사법연감 엑셀 시트의 셀 격자다(행 번호 r, 셀은 | 로 구분, 빈 칸은 공백). "
                f"'{title}' 표를 구조화하라.\n{SCHEMA}\n\n{block}")
        recs += to_records(r, key, f"{ed}_xlsx", rel(f), loc)
    return recs


def from_pdf(ed):
    f = glob.glob(str(BASE / f"raw/{ed}/pdf/*추이*.pdf"))[0]
    N = n_pages(f)
    recs = []
    for key, (fk, trx, title, _) in TABLES.items():
        hits = [p for p in range(1, N + 1) if re.search(trx, nz(page_text(f, p)))]
        if not hits:  # title text not detected -> classify titles with vision (only pages near keywords; scanning the whole domain range is too costly)
            kw = {"민사본안": "민사", "가사소송": "가사", "형사공판": "형사"}[key]
            cand = [p for p in range(1, N + 1) if "처리기간" in nz(page_text(f, p)) or kw in nz(page_text(f, p))[:80]]
            for p in cand[:40]:
                # Prompt (English translation; the Korean string below is the text actually sent):
                #   List every table title on this page as JSON {"titles": [..]}.
                t = ask("이 페이지의 모든 표 제목을 JSON {\"titles\": [..]} 로 나열하라.",
                        [page_png(f, p, dpi=110)], model="gpt-5.4-mini", detail="low")
                if re.search(trx, nz(" ".join(t.get("titles", [])))):
                    hits.append(p)
        pages = sorted(set(q for p in hits for q in (p, p + 1) if q <= N))[:3]
        if not pages:
            print(f"  {ed} {key}: PDF에서 표 위치 못 찾음")
            continue
        # Prompt (English translation; the Korean string below is the text actually sent):
        #   The images are 'Case trends (multi-year comparison)' pages of the Korean Judicial Yearbook. Structure
        #   only the table '{title}'. Pages may be laid out in two columns (left/right).
        #   {SCHEMA}
        r = ask(f"이미지들은 대한민국 사법연감 '사건의 추이(누년비교)' 페이지다. '{title}' 표만 구조화하라. "
                f"페이지가 좌우 2단일 수 있음.\n{SCHEMA}", [page_png(f, p) for p in pages])
        print(f"  {ed} {key}: pages={pages} found={r.get('found')} n={len(r.get('records') or [])}")
        recs += to_records(r, key, f"{ed}_pdf_vision", rel(f),
                           f"p{pages[0]}" if len(pages) == 1 else f"p{pages[0]}-{pages[-1]} (pages sent together)")
    return recs


def to_records(r, key, src, file="", page=""):
    out = []
    bins = r.get("bins") or []
    for rec in r.get("records") or []:
        try:
            y = int(rec["year"])
        except Exception:
            continue
        counts = rec.get("counts") or []
        lvl = re.sub(r"\(.*?\)", "", nz(rec.get("level")))  # strip parenthetical: `상고심(구분 없으면)` -> `상고심` (supreme court)
        base = dict(domain=key, year=y, level=lvl, source=src, source_file=file, source_page=page)
        out.append({**base, "bin": "합계", "value": rec.get("total")})
        out.append({**base, "bin": "평균처리기간(월)", "value": rec.get("avg_months")})
        for b, v in zip(bins, counts):
            out.append({**base, "bin": nz(b), "value": v})
    return out


def main():
    recs = []
    for ed in range(2025, 2018, -1):
        recs += from_excel(ed)
    for ed in (2016, 2011, 2006):
        recs += from_pdf(ed)
    df = pd.DataFrame(recs)
    df["value"] = pd.to_numeric(df.value, errors="coerce")

    # Check 1: sum of bins = total
    bins = df[~df.bin.isin(["합계", "평균처리기간(월)"])]
    s = bins.groupby(["source", "domain", "year", "level"]).value.sum()
    keys = ["source", "domain", "year", "level"]
    tt = df[df.bin == "합계"]
    dup = tt[tt.duplicated(keys, keep=False)]
    if len(dup):
        print(f"  경고: 같은 (출처,표,연도,심급) 합계 중복 {len(dup)}행 → duration_duplicates.csv")
        dup.to_csv(OUT / "duration_duplicates.csv", index=False, encoding="utf-8-sig")
    t = tt.groupby(keys).value.first()
    chk = pd.DataFrame({"sum_bins": s, "total": t}).dropna()
    chk["ok"] = (chk.sum_bins - chk.total).abs() < 0.5
    chk.to_csv(OUT / "duration_checks.csv", encoding="utf-8-sig")
    print("\n구간합=합계:", int(chk.ok.sum()), "/", len(chk))
    print(chk.groupby(level="source").ok.agg(["sum", "count"]).to_string())

    # Check 2: overlap across sources
    piv = df.pivot_table(index=["domain", "level", "bin", "year"], columns="source", values="value")
    ov = piv[piv.notna().sum(axis=1) > 1].copy()
    ov["일치"] = ov.apply(lambda r: r.dropna().round(1).nunique() == 1, axis=1)
    ov.to_csv(OUT / "duration_overlap_check.csv", encoding="utf-8-sig")
    print("출처 간 겹침 일치:", int(ov["일치"].sum()), "/", len(ov))

    # manual corrections (after the checks above, which therefore report the extracted values)
    for (dom, lvl, y, b), (v, why) in DURATION_FIXES.items():
        m = (df.domain == dom) & (df.level == lvl) & (df.year == y) & (df.bin == b) & (df.source == "2011_pdf_vision")
        assert m.sum() == 1, (dom, lvl, y, b, int(m.sum()))
        df.loc[m, "value"] = v
    print(f"  수동 정정: {len(DURATION_FIXES)}개 값")

    # prefer the most recent source
    pri = {f"{e}_xlsx": 2025 - e for e in range(2019, 2026)} | {"2016_pdf_vision": 10, "2011_pdf_vision": 11, "2006_pdf_vision": 12}
    df["p"] = df.source.map(pri)
    best = (df.sort_values("p").drop_duplicates(["domain", "level", "bin", "year"]).drop(columns="p")
              .query("2002 <= year <= 2025").sort_values(["domain", "level", "year", "bin"]))
    best.to_csv(OUT / "duration_long.csv", index=False, encoding="utf-8-sig")
    print(best[best.bin == "합계"].groupby(["domain", "level"]).year.agg(["min", "max", "count"]).to_string())


if __name__ == "__main__":
    main()
