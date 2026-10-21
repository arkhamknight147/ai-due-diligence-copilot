"""Unit tests for the generation layer (src/generation/).

These test the refusal-gate logic and orchestration deterministically, using
FakeLLMClient instead of a real Anthropic API call — no network, no API key
needed (see src/generation/llm_client.py docstring for why: this sandbox
can't be given a live ANTHROPIC_API_KEY, so the code path that matters most —
"does a fabricated number actually get caught and refused" — is verified here
with a controlled fake model, and the real end-to-end call is meant to be run
from an environment that has the key configured).

A minimal fake HybridIndex is used too, so these tests don't depend on the
embedding model (also network-blocked here — see docs/TRADE_OFFS.md Section 4).
"""

from __future__ import annotations

import json

from src.generation.generate import answer_question
from src.generation.llm_client import FakeLLMClient
from src.generation.refusal_gates import gate2_numeric_traceability
from src.ingestion.chunk import Chunk
from src.retrieval.index import SearchResult


def _make_result(text: str, similarity: float, section: str = "Segment Information") -> SearchResult:
    chunk = Chunk(text=text, chunk_type="table", section=section, index=0)
    return SearchResult(chunk=chunk, score=0.01, bm25_rank=0, vector_rank=0, vector_similarity=similarity)


class _FakeIndex:
    """Stands in for HybridIndex.search without needing a real embedding model."""

    def __init__(self, results: list[SearchResult]):
        self._results = results

    def search(self, query: str, k: int = 5):
        return self._results[:k]


def test_gate1_refuses_low_confidence_without_calling_the_llm():
    results = [_make_result("Americas | 178353", similarity=0.42)]
    index = _FakeIndex(results)
    llm = FakeLLMClient(response="THIS SHOULD NEVER BE CALLED")

    result = answer_question("What was Americas revenue?", index, llm)

    assert result.refused is True
    assert result.refusal_gate == 1
    assert llm.calls == [], "the LLM must not be called when retrieval confidence is below threshold"


def test_gate1_does_not_refuse_when_a_lower_ranked_result_is_confident():
    """Regression test for the bug found 2026-10-18 (see refusal_gates.py and
    docs/SOLUTION_CRITIQUE.md): HybridIndex.search() sorts by the RRF-fused
    score, which includes a table-chunk boost, so the #1 fused-rank result
    can carry weak vector similarity while a stronger match sits lower in
    the same batch. Gate 1 must look at the whole batch's best similarity,
    not just results[0], or it wrongly refuses before the LLM ever sees the
    confident match (this cost 13/30 real golden-set questions, e.g. A4)."""
    weak_top_ranked = _make_result("Table noise", similarity=0.45)  # ranks #1 by fused score (not modeled here) but weak alone
    strong_but_lower_ranked = _make_result("Americas | 178353 | 7%", similarity=0.85)
    results = [weak_top_ranked, strong_but_lower_ranked]
    index = _FakeIndex(results)
    llm_response = json.dumps(
        {
            "answer": "Americas net sales were $178,353 million.",
            "citation": "Segment Information",
            "is_refusal": False,
            "refusal_reason": "",
        }
    )
    llm = FakeLLMClient(response=llm_response)

    result = answer_question("What was Americas revenue?", index, llm)

    assert result.refused is False
    assert len(llm.calls) == 1, "a confident match anywhere in the batch must still reach the LLM"


def test_gate1_refuses_when_no_vector_candidate_exists():
    chunk = Chunk(text="Americas | 178353", chunk_type="table", section="Segment Information", index=0)
    result_no_vector = SearchResult(chunk=chunk, score=0.01, bm25_rank=0, vector_rank=None, vector_similarity=None)
    index = _FakeIndex([result_no_vector])
    llm = FakeLLMClient(response="SHOULD NOT BE CALLED")

    result = answer_question("What was Americas revenue?", index, llm)

    assert result.refused is True
    assert result.refusal_gate == 1
    assert llm.calls == []


def test_grounded_answer_with_supported_number_passes_through():
    results = [_make_result("Americas | 178353 | 7%", similarity=0.85)]
    index = _FakeIndex(results)
    llm_response = json.dumps(
        {
            "answer": "Americas net sales were $178,353 million.",
            "citation": "Segment Information",
            "is_refusal": False,
            "refusal_reason": "",
        }
    )
    llm = FakeLLMClient(response=llm_response)

    result = answer_question("What was Americas revenue?", index, llm)

    assert result.refused is False
    assert result.answer == "Americas net sales were $178,353 million."
    assert result.citation == "Segment Information"
    assert len(llm.calls) == 1


def test_gate2_overrides_llm_when_answer_contains_unsupported_number():
    results = [_make_result("Americas | 178353 | 7%", similarity=0.85)]
    index = _FakeIndex(results)
    # The model fabricates a plausible-looking number that never appeared in any retrieved chunk.
    llm_response = json.dumps(
        {
            "answer": "Americas net sales were $999,999 million.",
            "citation": "Segment Information",
            "is_refusal": False,
            "refusal_reason": "",
        }
    )
    llm = FakeLLMClient(response=llm_response)

    result = answer_question("What was Americas revenue?", index, llm)

    assert result.refused is True
    assert result.refusal_gate == 2
    assert "999999" in result.refusal_reason or "999,999" in result.refusal_reason


def test_llm_self_reported_ambiguous_question_maps_to_gate3():
    results = [_make_result("Revenue | 416161", similarity=0.9)]
    index = _FakeIndex(results)
    llm_response = json.dumps(
        {
            "answer": "",
            "citation": "",
            "is_refusal": True,
            "refusal_reason": "ambiguous_question",
        }
    )
    llm = FakeLLMClient(response=llm_response)

    result = answer_question("What was revenue?", index, llm)

    assert result.refused is True
    assert result.refusal_gate == 3
    assert result.refusal_reason == "ambiguous_question"


def test_llm_self_reported_silent_topic_maps_to_gate4():
    results = [_make_result("Risk factors...", similarity=0.9)]
    index = _FakeIndex(results)
    llm_response = json.dumps(
        {
            "answer": "",
            "citation": "",
            "is_refusal": True,
            "refusal_reason": "not_disclosed",
        }
    )
    llm = FakeLLMClient(response=llm_response)

    result = answer_question("What is FY2027 guidance?", index, llm)

    assert result.refused is True
    assert result.refusal_gate == 4


def test_malformed_llm_response_becomes_a_refusal_not_a_crash():
    results = [_make_result("Revenue | 416161", similarity=0.9)]
    index = _FakeIndex(results)
    llm = FakeLLMClient(response="I'm not going to give you JSON today.")

    result = answer_question("What was revenue?", index, llm)

    assert result.refused is True
    assert result.refusal_gate == 0


def test_numeric_traceability_tolerates_currency_percent_and_comma_formatting():
    results = [_make_result("Americas | $178,353 | (4)% | 111032", similarity=0.9)]
    # Same numbers, different formatting in the "answer" — should still be recognized as supported
    passes, unsupported = gate2_numeric_traceability("Revenue was 178353 and margin changed 4%.", results)
    assert passes is True
    assert unsupported == []


def test_numeric_traceability_flags_a_number_absent_from_every_chunk():
    results = [_make_result("Americas | 178353", similarity=0.9)]
    passes, unsupported = gate2_numeric_traceability("Revenue was 555555.", results)
    assert passes is False
    assert "555555" in unsupported


def test_numeric_traceability_does_not_flag_filing_form_name_digits():
    """Regression test for the bug found 2026-10-21 in the real eval run (N6):
    _NUMBER_RE was matching the leading digit of filing-form references like
    "10-K" and "10-Q" as a numeric claim ("10"), which then had no source chunk
    to match against (chunks don't restate "10-K" as a bare number) and tripped
    Gate 2 on an answer that was otherwise fully grounded."""
    results = [_make_result("NVIDIA's Annual Report on Form 10-K discloses segment revenue of 60922.", similarity=0.9)]
    passes, unsupported = gate2_numeric_traceability(
        "Per the 10-K, segment revenue was 60922.", results
    )
    assert passes is True
    assert unsupported == []


def test_numeric_traceability_does_not_flag_markdown_list_marker_digits():
    """Regression test for the bug found 2026-10-21 in the real eval run (N5):
    _NUMBER_RE was matching the leading digit of a markdown ordered-list marker
    ("1. ", "2. ") at the start of a line as a numeric claim, which then had no
    source chunk to match and tripped Gate 2 on an answer that was otherwise
    fully grounded."""
    results = [_make_result("Data Center | 115186\nGaming | 11351", similarity=0.9)]
    answer = "Risk factors include:\n1. Supply chain constraints\n2. Competition\n\nData Center revenue was 115186."
    passes, unsupported = gate2_numeric_traceability(answer, results)
    assert passes is True
    assert unsupported == []


def test_numeric_traceability_permits_unit_restatement_and_disclosed_arithmetic():
    """Regression test for the bug found 2026-10-21 in the real eval run
    (A1/M1/M4/A4): the system prompt explicitly permits the model to restate a
    sourced number in different units ("$416,161 million (or approximately
    $416.2 billion)") and to show arithmetic derived from two sourced numbers
    ("$33,696M - $28,703M = $4,993M (or roughly $5 billion)"). Gate 2 was
    flagging these legitimate restatements/derivations as unsupported
    fabrications because the derived figures never appear verbatim in any
    retrieved chunk."""
    results = [_make_result("Total net sales | 416161\nAmericas | 33696\nEurope | 28703", similarity=0.9)]

    passes, unsupported = gate2_numeric_traceability(
        "Total net sales were $416,161 million (or approximately $416.2 billion).",
        results,
    )
    assert passes is True
    assert unsupported == []

    passes, unsupported = gate2_numeric_traceability(
        "Americas exceeded Europe by $33,696M - $28,703M = $4,993M (or roughly $5 billion).",
        results,
    )
    assert passes is True
    assert unsupported == []


def test_numeric_traceability_does_not_flag_two_digit_filing_form_names():
    """Follow-up regression test for the bug found 2026-10-21, round 2 (same real eval
    re-run, confirmed on N6): the first fix for "10-K"/"10-Q" checked the dash-letter
    lookahead at the FIRST digit of the matched number, which only works for single-digit
    forms like "8-K". For a two-digit form the full match is "10" and the dash sits right
    after the LAST digit, so "10" kept slipping through as an unsupported number even after
    the first fix. The check now looks right after the whole matched number instead."""
    results = [_make_result("NVIDIA discusses export restrictions in its filing.", similarity=0.9)]
    passes, unsupported = gate2_numeric_traceability(
        "NVIDIA's 10-K discloses that U.S. export restrictions have already had a material effect.",
        results,
    )
    assert passes is True
    assert unsupported == []


def test_numeric_traceability_does_not_flag_fiscal_quarter_labels():
    """Regression test for the bug found 2026-10-21 (confirmed on N5): a fiscal-quarter
    label like "Q3" in "Q3 FY2023" had its bare digit parsed as a numeric claim, even
    though every list-marker digit ("1.", "2.", ...) in the same answer was already
    correctly excluded by the earlier list-marker fix. A quarter label isn't a data point
    and won't appear verbatim in a source chunk's own formatting."""
    results = [_make_result(
        "Export restrictions were announced in fiscal 2023 affecting certain chips, FY2023 FY2024",
        similarity=0.9,
    )]
    passes, unsupported = gate2_numeric_traceability(
        "Restrictions announced in Q3 FY2023 targeted certain chips, with further changes in Q2 FY2024.",
        results,
    )
    assert passes is True
    assert unsupported == []
