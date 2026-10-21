"""
Streamlit demo for the AI Due Diligence Copilot.

Run locally with your own ANTHROPIC_API_KEY set (see .env.example):
    streamlit run app.py

Without a key, the app still works in "retrieval-only" mode: it shows exactly
what would be sent to the LLM (retrieved passages, Gate 1's confidence check)
without actually calling out — useful for demonstrating the groundedness
pipeline's mechanics even if you don't want to spend API credits, and for
running this in an environment (like the one this was built in) where the
key isn't available.
"""

from __future__ import annotations

import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from src.generation.generate import answer_question
from src.generation.llm_client import AnthropicClient
from src.generation.refusal_gates import RETRIEVAL_CONFIDENCE_THRESHOLD, gate1_retrieval_confidence
from src.ingestion.chunk import chunk_markdown
from src.retrieval.index import HybridIndex

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parent

COMPANY_FILES = {
    "Apple (FY2025 10-K)": REPO_ROOT / "data" / "processed" / "aapl-20250927.md",
    "Microsoft (FY2025 10-K)": REPO_ROOT / "data" / "processed" / "msft-20250630.md",
    "NVIDIA (FY2025 10-K)": REPO_ROOT / "data" / "processed" / "nvda-20250126.md",
}

EXAMPLE_QUESTIONS = [
    "What were Apple's total net sales for fiscal year 2025?",
    "What was Apple's net sales in the Americas segment for fiscal year 2025?",
    "What revenue guidance does Microsoft provide for fiscal year 2026 in this filing?",
    "What was NVIDIA's Data Center revenue for FY2025, per the Revenue by End Market note?",
    "What was Microsoft's revenue?",  # deliberately ambiguous — should ask for clarification
]


@st.cache_resource(show_spinner="Building index from the parsed filing (first load only)...")
def get_index(company: str) -> HybridIndex:
    path = COMPANY_FILES[company]
    if not path.exists():
        raise FileNotFoundError(
            f"Missing parsed filing: {path}. Run `python src/ingestion/parse_filing.py data/raw/<file>.htm "
            f"data/processed/<file>.md` first (see docs/PRD.md Section 3 for the frozen filing scope)."
        )
    md = path.read_text(encoding="utf-8")
    chunks = chunk_markdown(md, source=path.name)
    index = HybridIndex(persist_dir=str(REPO_ROOT / "data" / "processed" / f"chroma_{company[:4].lower()}"))
    index.build(chunks)
    return index


def main() -> None:
    st.set_page_config(page_title="AI Due Diligence Copilot", page_icon="📄", layout="wide")
    st.title("AI Due Diligence Copilot")
    st.caption(
        "A grounded RAG assistant over frozen SEC 10-K filings (Apple, Microsoft, NVIDIA — FY2025), "
        "built to demonstrate table-aware retrieval and an explicit refusal policy, not to be used for "
        "actual investment decisions. See docs/PRD.md for the full threat model."
    )

    has_api_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    if not has_api_key:
        st.warning(
            "No ANTHROPIC_API_KEY found (copy .env.example to .env and fill it in). "
            "Running in **retrieval-only mode**: you'll see exactly what would be sent to the model "
            "and whether Gate 1 would refuse before any LLM call, but no generated answer.",
            icon="⚠️",
        )

    with st.sidebar:
        st.subheader("Threat model — refusal gates")
        st.markdown(
            f"""
This system is designed to refuse rather than fabricate. Four gates (`docs/PRD.md` Section 5):

1. **Retrieval confidence** — refuses if top-match cosine similarity < **{RETRIEVAL_CONFIDENCE_THRESHOLD:.2f}**
   (revised from an initial 0.70 after measuring the real score distribution — see `docs/SOLUTION_CRITIQUE.md` Section 10)
2. **Numeric-claim traceability** — every number in an answer must appear in a retrieved passage (code-enforced, not just prompted)
3. **Ambiguous question** — asks for clarification instead of guessing which line item is meant
4. **Silent topic** — explicitly names known 10-K omissions (guidance, named customers) rather than treating them as a miss
            """
        )
        st.subheader("Known limitations")
        st.markdown(
            "- Retrieval ranking for numeric questions is measurably improved but not fully solved — "
            "see `docs/SOLUTION_CRITIQUE.md` Section 9/11.\n"
            "- Faithfulness / Context Precision / Answer Relevance need an LLM-judge run "
            "(`eval/run_eval.py`), not yet done with a real model — see `docs/EVALS_AND_BENCHMARKS.md`."
        )

    company = st.selectbox("Filing", list(COMPANY_FILES.keys()))
    question = st.selectbox("Try an example question, or write your own below", ["(write your own)"] + EXAMPLE_QUESTIONS)
    if question == "(write your own)":
        question = st.text_input("Question", placeholder="e.g. What was Apple's total net sales for fiscal year 2025?")

    if st.button("Ask", type="primary", disabled=not question):
        index = get_index(company)

        with st.spinner("Retrieving..."):
            results = index.search(question, k=5)

        low_confidence = gate1_retrieval_confidence(results)
        top_sim = results[0].vector_similarity if results and results[0].vector_similarity is not None else None

        col1, col2 = st.columns([2, 1])
        with col2:
            st.metric("Top match confidence", f"{top_sim:.2f}" if top_sim is not None else "n/a")
            st.caption(f"Gate 1 threshold: {RETRIEVAL_CONFIDENCE_THRESHOLD:.2f}")

        with col1:
            if low_confidence:
                st.error(
                    "**Gate 1 fired — refused before calling the model.** "
                    "This information does not appear to be disclosed in this filing with sufficient confidence.",
                    icon="🚫",
                )
            elif has_api_key:
                with st.spinner("Generating..."):
                    result = answer_question(question, index, AnthropicClient(), k=5)
                if result.refused:
                    st.error(f"**Refused (Gate {result.refusal_gate}):** {result.refusal_reason}", icon="🚫")
                else:
                    st.success(result.answer)
                    st.caption(f"Citation: {result.citation}")
            else:
                st.info(
                    "Gate 1 passed (confidence above threshold) — a real run would call the LLM here. "
                    "Add ANTHROPIC_API_KEY to see the generated, cited answer.",
                    icon="ℹ️",
                )

        with st.expander(f"Retrieved passages ({len(results)})", expanded=False):
            for i, r in enumerate(results):
                st.markdown(f"**[{i}] {r.chunk.chunk_type} — {r.chunk.section}** (cosine similarity: {r.vector_similarity:.3f})" if r.vector_similarity is not None else f"**[{i}] {r.chunk.chunk_type} — {r.chunk.section}**")
                st.text(r.chunk.text[:500])


if __name__ == "__main__":
    main()
