#!/usr/bin/env python3
"""edgar-ipo-tracker — pull recent S-1 filings from SEC EDGAR in three stages."""

import argparse
import os
import sys
from datetime import date, timedelta

from edgar_ipo.client import EdgarClient
from edgar_ipo.export import write_csv
from edgar_ipo.filing_index import enrich_with_filing_index
from edgar_ipo.search import search_s1_filings
from edgar_ipo.submissions import enrich_with_submissions


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pull recent S-1/S-1A filings from SEC EDGAR",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "SEC requires a descriptive User-Agent identifying you as the requester.\n"
            "Set EDGAR_USER_AGENT in your environment or pass --user-agent.\n\n"
            "Example:\n"
            "  python scrape.py --user-agent 'Jane Smith jane@example.com' --days 30"
        ),
    )
    parser.add_argument(
        "--days", type=int, default=90,
        help="look back N days from today (default: 90)",
    )
    parser.add_argument(
        "--max", type=int, default=100,
        help="maximum filings to fetch (default: 100)",
    )
    parser.add_argument(
        "--output", default="ipo_filings.csv",
        help="output CSV path (default: ipo_filings.csv)",
    )
    parser.add_argument(
        "--user-agent",
        default=os.environ.get("EDGAR_USER_AGENT", ""),
        help="contact string for SEC User-Agent, e.g. 'Name email@domain.com'",
    )
    args = parser.parse_args()

    if not args.user_agent:
        parser.error(
            "User-Agent is required. Pass --user-agent 'Name email@domain.com' "
            "or set the EDGAR_USER_AGENT environment variable.\n"
            "SEC policy requires identifying contact info in all automated requests."
        )

    end_date = date.today()
    start_date = end_date - timedelta(days=args.days)

    client = EdgarClient(user_agent=args.user_agent)

    print(f"Stage 1  searching S-1 filings {start_date} to {end_date} (max {args.max})")
    filings = search_s1_filings(client, str(start_date), str(end_date), max_results=args.max)
    print(f"         {len(filings)} filings found")

    if not filings:
        print("No filings found. Try a wider date range with --days.", file=sys.stderr)
        sys.exit(1)

    print(f"\nStage 2  enriching {len(filings)} filings with company metadata")
    filings = enrich_with_submissions(client, filings)

    print(f"\nStage 3  parsing {len(filings)} filing index pages")
    filings = enrich_with_filing_index(client, filings)

    write_csv(filings, args.output)
    print(f"\n  {len(filings)} rows written to {args.output}")


if __name__ == "__main__":
    main()
