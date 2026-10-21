# AI Due Diligence Copilot

A grounded RAG assistant that answers factual questions from SEC 10-K filings — built to demonstrate table-aware retrieval and an explicit, code-enforced refusal policy against fabricated numbers, not to give investment advice.

**Status: functional prototype.** Ingestion, table-aware chunking, hybrid retrieval, and generation with refusal gates are built, unit-tested (33 tests), and verified against three real filings (not just synthetic fixtures). An eval harness exists and its retrieval-stage findings already drove two real design decisions (below). A full LLM-graded baseline run is the one step still pending — it needs an `ANTHROPIC_API_KEY` this build environment didn't have; see [Running it yourself](#running-it-yourself).

## The problem

Real-world RAG accuracy on financial questions collapses from ~89% under ideal retrieval conditions to under 20% under realistic ones — and a confident, well-cited-looking *wrong* answer is worse than no answer, because it invites a PE/VC deal-team associate to act on it without double-checking. Full evidence, market sizing, and the decision to build this over two other candidate projects: [`docs/PROBLEM_AND_SOLUTION.md`](docs/PROBLEM_AND_SOLUTION.md).

## What this demonstrates

- **Table-aware chunking** — financial tables are never split mid-row, which naive fixed-size chunking does (the root-cause failure mode this project targets).
- **Hybrid retrieval** — BM25 keyword search + vector similarity, merged with Reciprocal Rank Fusion, so exact numeric lookups aren't missed by embedding similarity alone.
- **A code-enforced refusal policy**, not just a prompted one — the two gates that can be mechanically checked (retrieval confidence, numeric-claim traceability) are checked in code, independent of what the model claims about itself. See [`docs/PRD.md`](docs/PRD.md) Section 5.
- **A documented trail of real findings**, not a polished-looking demo — see [Engineering log](#engineering-log-what-actually-happened) below. This is deliberate: the project's own thesis is that AI products should be judged on evidenced groundedness, not confident presentation, so the build process holds itself to the same standard.

## Architecture

```mermaid
flowchart LR
    subgraph Ingestion
        A[SEC 10-K HTML] --> B["parse_filing.py<br/>(tables, headings, encoding)"]
        B --> C["chunk.py<br/>(table-aware chunking)"]
    end
    subgraph Retrieval
        C --> D[(ChromaDB<br/>vector index)]
        C --> E[BM25 index]
        D --> F["HybridIndex.search()<br/>RRF fusion + table boost"]
        E --> F
    end
    subgraph Generation
        F --> G{Gate 1<br/>retrieval confidence}
        G -- below threshold --> H[Refuse — no LLM call]
        G -- above threshold --> I["Claude Haiku<br/>(citation-forcing prompt)"]
        I --> J{Gate 2<br/>numeric traceability}
        J -- unsupported number --> H
        J -- passes --> K[Answer + citation]
        I -- self-reports ambiguous/silent-topic --> H
    end
    K --> L[Streamlit demo]
    H --> L
```

Full threat model (all four gates, success metrics, scope): [`docs/PRD.md`](docs/PRD.md).

## Repo structure

```
docs/          PRD, problem/solution analysis, trade-off memo, golden question set, eval report, checkpoint critique
src/
  ingestion/   HTML parsing, table extraction, table-aware chunking
  retrieval/   Hybrid BM25 + vector search (RRF fusion)
  generation/  LLM client, citation-forcing prompt, refusal gates, orchestration
eval/          30-question golden set + scoring harness (eval/run_eval.py)
data/          Raw filings (gitignored) and parsed Markdown output
tests/         33 unit tests across ingestion, retrieval, generation, and the eval harness
app.py         Streamlit demo
```

## Running it yourself

```bash
pip install -r requirements.txt

# 1. Get the three frozen filings (see docs/PRD.md Section 3 for exact URLs/dates).
#    This sandbox's network couldn't reach sec.gov — download manually or run:
python src/ingestion/download_filings.py   # needs normal internet access

# 2. Parse them into table-aware Markdown
python src/ingestion/parse_filing.py data/raw/aapl-20250927.htm data/processed/aapl-20250927.md
python src/ingestion/parse_filing.py data/raw/msft-20250630.htm data/processed/msft-20250630.md
python src/ingestion/parse_filing.py data/raw/nvda-20250126.htm data/processed/nvda-20250126.md

# 3. Add your own Anthropic API key (see .env.example)
cp .env.example .env  # then fill in ANTHROPIC_API_KEY

# 4. Run the demo
streamlit run app.py

# 5. Run the eval harness for a real baseline (needs step 3's key)
python -m eval.run_eval
```

`python -m eval.run_eval --dry-run` runs the same harness with a scripted fake model — no API key needed — as a wiring smoke test only; see [`docs/EVALS_AND_BENCHMARKS.md`](docs/EVALS_AND_BENCHMARKS.md) for why its numbers aren't meaningful accuracy results.

## Engineering log: what actually happened

This project was built stage by stage, and several real defects were only found by testing against the actual downloaded filings rather than trusting synthetic fixtures or passing unit tests. The full trail, including the honest cost of a design decision that didn't fully work on the first try, lives in [`docs/SOLUTION_CRITIQUE.md`](docs/SOLUTION_CRITIQUE.md) and [`docs/TRADE_OFFS.md`](docs/TRADE_OFFS.md). Highlights:

- A table-column-deduplication bug's *first* fix passed its unit test but was still wrong on the real Apple filing — caught by re-checking against real data, not the test suite.
- Real 10-Ks don't use semantic `<h1>`-`<h6>` heading tags (SEC filings fake headings with bold styled `<div>`s) — section tagging and citations were completely broken on real filings (240/240 chunks tagged "unknown section") until this was found and fixed.
- Gate 1's retrieval-confidence threshold started at 0.70 per the PRD, with a built-in instruction to sanity-check it against real data once a baseline existed. That baseline showed answerable and unanswerable questions' similarity scores overlap almost entirely, and 0.70 alone refused 79% of answerable questions before the model was ever asked. Lowered to 0.60 as an explicit, logged decision — not a silent tuning change.
- A "fix" to help numeric-question retrieval (a small table-chunk boost) improved numeric coverage from 5/15 to 9/15 golden questions at the same retrieval depth, but was also caught promoting an irrelevant "Exhibit Listing" boilerplate table for one textual question — fixed with a narrow, documented exclusion rather than left as a silent false positive.

## Current filing scope (frozen for reproducibility)

| Company | Filing | Period end | Chunks | Tables |
|---|---|---|---|---|
| Apple Inc. | FY2025 10-K | 2025-09-27 | 240 | 54 |
| Microsoft Corp. | FY2025 10-K | 2025-06-30 | 301 | 36 |
| NVIDIA Corp. | FY2025 10-K | 2025-01-26 | 384 | 68 |

Newer FY2026 filings exist for Microsoft and NVIDIA as of this writing — deliberately not used, so the golden question set stays valid against a fixed target. See [`docs/PRD.md`](docs/PRD.md) Section 3.

## Docs

- [`docs/PROBLEM_AND_SOLUTION.md`](docs/PROBLEM_AND_SOLUTION.md) — problem discovery, evaluation against two other candidate projects, persona, solution rationale, all claims cited to primary sources
- [`docs/PRD.md`](docs/PRD.md) — scope, threat model, success metrics, decision log
- [`docs/TRADE_OFFS.md`](docs/TRADE_OFFS.md) — engineering trade-offs and fixes, in the order they actually happened
- [`docs/GOLDEN_QUESTION_SET.md`](docs/GOLDEN_QUESTION_SET.md) — the 30-question eval set, verified against the real filings
- [`docs/EVALS_AND_BENCHMARKS.md`](docs/EVALS_AND_BENCHMARKS.md) — what the eval harness measures, what it doesn't (yet), and why
- [`docs/SOLUTION_CRITIQUE.md`](docs/SOLUTION_CRITIQUE.md) — checkpoint self-critiques at each build milestone, including gaps this README doesn't hide

## Non-goals

Not investment advice. Not full-document summarization. Not optimized for latency — groundedness is prioritized over speed for this version. Full list: [`docs/PRD.md`](docs/PRD.md) Section 7.

## License

See [`LICENSE`](LICENSE).
