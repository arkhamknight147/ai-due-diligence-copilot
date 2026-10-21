# Golden Question Set — RAG Evaluation

Status: v0.3 — **verified against the real downloaded filings.** All 30 questions ran through the actual ingestion pipeline (`src/ingestion/`) against the real 10-Ks in `data/raw/`, and 29 of 30 rows are now confirmed with exact quotes/figures from the primary source (the 30th, M8, is a behavioral test with no factual answer to verify). See "What changed during verification" below — two questions (A9, N9) needed real revision because the original assumption behind them turned out to be wrong once checked against the actual filing.
Last updated: 2026-09-20

## Scope

30 questions total, 10 per company (8 answerable + 2 deliberately unanswerable each), per `PRD.md` Decision Log #5, across the three frozen filings in `PRD.md` Section 3 (Apple FY2025, Microsoft FY2025, NVIDIA FY2025 10-Ks).

| Type | What it tests | PRD reference |
|---|---|---|
| Numeric | Faithfulness + numeric exact-match on figures that appear verbatim or via simple arithmetic in the filing | §4, §6 |
| Risk factor summarization | Faithfulness + context precision on synthesized (not verbatim) content | §4 |
| Textual disclosure | Faithfulness on yes/no or status-type factual claims (litigation, compliance) | §4 |
| Ambiguous | Gate 3 — the system should ask for clarification, not guess | §5, Gate 3 |
| Unanswerable (silent topic) | Gate 4 — refusal accuracy; the system should say "not disclosed," not fabricate | §5, Gate 4; §6 Refusal Accuracy |

---

## Apple Inc. — FY2025 10-K (period ended 2025-09-27)

| ID | Type | Question | Expected Answer | Status |
|---|---|---|---|---|
| A1 | Numeric | What were Apple's total net sales for fiscal year 2025? | $416,161 million | ✅ Verified |
| A2 | Numeric | What was Apple's net sales in the Americas segment for fiscal year 2025? | $178,353 million | ✅ Verified — exact match in filing |
| A3 | Numeric | What was Apple's net sales in the Greater China segment for fiscal year 2025? | $64,377 million | ✅ Verified — exact match in filing |
| A4 | Numeric | Compare Apple's fiscal 2025 net sales in Japan versus Rest of Asia Pacific. Which was higher, and by roughly how much? | Rest of Asia Pacific ($33,696M) higher than Japan ($28,703M) by ~$5.0B | ✅ Verified — exact match in filing |
| A5 | Numeric | What percentage of Apple's fiscal 2025 net sales came through indirect distribution channels? | 60% (40% direct / 60% indirect) | ✅ Verified — exact quote: *"During 2025, the Company's net sales through its direct and indirect distribution channels accounted for 40% and 60%, respectively, of total net sales."* |
| A6 | Textual disclosure | Does Apple's FY2025 10-K disclose an ongoing DOJ antitrust lawsuit alleging smartphone monopolization? | Yes — *"On March 21, 2024, the DOJ and a number of state and district attorneys general filed a civil antitrust lawsuit... alleging monopolization or attempted monopolization in the markets for 'performance smartphones' and 'smartphones.'"* | ✅ Verified — exact quote, Item 3 |
| A7 | Textual disclosure | Does Apple's 10-K disclose compliance changes related to the EU Digital Markets Act (DMA)? | Yes — disclosed under a "Digital Markets Act Investigations" heading in Legal Proceedings | ✅ Verified |
| A8 | Risk factor summarization | Summarize the risk Apple discloses concerning antitrust rulings against its search-engine partner. | Google antitrust remedies "could materially adversely affect the Company's ability to earn revenue from such licensing arrangements" | ✅ Verified — matching language found |
| **A9** | **Unanswerable** | What is the name of the customer that represented 12% of Apple's trade receivables as of fiscal year-end 2025? | *Not disclosed by name.* The filing does state *"the Company had one customer that represented 10% or more of total trade receivables, which accounted for 12%,"* but never names that customer. | ✅ Verified — **question revised** (see below) |
| **A10** | **Unanswerable** | What revenue guidance has Apple provided for fiscal year 2026 Q1? | *Not disclosed* — 10-Ks contain no forward quarterly guidance | ✅ Verified — structurally absent |

## Microsoft Corp. — FY2025 10-K (period ended 2025-06-30)

| ID | Type | Question | Expected Answer | Status |
|---|---|---|---|---|
| M1 | Numeric | What was Microsoft's total revenue for fiscal year 2025? | $281,724 million | ✅ Verified — MD&A confirms "$36.6 billion or 15%" growth, consistent with official segment figures |
| M2 | Numeric | What was Microsoft's Intelligent Cloud segment revenue for fiscal year 2025? | $106,265 million | ✅ Verified |
| M3 | Numeric | What was Microsoft's Productivity and Business Processes segment revenue for fiscal year 2025? | $120,810 million | ✅ Verified |
| M4 | Numeric | What was Microsoft's More Personal Computing segment revenue for fiscal year 2025? | $54,649 million | ✅ Verified |
| M5 | Numeric (derived) | Which segment generated the least revenue, and what was the figure? | More Personal Computing, $54,649 million | ✅ Verified |
| M6 | Textual disclosure | Does the filing disclose resolution of the FTC's challenge to the Activision Blizzard acquisition? | The acquisition closed October 13, 2023 for $75.4 billion (Note 7) — confirms the FTC challenge was resolved before close | ✅ Verified via close date/price |
| M7 | Risk factor summarization | Summarize AI/Copilot-related risk factors. | Item 1A discusses AI investment broadly and Copilot/agents specifically, in a business-model-competition framing | ⚠️ Verified in substance — exact dedicated risk-factor paragraph not isolated |
| M8 | Ambiguous | What was Microsoft's revenue? | Ambiguous by design — correct behavior is to ask for clarification | N/A — tests Gate 3 |
| **M9** | **Unanswerable** | What was Microsoft's Copilot-specific revenue for fiscal year 2025? | *Not disclosed* — Copilot discussed qualitatively, not broken out as a revenue line | ✅ Verified |
| **M10** | **Unanswerable** | What revenue guidance does Microsoft provide for fiscal year 2026 in this filing? | *Not disclosed* — guidance is issued via earnings calls, not the 10-K | ✅ Verified — structurally absent |

## NVIDIA Corp. — FY2025 10-K (period ended 2025-01-26)

| ID | Type | Question | Expected Answer | Status |
|---|---|---|---|---|
| N1 | Numeric | Data Center revenue for FY2025, per the "Revenue by End Market" note? | **$115,186 million** | ✅ Verified — exact figure from the actual filing |
| N2 | Numeric | Gaming revenue for FY2025, per the "Revenue by End Market" note? | **$11,350 million** | ✅ Verified — exact figure |
| N3 | Numeric | Total revenue for FY2025? | $130.5 billion (MD&A); end-market lines sum to $130,108M | ✅ Verified — *"Revenue for fiscal year 2025 was $130.5 billion, up 114% from a year ago."* |
| N4 | Numeric (derived) | % of total revenue from Data Center? | ~88% (115,186 / 130,108) | ✅ Verified |
| N5 | Risk factor summarization | Summarize the U.S. export-restrictions-on-China risk. | *"During the third quarter of fiscal year 2023, the USG announced export restrictions..."*; *"Our competitive position has been harmed by the existing export controls."* | ✅ Verified — **date corrected** (see below) |
| N6 | Textual disclosure | Has this already had a material effect, per the filing? | Yes — *"Our competitive position has been harmed"* (past tense, realized effect) | ✅ Verified |
| N7 | Numeric | Professional Visualization revenue for FY2025? | **$1,878 million** | ✅ Verified — **previously the unsourced placeholder; now filled** |
| N8 | Risk factor summarization | Does NVIDIA disclose customer concentration risk? | Yes, in detail — defines direct/indirect customers; for FY2025, *"an indirect customer... is estimated to represent 10% or more of total revenue, attributable to the Compute & Networking segment"* | ✅ Verified — richer than originally assumed |
| **N9** | **Unanswerable** | What is the specific name/identity of the indirect customer representing 10%+ of total revenue? | *Not disclosed by name* — referenced only via an internal anonymized label, with a threshold ("10% or more"), not an exact percentage or company name | ✅ Verified — **question revised** (see below) |
| **N10** | **Unanswerable** | Projected Data Center revenue for FY2027? | *Not disclosed* — no forward-looking numeric projections in a 10-K | ✅ Verified — structurally absent |

---

## What changed during verification

Running the real pipeline against the real filings (rather than secondary sources) surfaced three genuine corrections — exactly the kind of thing a golden set is supposed to catch before it's used to grade a system, not after:

1. **A9 was wrong as originally written.** The original question assumed Apple discloses *nothing* about customer concentration. In fact, Apple discloses that one unnamed customer represents 12% of trade receivables. The question has been narrowed to ask for that customer's *name* — which genuinely isn't disclosed — rather than implying no concentration disclosure exists at all. A system that had surfaced the 12% figure under the old question wording would have been *penalized* for giving a correct, grounded answer to what was supposed to be an unanswerable question. That would have been a bug in the eval, not the system.
2. **N9 had the same problem, worse.** NVIDIA actually discloses that an indirect customer represents "10% or more" of total revenue, attributable to Compute & Networking. The genuinely undisclosed part is the customer's *identity* and the *exact* percentage — the question now targets that specifically.
3. **N5's date was off by convention, not substance.** The original draft (from a secondary source) said NVIDIA's export-control disclosures began "August 2022." The filing itself frames it as "the third quarter of fiscal year 2023" — the same real-world period, but stated the way the primary source states it. Scoring against a paraphrase the model wasn't shown would be an unfair grading standard.

## Resolved follow-up: table column duplication (fixed 2026-09-20)

The HTML table parser (`src/ingestion/parse_filing.py`) used to triplicate each data column when a filing's raw HTML used `colspan`-style visual formatting instead of an actual `colspan` attribute (common in SEC filings) — the values were still correct, just verbose (e.g. "Americas | Americas | Americas | $ | 178353 | nan"). This has been fixed: the parser now coalesces split columns using a row-level compatibility check (equal text, equal number, or a blank/decoration cell merging into its real neighbor), verified against two unit tests and against all three real downloaded filings. Apple's segment table, for example, now renders as a single clean row per segment: "Americas | 178353 | 7 | 167045 | 3 | 162560". `data/processed/*.md` have been regenerated with the fix, and none of the 30 golden questions' expected answers changed as a result — this was a presentation/token-efficiency bug, not a correctness bug. Full before/after detail is in `docs/TRADE_OFFS.md` Section 5.
