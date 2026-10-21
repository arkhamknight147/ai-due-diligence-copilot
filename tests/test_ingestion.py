"""Unit tests for the table-aware ingestion pipeline (parse_filing.py + chunk.py).

These run against a small synthetic fixture (tests/fixtures/sample_filing.html),
not a real 10-K, because the real filings couldn't be downloaded into this
environment (see docs/TRADE_OFFS.md - network egress note). The fixture is
deliberately shaped like a real filing's trouble spots: a real data table, a
layout-only single-column table (common padding pattern in SEC HTML), and a
heading structure the chunker should use for section tagging.
"""

from pathlib import Path

import pytest

from src.ingestion.chunk import chunk_markdown
from src.ingestion.parse_filing import parse_html_filing

FIXTURE = Path(__file__).parent / "fixtures" / "sample_filing.html"


@pytest.fixture(scope="module")
def parsed_markdown():
    return parse_html_filing(FIXTURE)


def test_parse_extracts_real_table_as_markdown(parsed_markdown):
    assert "Americas" in parsed_markdown
    assert "178353" in parsed_markdown
    # A real Markdown table has a header-separator row
    assert "---" in parsed_markdown


def test_parse_drops_layout_only_table(parsed_markdown):
    # The fixture has two <table> tags: one real data table, one single-empty-cell
    # layout table. Only the real one should survive as a Markdown table chunk.
    chunks = chunk_markdown(parsed_markdown, source="sample_filing.html")
    table_chunks = [c for c in chunks if c.chunk_type == "table"]
    assert len(table_chunks) == 1


def test_parse_preserves_heading_structure(parsed_markdown):
    assert "Segment Information" in parsed_markdown
    assert "Legal Proceedings" in parsed_markdown


def test_chunker_keeps_table_intact_as_single_chunk(parsed_markdown):
    chunks = chunk_markdown(parsed_markdown, source="sample_filing.html")
    table_chunks = [c for c in chunks if c.chunk_type == "table"]
    assert len(table_chunks) == 1, "the real segment table should produce exactly one table chunk"
    table_text = table_chunks[0].text
    # All three rows must be in the SAME chunk — this is the whole point of
    # table-aware chunking (PROBLEM_AND_SOLUTION.md Archetype C)
    assert "Americas" in table_text
    assert "Europe" in table_text
    assert "Greater China" in table_text


def test_chunker_tags_table_with_nearest_section(parsed_markdown):
    chunks = chunk_markdown(parsed_markdown, source="sample_filing.html")
    table_chunk = next(c for c in chunks if c.chunk_type == "table")
    assert table_chunk.section == "Segment Information"


def test_chunker_produces_text_chunks_for_narrative(parsed_markdown):
    chunks = chunk_markdown(parsed_markdown, source="sample_filing.html")
    text_chunks = [c for c in chunks if c.chunk_type == "text"]
    assert any("widgets" in c.text for c in text_chunks)
    assert any("legal proceedings" in c.text.lower() for c in text_chunks)


def test_chunker_tags_each_paragraph_with_its_own_nearest_heading_not_the_blocks_last_one():
    # Regression test for the bug found 2026-10-18 (see docs/SOLUTION_CRITIQUE.md):
    # a block of narrative text between two tables can span several real headings.
    # Every paragraph in that span must be tagged with the heading actually governing
    # it, not with whichever heading happens to sit right before the next table.
    md = """
## Legal Proceedings

The Company is involved in various legal proceedings.

## Department of Justice Lawsuit

On March 21, 2024, the DOJ filed a civil antitrust lawsuit against the Company.

## Purchases of Equity Securities by the Issuer and Affiliated Purchasers

The following table sets out monthly share repurchases.

| Month | Shares |
| --- | --- |
| July | 100 |
"""
    chunks = chunk_markdown(md, source="sample.md")
    doj_chunk = next(c for c in chunks if "DOJ" in c.text)
    assert doj_chunk.section == "Department of Justice Lawsuit"
    table_chunk = next(c for c in chunks if c.chunk_type == "table")
    assert table_chunk.section == "Purchases of Equity Securities by the Issuer and Affiliated Purchasers"


def test_table_dedup_collapses_colspan_style_duplicate_and_decoration_columns(tmp_path):
    # Simulates the real-world SEC pattern: each visual column rendered as three
    # <td> cells (label x3, or "$" + number + spacer) instead of one.
    html = """
    <html><body>
    <table>
      <tr><td>Americas</td><td>Americas</td><td>Americas</td><td>$</td><td>178353</td><td></td></tr>
      <tr><td>Europe</td><td>Europe</td><td>Europe</td><td>$</td><td>111032</td><td></td></tr>
    </table>
    </body></html>
    """
    p = tmp_path / "dup.html"
    p.write_text(html, encoding="utf-8")
    md = parse_html_filing(p)
    assert "178353" in md
    assert "Americas" in md
    # The whole point of the fix: no column should appear three times in a row
    assert "Americas | Americas" not in md
    assert md.count("Americas") == 1
    # A lone "$" should not survive as its own column
    header_and_rows = [line for line in md.splitlines() if line.strip().startswith("|")]
    for line in header_and_rows:
        cells = [c.strip() for c in line.strip("|").split("|")]
        assert cells.count("$") == 0


def test_table_dedup_merges_across_int_vs_float_string_mismatch(tmp_path):
    # Real-world edge case found when validating against the actual Apple 10-K:
    # pandas.read_html can infer one split-column copy as int-like ("2025")
    # and the other as float-like ("2025.0") even though they're the same
    # value, which a naive string-equality dedup would treat as a mismatch
    # and fail to merge — leaving a stray "$" column behind in the header row.
    html = """
    <html><body>
    <table>
      <tr><td></td><td>2025</td><td>2025.0</td></tr>
      <tr><td>Americas</td><td>$</td><td>178353</td></tr>
      <tr><td>Europe</td><td>111032</td><td>111032</td></tr>
    </table>
    </body></html>
    """
    p = tmp_path / "mismatch.html"
    p.write_text(html, encoding="utf-8")
    md = parse_html_filing(p)
    assert "178353" in md
    header_and_rows = [line for line in md.splitlines() if line.strip().startswith("|")]
    for line in header_and_rows:
        cells = [c.strip() for c in line.strip("|").split("|")]
        assert cells.count("$") == 0
        assert cells.count("2025") <= 1


def test_bold_span_div_is_detected_as_a_heading(tmp_path):
    # Real SEC filings mark section titles with a bold <span> inside a plain
    # <div>, not a semantic <h1>-<h6> tag (see docs/SOLUTION_CRITIQUE.md 7.1).
    html = """
    <html><body>
    <div style="margin-top:18pt"><span style="font-weight:700">Note 13 - Segment Information</span></div>
    <p>Americas net sales increased during 2025 compared to 2024.</p>
    </body></html>
    """
    p = tmp_path / "heading.html"
    p.write_text(html, encoding="utf-8")
    md = parse_html_filing(p)
    assert "## Note 13 - Segment Information" in md


def test_bold_span_within_a_longer_sentence_is_not_a_heading(tmp_path):
    # A bolded word or two inside an ordinary sentence should NOT be promoted
    # to a heading — only a block that IS essentially just the bold text.
    html = """
    <html><body>
    <p>The Company believes <span style="font-weight:700">iPhone</span> revenue remained strong this quarter across every region we track.</p>
    </body></html>
    """
    p = tmp_path / "not_heading.html"
    p.write_text(html, encoding="utf-8")
    md = parse_html_filing(p)
    assert "## " not in md


def test_italic_span_div_is_detected_as_a_heading(tmp_path):
    # Regression test for the bug found 2026-10-18 (see docs/SOLUTION_CRITIQUE.md):
    # Apple's real FY2025 10-K renders the "Department of Justice Lawsuit" sub-heading
    # in italic, font-weight:400 (NOT bold) — the bold-only heading check silently
    # absorbed it as narrative text, so that paragraph got tagged with an unrelated,
    # much-earlier heading instead ("Purchases of Equity Securities..."), which is a
    # wrong citation shown to the user, not just a missing heading.
    html = """
    <html><body>
    <div style="margin-top:18pt"><span style="font-weight:700">Legal Proceedings</span></div>
    <p>The Company is involved in various legal proceedings.</p>
    <div style="margin-top:18pt"><span style="font-style:italic;font-weight:400">Department of Justice Lawsuit</span></div>
    <p>On March 21, 2024, the DOJ filed a civil antitrust lawsuit against the Company.</p>
    </body></html>
    """
    p = tmp_path / "italic_heading.html"
    p.write_text(html, encoding="utf-8")
    md = parse_html_filing(p)
    assert "## Department of Justice Lawsuit" in md


def test_italic_phrase_within_a_longer_sentence_is_not_a_heading(tmp_path):
    # An italicized phrase inside an ordinary sentence should NOT be promoted to a
    # heading — only a block that IS essentially just the italic text, same as the
    # existing bold-span guard.
    html = """
    <html><body>
    <p>The Company believes <span style="font-style:italic">in general</span> that its defenses are substantial across every matter we track.</p>
    </body></html>
    """
    p = tmp_path / "not_italic_heading.html"
    p.write_text(html, encoding="utf-8")
    md = parse_html_filing(p)
    assert "## " not in md


def test_table_header_rows_are_promoted_instead_of_positional_integers(tmp_path):
    # Real SEC tables have no <thead> — the "2025 / Change / 2024" header a
    # human sees is really just an ordinary first row (see 7.2). Left alone,
    # pandas.read_html gives positional column names (0, 1, 2, ...), which
    # carry no information for a citation or for an embedding model.
    html = """
    <html><body>
    <table>
      <tr><td></td><td>2025</td><td>Change</td><td>2024</td></tr>
      <tr><td>Americas</td><td>178353</td><td>7</td><td>167045</td></tr>
      <tr><td>Europe</td><td>111032</td><td>10</td><td>101328</td></tr>
    </table>
    </body></html>
    """
    p = tmp_path / "header_promo.html"
    p.write_text(html, encoding="utf-8")
    md = parse_html_filing(p)
    header_line = next(line for line in md.splitlines() if line.strip().startswith("|"))
    assert "2025" in header_line
    assert "Change" in header_line
    # The old bug: a bare positional header line like "| 0 | 1 | 2 | 3 |"
    assert "| 0 " not in header_line and "|0|" not in header_line.replace(" ", "")


def test_windows_1252_smart_quotes_decode_correctly_not_as_replacement_chars(tmp_path):
    # Real filings are frequently saved as Windows-1252 despite HTML claiming
    # otherwise (see 7.1) — a naive strict-or-replace UTF-8 read turns every
    # curly quote/em dash into U+FFFD, corrupting section headings and citations.
    raw_bytes = (
        b"<html><body><div><span style=\"font-weight:700\">Note 13 "
        b"\x96 Segment Information and Geographic Data</span></div></body></html>"
    )
    p = tmp_path / "cp1252.html"
    p.write_bytes(raw_bytes)
    md = parse_html_filing(p)
    assert "�" not in md
    assert "Segment Information and Geographic Data" in md


def test_hidden_xbrl_header_block_is_stripped_not_leaked_as_narrative_text(tmp_path):
    # Real filings embed a machine-readable XBRL metadata block (<ix:header>, and/or
    # anything styled display:none) that a browser never renders — a naive text walk
    # used to emit it as ordinary narrative (see docs/SOLUTION_CRITIQUE.md Section 4).
    html = """
    <html><body>
    <ix:header>
      <div>aapl:AmericasSegmentMember 2024-09-29 2025-09-27 0000320193 us-gaap:OperatingSegmentsMember</div>
    </ix:header>
    <div style="display:none">gaap:CommonStockMember hidden fact 12345</div>
    <p>Americas net sales increased during 2025 compared to 2024.</p>
    </body></html>
    """
    p = tmp_path / "xbrl_noise.html"
    p.write_text(html, encoding="utf-8")
    md = parse_html_filing(p)
    assert "AmericasSegmentMember" not in md
    assert "CommonStockMember" not in md
    assert "Americas net sales increased" in md
