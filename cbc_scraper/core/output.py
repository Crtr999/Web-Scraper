"""
CSV output writer.

Each daily run writes to a dated file:  ss_cases_2024-01-15.csv
If the file already exists (e.g. the job ran twice today), new rows are appended.
The header is written only when the file is first created.
"""

import csv
import logging
from datetime import datetime
from pathlib import Path

from scrapers.base import CaseRecord

logger = logging.getLogger(__name__)

FIELDS = [
    "index_number",
    "party_name",
    "party_role",
    "court",
    "county",
    "case_type",
    "date_filed",
    "attorney",
    "source_site",
    "search_party",
    "scraped_at",
]


class CSVOutput:
    def __init__(self, output_dir: str, filename_prefix: str = "ss_cases"):
        self.output_dir = Path(output_dir).expanduser()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.prefix = filename_prefix

    def _today_path(self) -> Path:
        today = datetime.now().strftime("%Y-%m-%d")
        return self.output_dir / f"{self.prefix}_{today}.csv"

    def write(self, records: list[CaseRecord]) -> Path:
        """
        Append records to today's CSV. Returns the file path.
        Creates the file with a header row if it doesn't exist yet.
        """
        if not records:
            logger.info("[output] No new records to write.")
            return self._today_path()

        filepath = self._today_path()
        write_header = not filepath.exists()

        with open(filepath, "a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=FIELDS, extrasaction="ignore")
            if write_header:
                writer.writeheader()
            for r in records:
                writer.writerow(r.to_dict())

        logger.info(f"[output] Wrote {len(records)} record(s) → {filepath}")
        return filepath

    def summary(self, records: list[CaseRecord]) -> str:
        """Return a plain-text summary string suitable for a log or email subject."""
        if not records:
            return "No new structured settlement cases found today."

        by_site: dict[str, int] = {}
        for r in records:
            by_site[r.source_site] = by_site.get(r.source_site, 0) + 1

        lines = [f"New structured settlement cases found: {len(records)}"]
        for site, count in by_site.items():
            lines.append(f"  {site}: {count} new case(s)")
        return "\n".join(lines)
