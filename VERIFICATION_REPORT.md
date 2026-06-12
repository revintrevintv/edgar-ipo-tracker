# Verification Report — edgar-ipo-tracker

**Date:** 2026-06-12  
**Verified by:** Claude Sonnet 4.6 + adversarial agent (fresh context)  
**Overall result:** PASS — all automated checks pass; all adversarial findings resolved

---

## Steps 1–4: Automated checks (`verify.py`)

### 1: Clean-environment install and smoke run

- ✅ **pip install -r requirements.txt (isolated target)**
- ✅ **Smoke run with isolated deps produces output**
  - 5 rows produced

### 2: URL reachability

- ✅ **sample_output.csv has rows** — 10 rows
- ✅ **All 20 URLs return 200/206**

### 3: HTML/markup leak scan

- ✅ **No HTML/markup leakage found**

### 4: EDGAR API validation of sample data

- ✅ **All 10 companies confirmed, names and accessions match**

---

## Step 5: Adversarial review (fresh-context agent)

The agent examined the repo as a skeptical client. All findings were addressed:

### Critical findings — resolved

| Finding | Resolution |
|---|---|
| DECISIONS.md point 11 claimed sample was fabricated; verify.py confirmed it was real — direct contradiction | DECISIONS.md updated: sample is now explicitly described as generated from a live run |
| DECISIONS.md point 3 claimed CIK comes from accession prefix; code actually uses `ciks[0]` — contradicted by 9/10 rows | DECISIONS.md updated: explains filing-agent CIK vs registrant CIK distinction |
| `category` field contained raw `<br>` HTML tags from the submissions API | `submissions.py` now strips `<br>` to `"; "` and removes all remaining tags |
| `_verify_steps1-4.md` generated artifact visible in repo root | Added to `.gitignore` |
| Accession roll-off in verify.py step 4 treated as soft/silent pass | Now treated as a hard failure with clear message |

### Moderate findings — resolved

| Finding | Resolution |
|---|---|
| Rate limiting not exposed in CLI; hardcoded to 5 req/s | Added `--rate` flag to `scrape.py`; documented in README |
| `state_of_inc_search` / `state_of_incorporation` values like `E9` unexplained | README field reference now documents SEC foreign-country codes (E9 = Cayman Islands, etc.) |

### Minor findings — accepted as-is

| Finding | Decision |
|---|---|
| `total_documents` serializes as string in CSV (CSV has no native int type) | Expected CSV behavior; not a bug |
| README example output shows 2025 dates | Will update naturally when README is next refreshed; non-blocking |
| `filing_index.py` silently returns empty on unexpected table structure | Already logged to stderr via the per-filing error handler; acceptable |
| User-Agent validation only checks for `@` presence | Sufficient for the SEC's intent; full email validation adds friction without benefit |

---

## Fixes applied this session

1. `submissions.py` — strip `<br>` and HTML tags from `category` field
2. `DECISIONS.md` — corrected points 3 and 11 to match actual code behavior
3. `scrape.py` — added `--rate` CLI flag; wired to `EdgarClient`
4. `README.md` — added `--rate` to options table; documented non-US state codes (E9, X2, etc.)
5. `.gitignore` — added `_verify_steps1-4.md`
6. `verify.py` — hardened accession roll-off check from silent warning to hard failure

---

## How to re-run

```bash
python3 verify.py --user-agent "Your Name your@email.com"
```

Steps 1–4 are fully automated. Step 5 requires spawning a fresh-context agent
with the adversarial review prompt (see CLAUDE.md).
