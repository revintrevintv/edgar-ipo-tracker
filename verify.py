#!/usr/bin/env python3
"""
Pre-ship verification for edgar-ipo-tracker.

Steps 1–4 are automated. Step 5 (adversarial review) is a separate agent pass.
If ~/reports/report_lib.py is present, saves a polished HTML report to
~/reports/ and updates the index. Falls back to plain terminal output otherwise.

Usage:
  python3 verify.py --user-agent "Name email@example.com"
  EDGAR_USER_AGENT="Name email@example.com" python3 verify.py
"""

import argparse
import csv
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).parent
SAMPLE_CSV = REPO_ROOT / "data" / "sample_output.csv"
_RATE_INTERVAL = 0.2  # 5 req/s
_HTML_RE = re.compile(r"<[a-zA-Z/!][^>]*>|&(?:amp|lt|gt|quot|nbsp|#\d+);")
_NORM_RE = re.compile(r"[^a-z0-9]")

# Optional HTML report library
try:
    sys.path.insert(0, str(Path.home() / "reports"))
    from report_lib import Report  # type: ignore
    _HAS_REPORT = True
except ImportError:
    _HAS_REPORT = False


# ---------------------------------------------------------------------------
# Result accumulator
# ---------------------------------------------------------------------------
class Results:
    def __init__(self):
        self.checks = []
        self._section = ""

    def section_header(self, name: str) -> None:
        self._section = name
        print(f"\n{'='*60}\nStep {name}\n{'='*60}")

    def record(self, name: str, passed: bool, detail: str = "") -> bool:
        icon = "PASS" if passed else "FAIL"
        print(f"  [{icon}] {name}")
        if detail:
            for line in detail.splitlines():
                print(f"         {line}")
        self.checks.append({"section": self._section, "name": name,
                             "passed": passed, "detail": detail})
        return passed

    def passed_total(self):
        p = sum(1 for c in self.checks if c["passed"])
        return p, len(self.checks)

    def sections(self):
        seen, order = {}, []
        for c in self.checks:
            s = c["section"]
            if s not in seen:
                seen[s] = []
                order.append(s)
            seen[s].append(c)
        return [(s, seen[s]) for s in order]


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------
def throttle(state: dict) -> None:
    now = time.monotonic()
    elapsed = now - state.get("last", 0)
    if elapsed < _RATE_INTERVAL:
        time.sleep(_RATE_INTERVAL - elapsed)
    state["last"] = time.monotonic()


# ---------------------------------------------------------------------------
# Step implementations
# ---------------------------------------------------------------------------
def step1_clean_env(r: Results, user_agent: str) -> None:
    r.section_header("1: Clean-environment install and smoke run")
    with tempfile.TemporaryDirectory(prefix="edgar-verify-") as tmpdir:
        target = os.path.join(tmpdir, "site-packages")
        os.makedirs(target)
        p = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-q",
             "--target", target, "-r", str(REPO_ROOT / "requirements.txt")],
            capture_output=True, text=True,
        )
        if not r.record(
            "pip install -r requirements.txt (isolated target)",
            p.returncode == 0,
            p.stderr.strip()[:300] if p.returncode != 0 else "",
        ):
            return

        out_csv = os.path.join(tmpdir, "smoke.csv")
        env = {**os.environ, "PYTHONPATH": target}
        p = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scrape.py"),
             "--user-agent", user_agent,
             "--days", "7", "--max", "5", "--output", out_csv],
            capture_output=True, text=True, cwd=str(REPO_ROOT), env=env,
        )
        ran = p.returncode == 0 and os.path.exists(out_csv)
        row_count = 0
        if ran:
            with open(out_csv) as f:
                row_count = sum(1 for _ in f) - 1
        if not ran:
            detail = (p.stdout + p.stderr).strip()[:400]
        elif row_count == 0:
            ran, detail = False, "scraper ran but produced 0 rows"
        else:
            detail = f"{row_count} rows produced"
        r.record("Smoke run with isolated deps produces output", ran, detail)


def step2_urls(r: Results, session: requests.Session, state: dict) -> list:
    r.section_header("2: URL reachability")
    url_results = []
    if not SAMPLE_CSV.exists():
        r.record("sample_output.csv present", False, str(SAMPLE_CSV))
        return url_results

    with open(SAMPLE_CSV) as f:
        rows = list(csv.DictReader(f))
    r.record("sample_output.csv has rows", len(rows) > 0, f"{len(rows)} rows")

    url_fields = ["filing_index_url", "primary_document_url"]
    errors = []
    for row in rows:
        company = row.get("company_name", "?")
        for field in url_fields:
            url = row.get(field, "").strip()
            if not url:
                errors.append(f"{company} / {field}: empty")
                url_results.append({"company": company, "field": field,
                                     "url": "(empty)", "status": "FAIL"})
                continue
            try:
                throttle(state)
                resp = session.head(url, timeout=12, allow_redirects=True)
                ok = resp.status_code in (200, 206)
                if not ok:
                    errors.append(f"{company} / {field}: HTTP {resp.status_code}")
                url_results.append({"company": company, "field": field,
                                     "url": url, "status": str(resp.status_code)})
            except Exception as exc:
                errors.append(f"{company} / {field}: {exc}")
                url_results.append({"company": company, "field": field,
                                     "url": url, "status": "ERR"})

    if errors:
        r.record("All URLs return 200/206", False, "\n".join(errors))
    else:
        r.record(f"All {len(rows) * len(url_fields)} URLs return 200/206", True)
    return url_results


def step3_html_scan(r: Results) -> None:
    r.section_header("3: HTML/markup leak scan")
    if not SAMPLE_CSV.exists():
        r.record("sample_output.csv present", False)
        return
    leaks = []
    with open(SAMPLE_CSV) as f:
        for i, row in enumerate(csv.DictReader(f), 1):
            for field, val in row.items():
                if _HTML_RE.search(val):
                    leaks.append(f"row {i}, {field}: {val[:100]}")
    if leaks:
        r.record("No HTML/markup in any field", False, "\n".join(leaks[:10]))
    else:
        r.record("No HTML/markup leakage found", True)


def step4_edgar_validation(r: Results, session: requests.Session, state: dict) -> None:
    r.section_header("4: EDGAR API validation of sample data")
    if not SAMPLE_CSV.exists():
        r.record("sample_output.csv present", False)
        return

    with open(SAMPLE_CSV) as f:
        rows = list(csv.DictReader(f))

    def norm(s):
        return _NORM_RE.sub("", s.lower())

    errors = []
    for row in rows:
        cik = row.get("cik", "").strip()
        csv_name = row.get("company_name", "").strip()
        accession = row.get("accession_number", "").strip()
        if not cik:
            errors.append(f"missing CIK for '{csv_name}'")
            continue
        url = f"https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json"
        try:
            throttle(state)
            resp = session.get(url, timeout=12)
            if resp.status_code == 404:
                errors.append(f"CIK {cik} ({csv_name}): not found in EDGAR")
                continue
            resp.raise_for_status()
            data = resp.json()
            edgar_name = data.get("name", "")
            if norm(edgar_name)[:12] != norm(csv_name)[:12]:
                errors.append(f"CIK {cik}: EDGAR name '{edgar_name}' != CSV '{csv_name}'")
                continue
            accessions = data.get("filings", {}).get("recent", {}).get("accessionNumber", [])
            adsh_norm = accession.replace("-", "")
            if not any(a.replace("-", "") == adsh_norm for a in accessions):
                errors.append(
                    f"CIK {cik} ({csv_name}): accession {accession} "
                    f"not found in EDGAR recent filings — sample row may be stale"
                )
        except Exception as exc:
            errors.append(f"CIK {cik} ({csv_name}): {exc}")

    if errors:
        r.record("All sample companies confirmed in EDGAR", False, "\n".join(errors))
    else:
        r.record(f"All {len(rows)} companies confirmed, names and accessions match", True)


# ---------------------------------------------------------------------------
# HTML report generation
# ---------------------------------------------------------------------------
_ADVERSARIAL_FINDINGS = [
    # (severity, finding, resolution, status)
    ("Critical", "DECISIONS.md claimed sample data was fabricated; verify.py confirmed it was real",
     "DECISIONS.md point 11 updated: sample is generated from live run", "Resolved"),
    ("Critical", "DECISIONS.md claimed CIK extracted from accession prefix; code uses ciks[] instead",
     "DECISIONS.md point 3 updated: explains filing-agent vs registrant CIK", "Resolved"),
    ("Critical", "category field stored raw <br> HTML from EDGAR submissions API",
     "submissions.py strips <br> → '; ' and removes remaining tags", "Resolved"),
    ("Critical", "_verify_steps1-4.md generated artifact was visible in repo root",
     "Added _verify_steps1-4.md to .gitignore", "Resolved"),
    ("Critical", "Accession roll-off check was a soft warning, not a failure",
     "verify.py step 4 now treats missing accession as hard failure", "Resolved"),
    ("Moderate", "Rate limiting hardcoded; no way to override without editing code",
     "Added --rate flag to scrape.py, wired to EdgarClient", "Resolved"),
    ("Moderate", "Non-US state codes (e.g. E9) unexplained; looked like bad data",
     "README field reference documents SEC foreign-country codes", "Resolved"),
    ("Minor", "total_documents serializes as string in CSV",
     "Expected CSV behavior (CSV has no native int type) — accepted", "Accepted"),
    ("Minor", "README example output shows 2025 dates",
     "Non-blocking; will update naturally on next README refresh", "Accepted"),
    ("Minor", "filing_index.py silently returns empty on unexpected HTML structure",
     "Already logged to stderr via per-filing error handler — accepted", "Accepted"),
]


def _save_html_report(r: Results, url_results: list) -> str:
    date = datetime.now().strftime("%Y-%m-%d")
    passed, total = r.passed_total()
    failed = total - passed

    rpt = Report(
        "edgar-ipo-tracker — Verification Report",
        subtitle=f"Run {datetime.now().strftime('%Y-%m-%d %H:%M')} · verify.py steps 1–4 + adversarial review",
    )

    rpt.cards([
        {"label": "Total Checks", "value": str(total)},
        {"label": "Passed", "value": str(passed),
         "status": "pass" if passed == total else "warn"},
        {"label": "Failed", "value": str(failed),
         "status": "pass" if failed == 0 else "fail"},
        {"label": "Date", "value": date},
    ])

    for section_name, checks in r.sections():
        sec_passed = sum(1 for c in checks if c["passed"])
        sec_total  = len(checks)
        badge = "PASS" if sec_passed == sec_total else "FAIL"
        rpt.section(
            f"Step {section_name}",
            badge=f"{badge} {sec_passed}/{sec_total}",
        )
        rpt.checks(checks)

        # Step 2: append URL table
        if section_name.startswith("2:") and url_results:
            rpt.raw_html('<p style="margin:.6rem 0 .4rem;font-size:.78rem;color:var(--muted);">URLs checked</p>')
            rpt.table(
                headers=["Company", "Field", "Status", "URL"],
                rows=[
                    [
                        u["company"],
                        u["field"].replace("_url", ""),
                        {"text": u["status"],
                         "badge": "pass" if u["status"] in ("200", "206") else "fail"},
                        u["url"][:80] + ("…" if len(u["url"]) > 80 else ""),
                    ]
                    for u in url_results
                ],
            )
        rpt.end_section()

    # Step 5: static adversarial review section
    rpt.section("5: Adversarial review (fresh-context agent)", collapsed=True)
    rpt.prose(
        "A fresh-context agent examined the repo as a skeptical client on 2026-06-12. "
        "All Critical and Moderate findings were resolved before shipping."
    )
    severity_badge = {"Critical": "fail", "Moderate": "warn", "Minor": "info"}
    rpt.table(
        headers=["Severity", "Finding", "Resolution", "Status"],
        rows=[
            [
                {"text": sev, "badge": severity_badge.get(sev, "info")},
                finding,
                resolution,
                {"text": status, "badge": "pass" if status == "Resolved" else "info"},
            ]
            for sev, finding, resolution, status in _ADVERSARIAL_FINDINGS
        ],
    )
    rpt.end_section()

    filename = f"edgar-ipo-tracker-verify-{date}.html"
    path = rpt.save(filename)
    print(f"\nHTML report → {path}")
    print(f"View at    → http://localhost:8080/{filename}")
    return path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--user-agent",
        default=os.environ.get("EDGAR_USER_AGENT", ""),
        help="SEC User-Agent string (or set EDGAR_USER_AGENT)",
    )
    args = parser.parse_args()
    if not args.user_agent:
        parser.error("--user-agent required (or set EDGAR_USER_AGENT)")

    session = requests.Session()
    session.headers["User-Agent"] = args.user_agent
    rate_state: dict = {}

    r = Results()
    step1_clean_env(r, args.user_agent)
    url_results = step2_urls(r, session, rate_state)
    step3_html_scan(r)
    step4_edgar_validation(r, session, rate_state)

    passed, total = r.passed_total()
    print(f"\n{'='*60}")
    print(f"SUMMARY: {passed}/{total} checks passed")
    failed_checks = [c for c in r.checks if not c["passed"]]
    if failed_checks:
        print("\nFailed checks:")
        for c in failed_checks:
            print(f"  • [{c['section']}] {c['name']}")
            if c["detail"]:
                for line in c["detail"].splitlines():
                    print(f"    {line}")

    if _HAS_REPORT:
        _save_html_report(r, url_results)
    else:
        print("\n(report_lib not found — HTML report skipped; install ~/reports/report_lib.py)")

    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
