"""'New user' test (advisor Round 7): clean copy of release/, README + dictionary only.
Usage: python -I newuser_test.py <release_dir> <work_dir>"""
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

import pandas as pd

SRC, WORK = Path(sys.argv[1]), Path(sys.argv[2])
R = []


def ok(cond, msg):
    R.append(("PASS" if cond else "FAIL", msg))
    print(("PASS  " if cond else "FAIL  ") + msg, flush=True)


# 0. clean copy
if WORK.exists():
    shutil.rmtree(WORK)
shutil.copytree(SRC, WORK)
D = WORK / "data"

# 1. checksums
bad = []
lines = (WORK / "checksums.sha256").read_text(encoding="utf-8").splitlines()
for ln in lines:
    h, f = ln.split("  ", 1)
    if hashlib.sha256((WORK / f).read_bytes()).hexdigest() != h:
        bad.append(f)
ok(not bad, f"checksums.sha256: {len(lines)} files verified on the clean copy")

# 2. README code blocks run as written
readme = (WORK / "README.md").read_text(encoding="utf-8")
blocks = re.findall(r"```python\n(.*?)```", readme, re.S)
ns = {"pd": pd}
import os
cwd = os.getcwd(); os.chdir(WORK)
try:
    for i, b in enumerate(blocks, 1):
        exec(b, ns)
    ok(True, f"README: {len(blocks)} Python examples run unchanged")
except Exception as e:  # noqa: BLE001
    ok(False, f"README example failed: {e!r}")
finally:
    os.chdir(cwd)

# 3. dictionary covers every column; all fact tables load; lookups join
dd = pd.read_csv(D / "data_dictionary.csv")
facts = ["national_series", "pending_observed", "detail", "court_panel", "duration"]
lk = {"court_id_h": "courts", "table_id": "tables", "category_id": "categories", "instance_id": "instances",
      "metric_id": "metrics", "domain_id": "domains"}
for f in facts:
    d = pd.read_csv(D / f"{f}.csv")
    undocumented = [c for c in d.columns if not ((dd.file == f"{f}.csv") & (dd.column == c)).any()]
    joins = []
    for c, l in lk.items():
        if c in d:
            ref = pd.read_csv(D / f"{l}.csv")
            m = d.merge(ref, on=c, how="left", indicator=True)
            joins.append((c, int((m._merge != "both").sum())))
    ok(not undocumented and all(n == 0 for _, n in joins),
       f"{f}.csv: {len(d):,} rows load; all columns in dictionary; joins {', '.join(f'{c}→{lk[c]}' for c, _ in joins)} complete")

# 4. reproduce a national series two ways
n = pd.read_csv(D / "national_series.csv"); w = pd.read_csv(D / "national_series_wide.csv").set_index("year")
s = n.query("category_id=='main_cases' and instance_id=='all_instances' and metric_id=='filings'").set_index("year").value
ok(s.eq(w["main_cases__all_instances__filings"]).all() and len(s) == 24,
   "national series: main-case filings (24 years) identical in national_series and national_series_wide")
cp = pd.read_csv(D / "court_panel.csv"); det = pd.read_csv(D / "detail.csv")
t = cp.query("table_id=='civil_main_1st_total' and court_id_h=='national_total'").set_index("year").value
p = det.query("table_id=='civil_main_by_instance' and label_id=='first_instance' and metric_id=='filings'").set_index("year").value
ok(t.eq(p).all() and len(t) == 24, "national civil first-instance filings: court_panel derived total = detail.csv printed value, 24/24 years")

# 5. court-panel aggregation: district-wide small claims (README recipe) vs printed district-area totals
courts = pd.read_csv(D / "courts.csv"); parent = dict(zip(courts.court_id_h, courts.parent_court_id_h))
sc = cp[(cp.table_id == "civil_main_1st_small_claims") & cp.unit_type.isin(["main_court", "branch", "si_gun_court"]) & cp.dup_flag.isna()].copy()
sc["district"] = [c if u == "main_court" else parent[c] for c, u in zip(sc.court_id_h, sc.unit_type)]
mine = sc.groupby(["district", "year"]).value.sum()
at = cp[(cp.table_id == "civil_main_1st_small_claims") & cp.court_id_h.str.endswith("_area_total")].copy()
at["district"] = at.court_id_h.map(parent)
at = at.set_index(["district", "year"]).value
diff = (mine.reindex(at.index) - at)
ok((diff == 0).all(), f"court aggregation: district-wide small claims from court rows = printed district-area totals ({len(at)} district-years)")

# 6. reconstruction from the model-response cache (court panel, one page per request)
calls = [json.loads(l) for l in (WORK / "validation" / "model_calls.jsonl").read_text(encoding="utf-8").splitlines() if l]
bypage = {}
for c in calls:
    if c["model"] == "gpt-5.5" and len(c["images"]) == 1:
        im = c["images"][0]
        bypage.setdefault((im["pdf"], int(im["page"])), []).append(c["cache_key"])
nums = {}


def numbers(key):
    if key not in nums:
        txt = (WORK / "model_responses" / f"{key}.json").read_text(encoding="utf-8")
        nums[key] = {float(x.replace(",", "")) for x in re.findall(r"-?\d[\d,]*\.?\d*", txt)}
    return nums[key]


o = cp[(cp.extraction_method == "pdf_image_vlm")].copy()
hit, nocall = [], 0
for r in o.itertuples():
    keys = bypage.get((r.source_file, int(r.page_start)), [])
    if not keys:
        nocall += 1; hit.append(False); continue
    hit.append(any(float(r.value) in numbers(k) for k in keys) or float(r.value) == 0)
o["hit"] = hit
miss = o[~o.hit]
corr = miss.correction_status.ne("none").sum()
ok(nocall == 0 and (len(miss) - corr) == 0,
   f"reconstruction: {int(o.hit.sum()):,}/{len(o):,} OCR court-panel values found in the cached response for their page; "
   f"{len(miss)} not found, of which {corr} are logged corrections")
if len(miss) - corr:
    print(miss[miss.correction_status.eq("none")][["court_id_h", "table_id", "year", "value", "source_file", "page_start"]].head(20).to_string())

# 7. reconstruction for multi-page PDF requests (detail, duration, overview) and Excel-grid requests (duration)
def found(v, keys):
    return any(any(abs(float(v) - x) < 0.051 for x in numbers(k)) for k in keys)


multi = {}
for c in calls:
    if c["model"] == "gpt-5.5":
        for im in c["images"]:
            multi.setdefault((im["pdf"], int(im["page"])), set()).add(c["cache_key"])
DOM_KO = {"civil_main": "민사본안", "family_litigation": "가사소송", "criminal_trial": "형사공판"}
text_calls = [c for c in calls if c["model"] == "gpt-5.5" and not c["images"]]
for f in ("detail", "duration", "pending_observed"):
    d = pd.read_csv(D / f"{f}.csv")
    vcols = ["value"] if "value" in d else ["filings", "dispositions", "pending"]
    for em in ("pdf_image_vlm", "excel_llm_structured"):
        x = d[d.extraction_method == em]
        if x.empty:
            continue
        n_ok = n_all = n_corr_miss = 0
        misses = []
        for r in x.itertuples():
            if em == "pdf_image_vlm":
                keys = set().union(*[multi.get((r.source_file, pg), set()) for pg in range(int(r.page_start), int(r.page_end) + 1)])
            else:
                keys = {c["cache_key"] for c in text_calls if DOM_KO.get(r.domain_id, "#") in c["prompt"]}
            for vc in vcols:
                v = getattr(r, vc)
                n_all += 1
                if keys and (found(v, keys) or float(v) == 0):
                    n_ok += 1
                elif r.correction_status != "none":
                    n_corr_miss += 1
                else:
                    misses.append((r.year, vc, v, r.source_file, r.source_locator))
        ok(not misses, f"reconstruction: {f}.csv {em}: {n_ok:,}/{n_all:,} values found in the cached responses of their request"
                       + (f"; {n_corr_miss} not found are logged corrections" if n_corr_miss else "")
                       + (f"; UNEXPLAINED {len(misses)}: {misses[:5]}" if misses else ""))

print(f"\n{sum(s == 'PASS' for s, _ in R)} passed, {sum(s == 'FAIL' for s, _ in R)} failed")
