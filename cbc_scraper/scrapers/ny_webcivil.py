"""
NY WebCivil Supreme — Party Search scraper.
https://iapps.courts.state.ny.us/webcivil/FCASSearch?param=P

HOW IT WORKS
────────────
1.  Opens a real Chromium browser (via Playwright) — required because the site
    returns 403 to plain HTTP requests.
2.  Navigates to the party search form.
3.  Fills in the party name, sets Role → "All Roles", Status → "Open",
    Future Appearances → "No", then submits.
4.  Parses every results page into CaseRecord objects, following pagination
    until there are no more pages.
5.  Returns all records — deduplication happens in the runner.

SELECTOR NOTES  ⚠  READ BEFORE FIRST RUN
──────────────────────────────────────────
Because the site blocks automated HTTP fetches, I could not inspect the live
HTML. The selectors below are educated guesses based on common patterns in
NY court web apps. Run with --inspect (headless=false) on first use and check:

  • _PARTY_INPUT    — the text box for party / business name
  • _ROLE_SELECT    — the Role dropdown
  • _STATUS_SELECT  — the Case Status dropdown
  • _FUTURE_SELECT  — the Future Appearances dropdown
  • _SUBMIT         — the search / submit button
  • _RESULTS_TABLE  — the <table> that holds result rows
  • _NEXT_PAGE      — the "Next" pagination link

Update the constants below once confirmed. The scraper will also take a
screenshot named debug_<party>.png in the working directory any time it
catches a form or parse error, to help diagnose selector mismatches.
"""

import asyncio
import logging
from datetime import datetime

from patchright.async_api import async_playwright, Page, Browser

from .base import BaseScraper, CaseRecord

logger = logging.getLogger(__name__)

# ── URL ───────────────────────────────────────────────────────────────────────
_URL = "https://iapps.courts.state.ny.us/webcivil/FCASSearch?param=P"

# ── Form selectors  (confirmed from live page field dump) ─────────────────────
_PARTY_INPUT   = "input[name='txtPlaintiffLname']"              # Business / party name
_ROLE_RADIO    = "input[name='rdRepresents'][value='AllRoles']" # Role: All Roles (radio)
_STATUS_RADIO  = "input[name='rbStatus'][value='open']"         # Status: Open (radio)
_FUTURE_RADIO  = "input[name='rbFutureCases'][value='N']"       # Future appearances: No (radio)
_SUBMIT        = "input[name='btnFindCase']"                    # "Find Case(s)" button

# ── Results selectors  (⚠ provisional — confirm on first --inspect run) ───────
_RESULTS_TABLE = "table"          # Main results table — tighten after first run
_NEXT_PAGE     = "a:has-text('Next')"   # Pagination next-page link

# ── Column order in the results table  (⚠ provisional) ───────────────────────
# Adjust indices below once you see the actual table columns.
# Typical NY WebCivil Supreme columns:
#   0: Index Number  1: Party Name  2: Role  3: Court  4: County
#   5: Case Type     6: Date Filed  7: Attorney / Judge
_COL = {
    "index_number": 0,
    "party_name":   1,
    "party_role":   2,
    "court":        3,
    "county":       4,
    "case_type":    5,
    "date_filed":   6,
    "attorney":     7,
}

# ── Browser user-agent (mimics a real Chrome on Windows) ─────────────────────
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


class NYWebCivilScraper(BaseScraper):
    """Scraper for NY WebCivil Supreme Court — party / business name search."""

    # ── Public entry point ────────────────────────────────────────────────────

    def scrape(self, party_name: str) -> list[CaseRecord]:
        """Synchronous wrapper — runs the async scraper and returns results."""
        return asyncio.run(self._run(party_name))

    # ── Browser orchestration ─────────────────────────────────────────────────

    async def _run(self, party_name: str) -> list[CaseRecord]:
        headless = self.browser_config.get("headless", False)
        slow_mo  = self.browser_config.get("slow_mo", 400)

        async with async_playwright() as pw:
            browser: Browser = await pw.chromium.launch(
                headless=headless,
                slow_mo=slow_mo,
            )
            context = await browser.new_context(user_agent=_USER_AGENT)
            page = await context.new_page()
            try:
                records = await self._scrape_party(page, party_name)
            finally:
                if not headless:
                    # In inspect mode: pause so you can see the results before the browser closes.
                    # Press Enter in the terminal when you're done looking.
                    logger.info("[ny_webcivil] Browser paused — press Enter in the terminal to close it.")
                    await asyncio.get_event_loop().run_in_executor(None, input)
                await browser.close()

        return records

    # ── Form fill + pagination ────────────────────────────────────────────────

    async def _scrape_party(self, page: Page, party_name: str) -> list[CaseRecord]:
        logger.info(f"[ny_webcivil] Searching: {party_name!r}")
        await page.goto(_URL, wait_until="load", timeout=60_000)

        # If there's a Terms of Use acceptance page, click through it.
        await self._accept_terms_if_present(page)

        # ── Diagnostic: dump all form fields so we can confirm selectors ──────
        fields = await page.evaluate("""() =>
            Array.from(document.querySelectorAll('input, select, textarea')).map(el => ({
                tag:         el.tagName,
                name:        el.name,
                id:          el.id,
                type:        el.type || '',
                placeholder: el.placeholder || '',
                value:       el.value || '',
            }))
        """)
        logger.info(f"[ny_webcivil] Form fields on page: {fields}")
        await page.screenshot(path="form_loaded.png")
        logger.info("[ny_webcivil] Screenshot saved: form_loaded.png")

        # ── Fill the search form ──────────────────────────────────────────────
        try:
            await page.fill(_PARTY_INPUT, party_name)
            await page.click(_ROLE_RADIO)    # All Roles
            await page.click(_STATUS_RADIO)  # Open cases
            await page.click(_FUTURE_RADIO)  # Future appearances: No
            # NOTE: if a CAPTCHA challenge appears in the browser window at this
            # point, solve it manually — then the form will submit automatically.
            await page.click(_SUBMIT)
            await page.wait_for_load_state("load", timeout=120_000)  # Extra time for CAPTCHA
        except Exception as exc:
            safe_name = party_name.replace(" ", "_").replace(",", "")
            screenshot = f"debug_{safe_name}.png"
            await page.screenshot(path=screenshot)
            logger.error(
                f"[ny_webcivil] Form fill failed for {party_name!r}. "
                f"Screenshot saved to {screenshot}. Error: {exc}"
            )
            raise

        # ── Collect results across all pages ──────────────────────────────────
        all_records: list[CaseRecord] = []
        page_num = 1

        while True:
            # Wait for page to fully settle before reading — catches redirects
            # that fire after the initial load event.
            await page.wait_for_load_state("load", timeout=60_000)
            await page.screenshot(path=f"results_page_{page_num}.png")
            logger.info(f"[ny_webcivil] Screenshot saved: results_page_{page_num}.png")
            html = await page.content()
            page_records = self._parse_results(html, party_name)
            all_records.extend(page_records)
            logger.info(f"[ny_webcivil]   page {page_num}: {len(page_records)} records")

            next_link = page.locator(_NEXT_PAGE)
            if await next_link.count() == 0:
                break

            await next_link.first.click()
            await page.wait_for_load_state("load", timeout=60_000)
            page_num += 1

        logger.info(f"[ny_webcivil] Total for {party_name!r}: {len(all_records)}")
        return all_records

    # ── HTML parsing (uses Scrapling's Adaptor) ───────────────────────────────

    def _parse_results(self, html: str, search_party: str) -> list[CaseRecord]:
        """
        Parse a single results page into CaseRecord objects.

        Uses Scrapling's Adaptor for CSS selection — the same library that
        lives in this repo. Falls back gracefully if a row is malformed.
        """
        from scrapling.parser import Adaptor

        adaptor = Adaptor(html, auto_match=False)
        records: list[CaseRecord] = []

        # Find the results table rows, skip the header row.
        rows = adaptor.css(f"{_RESULTS_TABLE} tr")[1:]

        if not rows:
            logger.warning("[ny_webcivil] No table rows found — selectors may need updating.")

        for row in rows:
            cells = row.css("td")
            if len(cells) < 4:          # Not a real data row
                continue

            def cell(idx: int) -> str:
                try:
                    return cells[idx].text.strip()
                except (IndexError, AttributeError):
                    return ""

            # Skip rows that look like sub-headers or separators.
            if not cell(_COL["index_number"]):
                continue

            records.append(CaseRecord(
                index_number = cell(_COL["index_number"]),
                party_name   = cell(_COL["party_name"]),
                party_role   = cell(_COL["party_role"]),
                court        = cell(_COL["court"]),
                county       = cell(_COL["county"]),
                case_type    = cell(_COL["case_type"]),
                date_filed   = cell(_COL["date_filed"]),
                attorney     = cell(_COL["attorney"]),
                source_site  = "ny_webcivil",
                search_party = search_party,
                scraped_at   = datetime.now().isoformat(),
            ))

        return records

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    async def _accept_terms_if_present(page: Page) -> None:
        """
        Some NY court pages show a Terms of Use agreement on first visit.
        Click Accept/Agree if present, otherwise do nothing.
        """
        for label in ("Accept", "Agree", "I Agree", "Continue"):
            btn = page.locator(f"input[value='{label}'], button:has-text('{label}')")
            if await btn.count() > 0:
                logger.info(f"[ny_webcivil] Accepting terms: clicking '{label}'")
                await btn.first.click()
                await page.wait_for_load_state("load")
                break

    @staticmethod
    async def _select_option(page: Page, selector: str, label: str) -> None:
        """
        Try to select a dropdown option by visible label text.
        Silently skips if the selector doesn't match anything on the page.
        """
        locator = page.locator(selector)
        if await locator.count() == 0:
            logger.warning(f"[ny_webcivil] Dropdown not found: {selector!r} — skipping")
            return
        try:
            await locator.select_option(label=label)
        except Exception:
            # Fall back: try selecting by value instead of label
            await locator.select_option(value=label)
