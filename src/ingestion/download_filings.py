"""
Download the three frozen 10-K filings named in docs/PRD.md Section 3.

NOTE: this script requires normal outbound internet access to www.sec.gov. It
will NOT run inside this project's Claude Cowork session — that sandbox's
network egress is allow-listed to package registries only (pypi, npm, etc.)
and blocks sec.gov (and, as it happens, most of the general internet) at the
proxy level. Run this script from your own machine, or from GitHub Actions /
Streamlit Community Cloud / Hugging Face Spaces, all of which have normal
internet access. See docs/TRADE_OFFS.md for the full story.

SEC's fair-access policy requires a descriptive User-Agent header identifying
who's making the request (see https://www.sec.gov/os/webmaster-faq#developers) —
set FILER_CONTACT below to your own name/email before running.
"""

from __future__ import annotations

from pathlib import Path

import requests

FILER_CONTACT = "Nishant Kanhurkar nishant.kanhurkar@gmail.com"  # required by SEC's fair-access policy

# Frozen filing scope — see docs/PRD.md Section 3 for why these specific
# (not "whichever is newest") filings were chosen.
FILINGS = {
    "aapl-20250927.htm": "https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl-20250927.htm",
    "msft-20250630.htm": "https://www.sec.gov/Archives/edgar/data/789019/000095017025100235/msft-20250630.htm",
    "nvda-20250126.htm": "https://www.sec.gov/Archives/edgar/data/1045810/000104581025000023/nvda-20250126.htm",
}

RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"


def download_all() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    headers = {"User-Agent": FILER_CONTACT}
    for filename, url in FILINGS.items():
        out_path = RAW_DIR / filename
        print(f"Downloading {url} -> {out_path}")
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        out_path.write_bytes(resp.content)
        print(f"  wrote {len(resp.content):,} bytes")


if __name__ == "__main__":
    download_all()
