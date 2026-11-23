"""Download the Judicial Yearbook files (Excel zip, PDF, description workbook) from the Judicial Statistics Portal
and unzip the Excel archives.

Usage: python scrape_scourt.py [start_year] [end_year]   (default 2016-2025)
Output: data/raw/{year}/*.zip, data/xlsx/{year}/*.xlsx, data/catalog.csv
"""
import csv
import json
import re
import sys
import zipfile
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "https://portal.scourt.go.kr/pgp/index.on?m=PGP442M02&l=N&c=900"
BASE = Path(__file__).parent / "data"
Y0 = int(sys.argv[1]) if len(sys.argv) > 1 else 2016
Y1 = int(sys.argv[2]) if len(sys.argv) > 2 else 2025


def big_page(route):
    body = json.loads(route.request.post_data)
    body["dma_pageInfo"]["pageSize"] = 500
    route.continue_(post_data=json.dumps(body, ensure_ascii=False))


def unzip(zp: Path, out: Path):
    out.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zp) as z:
        for info in z.infolist():
            name = info.filename
            if not (info.flag_bits & 0x800):  # restore Korean file names (cp949)
                try:
                    name = name.encode("cp437").decode("cp949")
                except Exception:
                    pass
            if info.is_dir():
                continue
            target = out / Path(name).name
            target.write_bytes(z.read(info))


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="chrome")
        ctx = browser.new_context(accept_downloads=True)
        page = ctx.new_page()
        page.route("**/pgp442/selectAojAlmnLst.on", big_page)
        with page.expect_response("**/pgp442/selectAojAlmnLst.on") as r:
            page.goto(URL)
        rows = r.value.json()["data"]["dlt_aojAlmnLst"]
        page.wait_for_selector("#mf_mainFrame_gen_aojAlmnLst_0_spn_excelDownload")
        print(f"목록 {len(rows)}건")

        catalog = []
        kinds = [("excel", "excelFileNm", "excelNtatcAtflNm"),
                 ("pdf", "pdfFileNm", "pdfNtatcAtflNm"),
                 ("dscr", "dscrFileNm", "dscrNtatcAtflNm")]
        for i, row in enumerate(rows):
            title = row["aojAlmnTitlNm"]
            m = re.match(r"(\d{4})년", title)
            if not m or not (Y0 <= int(m.group(1)) <= Y1):
                continue
            year = m.group(1)
            for kind, key, disp in kinds:
                rec = {"year": year, "title": title, "kind": kind, "file": "", "status": ""}
                fname = (row.get(disp) or row.get(key) or "").strip()
                btn = page.locator(f"#mf_mainFrame_gen_aojAlmnLst_{i}_spn_{kind}Download")
                if not fname or fname == "NULL" or btn.count() == 0 or not btn.is_visible():
                    rec["status"] = "없음"
                    catalog.append(rec)
                    continue
                dest = BASE / "raw" / year / kind / re.sub(r'[\\/:*?"<>|]', "_", fname)
                dest.parent.mkdir(parents=True, exist_ok=True)
                try:
                    if not dest.exists():
                        with page.expect_download(timeout=180_000) as d:
                            btn.click()
                        d.value.save_as(dest)
                    if dest.suffix.lower() == ".zip":
                        unzip(dest, BASE / "xlsx" / year / dest.stem)
                    rec.update(file=str(dest.relative_to(BASE)), status="ok")
                    print("  ok", kind, title)
                except Exception as e:
                    rec["status"] = f"error: {e}"
                    print("  ERR", kind, title, e)
                catalog.append(rec)
        with open(BASE / "catalog.csv", "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=["year", "title", "kind", "file", "status"])
            w.writeheader()
            w.writerows(catalog)
        browser.close()


if __name__ == "__main__":
    main()
