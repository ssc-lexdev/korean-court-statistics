"""Assemble the public code repository folder (code_release/) from the working directory.

Copies only what is meant to be published: pipeline scripts, release templates, tests, the source
catalogue/manifest and the fixed validation inputs (human and independent-model readings, samples).
Re-run after any script change; the folder is rebuilt from scratch.
"""
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "code_release"

SCRIPTS = [
    "scrape_scourt.py", "vision_util.py", "build_courts.py", "build_series.py", "build_detail.py", "build_duration.py",
    "make_crosswalk_notes.py", "finalize_release.py", "court_lineage.py", "validate_ocr.py", "verify_manual.py",
    "verify_soak.py", "make_human_xlsx.py", "validation_blocks.py", "ocr_support.py", "make_release.py",
    "duration_position.py", "detail_position.py", "court_position.py", "duration_pdf_position.py",
]
TESTS = ["tests/newuser_test.py", "tests/check_code_unchanged.py", "tests/assemble_code_release.py", "tests/scan_private.py"]
DATA = ["data/catalog.csv", "data/source_manifest.csv"]
# Inputs that cannot be regenerated without people or an unrecorded model run: samples, the human and
# independent-model readings, and the text-layer hand check. They are also in the Zenodo archive (validation/).
VALIDATION_INPUTS = [
    "manual_sample.csv", "manual_sample_scored.csv", "visual_queue.csv", "visual_reads.csv", "human_errors.csv",
    "soak_sample.csv", "soak_sample_scored.csv", "visual_queue_soak.csv", "visual_reads_soak.csv", "human_errors_soak.csv",
    "text_layer_handcheck.csv", "soak_population_tl.csv",
]
REPO_FILES = ["README.md", "requirements.txt", ".gitignore", "CITATION.cff"]  # kept in repo_template/


def main():
    if OUT.exists():
        for c in OUT.iterdir():
            shutil.rmtree(c) if c.is_dir() else c.unlink()
    OUT.mkdir(exist_ok=True)
    for f in SCRIPTS + TESTS + DATA:
        (OUT / f).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / f, OUT / f)
    for f in VALIDATION_INPUTS:
        (OUT / "data" / "validation").mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / "data" / "validation" / f, OUT / "data" / "validation" / f)
    shutil.copytree(ROOT / "release_template", OUT / "release_template")
    for f in REPO_FILES:
        shutil.copyfile(ROOT / "repo_template" / f, OUT / f)
    # Plain MIT text only (the scope note after it stops GitHub from detecting the licence; README states the scope)
    mit = (ROOT / "release_template" / "LICENSE_CODE").read_text(encoding="utf-8").split("\nThis licence applies")[0].rstrip() + "\n"
    (OUT / "LICENSE").write_text(mit, encoding="utf-8", newline="\n")
    for d in ("data/series", "data/raw", "data/xlsx", "data/ocr_cache_backup"):
        (OUT / d).mkdir(parents=True, exist_ok=True)
        (OUT / d / ".gitkeep").write_text("", encoding="utf-8")
    n = sum(1 for p in OUT.rglob("*") if p.is_file())
    print(f"code_release/: {n} files")


if __name__ == "__main__":
    main()
