"""
Runs the 30-question golden set (eval/golden_question_set.json) through the
real pipeline — ingest -> chunk -> hybrid retrieval -> generation with the
four refusal gates — and scores the results against verified expected
answers. This produces the first real numbers for the docs/PRD.md Section 6
targets. See docs/EVALS_AND_BENCHMARKS.md for what each metric means and,
importantly, which of them this harness can actually compute vs. which still
need an LLM-judge or human rater (Faithfulness and Context Precision are
approximated here, not computed the way RAGAS would — see the docstrings
below and the report's own caveats section).

Usage:
    python -m eval.run_eval                # real run — needs ANTHROPIC_API_KEY in .env or the environment
    python -m eval.run_eval --dry-run       # wiring/smoke test with a scripted fake model, no API key needed

A --dry-run is NOT a real evaluation and its numbers must never be reported
as if they were — see the big warning it prints. It exists only to prove the
harness itself (index building, scoring math, report generation) works
end-to-end without requiring Nish's own Anthropic API key to be present in
this environment.
"""

from __future__ import annotations

import argparse
import json
import statistics
from dataclasses import asdict, dataclass, field
from pathlib import Path

from src.generation.generate import AnswerResult, answer_question
from src.generation.llm_client import AnthropicClient, FakeLLMClient, LLMClient
from src.generation.refusal_gates import _extract_numbers
from src.ingestion.chunk import chunk_markdown
from src.retrieval.index import HybridIndex

REPO_ROOT = Path(__file__).resolve().parents[1]
GOLDEN_SET_PATH = REPO_ROOT / "eval" / "golden_question_set.json"

COMPANY_FILES = {
    "Apple": REPO_ROOT / "data" / "processed" / "aapl-20250927.md",
    "Microsoft": REPO_ROOT / "data" / "processed" / "msft-20250630.md",
    "NVIDIA": REPO_ROOT / "data" / "processed" / "nvda-20250126.md",
}

# Question types that are meant to be refused/deflected, not answered directly.
# "ambiguous" is scored separately (Ambiguous Handling Accuracy) rather than folded
# into Refusal Accuracy / False-Refusal Rate, because for M8 asking a clarifying
# question IS the correct behavior — counting it as a "refusal failure" the way an
# ordinary answerable question's refusal would be scored would be actively wrong.
UNANSWERABLE_TYPE = "unanswerable_silent_topic"
AMBIGUOUS_TYPE = "ambiguous"
NUMERIC_TYPES = {"numeric", "numeric_derived"}


@dataclass
class QuestionOutcome:
    id: str
    company: str
    type: str
    question: str
    expected_answer: str
    got_answer: str
    got_citation: str
    refused: bool
    refusal_gate: int | None
    refusal_reason: str
    correct: bool | None  # None where "correct" isn't well-defined for this type without a judge
    notes: str = ""
    raw_llm_response: str = ""  # the model's raw response (or "" if Gate 1 refused before any LLM call) —
    # added 2026-10-18 after a real eval run showed every answerable question refused and there was no
    # recorded way to tell whether that was a retrieval problem or the model itself self-reporting
    # "not disclosed" against good passages. Without this field a bad run can't be root-caused after
    # the fact — see docs/SOLUTION_CRITIQUE.md.


def _normalize_numeric_match(expected_answer: str, actual_answer: str) -> bool:
    """A numeric answer is scored correct if every number the expected answer
    names also appears (after normalization — commas/currency/percent stripped)
    somewhere in the actual answer. This is deliberately the same normalization
    `refusal_gates.gate2_numeric_traceability` uses, so "is this number right"
    and "is this number traceable to a source" are checked the same way."""
    expected_numbers = _extract_numbers(expected_answer)
    if not expected_numbers:
        return False
    actual_numbers = _extract_numbers(actual_answer)
    return expected_numbers.issubset(actual_numbers)


_embedder = None


def _semantic_similarity(a: str, b: str) -> float:
    """Cosine similarity between two short texts, using the same embedding
    model already verified working in this environment (src/retrieval/index.py).
    Used as an approximate stand-in for textual-question correctness and for
    Answer Relevance / Faithfulness, since a real RAGAS-style judgment needs an
    LLM grader this harness doesn't have wired up. Explicitly a proxy — see
    docs/EVALS_AND_BENCHMARKS.md."""
    global _embedder
    if _embedder is None:
        from sentence_transformers import SentenceTransformer

        from src.retrieval.index import EMBEDDING_MODEL_NAME

        _embedder = SentenceTransformer(EMBEDDING_MODEL_NAME)
    import numpy as np

    vecs = _embedder.encode([a, b])
    a_vec, b_vec = vecs[0], vecs[1]
    denom = (np.linalg.norm(a_vec) * np.linalg.norm(b_vec)) or 1.0
    return float(np.dot(a_vec, b_vec) / denom)


def _build_indexes() -> dict[str, HybridIndex]:
    indexes: dict[str, HybridIndex] = {}
    for company, path in COMPANY_FILES.items():
        if not path.exists():
            raise FileNotFoundError(f"Missing parsed filing for {company}: {path}. Run src/ingestion/parse_filing.py first.")
        md = path.read_text(encoding="utf-8")
        chunks = chunk_markdown(md, source=path.name)
        index = HybridIndex(persist_dir=str(REPO_ROOT / "data" / "processed" / f"chroma_{company.lower()}"))
        index.build(chunks)
        indexes[company] = index
    return indexes


def run_eval(llm: LLMClient, k: int = 5) -> dict:
    questions = json.loads(GOLDEN_SET_PATH.read_text(encoding="utf-8"))
    indexes = _build_indexes()

    outcomes: list[QuestionOutcome] = []
    for q in questions:
        index = indexes[q["company"]]
        result: AnswerResult = answer_question(q["question"], index, llm, k=k)

        correct: bool | None
        notes = ""
        if q["type"] == UNANSWERABLE_TYPE:
            correct = result.refused
            notes = "correct = model refused" if correct else "should have refused but answered"
        elif q["type"] == AMBIGUOUS_TYPE:
            correct = result.refused and result.refusal_gate == 3
            notes = "correct = model asked for clarification (Gate 3)"
        elif q["type"] in NUMERIC_TYPES:
            correct = (not result.refused) and _normalize_numeric_match(q["expected_answer"], result.answer)
            notes = "correct = unrefused AND every expected number present in the answer"
        else:  # textual_disclosure, risk_factor_summary — no exact-match ground truth possible
            if result.refused:
                correct = False
                notes = "refused an answerable textual question — counted as incorrect"
            else:
                sim = _semantic_similarity(q["expected_answer"], result.answer)
                correct = sim >= 0.5  # proxy threshold, not a validated RAGAS cutoff — see caveats
                notes = f"semantic-similarity proxy = {sim:.3f} (threshold 0.5, NOT a validated RAGAS score)"

        outcomes.append(
            QuestionOutcome(
                id=q["id"],
                company=q["company"],
                type=q["type"],
                question=q["question"],
                expected_answer=q["expected_answer"],
                got_answer=result.answer,
                got_citation=result.citation,
                refused=result.refused,
                refusal_gate=result.refusal_gate,
                refusal_reason=result.refusal_reason,
                correct=correct,
                notes=notes,
                raw_llm_response=result.raw_llm_response,
            )
        )

    return _summarize(outcomes)


def _rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 3) if denominator else None


def _summarize(outcomes: list[QuestionOutcome]) -> dict:
    unanswerable = [o for o in outcomes if o.type == UNANSWERABLE_TYPE]
    ambiguous = [o for o in outcomes if o.type == AMBIGUOUS_TYPE]
    numeric = [o for o in outcomes if o.type in NUMERIC_TYPES]
    textual = [o for o in outcomes if o.type not in (UNANSWERABLE_TYPE, AMBIGUOUS_TYPE) and o.type not in NUMERIC_TYPES]
    # "Answerable, non-ambiguous" — the population False-Refusal Rate is defined over per PRD.md Section 6
    answerable_non_ambiguous = [o for o in outcomes if o.type not in (UNANSWERABLE_TYPE, AMBIGUOUS_TYPE)]

    metrics = {
        "refusal_accuracy": _rate(sum(o.correct for o in unanswerable), len(unanswerable)),
        "false_refusal_rate": _rate(sum(1 for o in answerable_non_ambiguous if o.refused), len(answerable_non_ambiguous)),
        "ambiguous_handling_accuracy": _rate(sum(o.correct for o in ambiguous), len(ambiguous)),
        "numeric_exact_match_rate": _rate(sum(o.correct for o in numeric), len(numeric)),
        "textual_semantic_proxy_pass_rate": _rate(sum(o.correct for o in textual), len(textual)),
        "faithfulness": None,
        "context_precision": None,
        "answer_relevance": None,
    }
    caveats = [
        "faithfulness, context_precision, and answer_relevance are NOT computed by this harness — they need an "
        "LLM-judge (RAGAS/DeepEval-style) or human rating, which this environment doesn't have a live model "
        "available for by default; wire up AnthropicClient as the judge once ANTHROPIC_API_KEY is set for real, "
        "and see docs/EVALS_AND_BENCHMARKS.md for the intended method.",
        "textual_semantic_proxy_pass_rate is an embedding-cosine-similarity stand-in (threshold 0.5, chosen for "
        "plausibility, not validated against human judgments) for risk_factor_summary / textual_disclosure "
        "questions — treat it as a rough signal, not the real Answer Relevance metric.",
    ]
    return {
        "metrics": metrics,
        "caveats": caveats,
        "outcomes": [asdict(o) for o in outcomes],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Use a scripted FakeLLMClient instead of the real Anthropic API — proves the harness works, "
        "produces NO meaningful accuracy numbers. Never report --dry-run output as a real evaluation result.",
    )
    parser.add_argument("--k", type=int, default=5, help="Number of chunks retrieved per question (default 5)")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "eval" / "results.json", help="Where to write the full report JSON")
    args = parser.parse_args()

    if args.dry_run:
        print("=" * 70)
        print("DRY RUN — using a scripted fake model, NOT a real LLM.")
        print("These numbers are a wiring/smoke test only. They say nothing about")
        print("real system accuracy. Run without --dry-run (with ANTHROPIC_API_KEY")
        print("set) to get a real baseline. See docs/EVALS_AND_BENCHMARKS.md.")
        print("=" * 70)
        llm: LLMClient = FakeLLMClient(
            response=json.dumps(
                {
                    "answer": "",
                    "citation": "",
                    "is_refusal": True,
                    "refusal_reason": "not_disclosed",
                }
            )
        )
    else:
        llm = AnthropicClient()

    report = run_eval(llm, k=args.k)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"\nMetrics (see {args.out} for full per-question detail):")
    for name, value in report["metrics"].items():
        print(f"  {name}: {value}")
    print("\nCaveats:")
    for c in report["caveats"]:
        print(f"  - {c}")


if __name__ == "__main__":
    main()
