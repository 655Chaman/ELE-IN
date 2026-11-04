"""
inbox_lock_service.py - Thread Reply Concurrency Lock & Lease Management.
Hardened under the Three-Layer Logic Architecture (Paranoia Framework).

Layer 0 (Foundational):
  - Optimistic concurrency lease locks on thread/lead replies.
  - Prevents race conditions and double-replies when multiple operators or automated copilots
    interact with the same conversation thread simultaneously.

Layer 1 (Environmental Failure Analysis):
  - In-memory thread-safe lease storage with automatic expiration sweep.
  - Self-healing TTL bounds [5s, 60s] prevent permanent deadlocks if an operator's tab crashes
    or a backend request terminates abruptly.

Layer 2 (Human Paranoia):
  - Idempotent re-acquisition for the same operator token / draft identifier.
  - Returns structured collision metadata (lease owner, remaining duration) enabling clear UI feedback.
"""

import time
import logging
import threading
from typing import Tuple, Optional, Dict, Any

logger = logging.getLogger(__name__)

# In-memory storage: (workspace_id, thread_key) -> { "operator_id": str, "expires_at": float, "acquired_at": float }
_REPLY_LEASES: Dict[Tuple[str, str], Dict[str, Any]] = {}
_LEASES_LOCK = threading.Lock()

DEFAULT_LEASE_TTL_SECONDS = 15
MIN_LEASE_TTL_SECONDS = 5
MAX_LEASE_TTL_SECONDS = 60


def _normalize_key(workspace_id: str, thread_key: str) -> Tuple[str, str]:
    return (str(workspace_id or "").strip(), str(thread_key or "").strip().lower())


def _prune_expired_leases_locked(now: float) -> int:
    """Removes expired leases. Must be called while holding _LEASES_LOCK."""
    expired_keys = [k for k, v in _REPLY_LEASES.items() if now >= v["expires_at"]]
    for k in expired_keys:
        del _REPLY_LEASES[k]
    return len(expired_keys)


def acquire_thread_reply_lease(
    workspace_id: str,
    thread_key: str,
    operator_id: str,
    ttl_seconds: int = DEFAULT_LEASE_TTL_SECONDS,
) -> Tuple[bool, Optional[str], float]:
    """
    Attempts to acquire an exclusive reply lease for a thread.
    Returns:
      (acquired: bool, current_owner: Optional[str], remaining_seconds: float)
    """
    if not workspace_id or not thread_key or not operator_id:
        return (False, "invalid_arguments", 0.0)

    key = _normalize_key(workspace_id, thread_key)
    op_clean = str(operator_id).strip()
    ttl = max(MIN_LEASE_TTL_SECONDS, min(MAX_LEASE_TTL_SECONDS, int(ttl_seconds)))
    now = time.time()

    with _LEASES_LOCK:
        _prune_expired_leases_locked(now)

        current = _REPLY_LEASES.get(key)
        if current:
            # Active lease exists
            if current["operator_id"] == op_clean:
                # Same operator/draft: extend lease idempotently
                current["expires_at"] = now + ttl
                return (True, op_clean, float(ttl))
            
            remaining = max(0.1, round(current["expires_at"] - now, 1))
            return (False, current["operator_id"], remaining)

        # Grant new lease
        _REPLY_LEASES[key] = {
            "operator_id": op_clean,
            "expires_at": now + ttl,
            "acquired_at": now,
        }
        return (True, op_clean, float(ttl))


def release_thread_reply_lease(
    workspace_id: str,
    thread_key: str,
    operator_id: str,
    force: bool = False,
) -> bool:
    """
    Releases a reply lease.
    Only the lease owner can release unless force=True.
    """
    if not workspace_id or not thread_key:
        return False

    key = _normalize_key(workspace_id, thread_key)
    op_clean = str(operator_id or "").strip()

    with _LEASES_LOCK:
        current = _REPLY_LEASES.get(key)
        if not current:
            return True

        if force or current["operator_id"] == op_clean:
            del _REPLY_LEASES[key]
            return True

        return False


def is_thread_reply_locked(
    workspace_id: str,
    thread_key: str,
) -> Tuple[bool, Optional[str], float]:
    """
    Checks if a thread currently has an active reply lease.
    Returns:
      (is_locked: bool, owner_operator_id: Optional[str], remaining_seconds: float)
    """
    if not workspace_id or not thread_key:
        return (False, None, 0.0)

    key = _normalize_key(workspace_id, thread_key)
    now = time.time()

    with _LEASES_LOCK:
        current = _REPLY_LEASES.get(key)
        if not current:
            return (False, None, 0.0)

        if now >= current["expires_at"]:
            del _REPLY_LEASES[key]
            return (False, None, 0.0)

        remaining = max(0.1, round(current["expires_at"] - now, 1))
        return (True, current["operator_id"], remaining)


def clear_all_reply_leases() -> None:
    """Clears all in-memory leases for test isolation."""
    with _LEASES_LOCK:
        _REPLY_LEASES.clear()
