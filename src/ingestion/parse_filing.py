"""
Parse a downloaded SEC filing (10-K) into a single table-aware Markdown document.

Design note (see docs/TRADE_OFFS.md): the original project brief assumed we'd be
parsing PDFs with pymupdf4llm. In practice, SEC EDGAR serves 10-Ks natively as
HTML/iXBRL, not PDF. Converting HTML -> PDF -> Markdown would be a lossy detour
(re-rendering can reflow or drop table structure), so this module parses the
HTML directly:

  - Tables are extracted with pandas.read_html (which uses lxml/html5lib under
    the hood) and re-serialized as Markdown tables, preserving row/column
    relationships instead of letting them collapse into a wall of numbers.
  - Narrative text is extracted from the surrounding HTML in document order,
    with heading tags mapped to Markdown headings, so a downstream chunker can
    still reason about section structure.

For a filing that *is* a PDF (e.g. some older filings, or if we ever add
non-EDGAR sources), `parse_pdf` below uses pymupdf4llm, which is table-aware
for PDFs the same way this module is for HTML.

Usage:
    from src.ingestion.parse_filing import parse_filing
    markdown_text = parse_filing("data/raw/aapl-20250927.htm")
"""

from __future__ import annotations

import io
import re
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup, NavigableString, Tag

HEADING_TAGS = {"h1": "#", "h2": "##", "h3": "###", "h4": "####", "h5": "#####", "h6": "######"}

# SEC 10-Ks are essentially never marked up with real <h1>-<h6> tags for their
# section/note titles ("Item 7. Management's Discussion...", "Note 13 — Segment
# Information..."). Instead, a section title is a short block whose entire text
# is wrapped in one bold-styled <span> (font-weight 700+), inside an otherwise
# plain <div>/<p> — visually a heading, structurally indistinguishable from
# ordinary text without checking inline styles. Missing this means the chunker
# can never tag a chunk with its real section (see docs/SOLUTION_CRITIQUE.md
# Section 7.1 — verified against all three real filings, not just a fixture).
_BOLD_STYLE_RE = re.compile(r"font-weight\s*:\s*(?:7\d\d|8\d\d|900|bold)", re.IGNORECASE)
# Bug found 2026-10-18 (see docs/SOLUTION_CRITIQUE.md): Apple's 10-K renders at least one
# real sub-heading ("Department of Justice Lawsuit", inside Legal Proceedings) in italic,
# font-weight:400 — not bold. The bold-only check silently absorbed it as narrative text,
# so the DOJ lawsuit paragraph got tagged with whatever unrelated heading came earlier in
# the document ("Purchases of Equity Securities by the Issuer and Affiliated Purchasers"),
# which is a wrong citation shown to the user, not just a cosmetic label issue. Detecting
# italic-only blocks the same way as bold ones (same "~90% of the block" heuristic, so
# ordinary italicized phrases inside a longer paragraph still don't qualify) catches this.
_ITALIC_STYLE_RE = re.compile(r"font-style\s*:\s*italic", re.IGNORECASE)
_MAX_HEADING_LEN = 200


def _looks_like_heading(node: Tag) -> str | None:
    """Return the heading text if this block's entire content is (almost)
    just bold or italic styled text, short enough to plausibly be a title
    rather than a styled sentence within a longer paragraph. Returns None
    otherwise."""
    full_text = node.get_text(" ", strip=True)
    if not full_text or len(full_text) > _MAX_HEADING_LEN:
        return None
    styled_spans = [
        s
        for s in node.find_all("span")
        if s.get("style") and (_BOLD_STYLE_RE.search(s.get("style")) or _ITALIC_STYLE_RE.search(s.get("style")))
    ]
    if not styled_spans:
        return None
    styled_text = " ".join(s.get_text(" ", strip=True) for s in styled_spans).strip()
    if not styled_text:
        return None
    # The styled text should account for essentially the whole block, not just a
    # bolded/italicized word or two inside a longer sentence.
    if len(styled_text) >= 0.9 * len(full_text):
        return full_text
    return None


# SEC filings' HTML very often renders a single visual column as several real
# <td> cells — a currency symbol, the number, a spacing cell for "%" or ")" —
# rather than using proper colspan. pandas.read_html has no way to know those
# were meant to be one column, so it hands them back as separate, mostly-
# duplicate or symbol-only columns. Left alone, this triples the rendered
# table's width with no new information (see docs/TRADE_OFFS.md Section 5).
#
# The tricky part (found when validating against the real filings, not just
# the synthetic fixture): the split isn't uniform down a column. In a real
# Apple segment table, the "Americas" row repeats "Americas" three times
# across three cells, while the "Europe" row directly below it instead
# repeats the *number* "111032" across the same three cells — because the
# "$" only appears on the first data row of the column. So whole-column
# equality checks miss most of the real duplication: column N and column
# N+1 aren't identical across every row, only "compatible" on a row-by-row
# basis (equal, or one side is blank/decoration). We therefore coalesce
# left-to-right at the cell level, not the whole-column level.
_DECORATION_TOKENS = {"$", "%", "(", ")", "—", "-"}


def _as_float(s: str) -> float | None:
    """Try to read a cell as a number, tolerating thousands separators. Used so
    "2025" (int, from an object-dtype column) and "2025.0" (float, from a
    same-value column pandas inferred as float64) are recognized as the same
    logical value — pandas.read_html can give the two <td> copies of one split
    column different inferred dtypes even though a person reading the filing
    sees one number."""
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


def _cells_compatible(a, b) -> bool:
    """True if two cells in the same row could plausibly be the same logical
    column split across two <td>s: one/both blank, equal (as text or as a
    number), or one is a bare decoration token (currency sign, percent sign,
    bracket, dash)."""
    if pd.isna(a) or pd.isna(b):
        return True
    sa, sb = str(a).strip(), str(b).strip()
    if sa == sb:
        return True
    if sa in _DECORATION_TOKENS or sb in _DECORATION_TOKENS:
        return True
    fa, fb = _as_float(sa), _as_float(sb)
    if fa is not None and fb is not None and fa == fb:
        return True
    return False


def _merge_cell(a, b):
    """Merge two compatible cells into the single value they represent,
    preferring whichever side actually carries content over a blank or a
    bare decoration token, and preferring the plain-integer rendering over a
    "123.0"-style float rendering when both name the same number."""
    if pd.isna(a):
        return b
    if pd.isna(b):
        return a
    sa, sb = str(a).strip(), str(b).strip()
    if sa == sb:
        return a
    if sa in _DECORATION_TOKENS:
        return b
    if sb in _DECORATION_TOKENS:
        return a
    fa, fb = _as_float(sa), _as_float(sb)
    if fa is not None and fb is not None and fa == fb:
        return b if sa.endswith(".0") and not sb.endswith(".0") else a
    return a  # unreachable given _cells_compatible, but keep something sane


def _dedupe_and_clean_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Collapse the column-splitting artifacts described above:
    1. Coalesce a run of adjacent columns into one wherever every row's cells
       in that run are pairwise "compatible" (see `_cells_compatible`) — this
       is what happens when a single visual column gets expanded into several
       <td>s via repeated cells and/or a decoration cell.
    2. Drop any resulting column whose only non-null values are pure
       decoration tokens ("$", "%", parentheses, dashes) — these carry no
       information once they had a real neighbor to merge into (or never did).
    All of this runs on column *values*, not names, since pandas.read_html
    gives every column an uninformative positional name (0, 1, 2, ...)."""
    if df.shape[1] == 0:
        return df

    coalesced: list[pd.Series] = []
    acc = df[df.columns[0]]
    for col in df.columns[1:]:
        cur = df[col]
        if all(_cells_compatible(a, b) for a, b in zip(acc, cur)):
            acc = pd.Series([_merge_cell(a, b) for a, b in zip(acc, cur)], index=acc.index)
        else:
            coalesced.append(acc)
            acc = cur
    coalesced.append(acc)

    keep_cols: list[pd.Series] = []
    for values in coalesced:
        non_null = values.dropna()
        is_decoration_only = len(non_null) > 0 and set(non_null.astype(str).str.strip()) <= _DECORATION_TOKENS
        is_empty = len(non_null) == 0
        if is_decoration_only or is_empty:
            continue
        keep_cols.append(values)

    if not keep_cols:
        return df.iloc[:, :0]
    result = pd.concat(keep_cols, axis=1)
    result.columns = range(len(keep_cols))
    return result


_YEAR_RE = re.compile(r"^(19|20)\d{2}$")


def _is_bare_year(s: str) -> bool:
    return bool(_YEAR_RE.match(s.strip("()%$")))


def _row_has_real_data_signal(row_values) -> bool:
    """True if any cell (other than the row's own label in column 0, which the
    caller excludes before calling this) looks like an actual financial figure
    rather than header scaffolding — a number that isn't a bare 4-digit year
    (SEC tables routinely put literal years like "2025" in a header row) and
    isn't plain text like "Change" or "(In millions)"."""
    for v in row_values:
        if pd.isna(v):
            continue
        s = str(v).strip()
        f = _as_float(s)
        if f is None:
            continue  # non-numeric header scaffolding ("Change", "(In millions)", a date string)
        if _is_bare_year(s):
            continue  # a year label, not a data value
        return True
    return False


def _promote_header_rows(df: pd.DataFrame) -> pd.DataFrame:
    """SEC financial tables are almost never marked up with a real HTML <thead> —
    pandas.read_html hands back a plain RangeIndex (0, 1, 2, ...) for the column
    names, and what a human would read as the header (e.g. "2025 | Change | 2024")
    ends up as an ordinary first data row instead. Left alone, every such table
    renders with a meaningless "| 0 | 1 | 2 |" header line, which carries no
    signal for either a human skimming a citation or an embedding model trying
    to match a natural-language question to this table (see
    docs/SOLUTION_CRITIQUE.md Section 7.2).

    This walks down from the top, treating a row as (part of) the header for as
    long as it contains no real data signal (see `_row_has_real_data_signal`),
    and stops at the first row that does — that row and everything after it is
    the actual data. Collected header rows are merged column-wise into a single
    descriptive header string per column. If no header rows are found (the very
    first row already looks like data) or every row lacks a data signal (this
    doesn't look like the pattern this function targets), the table is returned
    unchanged rather than guessing."""
    if df.shape[0] < 2:
        return df

    header_row_positions: list[int] = []
    data_start = None
    for i in range(len(df)):
        row = df.iloc[i]
        rest = [row.iloc[j] for j in range(1, len(row))]
        if _row_has_real_data_signal(rest):
            data_start = i
            break
        header_row_positions.append(i)

    if data_start is None or data_start == 0:
        return df  # either no data rows found at all, or no header rows to promote

    header_rows = df.iloc[header_row_positions]
    new_headers = []
    for col in df.columns:
        parts = [str(v).strip() for v in header_rows[col] if not pd.isna(v) and str(v).strip()]
        # de-duplicate consecutive repeats (e.g. "Year Ended" appearing on its own row
        # above the date row) without losing genuinely different pieces of the label
        deduped = []
        for p in parts:
            if not deduped or deduped[-1] != p:
                deduped.append(p)
        new_headers.append(" ".join(deduped) if deduped else f"col{col}")

    result = df.iloc[data_start:].reset_index(drop=True)
    result.columns = new_headers
    return result


def _table_to_markdown(table_tag: Tag) -> str | None:
    """Convert a single <table> tag to a Markdown table string, or None if it can't be parsed
    (e.g. a layout-only table with no real tabular data — common in SEC HTML filings, which use
    tables for visual spacing as often as for actual data)."""
    try:
        dfs = pd.read_html(io.StringIO(str(table_tag)))
    except ValueError:
        return None
    if not dfs:
        return None
    df = dfs[0]
    # Drop fully-empty rows/columns, which are common in SEC filings' spacer tables
    df = df.dropna(axis=0, how="all").dropna(axis=1, how="all")
    if df.empty or df.shape[1] < 2:
        # A single-column "table" is almost always a layout table, not real data
        return None

    df = _dedupe_and_clean_columns(df)
    # Re-check after cleanup: a table that was only decoration/duplicate columns
    # (or is down to 1 real column) is layout noise, not data.
    if df.empty or df.shape[1] < 2:
        return None

    df = _promote_header_rows(df)

    try:
        return df.to_markdown(index=False)
    except ImportError:
        # to_markdown needs the `tabulate` package; fall back to a plain CSV-ish rendering
        return df.to_csv(index=False, sep="|")


def _read_filing_text(html_path: Path) -> str:
    """Real SEC filings are frequently saved as Windows-1252 (smart quotes, em
    dashes) despite the era's HTML `Content-Type` claiming otherwise, and
    they don't reliably declare an encoding pandas/BeautifulSoup would pick up
    automatically. Reading as strict UTF-8 first and falling back to cp1252
    avoids silently mangling every curly quote/em dash into a `�`
    replacement character — which happened throughout this project's real
    section headings and citations until this was caught (see
    docs/SOLUTION_CRITIQUE.md Section 7.1) — while still handling the (rarer)
    genuinely-UTF-8 filing correctly."""
    raw_bytes = html_path.read_bytes()
    try:
        return raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return raw_bytes.decode("cp1252", errors="replace")


def parse_html_filing(html_path: str | Path) -> str:
    """Parse a SEC EDGAR HTML/iXBRL 10-K into a single Markdown document, with every
    real data table converted to a Markdown table in its original document position."""
    html_path = Path(html_path)
    raw = _read_filing_text(html_path)
    soup = BeautifulSoup(raw, "lxml")

    # Strip script/style — pure noise for our purposes
    for tag in soup(["script", "style"]):
        tag.decompose()

    # Strip the inline-XBRL header block and anything hidden from human readers via
    # display:none — inline XBRL filings embed a machine-readable metadata block
    # (raw taxonomy tag names, CIK numbers, date-range contexts) that a browser never
    # renders, but a naive text walk has no way to know that and emits it as ordinary
    # narrative. Measured impact before this fix: ~4.7% of a real filing's parsed text
    # was this one block (see docs/SOLUTION_CRITIQUE.md Section 4 / TRADE_OFFS.md
    # Section 6) — pure noise sitting in the retrieval index for no reason, and a risk
    # to the groundedness thesis if it were ever retrieved as "evidence."
    for tag in soup.find_all("ix:header"):
        tag.decompose()
    for tag in soup.find_all(style=lambda s: s and "display:none" in s.replace(" ", "").lower()):
        tag.decompose()

    body = soup.body or soup
    lines: list[str] = []

    def walk(node) -> None:
        if isinstance(node, NavigableString):
            text = str(node).strip()
            if text:
                lines.append(text)
            return
        if not isinstance(node, Tag):
            return

        name = node.name.lower()

        if name == "table":
            md_table = _table_to_markdown(node)
            if md_table:
                lines.append("\n" + md_table + "\n")
            # Whether or not it parsed as data, don't recurse into a table's children —
            # walking into it as prose would duplicate every cell as a run-on paragraph.
            return

        if name in HEADING_TAGS:
            text = node.get_text(" ", strip=True)
            if text:
                lines.append(f"\n{HEADING_TAGS[name]} {text}\n")
            return

        if name in ("p", "div", "li"):
            # Only emit a paragraph if this node's *direct* text (not nested block
            # children, which we'll visit separately) has real content — avoids
            # emitting the same text twice for deeply nested SEC HTML.
            has_block_child = any(isinstance(c, Tag) and c.name.lower() in ("table", "div", "p", *HEADING_TAGS) for c in node.children)
            if not has_block_child:
                heading_text = _looks_like_heading(node)
                if heading_text:
                    lines.append(f"\n## {heading_text}\n")
                    return
                text = node.get_text(" ", strip=True)
                if text:
                    lines.append(text)
                return

        for child in node.children:
            walk(child)

    walk(body)

    text = "\n\n".join(lines)
    # Collapse SEC filings' characteristic excessive blank lines / non-breaking spaces
    text = text.replace("\xa0", " ")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_pdf_filing(pdf_path: str | Path) -> str:
    """Parse a PDF filing into table-aware Markdown using pymupdf4llm."""
    import pymupdf4llm

    return pymupdf4llm.to_markdown(str(pdf_path))


def parse_filing(path: str | Path) -> str:
    """Dispatch to the HTML or PDF parser based on file extension."""
    path = Path(path)
    if path.suffix.lower() == ".pdf":
        return parse_pdf_filing(path)
    if path.suffix.lower() in (".htm", ".html"):
        return parse_html_filing(path)
    raise ValueError(f"Unsupported filing format: {path.suffix} ({path})")


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 3:
        print("Usage: python parse_filing.py <input filing> <output .md path>")
        raise SystemExit(1)
    md = parse_filing(sys.argv[1])
    Path(sys.argv[2]).write_text(md, encoding="utf-8")
    print(f"Wrote {len(md):,} characters to {sys.argv[2]}")
