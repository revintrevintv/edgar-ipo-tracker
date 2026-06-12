"""Stage 2: enrich filings with company metadata from the EDGAR submissions endpoint."""

import sys
from typing import List

from .client import EdgarClient
from .models import S1Filing


def enrich_with_submissions(client: EdgarClient, filings: List[S1Filing]) -> List[S1Filing]:
    """Fetch company metadata for each filing and write it onto the filing object."""
    total = len(filings)
    for i, filing in enumerate(filings, 1):
        cik_padded = filing.cik.zfill(10)
        url = f"{client.DATA_BASE}/submissions/CIK{cik_padded}.json"
        try:
            data = client.get(url).json()
        except Exception as exc:
            print(
                f"  [warn] submissions fetch failed for CIK {filing.cik} "
                f"({filing.company_name}): {exc}",
                file=sys.stderr,
            )
            continue

        filing.sic_code = data.get("sic", "")
        filing.sic_description = data.get("sicDescription", "")
        filing.state_of_incorporation = data.get("stateOfIncorporation", "")
        filing.category = data.get("category", "")

        tickers = data.get("tickers", [])
        exchanges = data.get("exchanges", [])
        filing.tickers = ", ".join(tickers) if tickers else ""
        filing.exchanges = ", ".join(exchanges) if exchanges else ""

        if i % 10 == 0 or i == total:
            print(f"  {i}/{total} companies enriched")

    return filings
