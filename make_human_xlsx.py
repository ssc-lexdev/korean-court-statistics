"""Build the (blind) Excel workbook for human verification: data/validation/human_check.xlsx

- `안내` (instructions) sheet: how to verify.
- `검증` (verification) sheet: for each cell, where to look (edition, table title, row, parent court, year, column) and an
  input cell. OCR values and Claude values are not shown (blind).
- `원문_…` (source) sheets: images of the relevant PDF pages, reached via links on the `검증` sheet.
After filling it in, `python make_human_xlsx.py score` joins it to manual_sample.csv by id and computes the error rate.
"""
import io
import math
import re
import sys
from pathlib import Path

import pandas as pd
from openpyxl import Workbook, load_workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
import verify_manual as vm  # noqa: E402
from vision_util import page_png  # noqa: E402

BASE = Path(__file__).parent / "data"
VAL = BASE / "validation"
OUT = VAL / "human_check.xlsx"
SAMPLE = VAL / "manual_sample.csv"
DPI = 150

INSTR = [
    ("목적", "AI(GPT 비전) OCR로 PDF에서 추출한 숫자가 맞는지 사람이 원문을 직접 읽어 확인합니다. 결과는 논문 Technical Validation의 '사람 검증 오류율'로 보고합니다."),
    ("blind 원칙", "이 파일에는 OCR 값이 없습니다. 원문 이미지를 보고 해당 칸의 숫자를 그대로 적어 주세요. (값을 미리 보면 판단이 쏠리므로 일부러 숨겼습니다.)"),
    ("진행 순서", "① '검증' 시트에서 한 행을 고릅니다. ② '원문 보기' 링크를 눌러 원문 이미지 시트로 이동합니다(여러 쪽이면 링크 2·3). "
                 "③ '표 제목'의 표를 찾고, '찾을 행'과 '찾을 열'이 만나는 칸의 숫자를 읽습니다. ④ '검증' 시트로 돌아와 '읽은 값' 칸(노란색)에 입력합니다."),
    ("입력 규칙", "숫자만 입력(쉼표 없이, 예: 12345). '-' 또는 빈칸은 0. 소수는 그대로(예: 6.2). 읽을 수 없거나 칸을 찾지 못하면 '읽은 값'은 비우고 '판독 불가'에 O 표시 후 비고에 이유."),
    ("행 찾기 요령 (법원별 표)", "같은 이름의 지원이 여러 지방법원에 있을 수 있습니다(예: 서부지원, 동부지원). '상위 법원' 열의 지방(가정)법원 아래에 있는 행을 고르세요. "
                              "'소계'는 그 상위 법원 묶음의 마지막 '소계' 행입니다. 표가 2단(좌·우)이면 해당 표 쪽 단에서 찾으세요."),
    ("행 찾기 요령 (처리기간 표)", "'찾을 행'은 심급(예: 제1심-단독), '찾을 열'은 처리기간 구간(예: 2월이내)과 연도입니다. 한 항목에 숫자 줄이 두 개(위: 주 행, 아래: 괄호·보조 행)면 위쪽 주 행을 읽으세요."),
    ("행 찾기 요령 (사건개황 표)", "제목에 '접수·처리·미제'가 들어간 표의 '총계'(또는 '합계') 행에서 '찾을 열'(접수/처리/미제)의 숫자를 읽으세요. 처리 칸이 세분되어 있으면 처리 합계."),
    ("이미지 확대", "원문 시트에서 Ctrl+마우스 휠로 확대하세요. 이미지는 원본 PDF를 150dpi로 렌더링한 것입니다. 원본 PDF 경로는 원문 시트 상단에 있습니다."),
    ("완료 후", "파일을 저장하고 알려 주세요. `python make_human_xlsx.py score`로 OCR 값과 대조해 오류율(95% 신뢰구간)을 계산합니다."),
]


def sample_pages(r):
    """sample cell → [(pdf, page)]"""
    if r.dataset in ("court_panel", "court_panel_soak"):
        return vm.court_pages(r)
    if r.dataset == "duration":
        return vm.duration_pages(r)
    loc = vm.pending_loc().get(int(r.year), {})
    c = r.table.split(" ")[0]
    if c not in loc:
        return []
    f, p = loc[c]
    m = re.search(r"p(\d+)", str(r.get("tl_pages", "")))
    first = int(m.group(1)) if m else p
    return [(f, first)] + ([(f, p + 1)] if first == p else [])


def describe(r):
    import build_courts as bc
    import build_duration as bdu
    ed = r.source[:4]
    if r.dataset in ("court_panel", "court_panel_soak"):
        title = bc.TABLES[r.table][3]
        if r.dataset == "court_panel_soak" and ed in ("2006", "2011"):
            title = "8. 소액사건 누년비교표－법원별 접수 (4쪽짜리 표, 2·4쪽째는 제목 없음)"
        row = r.row
        parent = "" if r.row in ("합계", "총계") else (r.district if r.district != r.row else "(자체)")
        col = f"{int(r.year)}년"
        kind = "법원별 접수"
    elif r.dataset == "duration":
        dom, lvl = r.table.split("/", 1)
        title = bdu.TABLES[dom][2]
        row = f"심급: {lvl}"
        parent = ""
        col = f"{int(r.year)}년 × 구간 '{r.row}'"
        kind = "처리기간"
    else:
        title = re.sub(r"^\S+\s+", "", r.table)
        row = "총계(또는 합계)"
        parent = ""
        col = r.row.split("/")[1]
        kind = "사건개황 접수·처리·미제"
    return ed, kind, title, row, parent, col


def png_to_jpeg_image(png_bytes, max_w=1500):
    im = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    if im.width > max_w:
        im = im.resize((max_w, int(im.height * max_w / im.width)))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=82)
    buf.seek(0)
    return XLImage(buf), im.size


def build(show_current=False, out=OUT, sample=SAMPLE, seed=20261113):
    """show_current=True (v2): show the current (dataset) value and verification method to the left of the value read,
    and a match formula to the right (for comparison; not blind)."""
    s = pd.read_csv(sample)
    wb = Workbook()
    ws0 = wb.active
    ws0.title = "안내"
    ws0["A1"] = "OCR 수기 검증 안내"
    ws0["A1"].font = Font(size=14, bold=True)
    for i, (k, v) in enumerate(INSTR, start=3):
        ws0.cell(i, 1, k).font = Font(bold=True)
        c = ws0.cell(i, 2, v)
        c.alignment = Alignment(wrap_text=True, vertical="top")
        ws0.row_dimensions[i].height = max(30, 15 * math.ceil(len(v) / 70))
    ws0.column_dimensions["A"].width = 24
    ws0.column_dimensions["B"].width = 110
    ws0.cell(len(INSTR) + 4, 1, f"검증 대상: {len(s)}칸 (층화 무작위 표본, seed {seed})").font = Font(italic=True)
    if show_current:
        ws0.cell(len(INSTR) + 6, 1, "v2 (대조용)").font = Font(bold=True, color="C00000")
        c = ws0.cell(len(INSTR) + 6, 2, "이 버전은 blind가 아닙니다. '현재 값'은 데이터셋에 들어간 값(GPT OCR → PDF 텍스트 레이어 또는 Claude 시각 판독으로 이미 확인)입니다. "
                     "원문 이미지를 보고 같으면 그대로, 다르면 원문 숫자를 '읽은 값'에 입력하세요. '일치' 칸은 자동 계산됩니다. "
                     "논문에는 '대조(non-blind) 사람 확인'으로 기재해야 합니다.")
        c.alignment = Alignment(wrap_text=True, vertical="top")
        ws0.row_dimensions[len(INSTR) + 6].height = 60

    ws = wb.create_sheet("검증")
    base = ["번호", "원문 보기", "원문 보기 2", "원문 보기 3", "연도판", "자료 종류", "표 제목(원문 표기)", "찾을 행", "상위 법원", "찾을 열"]
    mid = ["현재 값 (데이터셋)", "검증 방법"] if show_current else []
    tail = ["읽은 값 (입력)"] + (["일치"] if show_current else []) + ["판독 불가 (O)", "비고"]
    hdr = base + mid + tail
    col = {h: i + 1 for i, h in enumerate(hdr)}
    vmap = {"pdf_text_layer": "PDF 텍스트 레이어 일치", "claude_visual": "Claude 시각 판독 일치"}
    ws.append(hdr)
    thin = Side(style="thin", color="BBBBBB")
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="44546A")
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    yellow = PatternFill("solid", fgColor="FFF2CC")

    page_sheets = {}
    for _, r in s.iterrows():
        pages = sample_pages(r)
        links = []
        for f, p in pages[:3]:
            ed = r.source[:4]
            tag = "개황" if r.dataset.startswith("pending") else "추이"
            name = f"원문_{ed}_{tag}_p{p:03d}"
            if name not in page_sheets:
                wsp = wb.create_sheet(name)
                wsp["A1"] = f"{ed}년판 사법연감 ({'사건개황' if tag == '개황' else '사건의 추이(누년비교)'}) — PDF {p}쪽"
                wsp["A1"].font = Font(bold=True, size=12)
                wsp["A2"] = f"원본: {Path(f).relative_to(BASE.parent)}"
                wsp["A3"] = "← 검증 시트로 돌아가기"
                wsp["A3"].hyperlink = "#'검증'!A1"
                wsp["A3"].font = Font(color="0563C1", underline="single")
                img, _ = png_to_jpeg_image(page_png(f, p, dpi=DPI))
                wsp.add_image(img, "A5")
                page_sheets[name] = wsp
            links.append(name)
        ed, kind, title, row, parent, col_ = describe(r)
        cur = []
        if show_current:
            v = r.ocr_value
            cur = [int(v) if float(v).is_integer() else float(v), vmap.get(str(r.get("verifier")), "")]
        ws.append([int(r.id), None, None, None, f"{ed}년판", kind, title, row, parent, col_] + cur + [None] * len(tail))
        rr = ws.max_row
        if show_current:
            L = ws.cell(rr, col["읽은 값 (입력)"]).coordinate
            C = ws.cell(rr, col["현재 값 (데이터셋)"]).coordinate
            ws.cell(rr, col["일치"], f'=IF({L}="","",IF(ABS({L}-{C})<0.5,"일치","불일치"))')
            ws.cell(rr, col["현재 값 (데이터셋)"]).number_format = "#,##0.##"
        for j, name in enumerate(links):
            c = ws.cell(rr, 2 + j, "열기" if j == 0 else f"{j + 1}쪽")
            c.hyperlink = f"#'{name}'!A1"
            c.font = Font(color="0563C1", underline="single")
        if not links:
            ws.cell(rr, col["비고"], "원문 쪽 자동 탐색 실패 — 연도판 PDF에서 표 제목으로 찾아 주세요")
        for h in ("읽은 값 (입력)", "판독 불가 (O)"):
            ws.cell(rr, col[h]).fill = yellow
        if show_current:
            ws.cell(rr, col["현재 값 (데이터셋)"]).fill = PatternFill("solid", fgColor="E2EFDA")
        for c in ws[rr]:
            c.border = Border(top=thin, bottom=thin, left=thin, right=thin)
            c.alignment = Alignment(vertical="center", wrap_text=c.column in (col["표 제목(원문 표기)"], col["찾을 행"], col["찾을 열"], col["비고"]))
    wmap = {"번호": 6, "원문 보기": 7, "원문 보기 2": 7, "원문 보기 3": 7, "연도판": 9, "자료 종류": 16, "표 제목(원문 표기)": 46,
            "찾을 행": 22, "상위 법원": 16, "찾을 열": 22, "현재 값 (데이터셋)": 14, "검증 방법": 18, "읽은 값 (입력)": 14,
            "일치": 8, "판독 불가 (O)": 10, "비고": 30}
    widths = [wmap[h] for h in hdr]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[ws.cell(1, i).column_letter].width = w
    ws.freeze_panes = "B2"
    ws.auto_filter.ref = ws.dimensions
    wb._sheets.remove(ws)  # sheet order: instructions, verification, source pages
    wb._sheets.insert(1, ws)
    wb.active = 1
    wb.save(out)
    print(f"저장: {out}  (검증 {len(s)}칸, 원문 시트 {len(page_sheets)}개, {out.stat().st_size/1e6:.1f} MB)")


def score(path=OUT, sample=SAMPLE, tag=""):
    from validate_ocr import wilson
    s = pd.read_csv(sample)
    h = pd.read_excel(path, sheet_name="검증")
    h = h.rename(columns={"번호": "id", "읽은 값 (입력)": "human_value", "판독 불가 (O)": "unreadable", "비고": "human_note"})
    m = s.drop(columns=[c for c in ("human_value",) if c in s]).merge(h[["id", "human_value", "unreadable", "human_note"]], on="id")
    m["human_value"] = pd.to_numeric(m.human_value.astype(str).str.replace(",", ""), errors="coerce")
    done = m[m.human_value.notna()]
    done = done.assign(error=(done.human_value - done.ocr_value).abs() >= 0.5)
    p, lo, hi = wilson(int(done.error.sum()), len(done))
    print(f"사람 검증: 입력 {len(done)}/{len(m)}칸, OCR 오류 {int(done.error.sum())} → {p*100:.2f}% (95% CI {lo*100:.2f}–{hi*100:.2f}%)")
    print(done.groupby("dataset").error.agg(["sum", "count"]).to_string())
    if "verified_value" in m:
        both = done[done.verified_value.notna()]
        agree = (both.human_value - both.verified_value).abs() < 0.5
        print(f"사람 vs 독립검증(텍스트레이어/Claude) 일치: {int(agree.sum())}/{len(both)}")
    if "label_error" in m:
        lab = m[m.label_error.astype(bool)]
        if len(lab):
            print(f"행 라벨 오류 셀(원문에 해당 행 없음, 사람은 '판독 불가' 기대): {len(lab)}개 — 사람 표시 {int(lab.unreadable.notna().sum())}개")
    pre = "soak_sample" if tag == "soak" else "manual_sample"
    m.to_csv(VAL / f"{pre}_scored.csv", index=False, encoding="utf-8-sig")
    done[done.error].to_csv(VAL / f"human_errors{'_soak' if tag == 'soak' else ''}.csv", index=False, encoding="utf-8-sig")


OUT_V2 = VAL / "human_check_v2.xlsx"
OUT_SOAK = VAL / "human_check_soak.xlsx"  # separate sample for the small-claims extension (soak_sample.csv, verify_soak.py)

if __name__ == "__main__":
    # python make_human_xlsx.py [v2|soak]          → build (v2: shows current values, for comparison; soak: small-claims extension, blind)
    # python make_human_xlsx.py score [v2|soak]    → score
    args = sys.argv[1:]
    v2 = "v2" in args
    if "soak" in args:
        if "score" in args:
            score(OUT_SOAK, VAL / "soak_sample.csv", tag="soak")
        else:
            build(out=OUT_SOAK, sample=VAL / "soak_sample.csv", seed=20261118)
    elif "score" in args:
        score(OUT_V2 if v2 else OUT)
    else:
        build(show_current=v2, out=OUT_V2 if v2 else OUT)
