# Chunking & Parsing Trade-off Memo

Status: v0.2 — written as the ingestion pipeline was actually built, so this documents real trade-offs made, not theoretical ones
Last updated: 2026-10-22 (fixed CI running out of disk space on the GitHub-hosted runner — see Section 12)

## 1. HTML parsing instead of PDF-first

The original brief (and `PRD.md` Section 4) assumed a PyMuPDF4LLM-on-PDF pipeline. In practice, SEC EDGAR serves 10-Ks natively as HTML/iXBRL, not PDF. Converting HTML to PDF first, then to Markdown, would be a lossy detour — print-to-PDF rendering can reflow tables or drop structure depending on the renderer. `src/ingestion/parse_filing.py` instead parses HTML directly:

- Real `<table>` elements are converted to Markdown tables via `pandas.read_html`, preserving row/column relationships
- Narrative text is walked in document order via BeautifulSoup
- Headings are mapped to Markdown heading levels so downstream chunking can tag sections

A `parse_pdf_filing()` path using pymupdf4llm is kept for any future non-EDGAR or genuinely-PDF source.

**A SEC-specific wrinkle this surfaced:** filings use `<table>` tags for layout/spacing as often as for real data (e.g. a single-cell "table" used purely for whitespace). The parser drops any table that doesn't survive `pandas.read_html` with at least 2 real columns after blank-row/column pruning, rather than rendering visual noise as if it were data. Verified with `tests/test_ingestion.py::test_parse_drops_layout_only_table`.

## 2. Whole-table chunking, not fixed-size chunking

`src/ingestion/chunk.py` never splits a Markdown table across chunks (unless it exceeds 40 rows, in which case it splits on row boundaries with the header duplicated into each piece — never mid-row). This directly targets the root-cause problem identified in `docs/PROBLEM_AND_SOLUTION.md` Section 2.3, Archetype C: naive fixed-size chunking slices through tables and destroys the row/column relationship that gives a number its meaning. Narrative text is chunked separately, on paragraph boundaries, with a small overlap so a fact split across a boundary isn't lost from both sides. Verified with `tests/test_ingestion.py::test_chunker_keeps_table_intact_as_single_chunk`.

## 3. Reciprocal Rank Fusion for hybrid retrieval, not a weighted score blend

`src/retrieval/index.py` combines BM25 and vector (ChromaDB) rankings via Reciprocal Rank Fusion (RRF) rather than a weighted average of raw scores. BM25 and cosine similarity live on incomparable scales (unbounded term-frequency scores vs. a 0-1 similarity), so blending them with hand-picked weights is fragile and would need re-tuning per query type. RRF sidesteps that by fusing on *rank position* instead of raw score — a standard, well-understood technique for exactly this situation.

## 4. Environment constraint: network access inside this sandbox (partially resolved)

Building this pipeline hit a real environment constraint, worth documenting rather than hiding: for most of this build, the Claude Cowork sandbox only allowed outbound network access to a small allow-list (package registries, `api.anthropic.com`) and blocked essentially everything else, including `www.sec.gov` and `huggingface.co` (needed to download the sentence-transformer embedding model on first use).

**Update, 2026-09-20 (generation-layer milestone):** `huggingface.co` became reachable from this sandbox partway through the build — confirmed by `sentence-transformers` downloading the real `all-MiniLM-L6-v2` model weights and `tests/test_retrieval.py` passing for real (not skipping) for the first time. This closes the "hybrid retrieval never run with real embeddings" gap flagged in `docs/SOLUTION_CRITIQUE.md` Section 5 — real embeddings have now been exercised against all three real filings. `www.sec.gov` remained unreachable (the three filings were downloaded manually, as below), and general LLM provider APIs (Groq, Google AI Studio) were also unreachable, which is why generation uses the Anthropic API instead (`PRD.md` Section 8, item #6) — the one provider this sandbox could actually call.

**Resolution:** the three filings were downloaded manually (saved as complete webpages from the URLs in `PRD.md` Section 3) and placed in `data/raw/`, which unblocked the parsing and chunking stages entirely — those ran for real against the actual documents (see below). The embedding-model download for hybrid vector search is still blocked in this sandbox specifically; that part will run normally in GitHub Actions CI or once deployed to Streamlit Community Cloud / Hugging Face Spaces, both of which have normal internet access. `src/ingestion/download_filings.py` remains available for anyone re-running this pipeline from an environment with normal internet access.

**Real pipeline run, 2026-09-20 (post column-dedup fix — see Section 5):** `parse_filing.py` and `chunk.py` ran against all three real 10-Ks. Parsed Markdown size dropped materially once the column-duplication bug (Section 5) was fixed, since the parser stopped emitting duplicate/decoration columns:

| Filing | Parsed size, pre-fix | Parsed size, post-fix | Reduction |
|---|---|---|---|
| Apple FY2025 | 542,880 chars | 294,466 chars | -46% |
| Microsoft FY2025 | 424,202 chars | 402,806 chars | -5% |
| NVIDIA FY2025 | 847,583 chars | 467,624 chars | -45% |

BM25 keyword search (the retrieval half that doesn't need the blocked embedding model) was used to locate and verify every flagged fact in the golden question set against the real chunked text — see `docs/GOLDEN_QUESTION_SET.md` for the full results. 29 of 30 questions are verified with exact quotes/figures from the primary filings.

**One real fact-check surfaced an important correction:** NVIDIA's actual ASC 280 reportable segments, per its own 10-K, are "Compute & Networking" and "Graphics" — not separate "Data Center" / "Gaming" / "Professional Visualization" / "Automotive" segments. Those four are real, filing-native terms too, but as the "Revenue by End Market" note (Item 1 calls them "four large markets"), not the formal reportable-segment structure. `docs/GOLDEN_QUESTION_SET.md` and `eval/golden_question_set.json` reflect this. Specifically, questions N1, N2, N4, and N7 were reworded from "segment" to "revenue by end market / Revenue by End Market note" to match the filing's actual terminology (see `docs/GOLDEN_QUESTION_SET.md` rows N1-N9 for the verified figures this produced, including N7's previously-unsourced Professional Visualization figure getting filled in for real).

**A second, more interesting correction came from full verification, not just terminology:** two "unanswerable" questions (A9, N9) were wrong as originally written — both assumed a topic was completely undisclosed when the filing actually discloses a *related* fact (a customer-concentration percentage) while still withholding the *specific* fact the question should have targeted (the customer's identity). Both questions were narrowed to test the part that's genuinely undisclosed. This is worth calling out explicitly: a golden set built from assumptions instead of verification would have penalized a system for giving a correct answer that happened to not fit a wrong premise — which is precisely the kind of eval bug this project's whole thesis (measure groundedness rigorously, don't just claim it) is supposed to prevent.

## 5. Table column duplication — fixed 2026-09-20

**Original problem:** SEC filings' raw HTML renders a single visual table column as multiple `<td>` cells instead of using proper `colspan` — e.g. a currency sign, the number, and a blank spacing cell as three separate cells meant to look like one column. `pandas.read_html` has no way to know these were meant to be one column, so it handed back separate, mostly-duplicate columns. Left alone, this bloated every real data table 2-3x with no new information (e.g. `"Americas | Americas | Americas | $ | 178353 | nan"` instead of `"Americas | 178353"`).

**Why the first fix attempt wasn't enough:** an initial version compared whole columns for exact equality and dropped duplicates/decoration-only columns. That caught the easy cases but missed most of the real pattern, because the split isn't uniform down a column — in Apple's actual segment table, the "Americas" row repeats the *label* three times, while the very next "Europe" row instead repeats the *number* three times (the "$" only appears on the first data row). A whole-column equality check can't see that; it only holds row-by-row.

**Actual fix:** `_dedupe_and_clean_columns()` in `src/ingestion/parse_filing.py` now coalesces columns left-to-right using a row-level compatibility check — two adjacent columns merge if, for every row, their cells are equal (as text *or* as a number, so `"2025"` and `"2025.0"` are recognized as the same value despite pandas inferring different dtypes for the two split copies), or one side is blank, or one side is a bare decoration token (`$ % ( ) — -`). After coalescing, any leftover all-decoration or all-blank column is dropped.

**Verified two ways:**
- Two unit tests in `tests/test_ingestion.py` cover both the straightforward triplication case and the int-vs-float string-mismatch edge case that broke the first fix attempt.
- Re-ran the parser against all three real downloaded filings and confirmed the actual output. Apple's segment table now renders as:

  ```
  | Americas             | 178353 | 7      | 167045 | 3      | 162560 |
  | Europe               | 111032 | 10     | 101328 | 7      |  94294 |
  ```

  (previously: `Americas | Americas | Americas | $ | 178353 | nan | 7 | 7 | % | ...`). NVIDIA's "Revenue by End Market" table and Microsoft's segment tables were spot-checked the same way and show the same clean, single-value-per-column result.

This was a case worth being explicit about as a lesson: the unit test passing against a synthetic fixture didn't mean the fix was correct — the fixture happened to match the "easy" (whole-column-duplicate) case, not the real filings' row-varying pattern. Re-verifying against the actual downloaded documents, not just the test suite, is what caught it. `data/processed/*.md` have been regenerated with the fixed parser.

## 6. Inline-XBRL context noise in parsed text — fixed 2026-09-21

SEC HTML filings embed a hidden inline-XBRL context/header block (`<ix:header>`, plus assorted elements styled `display:none`) containing raw taxonomy tag names, CIK numbers, and date ranges (e.g. `aapl:AmericasSegmentMember 2024-09-29 2025-09-27`) that a browser never renders but the original HTML walker had no way to distinguish from ordinary narrative text, so it emitted the whole block as a normal paragraph.

Measured impact before the fix: one contiguous ~13,800-character block on the Apple filing (~4.7% of the parsed document) — roughly half a dozen pure-noise text chunks sitting in the retrieval index for no reason. Fixed in `parse_filing.py` by decomposing `<ix:header>` tags and any element with inline `display:none` styling before walking the document tree, matching what a human reading the filing in a browser would actually see. Verified: zero XBRL-taxonomy-tag mentions (`gaap:...Member`, `aapl:...Member`, etc.) in any of the three real parsed filings after the fix (was 190 in Apple's alone), with real reductions in parsed file size across all three. Covered by a new unit test using a synthetic fixture with both an `<ix:header>` block and a `display:none` element.

## 7. Fixed alongside the generation layer: Chroma was using the wrong distance metric for Gate 1

`PRD.md` Section 5, Gate 1 specifies retrieval confidence as "0.70 cosine similarity." `src/retrieval/index.py`'s `HybridIndex` created its Chroma collection without specifying a distance metric, which defaults to squared L2 distance, not cosine — so a threshold written as "cosine similarity" was never actually being checked against a cosine value. Fixed by creating the collection with `metadata={"hnsw:space": "cosine"}` and converting Chroma's returned cosine *distance* to cosine *similarity* (`1 - distance`), exposed as a new `SearchResult.vector_similarity` field (separate from the RRF-fused `score`, which remains on its own incomparable scale — see Section 3). `src/generation/refusal_gates.py`'s Gate 1 check reads this field directly.

## 8. Table-chunk boost in retrieval fusion — fixed 2026-09-21, with a caught false positive

Section 9 of `docs/SOLUTION_CRITIQUE.md` found that bare financial tables have almost no natural-language surface area, so even the exact right table often ranked below a narrative paragraph that merely discussed the same topic without the actual figure. Measured before fixing: only 5 of 15 numeric golden questions had their supporting evidence chunk in the top 5 retrieval results.

**Fix:** `src/retrieval/index.py`'s `HybridIndex.search()` now adds a small score bonus (one RRF rank position's worth, `1/60`) to table-type chunks after fusion — a deliberate, documented tie-breaking preference given this project's core thesis is "financial answers should come from tables, not narrative," not just a tuning hack. Measured after: 9 of 15 (60%) at the same `k=5` — better than doubling `k` to 10 without the boost (9/15), at half the context cost.

**Caught while verifying it:** the boost also promoted an irrelevant "Exhibit Listing" boilerplate table (pure legal filler — an index of exhibit numbers, no financial content) for one textual-disclosure golden question (M6), displacing more relevant narrative chunks purely because it happened to share incidental vocabulary with the query and got the same table bonus as a real financial table. Fixed with a narrow, named exclusion (`_BOILERPLATE_TABLE_SECTION_TERMS`) rather than left as a silent false positive — verified the exclusion removes the exhibit-table promotion on M6 while the 9/15 numeric-question gain is unaffected. Worth stating plainly: this wasn't found by the unit test suite, it was found by re-checking the real golden questions after making the change, the same lesson as every other real-filing finding in this document.

**Honest residual:** 6 of 15 numeric golden questions still don't have their evidence chunk in the top 5 even with the boost — bare financial tables are inherently sparse in a way one heuristic doesn't fully solve. A further lever (a numeric-question-aware retrieval path, or a re-ranker) would still help; not pursued further here to avoid diminishing-returns tuning against a single 30-question set.

## 9. Streamlit demo and README — completed 2026-09-21

`app.py` is a working demo (not a placeholder) wired to the real pipeline: it builds real indexes from the parsed filings, runs Gate 1's retrieval-confidence check for real, and calls the real Anthropic API for generation when `ANTHROPIC_API_KEY` is set — falling back to a clearly-labeled "retrieval-only mode" (shows retrieved passages and the Gate 1 decision, no generated answer) when it isn't, so the app is still useful for demonstrating the pipeline's mechanics in an environment without a key, like the one this was built in. Verified it starts cleanly and serves HTTP 200 with no runtime errors.

`README.md` was rewritten from a two-paragraph stub into a full portfolio-facing document: problem summary, a Mermaid architecture diagram, an honest "engineering log" section that surfaces the real defects found and fixed during this build (not just the polished end state), the frozen filing scope with real chunk/table counts, setup instructions, and links to every doc in `docs/`. A demo GIF is intentionally not included — recording one requires actually running the Streamlit app and interacting with it, which needs to happen on Nish's own machine (or wherever the app is deployed), not in this build sandbox.

## 10. Housekeeping note — merged a stray duplicate doc, 2026-10-18

A standalone `docs_TRADE_OFFS_addendum.md` had drifted out to the repo root during an earlier build session — an early draft of Sections 1-4 above, written before the environment's network constraints were resolved and before the pipeline had been run against the real filings. Everything in it was already superseded by the fuller account in Sections 1-4 (the embedding-model access update, the real pipeline run results, the NVIDIA segment-naming correction), with one exception: it named the specific golden-question IDs (N1, N2, N4, N7) affected by that correction, which has now been folded into Section 4 above. The standalone file has been deleted rather than left as a second, confusing trade-offs document.


## 11. Gate 2 false-positive fixes from the real eval baseline, and known limitations left as-is — 2026-10-21

The first real eval run with a live `ANTHROPIC_API_KEY` (see Section 4's embedding-model note for why earlier runs had been retrieval-only) surfaced `false_refusal_rate: 0.652` and `numeric_exact_match_rate: 0.267` — i.e. Gate 2 (numeric-claim traceability, `src/generation/refusal_gates.py`) was refusing a lot of answers that were actually correct and fully grounded. Diagnosed using `raw_llm_response`, a field added to `eval/run_eval.py`'s `QuestionOutcome` specifically so a refusal's actual model output could be inspected instead of silently discarded.

**Five distinct false-positive patterns found and fixed, across two passes of the same re-run:**

1. **Filing-form digits** — "10-K" was parsed as the bare number "10" (confirmed on N6).
2. **Markdown list markers** — "1. ", "2. " at the start of an answer line were parsed as numeric claims (confirmed on N5).
3. **Legitimate unit restatements and disclosed arithmetic** — e.g. restating "$416,161 million" as "$416.2 billion," or showing "$33,696M - $28,703M = $4,993M," both explicitly permitted by the system prompt's "show the arithmetic" rule (confirmed on A1/M1/M4/A4).
4. **Follow-up to #1** — the first fix for filing-form digits only worked for single-digit forms ("8-K"); "10-K"/"10-Q" (two digits) still slipped through because the lookahead was checked at the first digit instead of right after the whole matched number (still present on N6 after the first fix).
5. **Fiscal-quarter labels** — "Q3" in "Q3 FY2023" was parsed as a numeric claim needing a source citation (confirmed on N5).

Each fix has a dedicated regression test in `tests/test_generation.py` (one per bug, following this project's established practice), and the existing fabrication-detection test (`test_numeric_traceability_flags_a_number_absent_from_every_chunk`) was re-verified to still pass after every fix — the point of Gate 2 is to catch a genuinely made-up number, and narrowing its false positives must not blunt that.

**Measured impact:** `false_refusal_rate` 0.652 -> 0.478, `numeric_exact_match_rate` 0.267 -> 0.467 across the two passes (first pass fixed #1-3, second pass fixed #4-5).

**Three findings from this same real run that were deliberately left as documented limitations, not code changes, per Nish's explicit call to keep scope to the regression fix and move on to the GitHub push:**

- **N4 (a `numeric_derived` question) still refuses.** The model correctly divides $115,186M / $130,497M = 88.3%, but the system prompt's "show the arithmetic" rule (`prompts.py`) only explicitly permits a *sum or difference* of two sourced numbers, not a *ratio/percentage*. Gate 2 is doing exactly what it was told; extending the permitted-arithmetic rule to cover derived percentages is a prompt-design decision, not a bug fix.
- **N4 also has an unresolved numbers mismatch:** the golden set's expected answer uses a total-revenue denominator of 130,108, while the model (and its retrieved chunk) used 130,497 — a real discrepancy worth checking against the filing directly (possibly two different "total revenue" figures in NVIDIA's 10-K, or a golden-set transcription error), not yet investigated.
- **A4 and A5 are correct answers marked "incorrect" by the eval harness's strict string-matching**, not gate failures: A4 states the exact correct difference ("$4,993 million") but doesn't also restate it rounded to "$5.0 billion" the way the golden answer does; A5 correctly states "60% indirect" but doesn't also restate the complementary "40% direct." Both are a harness/golden-set tolerance question, left as-is.
- **M8 (the one `ambiguous`-type question) still scores 0% on ambiguous-handling** — the model answers with all three fiscal years' totals instead of asking a clarifying question. This is a prompt-engineering behavior gap (Gates 3/4 are self-reported, not code-enforced — see the module docstring in `refusal_gates.py`), not a Gate 2 issue, and not pursued further this round.


## 12. CI ran out of disk space on the GitHub-hosted runner — fixed 2026-10-22

The first CI run after pushing to GitHub (`.github/workflows/ci.yml`) failed during `pip install -r requirements.txt` with `OSError: [Errno 28] No space left on device`. Root cause: PyPI's default `torch` wheel (a transitive dependency of `sentence-transformers`) bundles the full NVIDIA CUDA toolkit as a pile of separate multi-GB packages (`nvidia-cublas`, `nvidia-cudnn-cu13`, `nvidia-cusparse`, `triton`, etc. — all visible in the failed install log), none of which this CPU-only CI job can use or needs. Combined with `chromadb`'s own sizeable dependency tree (`opentelemetry-*`, `kubernetes`, `huggingface-hub`, `transformers`), that was enough to exhaust the standard GitHub-hosted runner's disk mid-install.

**Fix:** `ci.yml` now installs the CPU-only `torch` wheel first (`pip install torch --index-url https://download.pytorch.org/whl/cpu`), before `pip install -r requirements.txt` — so when `sentence-transformers` later requests `torch`, pip sees it's already installed and satisfied, and never reaches for the much larger CUDA-bundled default. A `Free up runner disk space` step (removing preinstalled toolchains the job doesn't use — dotnet, Android SDK, etc.) was added as additional headroom, but the CPU-only torch install is the actual fix; the cleanup step alone would not have been enough given how large the CUDA wheel set is.

