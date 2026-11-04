import logging
import os
import threading
import time as _t
import uuid
import random
from collections import OrderedDict
from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)

# Distributed Multi-Pod Redis Lock Support
_redis_client = None
_redis_checked = False

def _get_redis_client():
    global _redis_client, _redis_checked
    if not _redis_checked:
        _redis_checked = True
        redis_url = os.getenv("REDIS_URL")
        if redis_url:
            try:
                import redis
                _redis_client = redis.Redis.from_url(redis_url, decode_responses=True, socket_timeout=3.0)
                _redis_client.ping()
                logger.info("[BrowserPool] Connected to Redis for distributed multi-pod account locking.")
            except Exception as e:
                logger.warning(f"[BrowserPool] Redis connection failed ({e}). Operating in resilient local lock mode.")
                _redis_client = None
    return _redis_client

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
ACCOUNT_LOCK_TIMEOUT_SECONDS = float(os.getenv("ACCOUNT_LOCK_TIMEOUT_SECONDS", 60.0))
BROWSER_ACQUIRE_TIMEOUT_SECONDS = float(os.getenv("BROWSER_ACQUIRE_TIMEOUT_SECONDS", 45.0))

class BrowserPool:
    def __init__(self, max_size=MAX_CONCURRENT_BROWSERS):
        self.max_size = max_size
        self.lock = threading.RLock()
        self.semaphore = threading.BoundedSemaphore(self.max_size)
        # account_id -> {"pw": ..., "browser": ..., "context": ..., "active_count": int, "created_at": float, "last_active_at": float, "ops_count": int}
        self.pool = OrderedDict()
        self.account_locks = {}  # account_id -> Lock() to strictly serialize concurrent requests to the same account
        self.active_lock_tokens = {}  # account_id -> fencing_token (UUID) to prevent lock theft across worker pods

    def acquire(self, account_id, setup_func, proxy_url=None, cookies_hash=None):
        """
        Acquires a browser context for the given account.
        Increments the active usage count so it won't be evicted while in use.
        Blocks for up to BROWSER_ACQUIRE_TIMEOUT_SECONDS.
        Paranoia Layer 1: Detects proxy rotations and cookie refreshes to prevent stale context leaks.
        """
        # Paranoia Layer 2: Daemon Multiplexing (Strict Serialization & Distributed Redlock)
        # Ensure that no two workers across any pods can ever interact with the same LinkedIn account simultaneously.
        # This prevents LinkedIn from detecting concurrent multi-geo sessions and triggering account bans.
        with self.lock:
            if account_id not in self.account_locks:
                self.account_locks[account_id] = threading.Lock()
            acc_lock = self.account_locks[account_id]
            
        # Block until this specific account is free from other threads locally
        if not acc_lock.acquire(timeout=ACCOUNT_LOCK_TIMEOUT_SECONDS):
            raise BrowserPoolExhaustedError(f"Account {account_id} is currently busy processing another task. Serialized queue timeout.")

        # Multi-Pod / Distributed Redis Lock Check with Cryptographic Fencing Token & Jitter
        redis_client = _get_redis_client()
        fencing_token = str(uuid.uuid4())
        if redis_client:
            lock_key = f"lock:linkedin:account:{account_id}"
            start_t = _t.time()
            redis_acquired = False
            base_delay = 0.05
            attempt = 0
            while _t.time() - start_t < ACCOUNT_LOCK_TIMEOUT_SECONDS:
                try:
                    if redis_client.set(lock_key, fencing_token, nx=True, px=int(ACCOUNT_LOCK_TIMEOUT_SECONDS * 1000)):
                        redis_acquired = True
                        with self.lock:
                            self.active_lock_tokens[account_id] = fencing_token
                        break
                except Exception as re:
                    logger.warning(f"[BrowserPool] Redis lock attempt failed: {re}")
                    break
                # Randomized exponential backoff with jitter to eliminate thundering herd
                backoff = min(0.5, base_delay * (1.5 ** min(attempt, 6))) * (0.8 + 0.4 * random.random())
                _t.sleep(backoff)
                attempt += 1
            if not redis_acquired and redis_client:
                acc_lock.release()
                raise BrowserPoolExhaustedError(f"Account {account_id} is busy on another worker pod. Distributed lock acquisition timeout.")

        if not self.semaphore.acquire(timeout=BROWSER_ACQUIRE_TIMEOUT_SECONDS):
            acc_lock.release()
            raise BrowserPoolExhaustedError(f"Browser pool exhausted. Max {self.max_size} concurrent browsers.")
        
        try:
            with self.lock:
                entry = self.pool.get(account_id)
                if entry:
                    is_alive = True
                    # Check connection status
                    if hasattr(entry.get("browser"), "is_connected") and not entry["browser"].is_connected():
                        is_alive = False

                    # Paranoia Layer 1: Stale proxy check (purge if account was rotated to a new proxy)
                    if proxy_url is not None and entry.get("proxy_url") != proxy_url:
                        logger.info(f"[BrowserPool] Proxy changed for account {account_id}. Purging stale browser context.")
                        is_alive = False

                    # Paranoia Layer 1: Stale cookie check (purge if account reconnected with new session)
                    if cookies_hash is not None and entry.get("cookies_hash") != cookies_hash:
                        logger.info(f"[BrowserPool] Cookies refreshed for account {account_id}. Purging stale browser context.")
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
                    "ops_count": 0,
                    "proxy_url": proxy_url,
                    "cookies_hash": cookies_hash
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

        # Paranoia Layer 1: Release Redis distributed lock using atomic fencing token Lua script
        redis_client = _get_redis_client()
        with self.lock:
            fencing_token = self.active_lock_tokens.pop(account_id, None)
        if redis_client and fencing_token:
            try:
                release_lua = """
                if redis.call("get", KEYS[1]) == ARGV[1] then
                    return redis.call("del", KEYS[1])
                else
                    return 0
                end
                """
                redis_client.eval(release_lua, 1, f"lock:linkedin:account:{account_id}", fencing_token)
            except Exception as e:
                logger.warning(f"[BrowserPool] Failed to release Redis lock for {account_id}: {e}")
        elif redis_client and not fencing_token:
            try:
                redis_client.delete(f"lock:linkedin:account:{account_id}")
            except Exception as e:
                logger.warning(f"[BrowserPool] Fallback Redis lock release failed for {account_id}: {e}")

        # Release the per-account serialization lock safely
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

    def evict(self, account_id: str):
        """
        Paranoia Layer 1: Immediately evicts and terminates any cached browser context for the given account.
        Called on proxy failovers, cookie refreshes, or security challenges.
        """
        with self.lock:
            entry = self.pool.pop(account_id, None)
            if entry:
                self._force_close_entry(entry)
                logger.info(f"[BrowserPool] Evicted browser context for account {account_id} to avoid stale state.")

    def teardown(self):
        with self.lock:
            for acc_id, entry in list(self.pool.items()):
                self._force_close_entry(entry)
            self.pool.clear()

# Global Singleton Pool
global_browser_pool = BrowserPool(max_size=MAX_CONCURRENT_BROWSERS)

import atexit
atexit.register(global_browser_pool.teardown)
