"""
Orchestrates one question through: retrieve -> Gate 1 -> LLM -> parse ->
Gate 2 -> final answer. This is the module that turns the threat model in
docs/PRD.md Section 5 into an actual code path, not just a design table.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from src.generation.llm_client import LLMClient
from src.generation.prompts import SYSTEM_PROMPT, build_user_prompt
from src.generation.refusal_gates import RETRIEVAL_CONFIDENCE_THRESHOLD, gate1_retrieval_confidence, gate2_numeric_traceability
from src.retrieval.index import HybridIndex, SearchResult


@dataclass
class AnswerResult:
    question: str
    answer: str
    citation: str
    refused: bool
    refusal_gate: int | None  # 1-4, or None if not refused
    refusal_reason: str
    results_used: list[SearchResult] = field(default_factory=list)
    raw_llm_response: str = ""


def _refusal(question: str, gate: int, reason: str, results: list[SearchResult], raw: str = "") -> AnswerResult:
    return AnswerResult(
        question=question,
        answer="",
        citation="",
        refused=True,
        refusal_gate=gate,
        refusal_reason=reason,
        results_used=results,
        raw_llm_response=raw,
    )


def _parse_llm_json(raw: str) -> dict:
    """The prompt asks for strict JSON, but models sometimes wrap it in
    prose or a code fence anyway — extract the first {...} block defensively
    rather than trusting response formatting to always be exactly right,
    which would be its own small groundedness gap."""
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"No JSON object found in LLM response: {raw!r}")
    return json.loads(raw[start : end + 1])


def answer_question(
    question: str,
    index: HybridIndex,
    llm: LLMClient,
    k: int = 5,
    confidence_threshold: float = RETRIEVAL_CONFIDENCE_THRESHOLD,
) -> AnswerResult:
    results = index.search(question, k=k)

    # Gate 1: retrieval confidence — checked BEFORE calling the LLM at all.
    if gate1_retrieval_confidence(results, threshold=confidence_threshold):
        return _refusal(
            question,
            gate=1,
            reason="This information does not appear to be disclosed in this filing (no sufficiently confident match retrieved).",
            results=results,
        )

    system = SYSTEM_PROMPT
    user = build_user_prompt(question, results)
    raw = llm.complete(system, user)

    try:
        parsed = _parse_llm_json(raw)
    except (ValueError, json.JSONDecodeError) as exc:
        # A malformed response is itself a groundedness failure worth surfacing as a
        # refusal rather than crashing the caller or silently returning nothing.
        return _refusal(question, gate=0, reason=f"Could not parse a well-formed answer from the model: {exc}", results=results, raw=raw)

    if parsed.get("is_refusal"):
        reason = parsed.get("refusal_reason") or "unspecified"
        gate = 3 if reason == "ambiguous_question" else 4
        return _refusal(question, gate=gate, reason=reason, results=results, raw=raw)

    answer_text = parsed.get("answer", "")
    citation = parsed.get("citation", "")

    # Gate 2: numeric-claim traceability — re-checked in code regardless of what
    # the model believes about its own answer (see refusal_gates.py docstring).
    passes, unsupported = gate2_numeric_traceability(answer_text, results)
    if not passes:
        return _refusal(
            question,
            gate=2,
            reason=f"Answer contained number(s) not found in any retrieved passage: {', '.join(unsupported)}",
            results=results,
            raw=raw,
        )

    return AnswerResult(
        question=question,
        answer=answer_text,
        citation=citation,
        refused=False,
        refusal_gate=None,
        refusal_reason="",
        results_used=results,
        raw_llm_response=raw,
    )


if __name__ == "__main__":
    import sys

    from src.generation.llm_client import AnthropicClient
    from src.ingestion.chunk import chunk_markdown

    if len(sys.argv) != 3:
        print("Usage: python -m src.generation.generate <parsed markdown file> <question>")
        raise SystemExit(1)

    md = open(sys.argv[1], encoding="utf-8").read()
    chunks = chunk_markdown(md, source=sys.argv[1])
    idx = HybridIndex()
    idx.build(chunks)
    result = answer_question(sys.argv[2], idx, AnthropicClient())

    if result.refused:
        print(f"REFUSED (gate {result.refusal_gate}): {result.refusal_reason}")
    else:
        print(f"ANSWER: {result.answer}\nCITATION: {result.citation}")
