#!/usr/bin/env python3
"""
Pre-ship verification for edgar-ipo-tracker.

Covers steps 1–4 of the Definition of Done verification pass:
  1. Clean-environment install and smoke run
  2. URL reachability for all URLs in sample output
  3. HTML/markup leak scan on all string fields
  4. EDGAR API confirmation that every sample company exists

Step 5 (adversarial review) is a separate agent pass with fresh context.

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
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).parent
SAMPLE_CSV = REPO_ROOT / "data" / "sample_output.csv"
_RATE_INTERVAL = 0.2  # 5 req/s
_HTML_RE = re.compile(r"<[a-zA-Z/!][^>]*>|&(?:amp|lt|gt|quot|nbsp|#\d+);")


class Results:
    def __init__(self):
        self.checks = []
        self.section = ""

    def section_header(self, name: str) -> None:
        self.section = name
        print(f"\n{'='*60}")
        print(f"Step {name}")
        print("=" * 60)

    def record(self, name: str, passed: bool, detail: str = "") -> bool:
        icon = "PASS" if passed else "FAIL"
        print(f"  [{icon}] {name}")
        if detail:
            for line in detail.splitlines():
                print(f"         {line}")
        self.checks.append({
            "section": self.section,
            "name": name,
            "passed": passed,
            "detail": detail,
        })
        return passed

    def summary(self) -> bool:
        passed = sum(1 for c in self.checks if c["passed"])
        total = len(self.checks)
        failed = [c for c in self.checks if not c["passed"]]
        print(f"\n{'='*60}")
        print(f"SUMMARY: {passed}/{total} checks passed")
        if failed:
            print("\nFailed checks:")
            for c in failed:
                print(f"  • [{c['section']}] {c['name']}")
                if c["detail"]:
                    for line in c["detail"].splitlines():
                        print(f"    {line}")
        return len(failed) == 0

    def as_markdown(self) -> str:
        lines = []
        current_section = None
        for c in self.checks:
            if c["section"] != current_section:
                current_section = c["section"]
                lines.append(f"\n### {current_section}\n")
            icon = "✅" if c["passed"] else "❌"
            lines.append(f"- {icon} **{c['name']}**")
            if c["detail"]:
                for line in c["detail"].splitlines():
                    lines.append(f"  - {line}")
        return "\n".join(lines)


def throttle(state: dict) -> None:
    now = time.monotonic()
    elapsed = now - state.get("last", 0)
    if elapsed < _RATE_INTERVAL:
        time.sleep(_RATE_INTERVAL - elapsed)
    state["last"] = time.monotonic()


def step1_clean_env(r: Results, user_agent: str) -> None:
    r.section_header("1: Clean-environment install and smoke run")
    with tempfile.TemporaryDirectory(prefix="edgar-verify-") as tmpdir:
        # Install deps into an isolated target dir (venv equivalent without python3-venv)
        target = os.path.join(tmpdir, "site-packages")
        os.makedirs(target)
        p = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-q",
             "--target", target,
             "-r", str(REPO_ROOT / "requirements.txt")],
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
             "--days", "7", "--max", "5",
             "--output", out_csv],
            capture_output=True, text=True,
            cwd=str(REPO_ROOT), env=env,
        )
        ran = p.returncode == 0 and os.path.exists(out_csv)
        row_count = 0
        if ran:
            with open(out_csv) as f:
                row_count = sum(1 for _ in f) - 1
        if not ran:
            detail = (p.stdout + p.stderr).strip()[:400]
        elif row_count == 0:
            ran = False
            detail = "scraper ran but produced 0 rows"
        else:
            detail = f"{row_count} rows produced"
        r.record("Smoke run with isolated deps produces output", ran, detail)


def step2_urls(r: Results, session: requests.Session, state: dict) -> None:
    r.section_header("2: URL reachability")
    if not SAMPLE_CSV.exists():
        r.record("sample_output.csv present", False, str(SAMPLE_CSV))
        return

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
                continue
            try:
                throttle(state)
                resp = session.head(url, timeout=12, allow_redirects=True)
                if resp.status_code not in (200, 206):
                    errors.append(f"{company} / {field}: HTTP {resp.status_code}")
            except Exception as exc:
                errors.append(f"{company} / {field}: {exc}")

    if errors:
        r.record("All URLs return 200/206", False, "\n".join(errors))
    else:
        r.record(f"All {len(rows) * len(url_fields)} URLs return 200/206", True)


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

            # Confirm name is reasonably consistent
            edgar_name = data.get("name", "")
            def norm(s: str) -> str:
                return re.sub(r"[^a-z0-9]", "", s.lower())
            if norm(edgar_name)[:12] != norm(csv_name)[:12]:
                errors.append(
                    f"CIK {cik}: EDGAR name '{edgar_name}' does not match "
                    f"CSV name '{csv_name}'"
                )
                continue

            # Confirm accession appears in recent filings
            recent = data.get("filings", {}).get("recent", {})
            accessions = recent.get("accessionNumber", [])
            adsh_norm = accession.replace("-", "")
            found = any(a.replace("-", "") == adsh_norm for a in accessions)
            if not found:
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
    step2_urls(r, session, rate_state)
    step3_html_scan(r)
    step4_edgar_validation(r, session, rate_state)

    all_passed = r.summary()

    # Write machine-readable results for report assembly
    report_path = REPO_ROOT / "_verify_steps1-4.md"
    with open(report_path, "w") as f:
        f.write(r.as_markdown())
    print(f"\nStep 1–4 results written to {report_path}")

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
