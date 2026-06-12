# Design Decisions

Decisions made during initial build, with reasoning.

---

**0. EFTS schema discovery: use `adsh`, `ciks[]`, and `display_names[]`**
The EFTS `_id` field is `{accession}:{primary_doc_filename}`, not a bare
accession number. The clean accession is in `_source.adsh`. The company CIK is
in `_source.ciks[]` — distinct from the filing-agent CIK that prefixes the
accession number. Company name is in `_source.display_names[]` as
`"Name (CIK 0001234567)"` and requires stripping the CIK suffix. All
location/state/file fields (`biz_locations`, `inc_states`, `file_num`) are
arrays. Confirmed by inspecting a live EFTS response.

**1. Rate limit: 5 req/s (half of SEC's cap)**
SEC's published limit is 10 req/s. Using 5 req/s keeps the tool well-behaved
even when running alongside other EDGAR tools and avoids 429s during development
iteration. Configurable via `EdgarClient(requests_per_second=N)` if needed.

**2. EFTS search API over browse-edgar CGI**
The `efts.sec.gov/LATEST/search-index` endpoint returns structured JSON and
supports server-side filtering by form type and date range. The browse-edgar CGI
(`/cgi-bin/browse-edgar`) returns HTML that requires parsing and is less stable
across SEC maintenance windows.

**3. Company CIK from `ciks[]`, not the accession number prefix**
The accession number prefix belongs to the **filing agent** (e.g. Toppan Merrill,
Edgar Filing Services), not the registrant. For companies that use a filing agent,
extracting CIK from the accession prefix yields the wrong entity. The EFTS
`_source.ciks[]` array contains the registrant's CIK and is always correct.
Fallback to the accession prefix is retained only for the rare case where `ciks[]`
is absent from the EFTS response.

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

**11. Sample CSV is generated from a real live run**
`data/sample_output.csv` is produced by running the scraper against the actual
EDGAR API and committing the output. Every company, CIK, accession number, and
URL in the file is real and verifiable. `verify.py` step 4 confirms this on every
pre-ship check. Fabricated sample data is never acceptable in a portfolio piece.
