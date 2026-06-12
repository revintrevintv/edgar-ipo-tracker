# edgar-ipo-tracker

Pull recent S-1 and S-1/A filings from SEC EDGAR in three stages: full-text
search → company metadata → filing document index.

## What it does

**Stage 1 — EFTS search:** queries the EDGAR Full-Text Search API for S-1 and
S-1/A filings in a configurable date range, with pagination.

**Stage 2 — Submissions:** enriches each filing with company metadata (SIC code
and description, state of incorporation, ticker, exchange, filer category) from
the EDGAR submissions endpoint.

**Stage 3 — Filing index:** fetches each filing's HTML index page and parses it
with BeautifulSoup to extract the primary document URL, document type, and total
document count in the filing package.

Output: a single CSV with all fields from all three stages.

## SEC access rules

The SEC requires every automated client to:

- Include a **descriptive `User-Agent` header** with your name and contact email
- Stay under **10 requests per second** per IP

This tool enforces **5 req/s** (half the cap) and will refuse to run without a
User-Agent. From the [SEC's access policy](https://www.sec.gov/privacy.htm#security):

> Automated access is acceptable as long as it does not place excessive load on
> our systems and includes appropriate identifying information in the User-Agent.

## Installation

```bash
git clone https://github.com/revintrevintv/edgar-ipo-tracker
cd edgar-ipo-tracker
pip install -r requirements.txt
```

Requires Python 3.8+. No API key needed.

## Usage

```bash
python scrape.py --user-agent "Your Name your@email.com"
```

Or set the environment variable and omit the flag:

```bash
export EDGAR_USER_AGENT="Your Name your@email.com"
python scrape.py --days 30 --max 50 --output recent_s1s.csv
```

### Options

| Flag | Default | Description |
|---|---|---|
| `--user-agent` | `$EDGAR_USER_AGENT` | Name + email for SEC User-Agent header (required) |
| `--days` | `90` | Look back N days from today |
| `--max` | `100` | Maximum filings to fetch |
| `--output` | `ipo_filings.csv` | Output CSV path |

### Example output (truncated)

```
Stage 1  searching S-1 filings 2025-03-14 to 2025-06-12 (max 100)
         87 filings found

Stage 2  enriching 87 filings with company metadata
  10/87 companies enriched
  20/87 companies enriched
  ...
  87/87 companies enriched

Stage 3  parsing 87 filing index pages
  10/87 filing indexes parsed
  ...
  87/87 filing indexes parsed

  87 rows written to ipo_filings.csv
```

## Sample output

See [`data/sample_output.csv`](data/sample_output.csv). Representative rows:

| company_name | filing_date | form_type | sic_description | state_of_incorporation | total_documents |
|---|---|---|---|---|---|
| Southern Cross Acquisition I Corp. | 2026-06-12 | S-1 | Blank Checks | E9 | 47 |
| CIMG Inc. | 2026-06-12 | S-1/A | Retail-Miscellaneous Retail | NV | 10 |
| Narragansett Bancorp, Inc. | 2026-06-12 | S-1 | State Commercial Banks-NEC | MD | 95 |
| First Carolina Financial Services, Inc. | 2026-06-12 | S-1/A | State Commercial Banks | NC | 38 |
| ENTRATA, INC. | 2026-06-11 | S-1/A | Services-Prepackaged Software | DE | 46 |

## Output fields

| Field | Stage | Description |
|---|---|---|
| `accession_number` | 1 | SEC accession number (e.g. `0001234567-25-000001`) |
| `cik` | 1 | Company CIK, extracted from accession number prefix |
| `company_name` | 1 | Entity name from EFTS |
| `filing_date` | 1 | Date filed |
| `form_type` | 1 | `S-1` or `S-1/A` |
| `business_location` | 1 | City, state from EFTS |
| `state_of_inc_search` | 1 | State of incorporation from EFTS (two-letter code) |
| `filing_number` | 1 | SEC file number (e.g. `333-287641`) |
| `sic_code` | 2 | SIC industry code |
| `sic_description` | 2 | SIC industry description |
| `state_of_incorporation` | 2 | State of incorporation from submissions endpoint |
| `tickers` | 2 | Ticker symbol(s), comma-separated (blank if not yet listed) |
| `exchanges` | 2 | Exchange(s), comma-separated (blank if not yet listed) |
| `category` | 2 | SEC filer category (e.g. `Emerging growth company`) |
| `filing_index_url` | 3 | URL of the filing's document index page |
| `primary_document_url` | 3 | URL of the primary S-1 document (sequence 1) |
| `primary_document_type` | 3 | Document type from the index (S-1, S-1/A, etc.) |
| `total_documents` | 3 | Total documents in the filing package |

## Design decisions

See [DECISIONS.md](DECISIONS.md) for rationale on rate limiting, API choices,
error handling strategy, and dependency selection.
