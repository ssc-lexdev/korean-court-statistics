"""Independent verification of the manual-check sample (manual_sample.csv) — stage 1: cross-check against the
PDF text layer (deterministic, non-AI).

For each cell, find the number at the same row label / year position in the text (pdfplumber) of the
corresponding page of the source PDF and compare it with the OCR value.
Result columns: tl_pages, tl_value, tl_status (match / mismatch / not_found / no_text_layer)
- Cells other than match go to stage 2 (visual reading by Claude) -> data/validation/visual_queue.csv
Once stage-2 results are saved as visual_reads.csv (id, visual_value, visual_note), `python verify_manual.py merge`
fills the verified_value / verifier columns of manual_sample.csv (human_value is left blank for human input).
"""
import glob
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from vision_util import n_pages, page_png, page_text  # noqa: E402

BASE = Path(__file__).parent / "data"
VAL = BASE / "validation"
NUM = re.compile(r"(?<![\d.])-?\d{1,3}(?:,\d{3})+(?![\d,])|(?<![\d.,])\d+(?![\d,.])|(?<!\S)-(?!\S)")


def nz(s):
    return re.sub(r"\s+", "", str(s or ""))


def fam(s):
    """Court-family key that ignores district-court vs family-court naming and parenthetical differences."""
    return re.sub(r"\(.*?\)", "", nz(s)).replace("가정법원", "지방법원")


def split_line(line):
    """Split a text line into (label, numbers), e.g. '서 울 중 앙 지 방 법 원 11,868 13,371 …' (Seoul Central
    District Court) -> ('서울중앙지방법원', [11868, 13371, …])."""
    m = re.match(r"^([^\d\-]*)(.*)$", line)
    label = nz(m.group(1))
    nums = []
    for t in NUM.findall(m.group(2)):
        nums.append(0 if t == "-" else int(t.replace(",", "")))
    return label, nums


# ---------------------------------------------------------------- page locations
def court_pages(row):
    return [(glob.glob(str(BASE / f"raw/{row.source[:4]}/pdf/*추이*.pdf"))[0], int(p))
            for p in re.findall(r"_p(\d+)\.png", str(row.page_ref))]


_pending_loc = None


def pending_loc():
    global _pending_loc
    if _pending_loc is None:
        import build_detail as bd
        YRS = range(2004, 2019)
        loc = {y: bd.locate_by_text(y) for y in YRS}
        core = [c for c in bd.CATS if c != "치료감호"]
        for y in YRS:
            miss = [c for c in core if c not in loc[y]]
            if miss:
                refy = min((r for r in YRS if r != y and all(c in loc[r] for c in miss)), key=lambda r: abs(r - y))
                ref = {c: (bd.gaehwang_pdfs(y)[0], loc[refy][c][1]) for c in miss}
                loc[y].update(bd.locate_by_vision(y, ref, win=6 if abs(refy - y) <= 2 else 12))  # served from cache
        loc[2014].setdefault("민사본안", (bd.gaehwang_pdfs(2014)[0], 18))
        _pending_loc = loc
    return _pending_loc


def duration_pages(row):
    import build_duration as bdu
    ed = int(row.source[:4])
    f = glob.glob(str(BASE / f"raw/{ed}/pdf/*추이*.pdf"))[0]
    key = row.table.split("/")[0]
    trx = bdu.TABLES[key][1]
    hits = [p for p in range(1, n_pages(f) + 1) if re.search(trx, nz(page_text(f, p)))]
    return [(f, q) for q in sorted(set(q for p in hits for q in (p, p + 1) if q <= n_pages(f)))[:3]]


# ---------------------------------------------------------------- cross-check (tracking table-title blocks)
_regions = {}


def regions(f, p):
    """Text of the full page plus its left/right halves (handles two-column layouts)."""
    k = (f, p)
    if k not in _regions:
        import logging
        import pdfplumber
        logging.disable(logging.WARNING)
        with pdfplumber.open(f) as pdf:
            pg = pdf.pages[p - 1]
            w, h = pg.width, pg.height
            _regions[k] = [pg.extract_text() or "",
                           pg.crop((0, 0, w / 2, h)).extract_text() or "",
                           pg.crop((w / 2, 0, w, h)).extract_text() or ""]
    return _regions[k]


def blocks(text, title_rx):
    """Lists of lines from each table-title line matching title_rx up to (not including) the next numbered title line."""
    out, cur = [], None
    for ln in text.splitlines():
        n = nz(ln)
        if re.search(title_rx, n):
            cur = []
            out.append(cur)
            continue
        if cur is not None and re.match(r"^\d+\.[가-힣]", n) and not re.search(title_rx, n):
            cur = None
            continue
        if cur is not None:
            cur.append(ln)
    return out


def check_court(row, pages):
    import build_courts as bc
    trx = bc.TABLES[row.table][2]
    want = nz(row.row)
    cands = []
    for f, p in pages:
        for reg in regions(f, p):
            for blk in blocks(reg, trx):
                years, district = None, None
                for ln in blk:
                    lab, nums = split_line(ln)
                    ys = [n for n in nums if 1990 < n < 2100]
                    if len(ys) >= 3 and len(ys) >= len(nums) - 1:
                        years = ys
                        continue
                    if not lab or not years:
                        continue
                    lab = bc.fix_label(lab)
                    if re.search(r"(지방법원|가정법원|회생법원)(\(.*\))?(관내합계)?$", lab):
                        district = re.sub(r"관내합계$", "", lab)
                    if want == "소계":
                        ok = lab == "소계" and fam(district) == fam(row.district)
                    elif want.endswith("지원") or re.search(r"(시|군)법원$", want):
                        ok = lab == want and (district is None or fam(district) == fam(row.district))
                    else:
                        ok = lab == want or (fam(lab) == fam(want))
                    if ok and row.year in years:
                        i = years.index(row.year)
                        if i < len(nums):
                            cands.append((nums[i], f"p{p}"))
    if not cands:
        return None, None
    hit = [c for c in cands if abs(c[0] - row.ocr_value) < 0.5]
    return hit[0] if hit else cands[0]


def check_pending(row):
    import build_detail as bd
    loc = pending_loc()
    cat = row.table.split(" ")[0]
    y = int(row.year)
    if cat not in loc.get(y, {}):
        return None, None, "not_located"
    f, p = loc[y][cat]
    col = row.row.split("/")[1]
    rx = bd.CATS[cat][0] + r".{0,12}접수.{0,3}처리.{0,3}미제"
    cands = []
    for q in (p, p + 1):
        if q > n_pages(f):
            continue
        if not re.search(r"[가-힣]{4,}", page_text(f, q)):
            return None, f"p{q}", "no_text_layer"
        for reg in regions(f, q):
            for blk in blocks(reg, rx):
                for ln in blk:
                    lab, nums = split_line(ln)
                    if re.fullmatch(r"(총계|합계|계)", lab) and len(nums) >= 3:
                        cands.append((nums, f"p{q}"))
                        break
    if not cands:
        return None, f"p{p}", "not_found"
    want = int(round(row.ocr_value))
    for nums, pg in cands:
        if (col == "접수" and nums[0] == want) or (col != "접수" and want in nums):
            return want, pg, None
    nums, pg = cands[0]
    guess = {"접수": 0, "처리": 1, "미제": 2}[col]
    return nums[guess] if guess < len(nums) else None, pg, None


def check_duration(row, pages):
    import build_duration as bdu
    trx = bdu.TABLES[row.table.split("/")[0]][1]
    want = int(round(row.ocr_value))
    yy = str(int(row.year))
    found_block = False
    for f, p in pages:
        if not re.search(r"[가-힣]{4,}", page_text(f, p)):
            return None, f"p{p}", "no_text_layer"
        for reg in regions(f, p):
            for blk in blocks(reg, trx):
                found_block = True
                for ln in blk:
                    lab, nums = split_line(ln)
                    if want in nums and (yy in ln or ("'" + yy[2:]) in ln):
                        return want, f"p{p}", None
    return None, ",".join(f"p{p}" for _, p in pages), "not_found" if found_block else "block_not_found"

def stage1():
    s = pd.read_csv(VAL / "manual_sample.csv")
    out = []
    for _, r in s.iterrows():
        val, pg, why = None, None, None
        if r.dataset == "court_panel":
            pages = court_pages(r)
            if pages and not re.search(r"[가-힣]{4,}", page_text(*pages[0])):
                why = "no_text_layer"
            else:
                val, pg = check_court(r, pages)
                pg = pg or ",".join(f"p{p}" for _, p in pages)
        elif r.dataset == "duration":
            val, pg, why = check_duration(r, duration_pages(r))
        else:
            val, pg, why = check_pending(r)
        if why:
            st = why
        elif val is None:
            st = "not_found"
        else:
            st = "match" if abs(val - r.ocr_value) < 0.5 else "mismatch"
        out.append((pg, val, st))
    s["tl_pages"], s["tl_value"], s["tl_status"] = zip(*out)
    s.to_csv(VAL / "manual_sample.csv", index=False, encoding="utf-8-sig")
    print(s.groupby(["dataset", "tl_status"]).size().unstack(fill_value=0).to_string())
    q = s[s.tl_status != "match"].copy()
    # prepare page images for visual reading
    pdir = VAL / "pages"
    imgs = []
    for _, r in q.iterrows():
        ed = r.source[:4]
        if r.dataset == "court_panel":
            pp = court_pages(r)
        elif r.dataset == "duration":
            pp = duration_pages(r)
        else:
            loc = pending_loc().get(int(r.year), {})
            c = r.table.split(" ")[0]
            pp = [(loc[c][0], loc[c][1])] if c in loc else []
        names = []
        for f, p in pp:
            tag = "gh" if r.dataset.startswith("pending") else "ny"
            out_png = pdir / f"{ed}_{tag}_p{p:03d}.png"
            if not out_png.exists():
                out_png.write_bytes(page_png(f, p))
            names.append(out_png.name)
        imgs.append(" ".join(names))
    q["visual_pages"] = imgs
    q.to_csv(VAL / "visual_queue.csv", index=False, encoding="utf-8-sig")
    print(f"\n시각 판독 대상 {len(q)}셀 → data/validation/visual_queue.csv")


def merge():
    s = pd.read_csv(VAL / "manual_sample.csv")
    v = pd.read_csv(VAL / "visual_reads.csv") if (VAL / "visual_reads.csv").exists() else pd.DataFrame(columns=["id", "visual_value", "visual_note"])
    s = s.drop(columns=[c for c in ("visual_value", "visual_note", "verified_value", "verifier") if c in s]).merge(v, on="id", how="left")
    s["verified_value"] = s.tl_value.where(s.tl_status == "match", s.visual_value)
    s["verifier"] = s.tl_status.map(lambda t: "pdf_text_layer" if t == "match" else None)
    s.loc[s.verifier.isna() & s.visual_value.notna(), "verifier"] = "claude_visual"
    s.to_csv(VAL / "manual_sample.csv", index=False, encoding="utf-8-sig")
    print(s.groupby(["dataset", "verifier"], dropna=False).size().to_string())


if __name__ == "__main__":
    merge() if len(sys.argv) > 1 and sys.argv[1] == "merge" else stage1()
