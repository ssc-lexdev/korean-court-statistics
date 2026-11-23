# Model-assisted extraction: models, prompts, parameters and response cache

This document records how generative models were used to build the dataset. It also records what is needed to **reconstruct** the released tables.

The released tables can be rebuilt exactly from the archived model responses. They are not guaranteed to be **re-runnable**: a fresh run against the same API would call proprietary models whose behaviour can change, and may return different output.

## 1. Where models were used

| Step | Values in release | Model | Input | Script / function |
|---|---|---|---|---|
| Page/title classification: find the page of a table when the PDF text layer does not reveal the title | none directly (selects pages) | `gpt-5.4-mini` | page image, 110 dpi, `detail = low` | `build_courts.classify_pages`, `build_detail.locate_by_vision`, `build_duration.from_pdf` |
| Court-panel tables, 2006 (small claims), 2011 and 2016 editions | `court_panel.csv`, `extraction_method = pdf_image_vlm` (6,113 values) | `gpt-5.5` | one page image per request, 200 dpi, `detail = high` | `build_courts.extract_pdf_page` |
| Overview stock/flow tables (filings, dispositions, pending), 2004–2018 editions | `pending_observed.csv`, `pdf_image_vlm` (83 rows) | `gpt-5.5` | one page, 200 dpi; the next page if the table is not found | `build_detail.extract_pdf` |
| Detailed year-on-year tables, 2011 and 2016 editions | `detail.csv`, `pdf_image_vlm` (784 values) | `gpt-5.5` | up to 4 pages per request, 200 dpi | `build_detail.detail_from_pdf` |
| Duration tables, 2006, 2011 and 2016 editions | `duration.csv`, `pdf_image_vlm` (1,915 values) | `gpt-5.5` | up to 3 pages per request, 200 dpi | `build_duration.from_pdf` |
| Duration tables, 2019–2025 Excel editions | `duration.csv`, `excel_llm_structured` (1,925 values) | `gpt-5.5` | **text** rendering of the Excel cell grid (row numbers, cells separated by `|`); no image | `build_duration.from_excel` |

**What `excel_llm_structured` means (duration tables, 2019–2025 Excel editions).**
- **No image is read.** The numbers are Excel cell contents. The build renders the cell block of a duration table as plain text (row numbers, cells separated by `|`) and passes it to the model.
- **What the model does:** it only maps that grid onto the normalized schema (domain, instance, bin, year), because the tables' merged headers and layouts change between editions and sheets. The model copies each number from the cell text into its JSON output.
- **Value check:** every structured value was checked deterministically to occur in its source cell block. All 1,925 do (`validation/duration_excel_cell_check.csv`).
- **Position check:** placement in the right row and column is checked indirectly:
  - the bins sum to the printed total in all 595 Excel series-years (`validation/duration_bin_sum_checks.csv`);
  - overlapping Excel editions agree on every shared value (`validation/overlap_duration.csv`).
- A separate cell-by-cell positional check was not made (`KNOWN_ISSUES.md` #11).

**Values that involve no generative model:**
- all other Excel values (rule-based cell parsing: `extraction_method = excel`);
- national series from PDF text layers (`pdf_text_layer`);
- derived values;
- validation parsers.

## 2. API call
- **Interface:** OpenAI Chat Completions API (`chat.completions.create`).
- **Request:** one `user` message containing the prompt text plus zero or more images as base64 PNG `image_url` parts with the stated `detail`.
- **Output format:** `response_format = {"type": "json_object"}`.
- **Sampling:** temperature, top-p and seed were **not** set (API defaults). There is no system message.
- **Model identifiers** are the aliases `gpt-5.5` and `gpt-5.4-mini` as sent in the request. The API's dated snapshot / `system_fingerprint` was not recorded.
- **Call dates:** 2026-11-13 (264 responses) and 2026-11-18 (12 responses, small-claims extension), from cache file timestamps.
- **Responses used:** 276 distinct requests.
  - `gpt-5.5`, 166 requests:
    - 122 with one page image;
    - 23 with 2–4 page images;
    - 21 with Excel grid text and no image.
  - `gpt-5.4-mini`, 110 single-image title classifications.
- **Rendering:** PDF pages were rendered with PyMuPDF (`get_pixmap(dpi)`) to PNG. PDF text layers for page location were read with pdfplumber and PyMuPDF.
- **Retries:** there is no automatic retry or re-sampling. Each (model, detail, prompt, images) combination was called once, and that response is the one used.

## 3. Prompts
- **Wording:** the prompts are in Korean, matching the source. Their full text is in the scripts listed in §1.
- **Per-call log:** each call's exact prompt is listed in `model_calls.jsonl` (§5), so the prompt behind any response can be read without running code.

**Common instructions**
- Read only the named table.
- Keep the row order as printed and include total, subtotal and si/gun court rows.
- Return integers without thousands separators, with "–" as 0 and null when unreadable.
- Exclude the "average" column.
- For a two-column page, read the left column, then the right.
- Use the stated JSON schema.

**Title guard (court panel)**
- The model must return `title_seen`, the table title exactly as printed on the page, and `found = false` if the requested title is absent.
- A page is accepted only if `found` is true **and** `title_seen` matches the table's title pattern.
- **Continuation pages** have no printed title (pp. 11 and 13 of the 4-page small-claims table in the 2006, 2011 and 2016 editions). They are read with a separate continuation prompt and rejected if the text layer shows another table title.

**Other tables**
- *Overview:* the table whose title contains filings, dispositions and pending. If the table is not found on the page, the next page is tried once.
- *Detailed and duration tables:* the named table among the pages sent. The duration prompt asks for standardized instance levels and the bins in printed order.

## 4. Acceptance and post-processing rules
1. **Title guard and continuation-page rule** (§3).
2. **Hierarchy assignment:** each row is assigned to its district, branch or si/gun court. Rows whose parent court a digital edition places differently are reassigned (`build_courts.repair_hierarchy`).
3. **Source priority:** where several editions cover a year, the value comes from the newest edition, and digital sources always take precedence over model-read values. Overlaps are compared (`*_overlap_check.csv`).
4. **Internal arithmetic checks**, and corrections after re-reading the source page (`correction_log.csv`). See `validation/validation_protocol.md`.
5. **Excel duration check:** every `excel_llm_structured` value was checked to occur in the source Excel cell block given in `source_locator`. Result: 1,925/1,925 (`validation/duration_excel_cell_check.csv`). Excel editions that overlap agree on every duration value they share; the only overlap disagreement is between Excel 3.45 and PDF 3.5 (rounding).

## 5. Response cache and call log
- **Response cache** (`model_responses/`): 276 JSON files, one per distinct request used by the current pipeline. Another 77 cached responses from development iterations (earlier prompt versions) are not used by any released value and are not included.
  - Key: `sha256(model + detail + prompt + concatenated PNG bytes)`, first 24 hex characters.
  - Content: the model's JSON output as parsed. The raw HTTP response, token usage and response IDs are not stored.
  - The pipeline reads this cache before calling the API. With the cache in place, the builds make **no** API calls (set `SCOURT_CACHE_ONLY=1` to enforce this).
- **Call log** (`model_calls.jsonl`): produced by replaying the builds from the cache with `SCOURT_CALL_LOG` set. Each line has:
  - `cache_key`, `model`, `detail` and the full `prompt`;
  - the images sent (PNG SHA-256, source PDF, page, dpi);
  - `cache_hit`.

  This links every cached response to its model, prompt and page.
- **Reconstruction:**
  1. Download the source files listed in `data/source_manifest.csv` and check the SHA-256 values.
  2. Place `model_responses/` in the cache directory (`SCOURT_CACHE`).
  3. Run the build scripts in order: `build_courts.py`, `build_series.py`, `build_detail.py`, `build_duration.py`, `finalize_release.py`, `validation_blocks.py`, `make_release.py`.

  Images are re-rendered from the PDFs. If rendering software changes the PNG bytes, the cache keys no longer match; the call log's PNG hashes make this detectable.

## 6. Other generative-AI use (not affecting values)
- **Independent model re-reading:** Anthropic Claude was used for validation re-reading (`validation/validation_protocol.md` §5) and as a coding and editing assistant. The exact Claude model identifier for the 2026-11-14 re-reading run was not recorded. Its readings are archived (`validation/reread_sample_*_model_reads.csv`) with the page references, so the released validation result can be reconstructed, but it cannot be re-run exactly from API metadata. No released value depends on this run: it is used only for validation.
- **Human review:** values were accepted only through the rules and checks above. Code was reviewed and tested against row counts and identities before use.
