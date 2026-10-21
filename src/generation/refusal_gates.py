"""
Code-enforced refusal gates, per docs/PRD.md Section 5.

Deliberate split, worth stating explicitly (see docs/SOLUTION_CRITIQUE.md):
  - Gate 1 (retrieval confidence) and Gate 2 (numeric-claim traceability) are
    enforced HERE, in code, independent of what the LLM claims about itself.
    These are mechanically checkable — a similarity score is just a number,
    and "is this number present in the source text" is a string search — so
    there's no reason to trust the model's self-assessment when a cheap,
    reliable check exists. This is the actual groundedness mechanism, not
    the prompt's request for good behavior.
  - Gate 3 (ambiguous question) and Gate 4 (silent/omitted topic) require
    semantic judgment a regex can't do reliably (is "revenue" ambiguous in
    THIS question's context? does the filing's silence on X reflect a known
    omission category or a retrieval miss?) — these are prompt-engineered
    behaviors (see prompts.py) that the model self-reports, and their
    accuracy is exactly what eval/run_eval.py's Refusal Accuracy /
    False-Refusal Rate metrics (docs/EVALS_AND_BENCHMARKS.md) will measure
    once that harness exists. Gates 1 and 2 don't need that measurement
    because they're not probabilistic — they're just checked.
"""

from __future__ import annotations

import re

from src.retrieval.index import SearchResult

# PRD.md Section 5, Gate 1 — cosine similarity. Originally 0.70 as "a starting point... to
# sanity-check against the actual score distribution once the baseline run exists." That
# baseline now exists (eval/run_eval.py, docs/SOLUTION_CRITIQUE.md Section 10): on the real
# 30-question golden set, answerable questions scored 0.408-0.749 (median 0.625) and
# unanswerable ones scored 0.591-0.700 (median 0.631) — the two distributions overlap almost
# entirely, so no threshold cleanly separates them, but 0.70 specifically refused 19/24 (79%)
# of answerable questions before the LLM was ever consulted. Lowered to 0.60 (Nish's decision,
# 2026-09-20) to sit below the answerable median and cut false refusals, leaning more on Gate 4
# (the LLM's own self-report) to catch genuinely undisclosed topics instead of similarity alone.
RETRIEVAL_CONFIDENCE_THRESHOLD = 0.60


def gate1_retrieval_confidence(results: list[SearchResult], threshold: float = RETRIEVAL_CONFIDENCE_THRESHOLD) -> bool:
    """True if retrieval confidence is too low to attempt an answer at all —
    the LLM is never even called in this case (saves cost and removes any
    chance of it fabricating an answer from a weak or irrelevant match).

    Confidence is read as the BEST raw vector cosine similarity
    (SearchResult.vector_similarity) across the whole returned result set,
    not just results[0]. Bug found 2026-10-18 (see docs/SOLUTION_CRITIQUE.md):
    `results` is sorted by the RRF-fused `score`, which includes the
    table-chunk boost (src/retrieval/index.py) — so a table chunk can rank
    #1 by fused score while carrying mediocre cosine similarity, and a much
    more confident text match can sit lower in the same top-k. Checking only
    results[0] let that weak top-ranked chunk's similarity stand in for "the"
    confidence signal and wrongly refuse questions a stronger match in the
    same batch would have answered (confirmed against the real golden set:
    13/30 real-eval refusals were Gate 1 firing this way, e.g. question A4).
    Taking the max across the batch means a confident match anywhere in the
    retrieved set is enough to let the LLM see it, regardless of how the
    table boost re-ordered the list for presentation."""
    if not results:
        return True
    similarities = [r.vector_similarity for r in results if r.vector_similarity is not None]
    if not similarities:
        # No vector candidate at all for this query (e.g. it only matched via BM25) —
        # treat conservatively as low-confidence rather than assume it's fine.
        return True
    return max(similarities) < threshold


_NUMBER_RE = re.compile(r"-?\$?\(?\d[\d,]*(?:\.\d+)?\)?%?")

# Bug found 2026-10-21, against the real eval run with a real ANTHROPIC_API_KEY (see
# docs/SOLUTION_CRITIQUE.md): the first real baseline showed Gate 2 refusing CORRECT answers
# for reasons that have nothing to do with fabrication —
#   1. "10-K" gets parsed as the number "10" (the regex doesn't know "-K" means this is the
#      filing's own name, not data) — would misfire on essentially any answer that mentions
#      "the 10-K", which is most of them (confirmed on question N6).
#   2. A markdown numbered list ("1. **...**\n\n2. **...**") gets its list markers (1, 2, 3...)
#      parsed as numeric claims needing a source citation (confirmed on N5).
# Both are about recognizing a digit sequence is NOT a data claim at all, so they're handled
# by excluding specific surrounding contexts before a number is even considered.
#
# Follow-up bug found 2026-10-21, same re-run, round 2 (still present after the first fix above):
#   1a. The first fix checked the lookahead at match.start() (the FIRST digit of the matched
#       number), which only works for single-digit forms ("8-K"). For a two-digit form like
#       "10-K"/"10-Q" the full match is "10" and the character right after the LAST digit is
#       the "-", not the character right after the first digit — so the check silently never
#       fired for "10-K" and "10" kept slipping through (confirmed on N6, which still flagged
#       "10" as unsupported even after fix #1 above). Fixed by checking match.end() instead.
#   3. Fiscal-quarter labels like "Q3 FY2023" get their quarter digit (the "3" in "Q3") parsed
#      as a numeric claim too — it's a quarter label, not a data point, and won't appear
#      verbatim in a source chunk's own formatting (confirmed on N5: "3" from "Q3 FY2023" was
#      flagged even though every list-marker "1."-"6." was correctly excluded by fix #2).
_FILING_FORM_SUFFIX_RE = re.compile(r"-[A-Za-z]")  # checked right after the number: "...0-K", "...8-K"
_LIST_MARKER_RE = re.compile(r"(?m)^\s*\d+\.\s")  # "1. ", "2. " at the start of a line
# Quarter labels ("Q3", "q1") are checked with a direct character lookback, not a regex
# (see _extract_numbers) — a quarter is always a single bare digit, so no pattern is needed.


def _normalize_number(token: str) -> str | None:
    """Reduce a matched number-like token to a bare numeric string for
    comparison, stripping currency/percent/parenthesis/comma formatting.
    Returns None if it doesn't actually contain a digit worth checking (guards
    against degenerate matches)."""
    stripped = token.strip()
    is_paren_negative = stripped.startswith("(") and stripped.endswith(")")
    core = stripped.strip("()$%")
    core = core.replace(",", "")
    if not core or not any(ch.isdigit() for ch in core):
        return None
    if is_paren_negative and not core.startswith("-"):
        core = "-" + core
    return core


def _extract_numbers(text: str) -> set[str]:
    numbers = set()
    list_marker_spans = {(m.start(), m.end()) for m in _LIST_MARKER_RE.finditer(text)}
    for match in _NUMBER_RE.finditer(text):
        # Skip "10-K"/"10-Q"/"8-K" style filing-form references — the digits name the
        # document, they are not a data claim that needs a source citation. Checked right
        # AFTER the full matched number (not its first digit) so this fires for both
        # single-digit ("8-K") and multi-digit ("10-K", "10-Q") form names.
        if _FILING_FORM_SUFFIX_RE.match(text, match.end()):
            continue
        # Skip a fiscal-quarter label ("Q3", "q1") — checked right BEFORE the matched
        # number, and only for a single bare digit, since a quarter is always 1-4 and
        # never carries currency/percent/comma/decimal formatting of its own.
        if (
            match.start() > 0
            and text[match.start() - 1] in ("Q", "q")
            and match.group().isdigit()
            and len(match.group()) == 1
        ):
            continue
        # Skip a markdown ordered-list marker ("1. ", "2. ") at the start of a line —
        # it's formatting, not a number the answer is asserting as fact.
        if any(start <= match.start() < end for start, end in list_marker_spans):
            continue
        normalized = _normalize_number(match.group())
        if normalized is not None:
            numbers.add(normalized)
    return numbers


def _as_float(normalized: str) -> float | None:
    try:
        return float(normalized)
    except ValueError:
        return None


def _is_permitted_restatement(candidate: float, source_values: list[float]) -> bool:
    """True if `candidate` isn't literally in the source text but is still a
    harmless restatement of it, not a fabrication — a number the system
    prompt (prompts.py) explicitly permits.

    Bug found 2026-10-21, against the real eval run: SEC filings report
    figures in millions, and correct answers routinely restate a disclosed
    figure in billions for readability ("$416,161 million (or approximately
    $416.2 billion)") — mathematically the same fact, just divided by 1000
    and rounded, yet absent verbatim from the source text. Separately, the
    prompt explicitly allows showing "a sum or difference of two numbers that
    ARE both shown... with the arithmetic shown" (e.g. "$33,696M - $28,703M =
    a difference of approximately $4,993 million (or roughly $5 billion)",
    confirmed on question A4) — Gate 2 had no concept of permitted arithmetic
    at all, so it flagged the model for doing exactly what it was told it
    could do. This checks both: every disclosed value, every pairwise
    sum/difference of two disclosed values, and the thousand-scaled
    restatement of either, at a few plausible rounding precisions."""
    bases = set(source_values)
    for a in source_values:
        for b in source_values:
            if a is not b:
                bases.add(a + b)
                bases.add(abs(a - b))
    for base in bases:
        for scale in (1, 1000, 1 / 1000):
            scaled = base * scale
            for decimals in range(0, 4):
                if abs(round(scaled, decimals) - candidate) < 1e-6:
                    return True
    return False


def gate2_numeric_traceability(answer_text: str, results: list[SearchResult]) -> tuple[bool, list[str]]:
    """True (passes) if every number-like claim in the answer text appears,
    after normalization, somewhere in the retrieved chunks' text — or is a
    permitted restatement of one (see _is_permitted_restatement). Returns
    (passes, list_of_unsupported_numbers) so a caller can log/inspect exactly
    what triggered a refusal, rather than a bare boolean.

    This deliberately only checks presence (or permitted derivation), not
    that the number is being used in the *correct context* (e.g. a number
    that's genuinely in a chunk but for the wrong fiscal year would still
    pass this check) — that class of error is closer to Context Precision
    than Faithfulness and belongs to the eval harness's job of measuring
    retrieval quality, not this gate's job of catching outright fabrication."""
    answer_numbers = _extract_numbers(answer_text)
    if not answer_numbers:
        return True, []
    source_numbers: set[str] = set()
    for r in results:
        source_numbers |= _extract_numbers(r.chunk.text)
    unsupported = sorted(answer_numbers - source_numbers)
    if unsupported:
        source_values = [v for v in (_as_float(s) for s in source_numbers) if v is not None]
        still_unsupported = []
        for s in unsupported:
            v = _as_float(s)
            if v is not None and _is_permitted_restatement(v, source_values):
                continue
            still_unsupported.append(s)
        unsupported = still_unsupported
    return len(unsupported) == 0, unsupported
