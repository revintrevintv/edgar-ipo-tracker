"""Stage 1: search EDGAR Full-Text Search (EFTS) for S-1 and S-1/A filings."""

import sys
from typing import List

from .client import EdgarClient
from .models import S1Filing

_PAGE_SIZE = 20  # EFTS max per page


def _cik_from_accession(accession: str) -> str:
    """Extract CIK from accession number prefix (first 10 digits, leading zeros stripped)."""
    return str(int(accession.split("-")[0]))


def search_s1_filings(
    client: EdgarClient,
    start_date: str,
    end_date: str,
    max_results: int = 100,
) -> List[S1Filing]:
    """Return up to max_results S-1/S-1A filings filed between start_date and end_date."""
    filings: List[S1Filing] = []
    offset = 0

    while len(filings) < max_results:
        url = (
            f"{client.EFTS_BASE}/LATEST/search-index"
            f"?forms=S-1"
            f"&dateRange=custom&startdt={start_date}&enddt={end_date}"
            f"&from={offset}&size={_PAGE_SIZE}"
        )
        try:
            data = client.get(url).json()
        except Exception as exc:
            print(f"  [warn] EFTS request failed at offset {offset}: {exc}", file=sys.stderr)
            break

        hits = data.get("hits", {}).get("hits", [])
        if not hits:
            break

        for hit in hits:
            if len(filings) >= max_results:
                break
            src = hit.get("_source", {})
            accession = hit["_id"]
            filings.append(
                S1Filing(
                    accession_number=accession,
                    cik=_cik_from_accession(accession),
                    company_name=src.get("entity_name", ""),
                    filing_date=src.get("file_date", ""),
                    form_type=src.get("form_type", "S-1"),
                    business_location=src.get("biz_location", ""),
                    state_of_inc_search=src.get("inc_states", ""),
                    filing_number=src.get("file_num", ""),
                )
            )

        total = data.get("hits", {}).get("total", {}).get("value", 0)
        offset += _PAGE_SIZE
        if offset >= total:
            break

    return filings
