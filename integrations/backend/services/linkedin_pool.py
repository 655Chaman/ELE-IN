import logging
import os
import threading
import time as _t
from collections import OrderedDict
from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)

# DANGER: DO NOT instantiate Playwright directly via sync_playwright() outside of this pool!
# Doing so will bypass the concurrency limit and instantly OOM the server.
# ALWAYS use global_browser_pool.acquire()!

class BrowserPoolExhaustedError(Exception):
    """Raised when the browser pool is at capacity and a worker times out waiting."""
    pass

MAX_CONCURRENT_BROWSERS = int(os.getenv("MAX_CONCURRENT_BROWSERS", 3))
MAX_BROWSER_OPS = int(os.getenv("MAX_BROWSER_OPS", 30))
MAX_BROWSER_AGE_SECONDS = int(os.getenv("MAX_BROWSER_AGE_SECONDS", 1800))
IDLE_BROWSER_TTL_SECONDS = int(os.getenv("IDLE_BROWSER_TTL_SECONDS", 600))

class BrowserPool:
    def __init__(self, max_size=MAX_CONCURRENT_BROWSERS):
        self.max_size = max_size
        self.lock = threading.RLock()
        self.semaphore = threading.BoundedSemaphore(self.max_size)
        # account_id -> {"pw": ..., "browser": ..., "context": ..., "active_count": int, "created_at": float, "last_active_at": float, "ops_count": int}
        self.pool = OrderedDict()
        self.account_locks = {}  # account_id -> Lock() to strictly serialize concurrent requests to the same account

    def acquire(self, account_id, setup_func):
        """
        Acquires a browser context for the given account.
        Increments the active usage count so it won't be evicted while in use.
        Blocks for up to 15 seconds.
        """
        # Paranoia Layer 2: Daemon Multiplexing (Strict Serialization)
        # Ensure that no two workers can ever interact with the same LinkedIn account simultaneously.
        # This prevents LinkedIn from detecting superhuman multi-tab concurrency.
        with self.lock:
            if account_id not in self.account_locks:
                self.account_locks[account_id] = threading.Lock()
            acc_lock = self.account_locks[account_id]
            
        # Block until this specific account is free from other workers
        if not acc_lock.acquire(timeout=25.0):
            raise BrowserPoolExhaustedError(f"Account {account_id} is currently busy processing another task. Serialized queue timeout.")

        if not self.semaphore.acquire(timeout=15.0):
            acc_lock.release()
            raise BrowserPoolExhaustedError(f"Browser pool exhausted. Max {self.max_size} concurrent browsers.")
        
        try:
            with self.lock:
                entry = self.pool.get(account_id)
                if entry:
                    # Check connection status
                    is_alive = True
                    if hasattr(entry.get("browser"), "is_connected") and not entry["browser"].is_connected():
                        is_alive = False
                    # Check age and ops count (recycling to prevent RAM leaks)
                    if is_alive:
                        now_t = _t.time()
                        if (now_t - entry.get("created_at", 0) > MAX_BROWSER_AGE_SECONDS) or (entry.get("ops_count", 0) >= MAX_BROWSER_OPS):
                            logger.info(f"[BrowserPool] Recycling browser for {account_id} (age: {int(now_t - entry.get('created_at', 0))}s, ops: {entry.get('ops_count', 0)})")
                            is_alive = False
                    if is_alive:
                        try:
                            page = entry["context"].new_page()
                            page.close()
                            self.pool.move_to_end(account_id)
                            entry["active_count"] += 1
                            entry["last_active_at"] = _t.time()
                            return entry["context"]
                        except Exception as e:
                            logger.warning(f"[BrowserPool] Health check failed for {account_id}, recreating: {e}")
                            is_alive = False

                    # Recreate entry if not alive
                    self._force_close_entry(entry)
                    if account_id in self.pool:
                        del self.pool[account_id]

                # Before creating, check if we need to evict an idle browser
                self._evict_idle_if_needed()

                # Create new browser
                pw = sync_playwright().start()
                try:
                    browser, context = setup_func(pw)
                except Exception:
                    try:
                        pw.stop()
                    except Exception:
                        pass
                    raise
                entry = {
                    "pw": pw,
                    "browser": browser,
                    "context": context,
                    "active_count": 1,
                    "created_at": _t.time(),
                    "last_active_at": _t.time(),
                    "ops_count": 0
                }
                self.pool[account_id] = entry
                return context
        except Exception:
            try:
                self.semaphore.release()
            except ValueError:
                pass
            try:
                acc_lock.release()
            except RuntimeError:
                pass
            raise

    def release(self, account_id):
        """
        Decrements the active usage count. If it hits 0, it becomes eligible for eviction.
        Releases the semaphore permit and the per-account serialization lock.
        """
        should_release = False
        with self.lock:
            entry = self.pool.get(account_id)
            if entry and entry.get("active_count", 0) > 0:
                entry["active_count"] -= 1
                entry["ops_count"] = entry.get("ops_count", 0) + 1
                entry["last_active_at"] = _t.time()
                should_release = True
            else:
                logger.warning(
                    f"[BrowserPool] Over-release or untracked release attempted for account {account_id}; skipping semaphore release."
                )

        if should_release:
            try:
                self.semaphore.release()
            except ValueError:
                logger.error(
                    f"[BrowserPool] Semaphore released beyond max_size ({self.max_size}) for account {account_id}."
                )

        # Paranoia Layer 1: Release the per-account serialization lock safely
        with self.lock:
            acc_lock = self.account_locks.get(account_id)
        if acc_lock and acc_lock.locked():
            try:
                acc_lock.release()
            except RuntimeError:
                pass

    def reap_idle_browsers(self, max_idle_seconds=IDLE_BROWSER_TTL_SECONDS):
        """Closes any idle browsers that have not been used for max_idle_seconds."""
        now_t = _t.time()
        with self.lock:
            idle_to_reap = [
                acc_id for acc_id, entry in self.pool.items()
                if entry.get("active_count", 0) == 0 and (now_t - entry.get("last_active_at", 0) > max_idle_seconds)
            ]
            for acc_id in idle_to_reap:
                entry = self.pool.pop(acc_id, None)
                if entry:
                    self._force_close_entry(entry)
                    logger.info(f"[BrowserPool] Reaped idle browser for account {acc_id} after {int(now_t - entry.get('last_active_at', 0))}s idle.")

    def _evict_idle_if_needed(self):
        """
        Evicts the oldest IDLE browsers until we are under max_size.
        If all browsers are active, we allow the pool to temporarily exceed max_size 
        to prevent deadlocks, but it will shrink later.
        """
        self.reap_idle_browsers()
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
