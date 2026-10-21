# PRD: AI Due Diligence Copilot

Status: Draft v0.3 — retrieval threshold and eval-set split confirmed by Nish, 2026-09-20
Owner: Nish
Last updated: 2026-09-20

This PRD is intentionally lean — the full problem discovery, evaluation, evidence base, and solution rationale live in `docs/PROBLEM_AND_SOLUTION.md`. This document translates that analysis into build requirements. If the two ever disagree, `PROBLEM_AND_SOLUTION.md` is the source of truth for *why*; this PRD is the source of truth for *what to build*.

## 1. Problem (summary)

Analysts doing due diligence on a company need to answer specific, high-stakes factual questions against SEC 10-K filings, but AI tools fast enough to help are not, by default, trustworthy enough to rely on for that purpose. Real-world RAG accuracy on financial questions collapses from ~89% under ideal retrieval to under 20% under realistic conditions, and this failure mode has already caused documented, costly incidents in due diligence work.

Full evidence and problem-archetype evaluation: `docs/PROBLEM_AND_SOLUTION.md`, Parts A.1–A.3.

## 2. Target user

**Primary persona: PE/VC deal-team associate** — confirmed as the highest-priority segment on severity of consequence and strength of market evidence.

Representative persona — **Priya Menon, 27**, associate at a mid-market PE fund, running first-pass diligence on 2-3 live deals at once under IC-deadline pressure. She needs a fast, source-linked answer to a specific factual question, and an honest signal when the filing doesn't disclose it — because guessing wrong in an IC memo is a career risk, not an inconvenience.

Full persona and journey map: `PROBLEM_AND_SOLUTION.md`, Sections 6-7.

## 3. Scope — v1

### Filing scope (frozen)

A golden eval set needs a fixed, reproducible target — "most recent filing" is a moving target that would silently break question/answer pairs every time a new 10-K drops. So scope is pinned to specific, dated filings rather than "whichever is newest":

| Company | Filing | Fiscal period end | Filed |
|---|---|---|---|
| Apple Inc. | FY2025 Form 10-K | 2025-09-27 | 2025-10-31 |
| Microsoft Corp. | FY2025 Form 10-K | 2025-06-30 | 2025-07-30 |
| NVIDIA Corp. | FY2025 Form 10-K | 2025-01-26 | 2025-02 (est.) |

*(A newer Microsoft 10-K for FY2026, ended 2025-06-30 [sic, ended 2026-06-30], and a newer NVIDIA 10-K for FY2026, ended 2026-01-25, already exist as of this writing — deliberately not used here, for the reproducibility reason above. Revisit this table if you want the copilot to demonstrate coverage of the newest filings instead.)*

### In scope
- Filing types: 10-K only (10-Q introduces a comparability/restatement problem that's a v2 concern)
- Question types: numeric lookups (revenue, margins, segment breakdowns), risk factor summarization, textual disclosure lookups (litigation, related-party transactions)
- Output: answer + inline citation (filing name, page/section) + confidence signal

### Out of scope for v1
- Cross-filing comparison (e.g. year-over-year margin change) — needs multi-document reasoning; natural v2 feature once single-filing grounding is proven
- 10-Q, 8-K, proxy statements
- Any generative summarization not directly traceable to a specific passage
- Multi-turn conversational memory beyond simple follow-up ("what about the prior year" is v2)

## 4. Core feature requirements

- Table-aware ingestion that preserves row/column relationships in financial tables — the primary lever against the root cause identified in `PROBLEM_AND_SOLUTION.md` Section 2.3, Archetype C (see `TRADE_OFFS.md` once written)
- Hybrid retrieval: BM25 keyword + vector similarity, so exact-match numeric and defined-term queries aren't missed by pure embedding similarity
- Inline citation on every factual claim (filing, section/page)
- A refusal path — see Section 5 — designed and tested as a first-class behavior, not a fallback

## 5. Threat model: groundedness & refusal policy

The failure mode being designed against: a confident, well-cited-looking answer that is wrong or fabricated — worse than "I don't know," because it invites the analyst to act on it without further checking. This is the same failure mode documented at $1.5M cost in a real due-diligence incident (`PROBLEM_AND_SOLUTION.md` Section 2.3).

**Refusal policy: conservative default**, quantified by the Section 6 targets below (refusal accuracy held to a high bar, capped by a false-refusal ceiling so the system can't game that bar by refusing everything).

| Gate | Trigger | System behavior |
|---|---|---|
| 1. Retrieval confidence | Top-k retrieved chunk similarity falls below **0.60 cosine similarity** *(revised 2026-09-20 from an initial 0.70 — the real 30-question baseline showed answerable and unanswerable questions' scores overlap almost entirely (0.408–0.749 vs. 0.591–0.700), so 0.70 alone refused 79% of answerable questions before the LLM was consulted. Lowered to sit below the answerable median, leaning more on Gate 4's LLM self-report to catch undisclosed topics; see `docs/SOLUTION_CRITIQUE.md` Section 10 for the full data.)* | Returns "This information does not appear to be disclosed in this filing" plus the closest related section found |
| 2. Numeric-claim | Answer would state a number not verbatim present in a retrieved chunk (or derivable from one via shown arithmetic) | Refuses to synthesize the number from general knowledge or cross-chunk extrapolation |
| 3. Ambiguous question | Question could refer to multiple line items (e.g. "revenue" without segment/product/geography specified) | Asks a clarifying question instead of guessing |
| 4. Silent topic | Question asks about something filings omit by design (forward guidance, named customers, unannounced products) | Explicitly names this as a known omission category, rather than treating it as a retrieval miss |

## 6. Success metrics

Reproduced from `PROBLEM_AND_SOLUTION.md` Section 8 — see that section for full rationale. These are provisional targets grounded in high-stakes-tier RAG evaluation practice, to be validated against the actual baseline run, not externally-sourced industry standards.

| Metric | Target | Notes |
|---|---|---|
| Faithfulness (RAGAS/DeepEval) | ≥ 0.90 | Unsupported claims here risk real financial decisions |
| Context Precision | ≥ 0.85 | Retrieved chunks mostly relevant |
| Answer Relevance | ≥ 0.85 | Standard bar for a usable QA system |
| Refusal Accuracy (on deliberately-unanswerable questions) | ≥ 0.90 | Core trust mechanic — should fail closed |
| False-Refusal Rate (on answerable questions) | ≤ 10% | Caps the "refuse everything" failure mode |
| Numeric exact-match rate (table-derived answers vs. source) | ≥ 0.95 | Highest-stakes, most verifiable claim type |

## 7. Non-goals

- Not an investment advice tool — will carry a disclaimer to that effect
- Not attempting full document summarization
- Not optimized for fastest possible response time — groundedness is prioritized over latency for v1 (latency/cost optimization is explicitly Project 3's territory)

## 8. Decision log

| # | Decision | Value | Date | Where documented |
|---|---|---|---|---|
| 1 | Evaluation criteria weighting | Stakes 0.25 / Demand 0.25 / Whitespace 0.25 / Feasibility 0.15 / Skill-fit 0.10 | 2026-09-20 | `PROBLEM_AND_SOLUTION.md` §2.1 |
| 2 | Primary persona | PE/VC deal-team associate | 2026-09-20 | `PROBLEM_AND_SOLUTION.md` §5 |
| 3 | Success metric targets | See Section 6 above | 2026-09-20 | `PROBLEM_AND_SOLUTION.md` §8 |
| 4 | Retrieval confidence threshold | 0.60 cosine similarity (revised from 0.70) | 2026-09-20 (revised 2026-09-20) | This document, §5; revision rationale in `docs/SOLUTION_CRITIQUE.md` §10 |
| 5 | Golden eval set composition | 30 questions: 24 answerable / 6 deliberately unanswerable | 2026-09-20 | `GOLDEN_QUESTION_SET.md` (next artifact) |

### Decided

| # | Decision | Value | Date | Notes |
|---|---|---|---|---|
| 6 | LLM/API choice for the generation layer | **Anthropic API (Claude Haiku)** | 2026-09-20 | Groq/Gemini were the original free-tier candidates, but this build sandbox can only reach `api.anthropic.com`, not their endpoints (see `docs/TRADE_OFFS.md` Section 4) — Anthropic was chosen so generation could actually be exercised end-to-end during development, not just unit-tested against a mock. Running it for real still requires Nish's own `ANTHROPIC_API_KEY` in `.env` (see `.env.example`); it is not a zero-cost choice, unlike Groq/Gemini's free tiers — worth being explicit about in the portfolio write-up. |

No other open decisions remain for this PRD version as of the ingestion/retrieval milestone (2026-09-20). See `docs/SOLUTION_CRITIQUE.md` for a full checkpoint critique of the solution as it stands, including what's built, what isn't, and a prioritized next-steps list — updated 2026-09-20 with two new findings from building and real-testing the generation layer (retrieval ranking and section-tagging gaps on the real filings).
