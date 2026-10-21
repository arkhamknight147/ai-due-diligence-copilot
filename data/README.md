# Data

This folder is gitignored except for this README and the .gitkeep markers — filings are re-downloaded, not committed, to keep the repo small and avoid redistributing SEC filings.

- `raw/` — original downloaded 10-K filings (PDF or HTML) for the three frozen filings in `docs/PRD.md` Section 3
- `processed/` — parsed/chunked intermediate output from `src/ingestion/`

Run `src/ingestion/download_filings.py` (once added) to repopulate `raw/` from SEC EDGAR.
