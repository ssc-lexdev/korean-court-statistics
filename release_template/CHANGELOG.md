# Changelog

All notable changes to the dataset. Versions follow `MAJOR.MINOR.PATCH`. A MAJOR change breaks identifiers or file structure. A MINOR change adds data or columns. A PATCH changes values or documentation.

## [1.0.0] — 2026-11-24
First public version, deposited on Zenodo (DOI 10.5281/zenodo.24470048). Changes made during pre-release review:

### Values
- A positional check of every OCR value against the PDF text layer (2026-11-20) found three OCR errors, now corrected: Cheonan Branch Court 2006 collegiate civil filings 530 → 536 and Hongseong Branch Court 177 → 171 (2011 edition); criminal final appeals from single-judge cases, 2010, more than 24 months, 113 → 133 (2011 edition). New validation files: `duration_excel_position_check.csv`, `duration_pdf_position_check.csv`, `detail_position_check.csv`, `court_position_check.csv`; new column `text_layer_position` in `ocr_value_support.csv`.
- Gwangju District Court 2005 civil single-judge filings corrected: OCR 9,560 → 9,566 (text layer and page image; district subtotal now reconciles).
- Earlier corrections: Ansan 2007 (5,748 → 5,948), Anyang 2007 (200 → 0) and Jinju 2009 (2,745 → 2,945). There are also 5 label corrections and 7 si/gun-court ID harmonizations (`data/correction_log.csv`).
- No released value carries an unresolved validation warning. The subtotal check now runs after manual corrections.

### Court lineage and jurisdiction changes (advisor Round 5)
- `court_events.csv` (57 events): machine-readable links between court units (`from_court_id_h` → `to_court_id_h`), affected parent series, case scope and recommended aggregation.
- `structural_breaks.csv` now has 14 entries, with `break_type`, `confidence` (verified / suspected / observed_only), effective date, old and new rule, legal basis, expected effect and unaffected alternative series. It adds the civil jurisdiction thresholds (2015, 2017, 2022), the Patent Court's IP appellate jurisdiction (2016), criminal Art. 32(1) amendments, and two unexplained criminal collegiate shifts.
- `court_panel.csv` changes:
  - new derived table `civil_main_1st_total`;
  - new columns `break_flag` (';'-separated codes) and `pre_establishment`;
  - `coverage.csv` status `present_before_establishment`.
- `courts.csv`: `first_year_in_data` / `last_year_in_data` now count non-zero values only, as documented.
- English labels:
  - 본안 → "Contentious/main cases", 본안외 → "Non-main/ancillary cases", 민사본안 → "Civil contentious/main cases", 특허·지식재산 → "Patent and intellectual property cases";
  - 즉결 with an explanatory label;
  - new `translation_note_en` column in `categories.csv`, `tables.csv` and `domains.csv`.
- New release checks:
  - court rows sum to the national total in every table and year;
  - the derived civil total equals the printed first-instance filings;
  - pre-establishment rows are zeros or listed restatements;
  - event and break references resolve.

### Family table and Goyang (advisor Round 6)
- `family_total_level_shift_2016` removed from `structural_breaks.csv` and from `break_flag`: the 2016 difference between editions is an official source-table error (appeals double-counted in the 2016/2018 editions' year-by-year table), not a definition change. It is logged as `official_source_table_error`; the released values are unchanged.
- `structural_breaks.csv` additions:
  - registry-only entries `family_noncontentious_categories_2013_2018` (verified statutory additions) and `family_noncontentious_2008` (suspected);
  - a new column `row_flagged`.
- Goyang 2002 small claims verified against the 2002 edition (Goyang Si Court row, 5,790). Its `coverage.csv` status is now `predecessor_reported_under_successor`, also used for Namyangju and Masan.

### Structure and metadata
- ASCII snake_case identifiers and bilingual lookup tables. Official English court names were added where available.
- Provenance columns on every fact table:
  - `source_file`;
  - `source_locator`, split into `page_start`, `page_end`, `exact_page` and `locator_note`;
  - `extraction_method` (incl. `excel_llm_structured`), `source_type` (digital / ocr / derived) and `correction_status`.
- New files:
  - `coverage.csv`: the full court × table × year grid, with the reason for every absent row;
  - `source_tables.csv`: printed titles and title-check evidence;
  - `file_inventory.csv`;
  - domain-specific `duration_bins.csv` with explicit bounds;
  - `structural_breaks.csv` entry `mean_months_bin_midpoint_2002_2006`.
- `source_manifest.csv`: page-level text-layer counts for every PDF, and retrieval information.
- `data_dictionary.csv`: every column of every file, including the validation files.
- Supporting folders:
  - `validation/`: evidence files, validation protocol, and summaries by cell, page and block;
  - `docs/model_extraction.md`;
  - `model_responses/`: 276 cached model outputs.

## Versioning policy
Identifiers (`court_id_h`, `table_id`, `category_id`, …) are stable across versions. A court unit keeps its ID through renaming, and a new or split unit receives a new ID.
