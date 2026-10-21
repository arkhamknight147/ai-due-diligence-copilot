"""Unit tests for eval/run_eval.py's scoring logic — the part that decides
whether a given model output counts as "correct" for each golden-question
type. These use controlled, scripted results rather than the real golden set
or a real LLM, so the scoring math itself is verified in isolation."""

from __future__ import annotations

from eval.run_eval import (
    AMBIGUOUS_TYPE,
    NUMERIC_TYPES,
    UNANSWERABLE_TYPE,
    QuestionOutcome,
    _normalize_numeric_match,
    _rate,
    _summarize,
)


def test_numeric_match_tolerates_currency_and_comma_formatting():
    assert _normalize_numeric_match("$416,161 million", "Total net sales were 416161.") is True


def test_numeric_match_fails_on_wrong_number():
    assert _normalize_numeric_match("$416,161 million", "Total net sales were 999999.") is False


def test_numeric_match_fails_when_expected_answer_has_no_number():
    assert _normalize_numeric_match("Not disclosed", "Whatever the model said") is False


def test_rate_handles_zero_denominator_without_dividing_by_zero():
    assert _rate(0, 0) is None
    assert _rate(3, 6) == 0.5


def _outcome(type_, correct, refused=False, refusal_gate=None):
    return QuestionOutcome(
        id="X1",
        company="Apple",
        type=type_,
        question="q",
        expected_answer="e",
        got_answer="a",
        got_citation="c",
        refused=refused,
        refusal_gate=refusal_gate,
        refusal_reason="",
        correct=correct,
    )


def test_summarize_computes_refusal_accuracy_from_unanswerable_questions_only():
    outcomes = [
        _outcome(UNANSWERABLE_TYPE, correct=True, refused=True),
        _outcome(UNANSWERABLE_TYPE, correct=False, refused=False),
        _outcome("numeric", correct=True),
    ]
    report = _summarize(outcomes)
    assert report["metrics"]["refusal_accuracy"] == 0.5


def test_summarize_excludes_ambiguous_questions_from_false_refusal_rate():
    # M8-style question: refusing (asking for clarification) is CORRECT here, and must
    # not be counted as a false refusal the way it would for an ordinary answerable question.
    outcomes = [
        _outcome(AMBIGUOUS_TYPE, correct=True, refused=True, refusal_gate=3),
        _outcome("numeric", correct=True, refused=False),
    ]
    report = _summarize(outcomes)
    assert report["metrics"]["false_refusal_rate"] == 0.0  # only the numeric question counts, and it wasn't refused
    assert report["metrics"]["ambiguous_handling_accuracy"] == 1.0


def test_summarize_counts_a_wrongly_refused_answerable_question_as_a_false_refusal():
    outcomes = [_outcome("numeric", correct=False, refused=True)]
    report = _summarize(outcomes)
    assert report["metrics"]["false_refusal_rate"] == 1.0


def test_summarize_never_claims_faithfulness_context_precision_or_answer_relevance():
    # These require an LLM-judge this harness doesn't have wired up — must stay None,
    # never a fabricated number, however the rest of the run goes.
    report = _summarize([_outcome("numeric", correct=True)])
    assert report["metrics"]["faithfulness"] is None
    assert report["metrics"]["context_precision"] is None
    assert report["metrics"]["answer_relevance"] is None
    assert len(report["caveats"]) >= 1
