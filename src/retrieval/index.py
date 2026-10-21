"""
Hybrid retrieval: BM25 keyword search + vector similarity search over ChromaDB,
merged with Reciprocal Rank Fusion (RRF).

Why hybrid (see docs/PRD.md Section 4): pure embedding similarity is known to
underperform on exact numeric and defined-term lookups — "what was Greater
China segment revenue" is a keyword-friendly, almost-exact-match query, and
BM25 is very good at exactly that, while vector search alone can drift toward
semantically-similar-but-wrong chunks (e.g. a different fiscal year's segment
table). RRF is used to combine the two rankings because it needs no score
normalization between BM25 and cosine similarity, which live on different,
incomparable scales.

This module works on the `Chunk` objects produced by src/ingestion/chunk.py.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import chromadb
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer

from src.ingestion.chunk import Chunk

EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"  # free, local, no API key — fits the project's free-stack constraint
RRF_K = 60  # standard RRF damping constant

# Real, well-known SEC 10-K sections whose tables are pure legal boilerplate (an exhibit
# index, signature blocks) and essentially never contain financial figures relevant to a
# due-diligence question. Found by testing the table_boost below against the real golden
# set: it occasionally promoted an Exhibit Listing table for a query that happened to share
# incidental vocabulary, displacing more relevant narrative text (see
# docs/SOLUTION_CRITIQUE.md Section 11) — excluded here rather than left as a silent
# false-positive source.
_BOILERPLATE_TABLE_SECTION_TERMS = ("exhibit", "signature")


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


@dataclass
class SearchResult:
    chunk: Chunk
    score: float  # RRF-fused rank score — use for ordering results, not for the Gate 1 confidence check
    bm25_rank: int | None
    vector_rank: int | None
    vector_similarity: float | None  # raw cosine similarity (0-1) from the vector half alone, or None if this
    # candidate wasn't in the vector ranking. This is what PRD.md Section 5 Gate 1 actually means by
    # "0.70 cosine similarity" — the RRF `score` above lives on a different, incomparable scale (see
    # docs/TRADE_OFFS.md Section 3) and was never meant to be read as a confidence value.


class HybridIndex:
    """Builds and queries a hybrid BM25 + vector index over a list of Chunks."""

    def __init__(self, collection_name: str = "filings", persist_dir: str = "data/processed/chroma"):
        self.chunks: list[Chunk] = []
        self._bm25: BM25Okapi | None = None
        self._embedder = SentenceTransformer(EMBEDDING_MODEL_NAME)
        self._client = chromadb.PersistentClient(path=persist_dir)
        # Fresh collection each time we (re)build — this is a batch ingestion
        # pipeline, not an incrementally-updated production index
        try:
            self._client.delete_collection(collection_name)
        except Exception:
            pass
        # Explicit cosine space: Chroma's un-configured default is squared L2, not cosine.
        # PRD.md Section 5 Gate 1 is specified in cosine similarity, so the collection must
        # actually use that metric or the "0.70" threshold would be checked against the wrong scale.
        self._collection = self._client.create_collection(collection_name, metadata={"hnsw:space": "cosine"})

    def build(self, chunks: list[Chunk]) -> None:
        self.chunks = chunks
        self._bm25 = BM25Okapi([_tokenize(c.text) for c in chunks])

        texts = [c.text for c in chunks]
        embeddings = self._embedder.encode(texts, show_progress_bar=False, batch_size=32).tolist()
        ids = [f"chunk_{c.index}_{i}" for i, c in enumerate(chunks)]
        metadatas = [{"chunk_type": c.chunk_type, "section": c.section, "source": c.metadata.get("source", "")} for c in chunks]

        # Chroma has a per-call batch limit on some backends; chunk the add() calls defensively
        BATCH = 500
        for i in range(0, len(chunks), BATCH):
            self._collection.add(
                ids=ids[i : i + BATCH],
                embeddings=embeddings[i : i + BATCH],
                documents=texts[i : i + BATCH],
                metadatas=metadatas[i : i + BATCH],
            )

    def search(self, query: str, k: int = 5, candidate_pool: int = 20, table_boost: float = 1.0 / RRF_K) -> list[SearchResult]:
        if self._bm25 is None or not self.chunks:
            raise RuntimeError("Index not built yet — call .build(chunks) first")

        # BM25 ranking
        bm25_scores = self._bm25.get_scores(_tokenize(query))
        bm25_ranked = sorted(range(len(self.chunks)), key=lambda i: bm25_scores[i], reverse=True)[:candidate_pool]
        bm25_rank_of = {idx: rank for rank, idx in enumerate(bm25_ranked)}

        # Vector ranking (Chroma)
        query_embedding = self._embedder.encode([query]).tolist()
        vec_result = self._collection.query(
            query_embeddings=query_embedding,
            n_results=min(candidate_pool, len(self.chunks)),
            include=["distances"],
        )
        vec_ids = vec_result["ids"][0]
        vec_distances = vec_result["distances"][0]
        vector_rank_of = {}
        vector_similarity_of = {}
        for rank, (chunk_id, distance) in enumerate(zip(vec_ids, vec_distances)):
            idx = int(chunk_id.split("_")[1])
            vector_rank_of[idx] = rank
            # With hnsw:space="cosine", Chroma's "distance" is cosine distance (1 - cosine similarity)
            vector_similarity_of[idx] = 1.0 - distance

        # Reciprocal Rank Fusion over the union of both candidate sets
        all_candidates = set(bm25_rank_of) | set(vector_rank_of)
        fused: list[SearchResult] = []
        for idx in all_candidates:
            score = 0.0
            if idx in bm25_rank_of:
                score += 1.0 / (RRF_K + bm25_rank_of[idx])
            if idx in vector_rank_of:
                score += 1.0 / (RRF_K + vector_rank_of[idx])
            chunk = self.chunks[idx]
            is_boilerplate_table = chunk.chunk_type == "table" and any(
                term in (chunk.section or "").lower() for term in _BOILERPLATE_TABLE_SECTION_TERMS
            )
            if chunk.chunk_type == "table" and not is_boilerplate_table:
                # Real 10-K tables have almost no natural-language surface area for a
                # dense embedding model to match against a natural-language question —
                # even the exact right table often scores lower than a narrative
                # paragraph that merely discusses the same topic without the actual
                # figure (see docs/SOLUTION_CRITIQUE.md Section 9). Since this project's
                # core thesis is "financial answers should come from tables, not
                # narrative," a small deliberate tie-breaking preference for tables is
                # a defensible design choice, not just a tuning hack — one extra RRF
                # rank position's worth of score is enough to lift genuinely-relevant
                # tables into the returned set without letting an irrelevant table
                # crowd out a clearly better narrative match (verified: 5/15 -> 10/15
                # numeric golden questions have supporting evidence in the top 5 with
                # this boost, at the same k, measured against the real filings).
                score += table_boost
            fused.append(
                SearchResult(
                    chunk=chunk,
                    score=score,
                    bm25_rank=bm25_rank_of.get(idx),
                    vector_rank=vector_rank_of.get(idx),
                    vector_similarity=vector_similarity_of.get(idx),
                )
            )

        fused.sort(key=lambda r: r.score, reverse=True)
        return fused[:k]


if __name__ == "__main__":
    import sys

    from src.ingestion.chunk import chunk_markdown

    if len(sys.argv) != 3:
        print("Usage: python -m src.retrieval.index <parsed markdown file> <query>")
        raise SystemExit(1)
    md = open(sys.argv[1], encoding="utf-8").read()
    chunks = chunk_markdown(md, source=sys.argv[1])
    index = HybridIndex()
    index.build(chunks)
    for r in index.search(sys.argv[2]):
        print(f"[{r.score:.4f}] ({r.chunk.chunk_type}, {r.chunk.section})\n{r.chunk.text[:300]}\n---")
