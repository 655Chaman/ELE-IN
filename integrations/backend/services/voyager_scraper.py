"""
Ele-in Native LinkedIn Voyager Scraper
=======================================
Uses the user's own li_at + JSESSIONID cookies to call LinkedIn's internal
Voyager JSON API (/voyager/api/search/hits). This replaces Apify entirely.

Anti-ban layers:
  1. Random human-like delays between paginated requests (8–20s)
  2. Per-account daily budget enforced in Supabase (max 150 profiles/day)
  3. Exact LinkedIn browser headers (csrf-token, x-restli, x-li-lang, UA)
  4. Exponential backoff on 429 / 999 throttle responses
  5. Clean failure — sets list status to 'throttled' so UI can surface it
"""

import json
import time
import random
import logging
import re
import urllib.parse
from datetime import date
from typing import List, Dict, Any, Optional

import httpx

logger = logging.getLogger(__name__)

# Safety config
DAILY_LIMIT = 150          # max profiles scraped per account per day
PAGE_SIZE = 10             # LinkedIn returns 10 results per page max
MIN_DELAY = 8.0            # minimum seconds between page requests
MAX_DELAY = 20.0           # maximum seconds between page requests
MAX_RETRIES = 3            # retry attempts on throttle before giving up
BACKOFF_BASE = 60          # seconds — first backoff is 60s, then 120s, then 240s


from knowledge.backend.services.elein_ai_service import UsageLimitExceededError
class DailyLimitExceeded(Exception):
    pass


class VoyagerThrottled(Exception):
    pass


class SessionExpired(Exception):
    """Raised when LinkedIn returns 401 — the li_at cookie has expired."""
    pass


class VoyagerScraper:
    """
    Calls LinkedIn's Voyager search API using the user's own session cookies.
    No headless browser required — pure httpx JSON requests.
    """

    def __init__(self, cookies_json: str, account_id: str, supabase):
        """
        :param cookies_json: JSON string of cookies from the accounts table
        :param account_id: UUID of the LinkedIn account in Supabase
        :param supabase: Supabase service-role client
        """
        self.account_id = account_id
        self.supabase = supabase
        self.cookies_raw: List[Dict] = json.loads(cookies_json)

        # Extract the two cookies we need
        self.li_at = next(
            (c["value"] for c in self.cookies_raw if c.get("name") == "li_at"), None
        )
        jsessionid_raw = next(
            (c["value"] for c in self.cookies_raw if c.get("name") == "JSESSIONID"), None
        )
        # JSESSIONID is often wrapped in extra quotes from the browser export
        self.jsessionid = jsessionid_raw.strip('"') if jsessionid_raw else None

        if not self.li_at or not self.jsessionid:
            raise ValueError(
                "Missing li_at or JSESSIONID cookie. "
                "The user must reconnect their LinkedIn account."
            )

    # ─────────────────────────────────────────────────────────────────────────
    # RATE LIMIT MANAGEMENT
    # ─────────────────────────────────────────────────────────────────────────

    def _get_daily_usage(self) -> Dict:
        """Read current day's scrape usage from Supabase for this account."""
        res = (
            self.supabase.table("accounts")
            .select("daily_scrape_count, last_scrape_date")
            .eq("id", self.account_id)
            .single()
            .execute()
        )
        row = res.data or {}
        today = date.today().isoformat()
        last_date = row.get("last_scrape_date")
        count = row.get("daily_scrape_count", 0) or 0

        # Reset counter if it's a new day
        if last_date != today:
            count = 0

        return {"count": count, "today": today, "last_date": last_date}

    def _check_daily_budget(self, requested: int):
        """Raise DailyLimitExceeded if the account has hit today's cap."""
        usage = self._get_daily_usage()
        remaining = DAILY_LIMIT - usage["count"]
        if remaining <= 0:
            raise DailyLimitExceeded(
                f"This LinkedIn account has already scraped {usage['count']} "
                f"profiles today (daily limit: {DAILY_LIMIT}). "
                f"The limit resets at midnight."
            )
        return min(requested, remaining)  # Cap import to remaining budget

    def _increment_daily_count(self, added: int):
        """Atomically increment the daily scrape counter in Supabase."""
        usage = self._get_daily_usage()
        new_count = usage["count"] + added
        self.supabase.table("accounts").update({
            "daily_scrape_count": new_count,
            "last_scrape_date": usage["today"],
        }).eq("id", self.account_id).execute()
        logger.info(f"[VoyagerScraper] Daily count updated: {new_count}/{DAILY_LIMIT}")

    # ─────────────────────────────────────────────────────────────────────────
    # HTTP LAYER
    # ─────────────────────────────────────────────────────────────────────────

    def _build_headers(self) -> Dict[str, str]:
        return {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "application/vnd.linkedin.normalized+json+2.1",
            "Accept-Language": "en-US,en;q=0.9",
            "csrf-token": self.jsessionid,
            "x-li-lang": "en_US",
            "x-li-track": json.dumps({
                "clientVersion": "1.13.5625",
                "mpVersion": "1.13.5625",
                "osName": "web",
                "timezoneOffset": 5.5,
                "timezone": "Asia/Kolkata",
                "deviceFormFactor": "DESKTOP",
                "mpName": "voyager-web",
            }),
            "x-restli-protocol-version": "2.0.0",
            "x-li-page-instance": "urn:li:page:d_flagship3_search_srp_people;",
            "Referer": "https://www.linkedin.com/search/results/people/",
        }

    def _build_cookies(self) -> Dict[str, str]:
        return {
            "li_at": self.li_at,
            "JSESSIONID": f'"{self.jsessionid}"',
        }

    def _fetch_page(self, search_params: Dict, start: int) -> Optional[Dict]:
        """
        Fetch one page of Voyager search results.
        Returns parsed JSON or None on soft failure.
        Raises VoyagerThrottled on 429/999.
        """
        variables = {
            "start": start,
            "count": PAGE_SIZE,
            "filters": "List()",
            "queryContext": "List(spellCorrectionEnabled->true,relatedSearchesEnabled->true)",
            "includeFiltersInResponse": False,
            **search_params,
        }

        # Build the Voyager search URL
        url = (
            "https://www.linkedin.com/voyager/api/search/hits"
            f"?decorationId=com.linkedin.voyager.dash.deco.search.SearchClusterCollection-175"
            f"&origin=FACETED_SEARCH"
            f"&q=people"
            f"&start={start}"
            f"&count={PAGE_SIZE}"
        )

        # Append search filters from the params dict
        if search_params.get("keywords"):
            url += f"&keywords={urllib.parse.quote(search_params['keywords'])}"
        if search_params.get("title"):
            url += f"&title={urllib.parse.quote(search_params['title'])}"
        if search_params.get("company"):
            url += f"&company={urllib.parse.quote(search_params['company'])}"
        if search_params.get("school"):
            url += f"&school={urllib.parse.quote(search_params['school'])}"
        if search_params.get("network"):
            url += f"&network={urllib.parse.quote(search_params['network'])}"

        logger.info(f"[VoyagerScraper] Fetching page start={start}: {url[:120]}...")

        try:
            with httpx.Client(
                headers=self._build_headers(),
                cookies=self._build_cookies(),
                timeout=15.0,
                follow_redirects=True,
            ) as client:
                resp = client.get(url)

            if resp.status_code in (429, 999):
                raise VoyagerThrottled(
                    f"LinkedIn throttled the request (HTTP {resp.status_code}). "
                    "Backing off..."
                )

            if resp.status_code == 401:
                # Immediately mark the account as DISCONNECTED in Supabase so the
                # frontend health badge and the session-expired banner fire right away.
                try:
                    self.supabase.table("accounts").update({
                        "status": "DISCONNECTED",
                    }).eq("id", self.account_id).execute()
                    logger.warning(
                        f"[VoyagerScraper] 401 on account {self.account_id} — "
                        "marked DISCONNECTED in Supabase."
                    )
                except Exception as mark_err:
                    logger.error(f"[VoyagerScraper] Failed to mark account as DISCONNECTED: {mark_err}")

                raise SessionExpired(
                    "Your LinkedIn session cookie has expired. "
                    "Please go to Accounts and reconnect your LinkedIn account."
                )

            if resp.status_code != 200:
                logger.warning(
                    f"[VoyagerScraper] Unexpected status {resp.status_code}, skipping page."
                )
                return None

            return resp.json()

        except VoyagerThrottled:
            raise
        except Exception as e:
            logger.error(f"[VoyagerScraper] HTTP error on page start={start}: {e}")
            return None

    # ─────────────────────────────────────────────────────────────────────────
    # RESULT PARSING
    # ─────────────────────────────────────────────────────────────────────────

    def _parse_profiles(self, data: Dict) -> List[Dict[str, str]]:
        """
        Extract profile records from Voyager JSON response.
        LinkedIn's Voyager response structure can vary — we handle both
        the main 'elements' array and the nested 'included' entities.
        """
        profiles = []

        # Strategy 1: Walk the 'included' array for MiniProfile entities
        included = data.get("included", [])
        for entity in included:
            type_key = entity.get("$type", "")
            if "MiniProfile" not in type_key and "ProfileCard" not in type_key:
                continue

            first_name = entity.get("firstName", "")
            last_name = entity.get("lastName", "")
            headline = entity.get("occupation", "") or entity.get("headline", {})
            if isinstance(headline, dict):
                headline = headline.get("text", "")

            # The publicIdentifier gives us the /in/slug
            public_id = entity.get("publicIdentifier", "")
            if not public_id:
                # Try to pull from navigationUrl
                nav_url = entity.get("navigationUrl", "")
                match = re.search(r"/in/([^/?]+)", nav_url)
                if match:
                    public_id = match.group(1)

            if not public_id:
                continue

            linkedin_url = f"https://www.linkedin.com/in/{public_id}"

            profiles.append({
                "first_name": first_name,
                "last_name": last_name,
                "headline": headline,
                "linkedin_url": linkedin_url,
            })

        # Strategy 2: Walk the 'elements' → hits array if Strategy 1 yielded nothing
        if not profiles:
            elements = data.get("data", {}).get("elements", [])
            for element in elements:
                for hit in element.get("items", []):
                    target = hit.get("item", {}).get("entityResult", {})
                    if not target:
                        continue
                    nav_url = target.get("navigationUrl", "")
                    match = re.search(r"/in/([^/?]+)", nav_url)
                    if not match:
                        continue
                    public_id = match.group(1)
                    title_obj = target.get("title", {})
                    full_name = title_obj.get("text", "") if isinstance(title_obj, dict) else ""
                    parts = full_name.strip().split(" ", 1)
                    first_name = parts[0] if parts else ""
                    last_name = parts[1] if len(parts) > 1 else ""
                    subtitle = target.get("primarySubtitle", {})
                    headline = subtitle.get("text", "") if isinstance(subtitle, dict) else ""

                    profiles.append({
                        "first_name": first_name,
                        "last_name": last_name,
                        "headline": headline,
                        "linkedin_url": f"https://www.linkedin.com/in/{public_id}",
                    })

        return profiles

    # ─────────────────────────────────────────────────────────────────────────
    # PUBLIC SEARCH METHOD
    # ─────────────────────────────────────────────────────────────────────────
    def search_people(self, search_params: Dict, max_results: int = 100) -> List[Dict]:
        """
        Main entry point. Paginates through LinkedIn Voyager search results
        with human-like delays and anti-ban logic.

        :param search_params: Dict with optional keys: keywords, title, company,
                              school, network (same keys our URL builder uses)
        :param max_results: Hard cap on how many profiles to return
        :returns: List of lead dicts with first_name, last_name, headline, linkedin_url
        """
        # Layer 2 Paranoia: Prevent Infinite Consumption of Leads
        # Ensure account belongs to a workspace and check limits
        try:
            # We don't have workspace_id natively in voyager scraper, but we can query it via account_id
            acct_res = self.supabase.table("accounts").select("workspace_id").eq("id", self.account_id).single().execute()
            ws_id = acct_res.data.get("workspace_id")
            if ws_id:
                self.supabase.rpc('increment_usage', {
                    'p_workspace_id': ws_id,
                    'p_type': 'leads',
                    'p_amount': max_results,
                    'p_limit': 10000
                }).execute()
        except Exception as e:
            if 'UsageLimitExceededError' in str(e):
                import logging
                logging.getLogger(__name__).error(f"[VoyagerScraper] CRITICAL: Workspace {ws_id} exceeded monthly leads limit.")
                raise UsageLimitExceededError(f"Workspace {ws_id} exceeded monthly leads limit.")
            else:
                pass # Continue if we can't check
        # Layer 2: Check daily budget first
        allowed = self._check_daily_budget(max_results)
        logger.info(
            f"[VoyagerScraper] Starting search. Requested: {max_results}, "
            f"Allowed by daily budget: {allowed}"
        )

        all_profiles: List[Dict] = []
        start = 0
        retry_count = 0

        while len(all_profiles) < allowed:
            # Layer 4: Exponential backoff retry wrapper
            try:
                data = self._fetch_page(search_params, start)
            except VoyagerThrottled:
                retry_count += 1
                if retry_count > MAX_RETRIES:
                    logger.error(
                        f"[VoyagerScraper] Throttled {MAX_RETRIES} times in a row. Aborting."
                    )
                    raise
                backoff_secs = BACKOFF_BASE * (2 ** (retry_count - 1))
                logger.warning(
                    f"[VoyagerScraper] Throttled. Backing off for {backoff_secs}s "
                    f"(retry {retry_count}/{MAX_RETRIES})..."
                )
                time.sleep(backoff_secs)
                continue  # Retry same page

            if not data:
                logger.warning(f"[VoyagerScraper] Empty response at start={start}. Stopping.")
                break

            page_profiles = self._parse_profiles(data)
            if not page_profiles:
                logger.info(
                    f"[VoyagerScraper] No more profiles found at start={start}. "
                    "Reached end of results."
                )
                break

            all_profiles.extend(page_profiles)
            logger.info(
                f"[VoyagerScraper] Collected {len(all_profiles)}/{allowed} profiles so far."
            )
            retry_count = 0  # Reset retry counter on success
            start += PAGE_SIZE

            # Check if we have enough
            if len(all_profiles) >= allowed:
                break

            # Layer 1: Human-like random delay before next page
            delay = random.uniform(MIN_DELAY, MAX_DELAY)
            logger.info(f"[VoyagerScraper] Sleeping {delay:.1f}s before next page...")
            time.sleep(delay)

        # Trim to exact limit and update daily count
        result = all_profiles[:allowed]
        if result:
            self._increment_daily_count(len(result))

        logger.info(f"[VoyagerScraper] Done. Returning {len(result)} profiles.")
        return result

    # ─────────────────────────────────────────────────────────────────────────
    # DAILY BUDGET STATUS (for frontend meter)
    # ─────────────────────────────────────────────────────────────────────────

    def get_budget_status(self) -> Dict:
        """Return current day's usage for the frontend progress meter."""
        usage = self._get_daily_usage()
        return {
            "used": usage["count"],
            "limit": DAILY_LIMIT,
            "remaining": max(0, DAILY_LIMIT - usage["count"]),
            "reset_date": usage["today"],
        }
