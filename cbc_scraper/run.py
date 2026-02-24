#!/usr/bin/env python3
"""
CBC Settlement Funding — Structured Settlement Case Scraper
Entry point for both manual runs and the daily 8am cron job.

Usage
─────
  python run.py                        # Run all enabled sites
  python run.py --inspect              # Visible browser (confirm selectors)
  python run.py --site ny_webcivil     # Run one specific site
  python run.py --no-dedup            # Skip deduplication (useful for testing)

First-time setup
────────────────
  1.  pip install -r requirements.txt
  2.  playwright install chromium
  3.  python run.py --inspect          # Watch the browser, verify selectors
  4.  Update selectors in ny_webcivil.py if needed
  5.  Set headless: true in config.yaml
  6.  bash setup_cron.sh               # Install 8am cron job
"""

import argparse
import logging
import sys
from pathlib import Path

import yaml

# Make sure the cbc_scraper package root is on sys.path when run directly.
sys.path.insert(0, str(Path(__file__).parent))
# Make the parent repo directory importable so 'import scrapling' works
# even if 'pip install -e .' failed (e.g. system Python permission issues).
sys.path.insert(0, str(Path(__file__).parent.parent))

from scrapers import SCRAPER_MAP
from core.storage import CaseStorage
from core.output import CSVOutput


def load_config(path: str = "config.yaml") -> dict:
    cfg_path = Path(__file__).parent / path
    with open(cfg_path) as fh:
        return yaml.safe_load(fh)


def setup_logging(log_dir: str, level: str) -> None:
    from datetime import datetime

    log_path = Path(log_dir).expanduser()
    log_path.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_path / f"scraper_{today}.log"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="CBC Structured Settlement Case Scraper")
    parser.add_argument(
        "--inspect",
        action="store_true",
        help="Override headless=true → open a visible browser window. "
             "Use this on first run to verify form selectors.",
    )
    parser.add_argument(
        "--site",
        metavar="SITE_ID",
        help="Run only this site (e.g. ny_webcivil). Runs all enabled sites if omitted.",
    )
    parser.add_argument(
        "--no-dedup",
        action="store_true",
        dest="no_dedup",
        help="Skip deduplication — report all records regardless of prior runs. "
             "Useful for testing / backfilling.",
    )
    args = parser.parse_args()

    config = load_config()
    setup_logging(config["logging"]["dir"], config["logging"]["level"])
    logger = logging.getLogger("runner")

    browser_cfg = config["browser"].copy()
    if args.inspect:
        browser_cfg["headless"] = False
        logger.info("--inspect: browser will be visible")

    storage = CaseStorage()
    output  = CSVOutput(
        output_dir=config["output"]["dir"],
        filename_prefix=config["output"]["filename_prefix"],
    )

    total_new: list = []

    for site_id, site_config in config["sites"].items():
        if not site_config.get("enabled", True):
            logger.info(f"Skipping disabled site: {site_id}")
            continue
        if args.site and args.site != site_id:
            continue

        scraper_class = SCRAPER_MAP.get(site_id)
        if not scraper_class:
            logger.warning(f"No scraper registered for '{site_id}' — add it to scrapers/__init__.py")
            continue

        logger.info(f"{'─'*60}")
        logger.info(f"Site: {site_config['name']}")
        logger.info(f"{'─'*60}")

        scraper = scraper_class(site_config, browser_cfg)
        all_records = []

        for party in site_config.get("search_parties", []):
            try:
                records = scraper.scrape(party)
                logger.info(f"  '{party}' → {len(records)} total record(s) found on site")
                all_records.extend(records)
            except Exception as exc:
                logger.error(f"  Failed scraping '{party}': {exc}", exc_info=True)

        if args.no_dedup:
            new_records = all_records
            logger.info("  (dedup skipped)")
        else:
            new_records = storage.filter_new(all_records)
            logger.info(f"  After dedup: {len(new_records)} new record(s)")

        if new_records:
            if not args.no_dedup:
                storage.mark_seen(new_records)
            csv_path = output.write(new_records)
            logger.info(f"  Saved → {csv_path}")

        total_new.extend(new_records)

    logger.info(f"{'═'*60}")
    logger.info(output.summary(total_new))
    logger.info(f"Total new records this run: {len(total_new)}")
    logger.info(f"Total cases in database:    {storage.total_seen()}")


if __name__ == "__main__":
    main()
