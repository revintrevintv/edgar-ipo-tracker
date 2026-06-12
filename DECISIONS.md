# Design Decisions

Decisions made during initial build, with reasoning.

---

**1. Rate limit: 5 req/s (half of SEC's cap)**
SEC's published limit is 10 req/s. Using 5 req/s keeps the tool well-behaved
even when running alongside other EDGAR tools and avoids 429s during development
iteration. Configurable via `EdgarClient(requests_per_second=N)` if needed.

**2. EFTS search API over browse-edgar CGI**
The `efts.sec.gov/LATEST/search-index` endpoint returns structured JSON and
supports server-side filtering by form type and date range. The browse-edgar CGI
(`/cgi-bin/browse-edgar`) returns HTML that requires parsing and is less stable
across SEC maintenance windows.

**3. CIK extracted from accession number, not a separate lookup**
An accession number's first 10 digits are always the filer's zero-padded CIK
(e.g. `0001234567-25-000001` → CIK `1234567`). This avoids one HTTP round-trip
per filing.

**4. Both S-1 and S-1/A included**
Amendments signal active filings where companies are responding to SEC staff
comments — often closer to the actual IPO date than the original S-1. Clients
tracking the IPO pipeline want both. The `form_type` column distinguishes them.

**5. Default lookback: 90 days**
Captures most in-flight IPO processes (the SEC review cycle typically runs 3–6
months) without hitting pagination limits in a single run. Adjustable with
`--days`.

**6. BeautifulSoup with `html.parser` (stdlib) over lxml**
Avoids a C extension dependency. `html.parser` is slightly slower but has zero
install friction on any platform. For a scraper processing hundreds of pages,
speed is not the bottleneck — network I/O and rate limiting are.

**7. Per-filing errors are non-fatal**
Stage 2 and Stage 3 errors (failed fetch, unexpected HTML structure) are logged
to stderr and the filing is kept in the output with whatever fields were
successfully populated. Partial output is more useful than a hard crash when one
of 100 filings has a malformed index page.

**8. `--user-agent` is a required CLI parameter**
SEC policy explicitly requires automated clients to identify themselves with
contact information. Making it a required argument (or env variable) ensures
users can't accidentally omit it and get their IP blocked. There is no sensible
default.

**9. No retry logic**
EDGAR is generally reliable. Adding `tenacity` or a manual retry loop would
introduce another dependency and complexity for a benefit that rarely materializes
in practice. Users can re-run the script if they hit transient errors — the
output CSV accumulates only successful rows, so a re-run with a tighter date
range can fill gaps.

**10. `requests` over `httpx` or `aiohttp`**
A sequential scraper respecting a 5 req/s rate limit has no use for async I/O.
`requests` is the most recognized library in the data-engineering ecosystem and
the simplest dependency story for clients who might want to extend this.

**11. Sample CSV is manually curated, not generated from a live run**
Ensures the repo is self-contained and reproducible without network access.
Company names, accession numbers, and metadata are representative of real EDGAR
filings but are not real companies. URL structure matches real EDGAR conventions.
