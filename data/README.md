# Data

Raw filings and their parsed Markdown output are tracked in this repo (not gitignored), so a fresh clone can run the demo and eval without re-downloading from SEC EDGAR or re-running the parser. Only `processed/chroma_*/` (the vector index, regenerated at runtime by `HybridIndex.build()`) is gitignored — see the repo-root `.gitignore` for the full list and reasoning.

- `raw/` — original downloaded 10-K HTML filings for the three frozen filings in `docs/PRD.md` Section 3
- `processed/` — parsed, table-aware Markdown output from `src/ingestion/parse_filing.py`

Run `python src/ingestion/download_filings.py` to re-download `raw/` from SEC EDGAR, or `python src/ingestion/parse_filing.py <raw.htm> <processed.md>` to re-parse — see the root [`README.md`](../README.md#running-it-yourself).
