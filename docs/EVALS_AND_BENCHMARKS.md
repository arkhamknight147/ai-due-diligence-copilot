# RAG Evals Report

Status: **Harness built and smoke-tested (`eval/run_eval.py`); no real baseline run yet.** This environment doesn't have `ANTHROPIC_API_KEY` configured, so the numbers below reflect the harness working correctly against real filings and real retrieval, not real LLM behavior — see `docs/SOLUTION_CRITIQUE.md` Section 10 for the first real finding this produced (a Gate 1 threshold calibration question) and Section 11 for what's next. Run `python -m eval.run_eval` (with the API key set, from your own machine) for a true baseline.

## What's real and what isn't, as of 2026-09-20

`eval/run_eval.py` builds real hybrid indexes from the real parsed filings and runs all 30 golden questions through the real retrieval + refusal-gate pipeline. Its `--dry-run` mode substitutes a scripted fake model for the LLM call specifically (no API key needed) — everything upstream of that (index building, Gate 1's retrieval-confidence check) is real. This is why the dry run could still surface a genuine finding: Gate 1's cosine-similarity check runs before the LLM is ever called, so its behavior is fully real even in dry-run mode. What ISN'T yet real: any metric that depends on what the LLM actually says (Numeric Exact-Match Rate, False-Refusal Rate past Gate 1, Faithfulness, Context Precision, Answer Relevance) — those need a real run.

## The plan, now that the generation layer exists

1. **Harness**: `eval/run_eval.py` iterates the 30 questions in `eval/golden_question_set.json`, runs each through the full pipeline (retrieve → generate → refuse-or-answer), and records the system's actual output alongside the verified `expected_answer`.
2. **Scoring rules per question type**:
   - Numeric questions: exact-match against `expected_answer` after normalizing formatting (commas, `$`, "million"/"M").
   - Textual disclosure / risk-factor-summarization questions: containment or semantic-similarity check against the key phrase in `expected_answer` (exact string match is too brittle for summarized text).
   - Unanswerable questions (6 of 30): pass if the system's refusal gate fires; fail if it fabricates or over-confidently answers.
3. **Metrics computed** (targets from `PRD.md` Section 6, reproduced here for traceability):

   | Metric | Target | How it's computed from the run |
   |---|---|---|
   | Faithfulness | ≥ 0.90 | Fraction of answer claims traceable to a retrieved chunk verbatim or via shown arithmetic |
   | Context Precision | ≥ 0.85 | Fraction of retrieved top-k chunks actually relevant to the question |
   | Answer Relevance | ≥ 0.85 | Whether the answer addresses what was asked, independent of correctness |
   | Refusal Accuracy | ≥ 0.90 | Of the 6 unanswerable questions, fraction correctly refused |
   | False-Refusal Rate | ≤ 10% | Of the 24 answerable questions, fraction wrongly refused |
   | Numeric exact-match rate | ≥ 0.95 | Of numeric-type questions, fraction matching `expected_answer` exactly after normalization |

4. **Baseline run**: the first real run of `run_eval.py` against the actual LLM choice (see `PRD.md` Section 8, open item on LLM/API selection) becomes the baseline. The Section 6 targets get revisited against that baseline per the existing call-out in `PRD.md` ("to be validated against the actual baseline run, not externally-sourced industry standards") — they are not expected to be hit perfectly on the first pass, and a miss is useful information, not a failure of the exercise.

## What's already true, and can be reused once the harness exists

- The golden set itself is fully verified against the real filings (29/30; see `docs/GOLDEN_QUESTION_SET.md`), so scoring against it means scoring against ground truth that's actually been checked, not assumed.
- BM25-only retrieval has already been spot-checked against several golden questions during verification and reliably surfaced the right chunk for numeric lookups — a useful (if partial) early signal, documented in `docs/TRADE_OFFS.md`.
- The four refusal gates are fully specified (`PRD.md` Section 5) and just need code, not further design work, before the harness can exercise them.
