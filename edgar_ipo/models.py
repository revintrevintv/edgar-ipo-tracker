from dataclasses import dataclass


@dataclass
class S1Filing:
    # Stage 1 — EFTS search
    accession_number: str
    cik: str
    company_name: str
    filing_date: str
    form_type: str
    business_location: str = ""
    state_of_inc_search: str = ""
    filing_number: str = ""

    # Stage 2 — submissions endpoint
    sic_code: str = ""
    sic_description: str = ""
    state_of_incorporation: str = ""
    tickers: str = ""
    exchanges: str = ""
    category: str = ""

    # Stage 3 — filing index page
    filing_index_url: str = ""
    primary_document_url: str = ""
    primary_document_type: str = ""
    total_documents: int = 0
