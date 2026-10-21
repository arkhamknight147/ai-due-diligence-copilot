"""
Table-aware chunking for parsed filing Markdown (see parse_filing.py).

The core problem this solves (docs/PROBLEM_AND_SOLUTION.md, Archetype C): naive
fixed-size text chunking slices straight through Markdown tables, splitting a
table's header row from its data rows, or splitting one row's cells across two
chunks. Either way, the retriever ends up with fragments that have lost the
row/column relationship that gave the numbers meaning in the first place —
which is exactly the failure mode this project's threat model (PRD.md Section 5)
is designed against for numeric answers.

Strategy:
  1. Split the document into "blocks": each Markdown table is its own block;
     everything else is narrative text, further split by heading boundaries.
  2. A table block is never split internally — it becomes exactly one chunk
     (unless it's pathologically large, in which case it's split by whole rows,
     never mid-row, keeping the header row duplicated into each piece so every
     chunk is independently interpretable).
  3. Narrative blocks are split by paragraph, accumulated up to `max_chars`,
     with a small overlap so a fact split across two paragraph-chunks doesn't
     disappear from both.

Each chunk carries lightweight metadata (chunk type, and the nearest preceding
heading, as a crude "section" tag) so retrieval results can cite *where* an
answer came from, per PRD.md Section 4 ("inline citation on every claim").
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

MAX_CHARS = 1500
OVERLAP_CHARS = 200
MAX_TABLE_ROWS_PER_CHUNK = 40  # only kicks in for pathologically large tables

_TABLE_BLOCK_RE = re.compile(r"(\n\|.+\|\n\|[-:| ]+\|\n(?:\|.*\|\n?)*)", re.MULTILINE)
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)


@dataclass
class Chunk:
    text: str
    chunk_type: str  # "table" | "text"
    section: str = "(unknown section)"
    index: int = 0
    metadata: dict = field(default_factory=dict)


def _split_table_if_huge(table_md: str) -> list[str]:
    lines = [l for l in table_md.strip().split("\n") if l.strip()]
    if len(lines) <= 2:
        return [table_md]
    header, separator, *rows = lines
    if len(rows) <= MAX_TABLE_ROWS_PER_CHUNK:
        return [table_md]
    pieces = []
    for i in range(0, len(rows), MAX_TABLE_ROWS_PER_CHUNK):
        row_slice = rows[i : i + MAX_TABLE_ROWS_PER_CHUNK]
        pieces.append("\n".join([header, separator, *row_slice]))
    return pieces


# Bug found 2026-10-18 (see docs/SOLUTION_CRITIQUE.md): the previous version of this
# module computed ONE section tag per inter-table block, from the single heading
# nearest the END of that block (right before the next table) — not from the heading
# actually governing each paragraph inside it. A block of narrative text between two
# tables commonly spans several real headings (e.g. Apple's "Item 3. Legal
# Proceedings" block contains four sub-sections before the next table appears), so
# every paragraph in that span — including ones under a completely different,
# unrelated heading — got mislabeled with whichever heading happened to sit just
# before the next table. Confirmed on the real Apple filing: the "Department of
# Justice Lawsuit" paragraph was tagged "Purchases of Equity Securities by the Issuer
# and Affiliated Purchasers" (a heading from much later in the document) — a wrong
# citation shown to the user, not just a missing one. Fixed by tracking the running
# section heading-by-heading as the text is split into paragraphs, instead of looking
# only at the text just before the next table.


def _iter_sectioned_paragraphs(text: str, section: str):
    """Yield (section, paragraph) pairs from narrative text. `section` is the
    section in effect on entry and is updated in place (via the generator's
    running local) whenever a Markdown heading line — one that IS a whole
    paragraph by itself, not just mentioned inside one — is encountered.
    Heading paragraphs themselves are not emitted as chunks; they only update
    the section used to tag the paragraphs that follow. The final `section`
    value in effect is returned to the caller so it can be carried into the
    next block (e.g. the table immediately following this narrative span)."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    for para in paragraphs:
        m = _HEADING_RE.match(para)
        if m and m.group(0).strip() == para:
            section = m.group(2).strip()
            continue
        yield section, para
    return section


def _split_narrative(pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Group (section, paragraph) pairs into <= MAX_CHARS chunks on paragraph
    boundaries, with a small trailing overlap carried into the next chunk —
    but never merging paragraphs from two different sections into one chunk,
    so a chunk's section tag always actually describes its own text."""
    out: list[tuple[str, str]] = []
    current_section: str | None = None
    current = ""
    for section, para in pairs:
        if current and (section != current_section or len(current) + len(para) + 1 > MAX_CHARS):
            out.append((current_section, current.strip()))
            if section == current_section:
                # carry a small overlap forward so a sentence split across the
                # boundary isn't lost from both sides
                current = current[-OVERLAP_CHARS:] + "\n\n" + para
            else:
                current = para
        else:
            current = (current + "\n\n" + para).strip() if current else para
        current_section = section
    if current.strip():
        out.append((current_section, current.strip()))
    return out


def chunk_markdown(markdown_text: str, source: str = "") -> list[Chunk]:
    """Split a parsed filing's Markdown into table-aware chunks."""
    chunks: list[Chunk] = []
    pos = 0
    idx = 0
    running_section = "(unknown section)"

    for match in _TABLE_BLOCK_RE.finditer(markdown_text):
        before = markdown_text[pos : match.start()]
        table_md = match.group(1)

        pairs = list(_iter_sectioned_paragraphs(before, running_section))

        # Narrative text before this table
        for section, para in _split_narrative(pairs):
            chunks.append(Chunk(text=para, chunk_type="text", section=section, index=idx, metadata={"source": source}))
            idx += 1

        # The section in effect at the end of this narrative span carries into
        # the table that follows it (a heading can precede a table directly,
        # with no narrative paragraph in between).
        if pairs:
            running_section = pairs[-1][0]

        for piece in _split_table_if_huge(table_md):
            chunks.append(Chunk(text=piece.strip(), chunk_type="table", section=running_section, index=idx, metadata={"source": source}))
            idx += 1

        pos = match.end()

    # Trailing narrative after the last table
    tail = markdown_text[pos:]
    pairs = list(_iter_sectioned_paragraphs(tail, running_section))
    for section, para in _split_narrative(pairs):
        chunks.append(Chunk(text=para, chunk_type="text", section=section, index=idx, metadata={"source": source}))
        idx += 1

    return chunks


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("Usage: python chunk.py <parsed markdown file>")
        raise SystemExit(1)
    md = open(sys.argv[1], encoding="utf-8").read()
    result = chunk_markdown(md, source=sys.argv[1])
    tables = sum(1 for c in result if c.chunk_type == "table")
    print(f"{len(result)} chunks ({tables} table chunks, {len(result) - tables} text chunks)")
