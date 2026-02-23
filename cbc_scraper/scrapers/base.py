from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class CaseRecord:
    """
    A single court case record as returned by any scraper.

    Fields are intentionally broad to accommodate different court systems.
    Scrapers should populate what they can and leave unknowns as empty strings.
    """
    index_number: str        # Primary dedup key — unique case identifier
    party_name: str          # Name of the matched party
    party_role: str          # Plaintiff / Defendant / Other
    court: str               # Court name
    county: str
    case_type: str
    date_filed: str
    attorney: str            # Attorney of record, if available
    source_site: str         # e.g. "ny_webcivil" — matches the sites key in config.yaml
    search_party: str        # The search term that surfaced this record
    scraped_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return {
            "index_number": self.index_number,
            "party_name": self.party_name,
            "party_role": self.party_role,
            "court": self.court,
            "county": self.county,
            "case_type": self.case_type,
            "date_filed": self.date_filed,
            "attorney": self.attorney,
            "source_site": self.source_site,
            "search_party": self.search_party,
            "scraped_at": self.scraped_at,
        }


class BaseScraper(ABC):
    """
    Abstract base class for all site-specific scrapers.

    To add a new site:
      1. Subclass this and implement scrape().
      2. Add the class to scrapers/__init__.py SCRAPER_MAP.
      3. Add a matching block in config.yaml.
    """

    def __init__(self, site_config: dict, browser_config: dict):
        self.site_config = site_config
        self.browser_config = browser_config

    @abstractmethod
    def scrape(self, party_name: str) -> list[CaseRecord]:
        """
        Scrape all matching cases for a given party name.
        Returns a list of CaseRecord objects (may include duplicates from prior runs —
        deduplication happens in the runner, not here).
        """
