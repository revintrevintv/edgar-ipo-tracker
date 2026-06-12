"""CSV export for S1Filing records."""

import csv
import dataclasses
from typing import List

from .models import S1Filing


def write_csv(filings: List[S1Filing], path: str) -> None:
    fields = [f.name for f in dataclasses.fields(S1Filing)]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for filing in filings:
            writer.writerow(dataclasses.asdict(filing))
