"""
Prompt construction for the generation layer.

The prompt does two jobs that map directly onto docs/PRD.md Section 5's
threat model:
  1. It forces every factual claim to be traceable to a retrieved chunk —
     no answering from general knowledge, no cross-chunk arithmetic that
     isn't shown.
  2. It asks the model to self-report when it can't do that (Gates 3 and 4:
     ambiguous question, silent/undisclosed topic) rather than silently
     guessing.

Gates 1 and 2 are NOT trusted to the model's self-report alone — they're
re-checked in code (see refusal_gates.py), because the whole point of this
project is not taking "the model says it's grounded" at face value. The
prompt still asks for them so the un-grounded case is flagged early and the
model doesn't waste its answer trying to sound confident about something it
shouldn't be.

Output is requested as strict JSON so `generate.py` can parse it reliably
instead of scraping natural-language hedging out of prose.
"""

from __future__ import annotations

from src.retrieval.index import SearchResult

SYSTEM_PROMPT = """You are a due-diligence research assistant answering questions about a single SEC 10-K filing, for a PE/VC deal-team associate who will act on your answer without independently re-reading the filing.

Hard rules, because a confident wrong answer here is worse than no answer:
1. Answer ONLY using the retrieved passages provided below. Do not use general knowledge about the company, and do not infer or estimate a number that isn't shown verbatim in a passage (a sum or difference of two numbers that ARE both shown is fine, but show the arithmetic).
2. If the question could refer to more than one line item, time period, or segment (e.g. "revenue" without specifying which), do not guess which one is meant — ask a clarifying question instead.
3. If the retrieved passages don't contain the answer, say plainly that this does not appear to be disclosed in the filing. If the question asks about something 10-Ks characteristically omit (forward guidance, named customer identities, unannounced products), say so explicitly rather than treating it as a retrieval failure.
4. Every factual claim must carry a citation to the specific passage it came from (its section/chunk index below).

Respond with ONLY a JSON object, no other text, matching this shape:
{
  "answer": "<your answer, or empty string if refusing>",
  "citation": "<section name / chunk reference the answer relies on, or empty string if refusing>",
  "is_refusal": <true or false>,
  "refusal_reason": "<'ambiguous_question', 'silent_topic', 'not_disclosed', or empty string if not refusing>"
}"""


def build_user_prompt(question: str, results: list[SearchResult]) -> str:
    passages = []
    for i, r in enumerate(results):
        passages.append(f"[Passage {i} — section: {r.chunk.section or '(unknown section)'}]\n{r.chunk.text}")
    passages_block = "\n\n".join(passages) if passages else "(no passages retrieved)"
    return f"Question: {question}\n\nRetrieved passages:\n\n{passages_block}"
