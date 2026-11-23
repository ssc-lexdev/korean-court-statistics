# Korean Judicial Yearbook Court Statistics, 2002–2025 — build code

Code that builds, validates and packages the dataset **Korean Judicial Yearbook Court Statistics, 2002–2025: National Caseload Series, Court-Level Filing Panel, and Duration Distributions**.

- **Dataset:** Zenodo, DOI: [10.5281/zenodo.24470048](https://doi.org/10.5281/zenodo.24470048) (version 1.0.0).
- **Authors:** Sungsoo Choi and Taeyeon Oh (contact); see `CITATION.cff`.
- **Licences:** this code is under MIT (`LICENSE`). The dataset is under CC BY 4.0 (see its `LICENSE_DATA.md`).

The dataset digitizes the *Judicial Yearbook* (사법연감), 2002–2025 editions, of the National Court Administration of Korea. It contains national caseload series, a court-level filing panel, detailed civil/family/criminal tables and disposition-time distributions. Values come from Excel files, PDF text layers and, where neither is usable, page images read by a vision-language model.

**Most users do not need this repository.** Download the dataset from Zenodo; its `README.md` documents every file. This repository is for checking how the dataset was made and for rebuilding it.

## Requirements
- Python 3.11 or later (developed with 3.13).
- `pip install -r requirements.txt`. The download script drives an installed **Google Chrome** through Playwright (`channel="chrome"`); without Chrome, run `playwright install chromium` and remove that argument.
- An OpenAI API key **only** if you want to re-run model calls. Reconstruction from the published model responses needs no key (see below).

## Pipeline

| Step | Script | Output (under `data/`) |
|---|---|---|
| 1. Download sources | `scrape_scourt.py 2002 2025` | `raw/`, `xlsx/`, `catalog.csv` |
| 2. Extract | `build_courts.py`, `build_series.py`, `build_detail.py`, `build_duration.py` | `series/` working tables |
| 3. Court notes | `make_crosswalk_notes.py` | `series/court_crosswalk_notes.csv` |
| 4. Finalize | `finalize_release.py` | provenance columns, correction log, structural breaks, `source_manifest.csv` |
| 5. Validate | `validate_ocr.py` (checks A, A2, B), `validation_blocks.py` | `validation/` |
| 6. Package, first pass | `make_release.py` | `release/`; its positional-check entries fail until step 7 has run on this release |
| 7. Positional checks | `duration_position.py` (Excel durations, rule-based re-read), `detail_position.py`, `court_position.py`, `duration_pdf_position.py` (PDF values against the text-layer word coordinates), then `ocr_support.py` (per-value validation paths; the six blocks of the 2016 detailed tables) | `validation/` |
| 8. Package | `make_release.py` | `release/` (the Zenodo archive) + `release_checks.txt` |

`vision_util.py` holds the shared model call, response cache and call log, and `court_lineage.py` the court-event table, jurisdiction-threshold breaks and the derived civil total. `release_template/` contains the dataset documentation copied into `release/`.

Run the steps in the order above from the repository root, e.g. `python build_courts.py`. `make_release.py` stops if any of its integrity checks fails.

## Reconstructing the dataset without API calls
Model responses are cached by a key computed from the model, prompt and page image. The published dataset includes every response it uses (`model_responses/`, 276 files) and the call log (`validation/model_calls.jsonl`). To rebuild without calling any model:

1. **Get the sources:** run step 1, then check the downloaded files against the SHA-256 values in `data/source_manifest.csv`. The cache keys depend on the exact source files.
2. **Load the cache:** download the dataset from Zenodo, then copy:
   - `model_responses/*.json` to `<cache>/ocr_cache/` and to `data/ocr_cache_backup/`. `<cache>` is `~/.cache/scourt_stats`, or the folder named by the environment variable `SCOURT_CACHE`.
   - `validation/model_calls.jsonl` to `data/validation/model_calls.jsonl`.
3. **Run without the API:** set `SCOURT_CACHE_ONLY=1`, which makes any cache miss an error instead of an API call. Then run steps 2–8.
4. **Check the rebuild:** compare the new `release/` with the published one, or run `python -I tests/newuser_test.py <release_dir> <work_dir>` on either copy.

**Re-running the model calls** (`OPENAI_API_KEY` set, cache empty) is possible but **not guaranteed to reproduce the published values**. The scripts use model aliases (`gpt-5.5`, `gpt-5.4-mini`) without dated snapshots, and sampling parameters were left at API defaults. See the dataset's `docs/model_extraction.md`.

## Prompts
The prompts were written and sent in **Korean**, because the source tables are Korean. Each prompt in the code has an English translation in a comment directly above it. The Korean strings are left unchanged: they are part of the cache keys, so editing them would break reconstruction.

## Validation inputs that cannot be regenerated
`data/validation/` ships the inputs that came from people or from a model run whose identifier was not recorded:
- the re-reading samples (`manual_sample*.csv`, `soak_sample*.csv`);
- independent model readings (`visual_reads*.csv`) and human–verifier disagreements (`human_errors*.csv`);
- the small-claims text-layer census and the text-layer hand check.

The scripts that produced them are included for transparency: `validate_ocr.py c`, `verify_manual.py`, `verify_soak.py` and `make_human_xlsx.py`. They need the blind human workbooks, which are **not published** because they embed page images of the source. Do not re-run the sampling step (`validate_ocr.py c --force`): it redraws the sample and overwrites these files.

## Tests
- `tests/newuser_test.py <release_dir> <work_dir>`: checks a release on a clean copy. It verifies checksums, runs the README examples, checks the dictionary and joins, reproduces series and aggregations, and reconstructs every model-derived value from the cached responses.
- `tests/check_code_unchanged.py <original_dir> <edited_dir>`: confirms that edits changed only comments and docstrings (syntax-tree comparison).
- `tests/assemble_code_release.py`: assembles this repository from the authors' working directory.
- `tests/scan_private.py <folder>`: scans a folder for local paths, user names, API keys and e-mail addresses before publishing.

## Source data
The Yearbook PDF and Excel files are published by the National Court Administration on the Judicial Statistics Portal and are not redistributed here. Use of official source data does not imply endorsement by the National Court Administration.

## Citation
Cite the dataset (Zenodo DOI) and, if you use the code, this repository; see `CITATION.cff`.
