import logging
import os
import threading
from collections import OrderedDict
from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)

# DANGER: DO NOT instantiate Playwright directly via sync_playwright() outside of this pool!
# Doing so will bypass the concurrency limit and instantly OOM the server.
# ALWAYS use global_browser_pool.acquire()!

class BrowserPoolExhaustedError(Exception):
    """Raised when the browser pool is at capacity and a worker times out waiting."""
    pass

MAX_CONCURRENT_BROWSERS = int(os.getenv("MAX_CONCURRENT_BROWSERS", 50))

class BrowserPool:
    def __init__(self, max_size=MAX_CONCURRENT_BROWSERS):
        self.max_size = max_size
        self.lock = threading.Lock()
        self.semaphore = threading.Semaphore(self.max_size)
        # account_id -> {"pw": ..., "browser": ..., "context": ..., "active_count": int}
        self.pool = OrderedDict()

    def acquire(self, account_id, setup_func):
        """
        Acquires a browser context for the given account.
        Increments the active usage count so it won't be evicted while in use.
        Blocks for up to 15 seconds.
        """
        if not self.semaphore.acquire(timeout=15.0):
            raise BrowserPoolExhaustedError(f"Browser pool exhausted. Max {self.max_size} concurrent browsers.")
        
        try:
            with self.lock:
                entry = self.pool.get(account_id)
                if entry:
                    try:
                        # Health check - if it fails, we drop down to recreation
                        page = entry["context"].new_page()
                        page.close()
                        
                        self.pool.move_to_end(account_id)
                        entry["active_count"] += 1
                        return entry["context"]
                    except Exception as e:
                        logger.warning(f"[BrowserPool] Health check failed for {account_id}, recreating. Error: {e}")
                        self._force_close_entry(entry)
                        del self.pool[account_id]

                # Before creating, check if we need to evict an idle browser
                self._evict_idle_if_needed()

                # Create new browser
                pw = sync_playwright().start()
                browser, context = setup_func(pw)
                entry = {
                    "pw": pw,
                    "browser": browser,
                    "context": context,
                    "active_count": 1
                }
                self.pool[account_id] = entry
                return context
        except Exception:
            self.semaphore.release()
            raise

    def release(self, account_id):
        """
        Decrements the active usage count. If it hits 0, it becomes eligible for eviction.
        Releases the semaphore permit.
        """
        try:
            with self.lock:
                entry = self.pool.get(account_id)
                if entry:
                    entry["active_count"] = max(0, entry["active_count"] - 1)
        finally:
            self.semaphore.release()

    def _evict_idle_if_needed(self):
        """
        Evicts the oldest IDLE browsers until we are under max_size.
        If all browsers are active, we allow the pool to temporarily exceed max_size 
        to prevent deadlocks, but it will shrink later.
        """
        if len(self.pool) < self.max_size:
            return

        # Find idle accounts (active_count == 0)
        idle_accounts = [acc_id for acc_id, data in self.pool.items() if data["active_count"] == 0]
        
        # We need to remove (len(pool) - max_size + 1) items to make room for 1
        to_remove = (len(self.pool) - self.max_size) + 1
        
        for acc_id in idle_accounts:
            if to_remove <= 0:
                break
            entry = self.pool.pop(acc_id)
            self._force_close_entry(entry)
            logger.info(f"[BrowserPool] Evicted idle browser for account {acc_id} to free RAM.")
            to_remove -= 1

    def _force_close_entry(self, entry):
        try:
            entry["context"].close()
        except: pass
        try:
            entry["browser"].close()
        except: pass
        try:
            entry["pw"].stop()
        except: pass

    def teardown(self):
        with self.lock:
            for acc_id, entry in list(self.pool.items()):
                self._force_close_entry(entry)
            self.pool.clear()

# Global Singleton Pool
global_browser_pool = BrowserPool(max_size=MAX_CONCURRENT_BROWSERS)

import atexit
atexit.register(global_browser_pool.teardown)
