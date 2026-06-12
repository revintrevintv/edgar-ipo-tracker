"""Stage 1: search EDGAR Full-Text Search (EFTS) for S-1 and S-1/A filings."""

import re
import sys
from typing import List

from .client import EdgarClient
from .models import S1Filing

_PAGE_SIZE = 20  # EFTS max per page
_CIK_SUFFIX = re.compile(r"\s*\(CIK \d+\)\s*$")


def _parse_hit(hit: dict) -> S1Filing:
    src = hit.get("_source", {})

    # adsh is the clean accession number; _id appends ":filename" which we don't want
    accession = src.get("adsh") or hit["_id"].split(":")[0]

    # ciks[] is the registrant's CIK — distinct from the filing-agent CIK
    # embedded in the accession number prefix
    ciks = src.get("ciks", [])
    cik = str(int(ciks[0])) if ciks else str(int(accession.split("-")[0]))

    # display_names[] = "Company Name  (CIK 0001234567)" — strip the CIK suffix
    display_names = src.get("display_names", [])
    company_name = _CIK_SUFFIX.sub("", display_names[0]).strip() if display_names else ""

    # All location/state/file fields are arrays in EFTS
    biz_locations = src.get("biz_locations", [])
    inc_states = src.get("inc_states", [])
    file_nums = src.get("file_num", [])

    return S1Filing(
        accession_number=accession,
        cik=cik,
        company_name=company_name,
        filing_date=src.get("file_date", ""),
        form_type=src.get("form", src.get("file_type", "S-1")),
        business_location=biz_locations[0] if biz_locations else "",
        state_of_inc_search=inc_states[0] if inc_states else "",
        filing_number=file_nums[0] if file_nums else "",
    )


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
            filings.append(_parse_hit(hit))

        total = data.get("hits", {}).get("total", {}).get("value", 0)
        offset += _PAGE_SIZE
        if offset >= total:
            break

    return filings
