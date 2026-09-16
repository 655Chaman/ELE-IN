import json
import time
import random
import re
from typing import Dict, Any, Optional, List
from playwright.sync_api import sync_playwright, Page
class SecurityChallengeError(Exception):
    pass

class SessionExpiredError(Exception):
    """Raised when the LinkedIn session is no longer valid (e.g., password changed, logged out)."""
    pass

class LinkedInActionOutcomeUnknown(Exception):
    """Raised when an exception occurs during or after an external mutation is dispatched, meaning the outcome is unknown."""
    pass


from integrations.backend.services.linkedin_pool import global_browser_pool, BrowserPoolExhaustedError

import logging
logger = logging.getLogger(__name__)

from functools import wraps
import contextlib

REACTION_LABEL_MAP = {
    "LIKE": "Like", "CELEBRATE": "Celebrate", "SUPPORT": "Support",
    "LOVE": "Love", "INSIGHTFUL": "Insightful", "FUNNY": "Funny",
    "EMPATHY": "Insightful", "PRAISE": "Celebrate",
}

# DANGER: DO NOT instantiate Playwright directly via sync_playwright() outside of the global_browser_pool!
# Doing so will bypass the concurrency limit and instantly OOM the server.
# ALWAYS use self._get_or_create_context()!

def linkedin_action_safe(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except SecurityChallengeError as e:
            logger.error(f"Security challenge encountered: {e}")
            return {"status": "security_challenge"}
        except SessionExpiredError as e:
            logger.error(f"Session expired: {e}")
            return {"status": "session_expired"}
        except BrowserPoolExhaustedError as e:
            logger.error(f"Browser pool exhausted: {e}")
            return {"status": "pool_exhausted"}
        except LinkedInActionOutcomeUnknown:
            raise
        except Exception as e:
            return {"status": "error", "error": str(e)}
    return wrapper

# WARNING: DO NOT apply with_retries to message-send actions.
# A network ambiguity after send will retry and DOUBLE-SEND the message.
# Only safe for read-only or idempotent operations.
def with_retries(max_retries=3):
    """
    Layer 2: Add structural guards against developer mistakes.
    # RESILIENCE: All DB mutations in workers MUST be wrapped in this retry logic.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            import time
            delay = 1
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    # Layer 1 Paranoia: What if the error is a 400 Bad Request?
                    # Retrying a bad request is pointless and wastes time.
                    err_str = str(e).lower()
                    if "400" in err_str or "bad request" in err_str:
                        raise e
                    
                    if attempt == max_retries - 1:
                        raise e
                    
                    time.sleep(delay)
                    delay *= 2
            return func(*args, **kwargs)
        return wrapper
    return decorator

class LinkedInWorker:
    """
    Playwright-backed LinkedIn browser automation worker.
    All actions use cookies injected from the saved session.
    Human-like delays and scrolls are applied throughout.
    """

    def __init__(self, cookies_json: str, proxy_url: str = None, account_id: str = None):
        if account_id is None:
            raise ValueError("LinkedInWorker requires a non-None account_id to prevent cross-account pool contamination.")
        self.proxy_url = proxy_url
        self.account_id = account_id
        self._last_security_event = None
        self.cookies = json.loads(cookies_json)
        for ck in self.cookies:
                if "sameSite" in ck and ck["sameSite"] not in ["Strict", "Lax", "None"]:
                    del ck["sameSite"]

    def _setup_browser_headless(self, p):
        import os
        
        launch_args = {"headless": True}
        if self.proxy_url:
            launch_args["proxy"] = {"server": self.proxy_url}
            
        browserless_url = os.environ.get("BROWSERLESS_URL")
        if browserless_url:
            browser = p.chromium.connect_over_cdp(browserless_url)
        else:
            browser = p.chromium.launch(**launch_args)
            
        proxy_config = {"server": self.proxy_url} if self.proxy_url else None
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            locale="en-US",
            proxy=proxy_config,
        )
        context.add_cookies(self.cookies)
        return browser, context

    @contextlib.contextmanager
    def _get_or_create_context(self):
        """
        Yields a page for this account from the LRU BrowserPool.
        Automatically guarantees the pool is released when the context manager exits.
        """
        account_id = self.account_id
        
        # Acquire context from bounded LRU pool (increments active_count)
        context = global_browser_pool.acquire(account_id, self._setup_browser_headless)
        try:
            context.add_cookies(self.cookies)
        except Exception:
            pass
        page = None
        
        try:
            page = context.new_page()

            def on_response(response):
                if "linkedin.com" in response.url.lower():
                    if response.status in (403, 429):
                        self._last_security_event = f"HTTP {response.status} from {response.url}"
                    if "/checkpoint" in response.url.lower():
                        self._last_security_event = f"Checkpoint URL: {response.url}" 
            page.on("response", on_response)

            yield page
        finally:
            if page:
                try:
                    page.close()
                except Exception:
                    pass
            global_browser_pool.release(account_id)

    @contextlib.contextmanager
    def _mutation_boundary(self):
        """
        Envelopes the mutation execution scope. Any exception thrown inside this boundary
        is assumed to have occurred during or after dispatch, making the LinkedIn outcome unknown.
        It coerces the exception into LinkedInActionOutcomeUnknown to enforce the fail-closed idempotency invariant.
        """
        try:
            yield
        except Exception as e:
            if isinstance(e, LinkedInActionOutcomeUnknown):
                raise
            raise LinkedInActionOutcomeUnknown(f"Unknown external outcome: {str(e)}") from e

    def _http_get(self, url: str):
        import httpx
        # Extract li_at and JSESSIONID for cookies and CSRF
        li_at = next((c["value"] for c in self.cookies if c["name"] == "li_at"), None)
        jsessionid = next((c["value"] for c in self.cookies if c["name"] == "JSESSIONID"), None)
        
        if not li_at or not jsessionid:
            raise ValueError("Missing essential cookies for HTTP offloading")
            
        # Clean JSESSIONID (often wrapped in quotes)
        csrf_token = jsessionid.strip('"')
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "csrf-token": csrf_token,
            "x-li-lang": "en_US",
            "x-restli-protocol-version": "2.0.0",
        }
        
        cookies = {
            "li_at": li_at,
            "JSESSIONID": jsessionid
        }
        
        mounts = {"all://": httpx.HTTPTransport(proxy=self.proxy_url)} if self.proxy_url else None
        
        client = httpx.Client(headers=headers, cookies=cookies, mounts=mounts, timeout=10.0)
        try:
            response = client.get(url)
            return response
        finally:
            client.close()

    def _human_delay(self, min_sec: float = 2.0, max_sec: float = 5.0):
        time.sleep(random.uniform(min_sec, max_sec))

    def _human_scroll(self, page: Page):
        page.mouse.wheel(0, random.randint(200, 600))
        self._human_delay(0.5, 1.5)

    def _safe_click(self, page: Page, selector: str) -> bool:
        try:
            el = page.locator(selector).first
            if el.is_visible(timeout=3000):
                el.click(delay=random.randint(50, 150))
                return True
        except Exception:
            pass
        return False

    # ── B4: Challenge/captcha detector ───────────────────────────────────────

    CHALLENGE_URL_PATTERNS = [
        "/checkpoint/challenge",
        "/checkpoint/rm/",
        "/uas/request-password-reset",
        "/checkpoint/lg/login-submit",
    ]
    CHALLENGE_TITLE_PATTERNS = [
        "security verification",
        "let's do a quick security check",
        "unusual activity",
        "verify it's you",
    ]

    def _check_for_challenge(self, page: Page) -> None:
        """
        B4: Raises SecurityChallengeError if LinkedIn has served a security challenge page.
        Call this immediately after every page.goto() completes.
        The orchestrator will catch this, mark the account as NEEDS_REVIEW,
        and stop processing any more leads on that account until a human clears it.
        """
        if getattr(self, '_last_security_event', None):
            raise SecurityChallengeError(self._last_security_event)
        current_url = page.url.lower()
        if "/login" in current_url or "/checkpoint/lg/login" in current_url or "session-expired" in current_url:
            raise SessionExpiredError("LinkedIn session expired or logged out.")
        current_url = page.url.lower()
        for pattern in self.CHALLENGE_URL_PATTERNS:
            if pattern in current_url:
                raise SecurityChallengeError(
                    f"B4: LinkedIn security challenge detected (url: {page.url}) — "
                    f"account requires human review before resuming"
                )
        try:
            title = (page.title() or "").lower()
        except Exception:
            title = ""
        for pattern in self.CHALLENGE_TITLE_PATTERNS:
            if pattern in title:
                raise SecurityChallengeError(
                    f"B4: LinkedIn challenge page title detected ('{title}') — "
                    f"account requires human review before resuming"
                )

    # ── B5: Session validity pre-flight ──────────────────────────────────────

    def check_session_valid(self) -> bool:
        """

        B5: Verifies that the session cookies still produce a valid LinkedIn session
        by hitting the lightweight /me GraphQL endpoint (no browser context needed).
        Returns True if the session is active.
        Returns False (and logs) if the session has expired or been revoked.
        Callers should mark the account NEEDS_REVIEW on False and skip further execution.
        """
        li_at = next((c["value"] for c in self.cookies if c["name"] == "li_at"), None)
        if not li_at:
            logger.error("[B5] No li_at cookie found — session is invalid")
            return False
        try:
            resp = self._http_get(
                "https://www.linkedin.com/voyager/api/me"
            )
            if resp.status_code == 401:
                logger.error("[B5] Session expired (401) — account needs re-authentication")
                return False
            if resp.status_code == 999:
                logger.warning("[B5] LinkedIn returning 999 (bot detection) — back off before retrying")
                return False
            if resp.status_code >= 400:
                logger.warning(f"[B5] Unexpected status {resp.status_code} on session check")
                return False
            logger.info("[B5] Session is valid")
            return True
        except Exception as e:
            logger.error(f"[B5] Session validity check failed: {e}")
            return False

    # ── C8: Human-like typing helper ─────────────────────────────────────────

    def _human_type(self, page: Page, selector: str, text: str) -> None:
        """

        C8: Types text into a field with randomized per-character delay (30-90ms)
        and micro-pauses between words, mimicking human typing rhythm.
        Playwright's default .type() already supports a delay= arg; this wraps it
        with word-boundary pauses for additional realism.
        """
        el = page.locator(selector).first
        el.click(delay=random.randint(50, 150))
        self._human_delay(0.3, 0.8)
        words = text.split(" ")
        for i, word in enumerate(words):
            el.type(word, delay=random.randint(30, 90))
            if i < len(words) - 1:
                el.type(" ", delay=random.randint(50, 130))
                if random.random() < 0.15:
                    # Occasional longer pause between words (thinking time)
                    time.sleep(random.uniform(0.2, 0.6))



    # ─────────────────────────────────────────────────────────────────────────
    # PROFILE ACTIONS
    # ─────────────────────────────────────────────────────────────────────────

    @linkedin_action_safe
    def view_profile(self, profile_url: str) -> Dict[str, Any]:
        with self._get_or_create_context() as page:

            try:
                page.goto(profile_url, wait_until="domcontentloaded")
                self._check_for_challenge(page)  # B4: halt immediately on challenge
                self._human_delay(3, 7)
                self._human_scroll(page)
                self._human_delay(2, 4)
                self._human_scroll(page)
                logger.info(f"[LIVE] view_profile: {profile_url}")
                return {"status": "success", "action": "view_profile"}


            finally:
                pass
    @linkedin_action_safe
    def follow_profile(self, profile_url: str) -> Dict[str, Any]:
        with self._get_or_create_context() as page:

            try:

                page.goto(profile_url, wait_until="domcontentloaded")
                self._check_for_challenge(page)
                self._human_delay(3, 5)
                follow_btn = page.locator("button[aria-label^='Follow']").first
                if follow_btn.is_visible(timeout=3000):
                    with self._mutation_boundary():
                        follow_btn.click(delay=random.randint(50, 150))
                        self._human_delay(1, 2)
                        return {"status": "success", "action": "follow_profile"}

                # Check under More menu
                if self._safe_click(page, "button[aria-label^='More actions']"):
                    self._human_delay(1, 2)
                    follow_option = page.locator("div[role='option']").filter(has_text="Follow").first
                    if follow_option.is_visible(timeout=2000):
                        with self._mutation_boundary():
                            follow_option.click(delay=random.randint(50, 150))
                            self._human_delay(1, 2)
                            return {"status": "success", "action": "follow_profile"}

                return {"status": "error", "error": "Follow button not found (may already be following)"}

            except LinkedInActionOutcomeUnknown:
                raise
            except Exception as e:

                return {"status": "error", "error": str(e)}




    @linkedin_action_safe
    def follow_company(self, profile_url: str) -> Dict[str, Any]:
        """Navigate to the lead's company page and follow it."""


        with self._get_or_create_context() as page:

            try:

                page.goto(profile_url, wait_until="domcontentloaded")
                self._check_for_challenge(page)
                self._human_delay(3, 5)
                # Click the company link in the Experience section
                company_link = page.locator("section[data-field='experience'] a[href*='/company/']").first
                if company_link.is_visible(timeout=3000):
                    company_href = company_link.get_attribute("href")
                    if company_href and company_href.startswith("http"):
                        full_url = company_href
                    else:
                        full_url = f"https://www.linkedin.com{company_href}"
                    page.goto(full_url, wait_until="domcontentloaded")
                    self._check_for_challenge(page)
                    self._human_delay(2, 4)
                    follow_btn = page.locator("button[aria-label^='Follow']").first
                    if follow_btn.is_visible(timeout=3000):
                        with self._mutation_boundary():
                            follow_btn.click(delay=random.randint(50, 150))
                            self._human_delay(1, 2)
                            return {"status": "success", "action": "follow_company"}

                return {"status": "error", "error": "Company page not found on profile"}

            except LinkedInActionOutcomeUnknown:
                raise
            except Exception as e:

                return {"status": "error", "error": str(e)}




    @linkedin_action_safe
    def like_post(self, profile_url: str) -> Dict[str, Any]:
        with self._get_or_create_context() as page:

            try:

                page.goto(f"{profile_url.rstrip('/')}/recent-activity/all/", wait_until="domcontentloaded")
                self._check_for_challenge(page)
                self._human_delay(4, 7)
                like_btn = page.locator("button[aria-label^='Like']").first
                if like_btn.is_visible(timeout=5000):
                    with self._mutation_boundary():
                        like_btn.click(delay=random.randint(50, 150))
                        self._human_delay(1, 3)
                        return {"status": "success", "action": "like_post"}

                return {"status": "error", "error": "No recent posts found to like"}

            except LinkedInActionOutcomeUnknown:
                raise
            except Exception as e:

                return {"status": "error", "error": str(e)}




    @linkedin_action_safe
    def react_to_post(self, profile_url: str, reaction: str = "LIKE") -> Dict[str, Any]:
        """Apply a specific reaction (LIKE, EMPATHY/Insightful, PRAISE/Celebrate) to most recent post."""


        with self._get_or_create_context() as page:

            try:
                page.goto(f"{profile_url.rstrip('/')}/recent-activity/all/", wait_until="domcontentloaded")
                self._check_for_challenge(page)
                self._human_delay(4, 7)
                # Hover over the like button to open reaction palette
                like_btn = page.locator("button[aria-label^='Like']").first
                if like_btn.is_visible(timeout=5000):
                    like_btn.hover()
                    self._human_delay(1, 2)
                    # Click the specific reaction type
                    reaction_label = REACTION_LABEL_MAP.get(reaction.upper(), reaction.capitalize())
                    reaction_btn = page.locator(f"button[aria-label='{reaction_label}']").first
                    with self._mutation_boundary():
                        if reaction_btn.is_visible(timeout=2000):
                            reaction_btn.click(delay=random.randint(50, 150))
                        else:
                            like_btn.click(delay=random.randint(50, 150))
                        self._human_delay(1, 2)
                        return {"status": "success", "action": f"react_{reaction.lower()}"}
                return {"status": "error", "error": "No posts found for reaction"}

            except LinkedInActionOutcomeUnknown:
                raise
            except Exception as e:
                return {"status": "error", "error": str(e)}

    @linkedin_action_safe
    def comment_on_post(self, profile_url: str, comment: str) -> Dict[str, Any]:
        with self._get_or_create_context() as page:

            try:
                page.goto(f"{profile_url.rstrip('/')}/recent-activity/all/", wait_until="domcontentloaded")
                self._check_for_challenge(page)
                self._human_delay(4, 7)
                comment_btn = page.locator("button[aria-label^='Comment']").first
                if comment_btn.is_visible(timeout=5000):
                    comment_btn.click(delay=random.randint(50, 150))
                    self._human_delay(1, 2)
                    textbox = page.locator("div[role='textbox']").first
                    textbox.click(delay=random.randint(50, 150))
                    self._human_type(page, "div[role=\'textbox\']", comment)
                    self._human_delay(1, 2)
                    submit = page.locator("button[type='submit']").first
                    if submit.is_visible(timeout=2000):
                        with self._mutation_boundary():
                            submit.click(delay=random.randint(50, 150))
                            return {"status": "success", "action": "comment_on_post"}
                return {"status": "error", "error": "Comment button not found"}

            except LinkedInActionOutcomeUnknown:
                raise
            except Exception as e:
                return {"status": "error", "error": str(e)}

    @linkedin_action_safe
    def endorse_skill(self, profile_url: str) -> Dict[str, Any]:
        with self._get_or_create_context() as page:

            try:
                page.goto(profile_url, wait_until="domcontentloaded")
                self._check_for_challenge(page)
                self._human_delay(3, 5)
                # Scroll to Skills section
                page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
                self._human_delay(1, 2)
                endorse_btn = page.locator("button[aria-label^='Endorse']").first
                if endorse_btn.is_visible(timeout=5000):
                    with self._mutation_boundary():
                        endorse_btn.click(delay=random.randint(50, 150))
                        self._human_delay(1, 2)
                        return {"status": "success", "action": "endorse_skill"}
                return {"status": "error", "error": "Endorse button not found"}

            except LinkedInActionOutcomeUnknown:
                raise
            except Exception as e:
                return {"status": "error", "error": str(e)}
    @linkedin_action_safe
    def repost(self, profile_url: str, comment: str = "") -> Dict[str, Any]:
        with self._get_or_create_context() as page:

            try:
                page.goto(f"{profile_url.rstrip('/')}/recent-activity/all/", wait_until="domcontentloaded")
                self._check_for_challenge(page)
                self._human_delay(4, 7)
                repost_btn = page.locator("button[aria-label^='Repost']").first
                if repost_btn.is_visible(timeout=5000):
                    repost_btn.click(delay=random.randint(50, 150))
                    self._human_delay(1, 2)
                    if comment:
                        # Choose "Repost with your thoughts"
                        with_thoughts = page.locator("button").filter(has_text="with your thoughts").first
                        if with_thoughts.is_visible(timeout=2000):
                            with_thoughts.click(delay=random.randint(50, 150))
                            self._human_delay(1, 2)
                            textbox = page.locator("div[role='textbox']").first
                            self._human_type(page, "div[role=\'textbox\']", comment)
                            self._human_delay(1, 2)
                    submit = page.locator("button[type='submit']").first
                    if submit.is_visible(timeout=2000):
                        with self._mutation_boundary():
                            submit.click(delay=random.randint(50, 150))
                            return {"status": "success", "action": "repost"}
                return {"status": "error", "error": "Repost button not found"}

            except LinkedInActionOutcomeUnknown:
                raise
            except Exception as e:
                return {"status": "error", "error": str(e)}
    @linkedin_action_safe
    def invite_to_event(self, profile_url: str, event_url: str, note: str = "") -> Dict[str, Any]:
        with self._get_or_create_context() as page:

            try:
                page.goto(event_url, wait_until="domcontentloaded")
                self._check_for_challenge(page)
                self._human_delay(3, 5)
                invite_btn = page.locator("button").filter(has_text="Invite").first
                if invite_btn.is_visible(timeout=5000):
                    invite_btn.click(delay=random.randint(50, 150))
                    self._human_delay(2, 4)
                    # Search for the lead to invite
                    search_box = page.locator("input[placeholder*='Search']").first
                    if search_box.is_visible(timeout=3000):
                        # Extract name from profile URL if possible
                        name = profile_url.rstrip("/").split("/")[-1].replace("-", " ")
                        self._human_type(page, "input[placeholder*=\'Search\']", name)
                        self._human_delay(2, 3)
                    return {"status": "success", "action": "invite_to_event"}
                return {"status": "error", "error": "Event invite button not found"}

            finally:
                pass
    # ─────────────────────────────────────────────────────────────────────────
    # CONNECTION ACTIONS
    # ─────────────────────────────────────────────────────────────────────────

    @linkedin_action_safe
    def send_connection_request(self, profile_url: str, note: Optional[str] = None, fallback: Optional[str] = None) -> Dict[str, Any]:
        with self._get_or_create_context() as page:

            try:
                page.goto(profile_url, wait_until="domcontentloaded")
                self._check_for_challenge(page)
                self._human_delay(3, 6)
                connect_clicked = False
                direct_btn = page.locator("button[aria-label^='Invite']").first
                if direct_btn.is_visible(timeout=3000):
                    direct_btn.click(delay=random.randint(50, 150))
                    connect_clicked = True
                else:
                    if self._safe_click(page, "button[aria-label^='More actions']"):
                        self._human_delay(1, 2)
                        connect_item = page.locator("div[role='option']").filter(has_text="Connect").first
                        if connect_item.is_visible(timeout=2000):
                            connect_item.click(delay=random.randint(50, 150))
                            connect_clicked = True
                if not connect_clicked:
                    return {"status": "error", "error": "Connect button not found on profile"}
                self._human_delay(2, 4)
                if note:
                    add_note_btn = page.locator("button[aria-label='Add a note']")
                    if add_note_btn.is_visible(timeout=3000):
                        add_note_btn.click(delay=random.randint(50, 150))
                        self._human_delay(1, 2)
                        textarea = page.locator("textarea[name='message']")
                        self._human_type(page, "textarea[name=\'message\']", note[:300])
                        self._human_delay(1, 2)
                    else:
                        # Can't add note — use fallback message or blank
                        logger.warning("Add note button not available — sending without note")
                send_btn = page.locator("button[aria-label='Send now']")
                if send_btn.is_visible(timeout=3000):
                    with self._mutation_boundary():
                        send_btn.click(delay=random.randint(50, 150))
                        logger.info(f"[LIVE] connection_request: {profile_url}")
                        return {"status": "success", "action": "connection_request"}
                return {"status": "error", "error": "Send button not found"}

            except LinkedInActionOutcomeUnknown:
                raise
            except Exception as e:
                return {"status": "error", "error": str(e)}
    @linkedin_action_safe
    def withdraw_connection_request(self, profile_url: str) -> Dict[str, Any]:
        with self._get_or_create_context() as page:

            try:
                page.goto(profile_url, wait_until="domcontentloaded")
                self._check_for_challenge(page)
                self._human_delay(3, 5)
                pending_btn = page.locator("button").filter(has_text="Pending").first
                if pending_btn.is_visible(timeout=3000):
                    pending_btn.click(delay=random.randint(50, 150))
                    self._human_delay(1, 2)
                    withdraw_btn = page.locator("button").filter(has_text="Withdraw").first
                    if withdraw_btn.is_visible(timeout=2000):
                        withdraw_btn.click(delay=random.randint(50, 150))
                        self._human_delay(1, 2)
                        confirm = page.locator("div[role='dialog'] button").filter(has_text="Withdraw").first
                        if confirm.is_visible(timeout=2000):
                            with self._mutation_boundary():
                                confirm.click(delay=random.randint(50, 150))
                                return {"status": "success", "action": "withdraw_request"}
                        return {"status": "error", "error": "Confirm withdraw button not found"}
                return {"status": "error", "error": "No pending request found to withdraw"}

            except LinkedInActionOutcomeUnknown:
                raise
            except Exception as e:
                return {"status": "error", "error": str(e)}

    @linkedin_action_safe
    def remove_connection(self, profile_url: str) -> Dict[str, Any]:
        with self._get_or_create_context() as page:

            try:
                page.goto(profile_url, wait_until="domcontentloaded")
                self._check_for_challenge(page)
                self._human_delay(3, 5)
                if self._safe_click(page, "button[aria-label^='More actions']"):
                    self._human_delay(1, 2)
                    remove_item = page.locator("div[role='option']").filter(has_text="Remove connection").first
                    if remove_item.is_visible(timeout=2000):
                        remove_item.click(delay=random.randint(50, 150))
                        self._human_delay(1, 2)
                        confirm = page.locator("button").filter(has_text="Remove").first
                        if confirm.is_visible(timeout=2000):
                            with self._mutation_boundary():
                                confirm.click(delay=random.randint(50, 150))
                                return {"status": "success", "action": "remove_connection"}
                        return {"status": "error", "error": "Confirm remove button not found"}
                return {"status": "error", "error": "Remove connection option not found"}

            except LinkedInActionOutcomeUnknown:
                raise
            except Exception as e:
                return {"status": "error", "error": str(e)}
    # ─────────────────────────────────────────────────────────────────────────
    # MESSAGING ACTIONS
    # ─────────────────────────────────────────────────────────────────────────

    @linkedin_action_safe
    def send_message(self, profile_url: str, message: str) -> Dict[str, Any]:
        with self._get_or_create_context() as page:

            try:
                page.goto(profile_url, wait_until="domcontentloaded")
                self._check_for_challenge(page)
                self._human_delay(3, 5)
                if self._safe_click(page, "button[aria-label^='Message']"):
                    self._human_delay(2, 4)
                    textbox = page.locator("div[role='textbox']").first
                    if textbox.is_visible(timeout=3000):
                        textbox.click(delay=random.randint(50, 150))
                        self._human_type(page, "div[role=\'textbox\']", message)
                        self._human_delay(1, 3)
                        submit_btn = page.locator("button[type='submit']").first
                        if submit_btn.is_visible(timeout=3000):
                            with self._mutation_boundary():
                                submit_btn.click(delay=random.randint(50, 150))
                                logger.info(f"[LIVE] send_message: {profile_url}")
                                return {"status": "success", "action": "send_message"}
                return {"status": "error", "error": "Message button or textbox not found"}

            except LinkedInActionOutcomeUnknown:
                raise
            except Exception as e:
                return {"status": "error", "error": str(e)}

    @linkedin_action_safe
    def send_inmail(self, profile_url: str, subject: str, body: str) -> Dict[str, Any]:
        with self._get_or_create_context() as page:

            try:
                page.goto(profile_url, wait_until="domcontentloaded")
                self._check_for_challenge(page)
                self._human_delay(3, 5)
                if self._safe_click(page, "button[aria-label^='More actions']"):
                    self._human_delay(1, 2)
                    inmail_btn = page.locator("div[role='option']").filter(has_text="Message").first
                    if inmail_btn.is_visible(timeout=2000):
                        inmail_btn.click(delay=random.randint(50, 150))
                        self._human_delay(2, 4)
                        if subject:
                            subj_input = page.locator("input[name='subject']").first
                            if subj_input.is_visible(timeout=2000):
                                self._human_type(page, "input[name=\'subject\']", subject[:200])
                                self._human_delay(0.5, 1)
                        textbox = page.locator("div[role='textbox']").first
                        if textbox.is_visible(timeout=3000):
                            self._human_type(page, "div[role=\'textbox\']", body)
                            self._human_delay(1, 3)
                            submit_btn = page.locator("button[type='submit']").first
                            if submit_btn.is_visible(timeout=3000):
                                with self._mutation_boundary():
                                    submit_btn.click(delay=random.randint(50, 150))
                                    logger.info(f"[LIVE] send_inmail: {profile_url}")
                                    return {"status": "success", "action": "send_inmail"}
                return {"status": "error", "error": "InMail modal not found"}

            except LinkedInActionOutcomeUnknown:
                raise
            except Exception as e:
                return {"status": "error", "error": str(e)}

    @linkedin_action_safe
    def send_message_with_attachment(self, profile_url: str, body: str, attachment_url: str, attachment_type: str = "document") -> Dict[str, Any]:
        """Send a message and then paste the attachment URL inline (LinkedIn downloads/previews from URL)."""


        with self._get_or_create_context() as page:

            try:
                page.goto(profile_url, wait_until="domcontentloaded")
                self._check_for_challenge(page)
                self._human_delay(3, 5)
                if self._safe_click(page, "button[aria-label^='Message']"):
                    self._human_delay(2, 4)
                    textbox = page.locator("div[role='textbox']").first
                    if textbox.is_visible(timeout=3000):
                        full_message = f"{body}\n\n{attachment_url}" if attachment_url else body
                        self._human_type(page, "div[role=\'textbox\']", full_message.strip())
                        self._human_delay(1, 3)
                        submit_btn = page.locator("button[type='submit']").first
                        if submit_btn.is_visible(timeout=3000):
                            with self._mutation_boundary():
                                submit_btn.click(delay=random.randint(50, 150))
                                logger.info(f"[LIVE] send_message_with_{attachment_type}: {profile_url}")
                                return {"status": "success", "action": f"send_{attachment_type}_message"}
                return {"status": "error", "error": "Message dialog not available"}

            except LinkedInActionOutcomeUnknown:
                raise
            except Exception as e:
                return {"status": "error", "error": str(e)}
    # ─────────────────────────────────────────────────────────────────────────
    # CONDITION CHECKS (Playwright scrapers)
    # ─────────────────────────────────────────────────────────────────────────

    def check_if_connected(self, profile_url: str) -> Dict[str, Any]:
        """Returns branch: 'Connected' or 'Not connected'."""


        with self._get_or_create_context() as page:

            try:
                page.goto(profile_url, wait_until="domcontentloaded")
                self._check_for_challenge(page)
                self._human_delay(3, 5)
                # 1st-degree badge or Message button indicates connected
                msg_btn = page.locator("button[aria-label^='Message']").first
                degree_badge = page.locator("span.dist-value").first
                if msg_btn.is_visible(timeout=3000):
                    branch = "Connected"
                elif degree_badge.is_visible(timeout=2000) and "1st" in degree_badge.inner_text():
                    branch = "Connected"
                else:
                    branch = "Not connected"
                return {"status": "success", "branch": branch}
            except (SecurityChallengeError, SessionExpiredError):
                raise  # Never fail-open on security events
            except Exception as e:
                logger.warning(f"check_if_connected DOM lookup error: {e}")
                return {"status": "success", "branch": "Not connected"}

    def check_if_replied(self, profile_url: str) -> Dict[str, Any]:
        """Checks the LinkedIn messaging inbox for a reply from this profile."""


        with self._get_or_create_context() as page:

            try:
                page.goto("https://www.linkedin.com/messaging/", wait_until="domcontentloaded")
                self._check_for_challenge(page)
                self._human_delay(3, 5)
                # Extract lead name from profile URL to search
                slug = profile_url.rstrip("/").split("/in/")[-1].replace("-", " ").title()
                search_input = page.locator("input[placeholder*='Search']").first
                if search_input.is_visible(timeout=3000):
                    self._human_type(page, "input[placeholder*=\'Search\']", slug)
                    self._human_delay(2, 3)
                    thread = page.locator("li.msg-conversation-listitem").first
                    if thread.is_visible(timeout=3000):
                        thread.click(delay=random.randint(50, 150))
                        self._human_delay(2, 3)
                        # Check if the most recent message is from them (not us)
                        last_msg = page.locator(".msg-s-event-listitem").last
                        sender = last_msg.locator(".msg-s-event-listitem__link").first
                        if sender.is_visible(timeout=2000):
                            sender_text = sender.inner_text()
                            if slug.lower() in sender_text.lower():
                                return {"status": "success", "branch": "Replied"}
                return {"status": "success", "branch": "No reply"}
            except (SecurityChallengeError, SessionExpiredError):
                raise  # Never fail-open on security events
            except Exception as e:
                logger.warning(f"check_if_replied DOM lookup error: {e}")
                return {"status": "success", "branch": "No reply"}

    def check_open_profile(self, profile_url: str) -> Dict[str, Any]:
        """Checks if the profile is an open profile (allows free InMail)."""


        with self._get_or_create_context() as page:

            try:
                page.goto(profile_url, wait_until="domcontentloaded")
                self._check_for_challenge(page)
                self._human_delay(3, 5)
                # Open profile shows "Message" even without connection + "Open" badge
                open_badge = page.locator("span").filter(has_text="Open").first
                msg_btn = page.locator("button[aria-label^='Message']").first
                if open_badge.is_visible(timeout=2000) and msg_btn.is_visible(timeout=3000):
                    branch = "Open"
                else:
                    branch = "Not open"
                return {"status": "success", "branch": branch}
            except (SecurityChallengeError, SessionExpiredError):
                raise  # Never fail-open on security events
            except Exception as e:
                logger.warning(f"check_open_profile DOM lookup error: {e}")
                return {"status": "success", "branch": "Not open"}

    def check_premium_badge(self, profile_url: str) -> Dict[str, Any]:
        with self._get_or_create_context() as page:

            try:
                page.goto(profile_url, wait_until="domcontentloaded")
                self._check_for_challenge(page)
                self._human_delay(3, 5)
                premium_icon = page.locator("li-icon[type='linkedin-premium-gold-icon']").first
                if premium_icon.is_visible(timeout=3000):
                    return {"status": "success", "branch": "Premium"}
                return {"status": "success", "branch": "Free"}
            except (SecurityChallengeError, SessionExpiredError):
                raise  # Never fail-open on security events
            except Exception as e:
                logger.warning(f"check_premium_badge DOM lookup error: {e}")
                return {"status": "success", "branch": "Free"}

    def get_mutual_connection_count(self, profile_url: str) -> Dict[str, Any]:
        with self._get_or_create_context() as page:

            try:
                page.goto(profile_url, wait_until="domcontentloaded")
                self._check_for_challenge(page)
                self._human_delay(3, 5)
                mutual_link = page.locator("a[href*='mutual']").first
                if mutual_link.is_visible(timeout=3000):
                    text = mutual_link.inner_text()
                    nums = [int(s) for s in text.split() if s.isdigit()]
                    count = nums[0] if nums else 0
                else:
                    count = 0
                return {"status": "success", "count": count}
            except Exception as e:
                return {"status": "success", "count": 0}

    def check_recently_active(self, profile_url: str, days: int = 7) -> Dict[str, Any]:
        """Checks if they have a recent post within N days."""


        with self._get_or_create_context() as page:

            try:
                page.goto(f"{profile_url.rstrip('/')}/recent-activity/all/", wait_until="domcontentloaded")
                self._check_for_challenge(page)
                self._human_delay(3, 5)
                # Look for posts with timestamp — simplistic: any post visible = active
                post = page.locator(".feed-shared-update-v2").first
                if post.is_visible(timeout=5000):
                    return {"status": "success", "branch": "Active"}
                return {"status": "success", "branch": "Inactive"}
            except (SecurityChallengeError, SessionExpiredError):
                raise  # Never fail-open on security events
            except Exception as e:
                logger.warning(f"check_recently_active DOM lookup error: {e}")
                return {"status": "success", "branch": "Inactive"}

    def check_has_recent_posts(self, profile_url: str, days: int = 30) -> Dict[str, Any]:
            return self.check_recently_active(profile_url, days)


    def check_company_hiring(self, profile_url: str, role_filter: str = "") -> Dict[str, Any]:
        with self._get_or_create_context() as page:

            try:
                page.goto(profile_url, wait_until="domcontentloaded")
                self._check_for_challenge(page)
                self._human_delay(3, 5)
                hiring_link = page.locator("a[href*='jobs']").filter(has_text="hiring").first
                if not hiring_link.is_visible(timeout=3000):
                    hiring_link = page.locator("a").filter(has_text="See all jobs").first
                if hiring_link.is_visible(timeout=2000):
                    return {"status": "success", "branch": "Hiring"}
                return {"status": "success", "branch": "Not hiring"}
            except (SecurityChallengeError, SessionExpiredError):
                raise  # Never fail-open on security events
            except Exception as e:
                logger.warning(f"check_company_hiring DOM lookup error: {e}")
                return {"status": "success", "branch": "Not hiring"}

    def check_connection_pending(self, profile_url: str) -> Dict[str, Any]:
        with self._get_or_create_context() as page:

            try:
                page.goto(profile_url, wait_until="domcontentloaded")
                self._check_for_challenge(page)
                self._human_delay(3, 5)
                pending_btn = page.locator("button").filter(has_text="Pending").first
                if pending_btn.is_visible(timeout=3000):
                    return {"status": "success", "branch": "Still pending"}
                return {"status": "success", "branch": "Accepted or withdrawn"}
            except (SecurityChallengeError, SessionExpiredError):
                raise  # Never fail-open on security events
            except Exception as e:
                logger.warning(f"check_connection_pending DOM lookup error: {e}")
                return {"status": "success", "branch": "Accepted or withdrawn"}

    # ─────────────────────────────────────────────────────────────────────────
    # ENRICHMENT SCRAPING
    # ─────────────────────────────────────────────────────────────────────────

    def extract_company_url(self, profile_url: str) -> Dict[str, Any]:
        with self._get_or_create_context() as page:

            try:
                page.goto(profile_url, wait_until="domcontentloaded")
                self._check_for_challenge(page)
                self._human_delay(3, 5)
                company_link = page.locator("section[data-field='experience'] a[href*='/company/']").first
                if company_link.is_visible(timeout=3000):
                    href = company_link.get_attribute("href")
                    if href and href.startswith("http"):
                        full_url = href
                    else:
                        full_url = f"https://www.linkedin.com{href}"
                    return {"status": "success", "branch": "Found", "company_url": full_url}
                return {"status": "success", "branch": "Not found"}
            except Exception as e:
                return {"status": "success", "branch": "Not found"}

    def extract_company_website(self, profile_url: str) -> Dict[str, Any]:
        """Navigate to the company page and grab the website link."""
        result = self.extract_company_url(profile_url)
        if result.get("branch") != "Found":
            return {"status": "success", "branch": "Not found"}
        company_url = result.get("company_url", "")
        with self._get_or_create_context() as page:
            try:
                page.goto(company_url, wait_until="domcontentloaded")
                self._check_for_challenge(page)
                self._human_delay(2, 4)
                website_link = page.locator("a[data-field='company_website']").first
                if website_link.is_visible(timeout=3000):
                    website = website_link.get_attribute("href") or website_link.inner_text()
                    return {"status": "success", "branch": "Found", "company_website": website}
                return {"status": "success", "branch": "Not found"}
            except Exception as e:
                return {"status": "success", "branch": "Not found"}

    def extract_company_headcount(self, profile_url: str) -> Dict[str, Any]:
        result = self.extract_company_url(profile_url)
        if result.get("branch") != "Found":
            return {"status": "success", "branch": "Not found", "headcount": 0}
        company_url = result.get("company_url", "")
        with self._get_or_create_context() as page:
            try:
                page.goto(company_url + "about/", wait_until="domcontentloaded")
                self._check_for_challenge(page)
                self._human_delay(2, 4)
                headcount_str = page.locator("dd.t-normal").filter(has_text="employees").first
                if headcount_str.is_visible(timeout=3000):
                    text = headcount_str.inner_text()
                    nums = [int(n) for n in re.findall(r'\d+', text.replace(',', ''))]
                    count = nums[0] if nums else 0
                    return {"status": "success", "branch": "Found", "headcount": count}
                return {"status": "success", "branch": "Not found", "headcount": 0}
            except Exception as e:
                return {"status": "success", "branch": "Not found", "headcount": 0}

    def get_activity_score(self, profile_url: str) -> Dict[str, Any]:
        """Counts visible posts to classify activity level."""


        with self._get_or_create_context() as page:

            try:
                page.goto(f"{profile_url.rstrip('/')}/recent-activity/all/", wait_until="domcontentloaded")
                self._check_for_challenge(page)
                self._human_delay(3, 5)
                posts = page.locator(".feed-shared-update-v2").all()
                count = len(posts)
                if count >= 4:
                    branch = "Active (>4 posts/month)"
                elif count >= 1:
                    branch = "Passive (1-4)"
                else:
                    branch = "Inactive (<1)"
                return {"status": "success", "branch": branch, "post_count": count}
            except Exception as e:
                return {"status": "success", "branch": "Inactive (<1)", "post_count": 0}


    
    @linkedin_action_safe
    def scrape_basic_profile_dom(self, profile_url: str) -> Dict[str, Any]:
        """


            C4: Scrapes basic profile data using Playwright DOM extraction instead of HTTP/Voyager.

            Prevents TLS fingerprint mismatch by routing traffic through the Chromium browser.

        """


        with self._get_or_create_context() as page:

            try:
                page.goto(profile_url, wait_until="domcontentloaded")
                self._check_for_challenge(page)
                self._human_delay(2, 4)
            
                # Extract using selectors that match LinkedIn's current DOM
                name_loc = page.locator("h1.text-heading-xlarge").first
                title_loc = page.locator("div.text-body-medium").first
                company_loc = page.locator("button[aria-label*='Current company'] div").first
            
                name = name_loc.inner_text().strip() if name_loc.is_visible() else ""
                title = title_loc.inner_text().strip() if title_loc.is_visible() else ""
                company = company_loc.inner_text().strip() if company_loc.is_visible() else ""
            
                parts = name.split(" ")
                first_name = parts[0] if parts else ""
            
                return {
                    "status": "success",
                    "data": {
                        "name": name,
                        "first_name": first_name,
                        "title": title,
                        "company": company,
                        "method": "dom"
                    }
                }

            finally:
                pass
    @linkedin_action_safe
    def scrape_basic_profile(self, profile_url: str) -> Dict[str, Any]:
            # 1. Attempt Fast HTTP Scrape

        try:

            res = self._http_get(profile_url)
            html = res.text
            
            # Extract from embedded Redux state or JSON LD
            first_name = re.search(r'"firstName":"([^"]+)"', html)
            last_name = re.search(r'"lastName":"([^"]+)"', html)
            headline = re.search(r'"headline":"([^"]+)"', html)
            
            if first_name and last_name:
                fname = first_name.group(1)
                lname = last_name.group(1)
                title = headline.group(1) if headline else ""
                
                return {
                    "status": "success",
                    "data": {
                        "name": f"{fname} {lname}",
                        "first_name": fname,
                        "company": "", # Company is notoriously hard to reliably regex, leave empty for enrichment
                        "title": title,
                        "method": "http"
                    }
                }
        except Exception as e:

            pass # Fallback to Playwright
            
            # 2. Fallback to Playwright Headless Browser

    

        with self._get_or_create_context() as page:

            try:
                page.goto(profile_url, wait_until="domcontentloaded")
                self._check_for_challenge(page)
                self._human_delay(2, 4)
            
                name_el = page.locator("h1.text-heading-xlarge").first
                name = name_el.inner_text().strip() if name_el.is_visible(timeout=3000) else ""
                first_name = name.split()[0] if name else ""
            
                company_el = page.locator("button[aria-label*='Current company']").first
                if not company_el.is_visible(timeout=1000):
                    company_el = page.locator(".pv-text-details__right-panel-item").first
                company = company_el.inner_text().strip() if company_el.is_visible(timeout=2000) else ""
            
                title_el = page.locator(".text-body-medium.break-words").first
                title = title_el.inner_text().strip() if title_el.is_visible(timeout=1000) else ""
            
                return {
                    "status": "success",
                    "name": name,
                    "first_name": first_name,
                    "company": company,
                    "title": title,
                    "method": "playwright"
                }

            finally:
                pass
    @linkedin_action_safe
    def get_follower_count(self, profile_url: str) -> Dict[str, Any]:
            # 1. Attempt Fast HTTP Scrape

        try:

            res = self._http_get(profile_url)
            html = res.text
            match = re.search(r'"followerCount":\s*(\d+)', html)
            if match:
                return {"status": "success", "followers": int(match.group(1)), "method": "http"}

        except Exception as e:

            pass # Fallback to Playwright
        
        # 2. Fallback to Playwright Headless Browser



        with self._get_or_create_context() as page:

            try:
                page.goto(profile_url, wait_until="domcontentloaded")
                self._check_for_challenge(page)
                self._human_delay(2, 4)
            
                follower_el = page.locator("li").filter(has_text="followers").first
                if not follower_el.is_visible(timeout=2000):
                    follower_el = page.locator("span").filter(has_text="followers").first
                
                if follower_el.is_visible(timeout=2000):
                    text = follower_el.inner_text().strip()
                    numbers = re.sub(r'[^0-9]', '', text)
                    if numbers:
                            return {"status": "success", "followers": int(numbers), "method": "playwright"}
                
                    return {"status": "success", "followers": 0, "method": "playwright"}

            finally:
                pass
    @linkedin_action_safe
    def sync_inbox(self, max_threads: int = 10) -> List[Dict[str, Any]]:
        """Scrapes the preview text of the top N threads in the messaging inbox."""


        results = []

        with self._get_or_create_context() as page:

            try:
                page.goto("https://www.linkedin.com/messaging/", wait_until="domcontentloaded")
                self._check_for_challenge(page)
                self._human_delay(4, 6)
            
                conversations = page.locator("li.msg-conversation-listitem").all()
                if not conversations:
                    # Fallback locator if class changes
                    conversations = page.locator("div.msg-conversation-card").all()
            
                for conv in conversations[:max_threads]:
                    try:
                        # Extract sender name
                        name_el = conv.locator("h3").first
                        if not name_el.is_visible(timeout=2000):
                            continue
                        name = name_el.inner_text().strip()
                    
                        # Extract preview message text
                        msg_el = conv.locator("p").first
                        if not msg_el.is_visible(timeout=2000):
                            continue
                        msg_text = msg_el.inner_text().strip()
                    
                        # Determine direction
                        direction = "outbound" if msg_text.startswith("You: ") else "inbound"
                        if msg_text.startswith("You: "):
                            msg_text = msg_text[5:]
                        
                        # Timestamp
                        time_el = conv.locator("time").first
                        timestamp = time_el.inner_text().strip() if time_el.is_visible(timeout=1000) else ""
                    
                        results.append({
                            "sender_name": name,
                            "message_text": msg_text,
                            "direction": direction,
                            "timestamp_str": timestamp
                        })
                    except Exception as e:
                        logger.warning(f"Error parsing conversation: {e}")
                        continue
                    
                return results
            except Exception as e:
                logger.error(f"Error syncing inbox: {e}")
                return results


    @linkedin_action_safe
    def send_message_to_existing_thread(self, sender_name: str, message: str) -> Dict[str, Any]:
        """


            Find an existing LinkedIn thread by sender name and send a message.

            Used by the Approval Queue 'Approve & Send' action.

        """


        with self._get_or_create_context() as page:

            try:
                # Navigate to messaging
                page.goto("https://www.linkedin.com/messaging/", wait_until="domcontentloaded")
                self._check_for_challenge(page)
                self._human_delay(3, 5)

                # Search for the thread by name
                search_input = page.locator("input[placeholder*='Search']").first
                if search_input.is_visible(timeout=5000):
                    search_input.click(delay=random.randint(50, 150))
                    self._human_type(page, "input[placeholder*=\'Search\']", sender_name)
                    self._human_delay(1.5, 2.5)

                # Click the matching conversation
                thread_item = page.locator(f"[data-control-name='overlay.minimize_connection_list_entry']").filter(has_text=sender_name).first
                if not thread_item.is_visible(timeout=3000):
                    # Try simpler selector
                    thread_item = page.locator(".msg-conversation-listitem").filter(has_text=sender_name).first

                if thread_item.is_visible(timeout=3000):
                    thread_item.click(delay=random.randint(50, 150))
                    self._human_delay(1.5, 2.5)
                else:
                    return {"status": "error", "error": f"Thread for '{sender_name}' not found"}

                # Find the message compose box and type
                compose = page.locator("div[role='textbox'][data-artdeco-is-focused]").first
                if not compose.is_visible(timeout=3000):
                    compose = page.locator(".msg-form__contenteditable").first

                if compose.is_visible(timeout=3000):
                    compose.click(delay=random.randint(50, 150))
                    self._human_delay(0.5, 1.0)
                    self._human_type(page, "div[aria-label*=\'Write a message\']", message)
                    self._human_delay(1.0, 2.0)

                    # Send
                    send_btn = page.locator("button.msg-form__send-button").first
                    if send_btn.is_visible(timeout=3000):
                        with self._mutation_boundary():
                            send_btn.click(delay=random.randint(50, 150))
                            self._human_delay(1.0, 2.0)
                            logger.info(f"[LIVE] send_message_to_existing_thread: {sender_name}")
                            return {"status": "success", "action": "send_reply", "recipient": sender_name}
                    return {"status": "error", "error": "Send button not found"}
                return {"status": "error", "error": "Compose box not found"}
            except LinkedInActionOutcomeUnknown:
                raise
            except Exception as e:
                return {"status": "error", "error": str(e)}
