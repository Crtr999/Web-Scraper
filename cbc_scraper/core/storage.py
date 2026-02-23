"""
SQLite-backed deduplication store.

Tracks every case index number ever seen, keyed by (index_number, source_site).
On each daily run the runner calls filter_new() to get only cases we haven't
reported before, then mark_seen() to record them so they don't appear again.

The database file is created automatically on first run.
"""

import sqlite3
import logging
from datetime import datetime
from pathlib import Path

from scrapers.base import CaseRecord

logger = logging.getLogger(__name__)

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS seen_cases (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    index_number     TEXT    NOT NULL,
    source_site      TEXT    NOT NULL,
    search_party     TEXT    NOT NULL,
    first_seen_date  TEXT    NOT NULL,
    UNIQUE(index_number, source_site)
)
"""


class CaseStorage:
    def __init__(self, db_path: str = "cbc_cases.db"):
        self.db_path = Path(db_path).expanduser()
        self._init()

    def _init(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(_CREATE_TABLE)
        logger.debug(f"[storage] DB at {self.db_path} ({self._count()} records seen so far)")

    def _count(self) -> int:
        with sqlite3.connect(self.db_path) as conn:
            return conn.execute("SELECT COUNT(*) FROM seen_cases").fetchone()[0]

    def filter_new(self, records: list[CaseRecord]) -> list[CaseRecord]:
        """Return only records whose (index_number, source_site) has not been seen before."""
        if not records:
            return []

        new: list[CaseRecord] = []
        with sqlite3.connect(self.db_path) as conn:
            for r in records:
                exists = conn.execute(
                    "SELECT 1 FROM seen_cases WHERE index_number=? AND source_site=?",
                    (r.index_number, r.source_site),
                ).fetchone()
                if not exists:
                    new.append(r)

        logger.debug(f"[storage] filter_new: {len(records)} in → {len(new)} new")
        return new

    def mark_seen(self, records: list[CaseRecord]) -> None:
        """Persist records so they are excluded from future filter_new() calls."""
        if not records:
            return

        now = datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.executemany(
                "INSERT OR IGNORE INTO seen_cases "
                "(index_number, source_site, search_party, first_seen_date) "
                "VALUES (?, ?, ?, ?)",
                [(r.index_number, r.source_site, r.search_party, now) for r in records],
            )

        logger.debug(f"[storage] marked {len(records)} records as seen")

    def total_seen(self) -> int:
        return self._count()
