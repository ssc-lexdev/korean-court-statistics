# Validation protocol

This document specifies how the released values were checked: populations, sampling, readers, blinding, adjudication, denominators and interval methods. Results are summarized in the manuscript (Technical Validation) and stored in the files listed in §9. All counts refer to the release unless a date is given.

The claims are descriptive. They describe how often the checked extraction paths disagreed with an independent reading of the same source. They are not a general accuracy estimate for the extraction model.

## 1. Populations and check types

| Check | Population (frame) | Design | Comparison type |
|---|---|---|---|
| A. Digital-comparator check | OCR values for which the same cell is also available from an Excel edition (2019–2025) | Census (5,127 cells) | Independent official source |
| A2. Cross-edition OCR check | Court-panel cells without a digital comparator that were read by OCR in **both** the 2011 and 2016 editions | Census (1,407 cells) | Two independent model readings of two printed editions |
| B. Internal arithmetic checks | All OCR blocks with printed totals: district subtotal = sum of member courts; group total = sum of member courts; national total = sum of districts; duration bins sum = total; stock–flow identity | Census | Internal consistency |
| C1. Re-reading sample (main) | OCR-only values retained in the release as of 2026-11-14 (no digital comparator) | Stratified random sample, 295 cells | Same-document text layer; independent model; human |
| C2. Re-reading sample (small claims) | Small-claims OCR values added on 2026-11-18 (2,228 cells) | Stratified random sample, 62 cells, plus text-layer census | Same-document text layer; independent model; human |
| D. Statutory-date plausibility check | 56 court units with a statutory establishment, renaming or conversion date | Census | External institutional information |
| E. Positional check | Every released OCR value of the court panel, detailed and duration tables (8,812 values, 2006, 2011 and 2016 PDF editions), and every `excel_llm_structured` duration value (1,925) | Census | PDF text layer of the same page, rebuilt from word coordinates; Excel cells re-read by rules |

"OCR" here means extraction from page images by a vision-language model (`extraction_method = pdf_image_vlm`). Values from Excel workbooks and from PDF text layers are not OCR.

## 2. Check A — digital-comparator check
- **Unit:** one cell, i.e. a (table, row, year) value that appears both in an OCR-read PDF edition and in an Excel edition.
- **Rule:** discrepancy if |OCR − Excel| ≥ 0.5.
- **Adjudication of discrepancies:** the printed PDF page (text layer and page image) is compared with both values.
  - *OCR error:* the page shows the Excel value.
  - *Source-to-source difference:* the page shows the OCR value, and either the PDF text layer agrees with the OCR value or the value satisfies the table's own identity.
- **Release impact:** none in all cases, because the release takes the digital value wherever one exists (source priority).
- **Result:** 6 discrepancies = 4 OCR errors + 2 source-to-source differences. They fall in 5 edition × table blocks, and 0 released values are affected. Error types: 5 single-digit misreads, 1 transposition, 0 row/table confusions.

## 3. Check A2 — cross-edition OCR check
- **Unit:** a court-panel cell read independently from the 2011 and the 2016 editions, with no digital comparator.
- **Adjudication:** the source page image and text layer of the priority edition (2016) are read by hand.
- **Result:** 2 of 1,407 cells disagreed, and both were OCR errors in the 2016 reading. They are corrected in the release: `correction_log.csv`, `correction_status = corrected_value`.

## 4. Check B — internal arithmetic checks
- **Tolerance:** 0.5 for counts. For the stock–flow identity \(P_t = P_{t-1} + F_t - D_t\), |gap| ≤ 2% of \(P_t\).
- **Unit of a failure:** one edition × table × year × district block. A failing block flags the OCR values it contains.
- **Process:** a failing block is re-read on the source page.
  - If the page shows a different value, the value is corrected (`VALUE_FIXES`).
  - If the printed figures themselves do not add up, they are kept as printed and flagged.
- **Order of steps:** since 2026-11-19 the check is re-run **after** the manual corrections (`court_checks_after_fixes.csv`). Before that change, two blocks (12 rows) carried a stale `district_sum_mismatch` flag:
  - Changwon 2009: already reconciled by an earlier correction.
  - Gwangju 2005: resolved by a new correction, 9,560 → 9,566 (text layer and page image).
- **Remaining failures:** no released value carries an unresolved warning. Six blocks still fail after corrections; in all of them the released value comes from another source.
- **Limitation:** a subtotal check does not detect an error that moves value between two rows of the same block. Example: Ansan/Anyang 2007, 5,948 read as 5,748 + 200. Checks A2 and D complement it.

## 5. Check C1 — main re-reading sample (295 cells)

**Sampling frame**
- OCR-only values in the working datasets on 2026-11-14:
  - court panel: 2011 and 2016 editions;
  - duration counts: 2006, 2011 and 2016 editions, means excluded;
  - overview stock/flow totals (filings, dispositions, pending): 2004–2018 editions.
- The frame was drawn **before** the small-claims extension and before the corrections of 2026-11-18/19. None of the four corrected cells is in the sample.

**Strata and allocation** (`validate_ocr.py part_c`)
- 20 strata = dataset × source edition.
- Allocation:
  - 10 cells per stratum, plus the remainder allocated proportionally to stratum size;
  - the 2015 (scanned) and 2017 (broken-encoding) editions get double weight;
  - target 300; 295 after rounding.
- Simple random sampling within strata, seed **20261113**, followed by a random shuffle of row order with the same seed.

**Realized sample**

| Dataset | Cells | Strata |
|---|---|---|
| Court panel | 87 | 2011 ed. 50 · 2016 ed. 37 |
| Duration | 58 | 2006 ed. 19 · 2011 ed. 22 · 2016 ed. 17 |
| Overview totals | 150 | 10 per edition, 2004–2018 |

**Readers** (applied to every sampled cell unless stated)
1. **Deterministic text-layer parser** (`verify_manual.py`, non-AI).
   - Locates the table title block, the row label and the year column in the PDF text layer and reads the number.
   - Outcomes: 196 match; 20 value differs; 59 cell not located; 20 no usable text layer.
   - A match is accepted as verification.
2. **Independent model reading:** Anthropic Claude, a different model family and a different prompt from the extraction model. The exact Claude model identifier of this run (2026-11-14) was not recorded. Its readings are archived in `reread_sample_*_model_reads.csv`, so the result can be reconstructed but not re-run exactly from API metadata (`../KNOWN_ISSUES.md` #12).
   - Read the 99 cells not matched by the parser from page images (150–200 dpi).
   - Shown the cell's location but **not** the extracted value.
3. **Human reading (blind):** one reader re-read all 295 cells in a workbook (`human_check.xlsx`).
   - The workbook gives the cell location (edition, table title, row, parent court, year, column) and the page images.
   - It does not show the extracted value or the model reading.
   - The reader could see the printed page context, including printed totals and averages.
   - Rules given: digits only; "–" or blank = 0; mark "unreadable" if the cell cannot be found.

**Adjudication**
- A cell is an extraction error if the verified value differs from the released value by ≥ 0.5.
- The verified value is the text-layer value when it matched, otherwise the independent model reading.
- Human–verifier disagreements are resolved by re-reading the page image and checking the printed row/column totals or averages.

**Result**
- 0 extraction errors in 295 cells.
- All 20 parser value mismatches were parser errors: the parser picked a different column (e.g., 2004–2006 "total receipts incl. carried-over") or a different table. The extracted value was correct.
- Human vs verified: 295/295 agree; 0 unreadable.

## 6. Check C2 — small-claims sample (62 cells)

**Frame**
- Small-claims court-panel values from OCR, added 2026-11-18: 2,228 cells (2006 ed. 850, 2011 ed. 860, 2016 ed. 518).

**Strata**
- Edition (3) × unit type (main court, branch, si/gun court, total) = 12 strata × 5 cells, seed **20261118**.
- Plus every zero-valued cell (2), giving 62 cells.

**Readers**
- Text-layer parser using word coordinates: 61 match, 1 row not found.
- Independent model reading: 1 cell.
- One blind human reader: all 62 cells (`human_check_soak.xlsx`).

**Text-layer census of the whole frame**
- 2,223 of 2,228 cells located with an identical value; 0 numeric mismatches.
- The 5 cells not located belong to one row-label error.

**Result**
- Numeric errors: 0/61.
- One row-label error (2016 ed.: "과천시법원" for the printed "광명시법원"), detected by all three paths and corrected (`corrected_label`).
- One human–verifier disagreement, which turned out to be a human typing error: the page shows 628, consistent with the printed five-year average.

## 7. Check D — statutory-date plausibility
- **Comparison:** for each of 56 court units, the statutory effective date (Addenda to the Act on the Establishment and Jurisdictional Districts of Courts at All Levels; law.go.kr) is compared with the unit's first non-zero year in the data.
- **Reading of a mismatch:** a non-zero value before establishment is treated as a possible extraction error and re-read.
- **Result:** 1 additional OCR error found (Anyang 2007, "200" for a printed "–"), corrected.
- This is a plausibility check, not a validation of every value.

## 7a. Check E — positional check (2026-11-20)
- **Why:** presence of a value on its page or in its cell block does not establish its row or column. Two values of the same row or column can be swapped, or misread so that their sum is preserved, and still pass checks B.
- **Excel durations (`duration_position.py`):** the cell blocks given to the model were re-read by rules, without a model: the year from the row label (merged year cells: nearest year label of the same section), the instance from the section (제1심/항소심/상고심) and level labels, and the bin from the column header. A value passes if the cell at its (year, instance, bin) position equals it. Result: 1,925 of 1,925. Control: every swap of two adjacent unequal bins in a row (1,408) and every one-year shift would have been detected.
- **PDF values (`court_position.py`, `detail_position.py`, `duration_pdf_position.py`):** the text layers of the 2006, 2011 and 2016 editions have valid characters but a scrambled reading order. Each table was rebuilt from the word coordinates: the printed title, the year header (court panel) or year labels (detailed and duration tables), the court, category or section labels, and the column headers. Each number is assigned to the column whose centre is nearest (court panel, durations) or to the labels in left-to-right order (detailed tables). A value passes if the word at its row and column equals it (a printed dash is read as 0).
- **Result:** 8,809 of 8,812 agree (court panel 6,111 of 6,113; detailed tables 784 of 784; durations 1,914 of 1,915). The three others were OCR errors, confirmed on the page image and corrected (`../data/correction_log.csv`): Cheonan and Hongseong Branch Courts, 2006 collegiate civil filings, 2011 edition (530 → 536, 177 → 171; the pair keeps its sum, so the subtotal check passed); criminal final appeals from single-judge cases, 2010, disposed of after more than 24 months, 2011 edition (113 → 133; this series-year had failed the bin-sum check). After correction, all values agree.
- **Titles:** the rebuilt tables recover the printed title of every detailed-table block, including the six 2016-edition blocks without title evidence in `source_tables.csv`.
- **Not covered:** the 249 OCR values of the single-year overview tables (2004–2018 volumes), some of whose text layers are scanned or mis-encoded.
- **What it shows:** the text layer is the PDF's own digital text, independent of the page-image reading. Agreement shows that the value is the one the PDF prints at that position; it does not test the printed statistics themselves.

## 8. Intervals and denominators
- **Zero-error samples:** exact Clopper–Pearson one-sided 95% upper bound.
  - 295 cells → 1.0%;
  - 61 cells → 4.8%;
  - 20 cells (2015/2017 editions) → 13.9%.
- **Non-zero counts:** Wilson two-sided 95% interval, e.g. check A: 6/5,127.
- **Assumptions:** intervals are cell-level and descriptive. They treat cells as independent and do not account for clustering by page, table, edition, prompt or model run.
- **Cell, page and block counts** are reported alongside (`validation_blocks.csv`; per block in `validation_blocks_detail.csv`). For example, the 6 discrepancies of check A fall in 5 of 53 edition × table blocks (117 source pages), and the 2 of check A2 in 2 of 9 blocks.
- **Denominators:**
  - checks A and A2 use all comparable cells;
  - samples C1 and C2 use sampled cells with a determinable verified value;
  - C2 numeric results exclude the one cell with a row-label error.

## 9. Limitations
- **One human reader:** there was one human reader, and it is not independent of the authors. The reader was blind to extracted values but could see page context.
- **The independent model reading** is not a human reading. It is used to adjudicate only where the deterministic text layer could not.
- **Sample timing:** sample C1 was drawn from the 2026-11-14 working data. Values added or corrected later are covered by C2, A2, B and D, not by C1.
- **Unsampled OCR cells:** within-block shifts (§4) are the main error type that arithmetic checks cannot catch. Check E covers them for every OCR value except the 249 overview values.
- **Sample C1 bound:** the 1.0% upper bound applies to the unweighted cells of the C1 frame (court panel 87 of 3,887 values, duration counts 58 of 1,748, overview 150 of 249; the strata were sampled at different rates). It is not an error bound for the OCR release as a whole.
- **Page-range provenance:** 352 detail and duration values read in multi-page requests have only a page range (`exact_page = False`). The other 2,347 values from such requests were located on a single page in the text layer.

## 10. Files (this folder)

| File | Check | Content |
|---|---|---|
| `digital_comparator_summary.csv`, `digital_comparator_discrepancies.csv` | A | Cell counts and error rates; the 6 discrepancies |
| `cross_edition_summary.csv`, `cross_edition_discrepancies.csv` | A2 | 2011 vs 2016 OCR |
| `internal_consistency_summary.csv` | B | Pass counts by check and edition |
| `subtotal_checks_extracted.csv`, `subtotal_checks_after_corrections.csv` | B | Every subtotal/group/national check per source block, before and after manual corrections |
| `duration_bin_sum_checks.csv` | B | Duration bins sum = total, per source |
| `overlap_court_panel.csv`, `overlap_duration.csv`, `overlap_detail.csv`, `overlap_national_series.csv` | A/A2 | Values for the same cell from every edition that reports it (`agree`) |
| `reread_sample_main.csv` | C1 | 295 sampled cells: stratum, released value, text-layer value/status, model reading, verified value, human value |
| `reread_sample_main_model_reads.csv`, `reread_sample_main_human_disagreements.csv` | C1 | Model readings (99) with page notes; human–verifier disagreements (none) |
| `reread_sample_small_claims.csv`, `reread_sample_small_claims_model_reads.csv`, `reread_sample_small_claims_human_disagreements.csv` | C2 | 62 sampled cells, model readings and human–verifier disagreements |
| `small_claims_text_layer_census.csv` | C2 | Text-layer census of all 2,228 small-claims OCR cells |
| `validation_blocks.csv`, `validation_blocks_detail.csv` | all | Cell, page and edition × table block counts per check |
| `text_layer_handcheck.csv` | — | Hand check of the automatic text-layer page label (3 pages of the 2016 edition, see `../KNOWN_ISSUES.md` #9) |
| `duration_mean_method_check.csv` | — | Printed vs bin-midpoint mean disposition time (method change 2006/2007) |
| `duration_excel_cell_check.csv` | — | Every `excel_llm_structured` value located in its source cell block |
| `duration_excel_position_check.csv` | E | Every `excel_llm_structured` value compared with the Excel cell at its (year, instance, bin) position |
| `court_position_check.csv`, `detail_position_check.csv`, `duration_pdf_position_check.csv` | E | Every OCR value of these tables compared with the text-layer word at its row and column |
| `overview_no_path_reread.csv` | — | The 6 overview values with no other per-value path (2015 and 2017 volumes, mis-encoded text layers), re-read from the page images by one author, S.C. (not blind); all agree and equal the sum of their printed instance rows |
| `ocr_value_support.csv`, `title_unverified_blocks.csv` | all | Validation paths of every released OCR value; the six 2016-edition detailed blocks |
| `model_calls.jsonl` | — | Model, prompt and page images of every cached model response (`../docs/model_extraction.md`) |
| `../data/courts.csv` (`legal_start`, `legal_basis_*`) | D | Statutory dates |
| `../data/correction_log.csv` | all | Corrections and curation decisions |

Validation files keep Korean source labels (table and court names, as printed) because they document the extraction against the Korean source. The blind human workbooks are not released because they embed page images of the source; the human values are in the `reread_sample_*` files.

Scripts: `duration_position.py`, `court_position.py`, `detail_position.py`, `duration_pdf_position.py` (E), `ocr_support.py` (per-value paths), `validate_ocr.py` (A, A2, C1 sampling), `verify_manual.py` (C1 text layer), `verify_soak.py` (C2), `make_human_xlsx.py` (blind workbooks and scoring), `build_courts.py` (B and corrections), `finalize_release.py` (correction log, duration mean check).
