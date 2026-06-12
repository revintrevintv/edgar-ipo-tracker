"""Stage 3: fetch each filing's HTML index page and parse document links with BeautifulSoup."""

import sys
from typing import List, Tuple

from bs4 import BeautifulSoup

from .client import EdgarClient
from .models import S1Filing


def _index_url(cik: str, accession: str) -> str:
    accession_nodash = accession.replace("-", "")
    return (
        f"https://www.sec.gov/Archives/edgar/data/{cik}"
        f"/{accession_nodash}/{accession}-index.htm"
    )


def _parse_index(html: str) -> Tuple[str, str, int]:
    """Return (primary_doc_url, primary_doc_type, total_docs) from the filing index HTML."""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", class_="tableFile")
    if not table:
        return "", "", 0

    docs = []
    for row in table.find_all("tr")[1:]:  # skip header row
        cells = row.find_all("td")
        if len(cells) < 4:
            continue
        link = cells[2].find("a")
        if link and link.get("href"):
            doc_url = "https://www.sec.gov" + link["href"]
        else:
            doc_url = ""
        doc_type = cells[3].get_text(strip=True)
        docs.append((doc_url, doc_type))

    if not docs:
        return "", "", 0

    # Sequence 1 (first data row) is always the primary document
    primary_url, primary_type = docs[0]
    return primary_url, primary_type, len(docs)


def enrich_with_filing_index(client: EdgarClient, filings: List[S1Filing]) -> List[S1Filing]:
    """Fetch and parse the HTML filing index page for each filing."""
    total = len(filings)
    for i, filing in enumerate(filings, 1):
        url = _index_url(filing.cik, filing.accession_number)
        filing.filing_index_url = url
        try:
            html = client.get(url).text
            primary_url, primary_type, doc_count = _parse_index(html)
            filing.primary_document_url = primary_url
            filing.primary_document_type = primary_type
            filing.total_documents = doc_count
        except Exception as exc:
            print(
                f"  [warn] index fetch failed for {filing.accession_number} "
                f"({filing.company_name}): {exc}",
                file=sys.stderr,
            )

        if i % 10 == 0 or i == total:
            print(f"  {i}/{total} filing indexes parsed")

    return filings
