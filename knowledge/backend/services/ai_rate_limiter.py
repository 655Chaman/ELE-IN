"""
AI Rate Limiter & Token Budget Engine — Paranoia Layer 1 & 2
=============================================================
Per-workspace Token Bucket rate limiter enforcing Requests-Per-Minute (RPM)
and Tokens-Per-Minute (TPM) ceilings across all AI endpoints.

Prevents:
- Runaway sequence loops draining workspace AI credits or platform budgets
- Noisy neighbor problems where one tenant starves shared NVIDIA/OpenAI quotas
- Upstream provider 429 throttling via proactive client-side rate regulation
"""

import time
import logging
import threading
from typing import Dict, Any, Tuple, Optional

logger = logging.getLogger(__name__)

# Default platform limits by tier
TIER_LIMITS: Dict[str, Dict[str, int]] = {
    "free": {"rpm": 30, "tpm": 25000},
    "starter": {"rpm": 60, "tpm": 60000},
    "pro": {"rpm": 180, "tpm": 200000},
    "enterprise": {"rpm": 600, "tpm": 800000},
}

_limiter_lock = threading.RLock()
# Structure: {workspace_id: {"window_start": float, "requests": int, "tokens": int}}
_WORKSPACE_WINDOWS: Dict[str, Dict[str, Any]] = {}
_MAX_TRACKED_WORKSPACES = 5000


class AIRateLimitExceededError(Exception):
    """Raised when a workspace exceeds its allocated RPM or TPM quota."""
    def __init__(self, workspace_id: str, limit_type: str, limit_value: int, retry_after: float):
        self.workspace_id = workspace_id
        self.limit_type = limit_type
        self.limit_value = limit_value
        self.retry_after = round(max(1.0, float(retry_after)), 1)
        super().__init__(
            f"Workspace '{workspace_id}' exceeded {limit_type} limit of {limit_value}. "
            f"Please retry after {self.retry_after}s."
        )


def check_and_record_ai_usage(
    workspace_id: str,
    estimated_tokens: int = 150,
    tier: str = "pro",
    custom_rpm: Optional[int] = None,
    custom_tpm: Optional[int] = None,
) -> Tuple[bool, float]:
    """
    Checks if a workspace is within its allocated RPM/TPM limits and records usage.
    Returns: (is_allowed, retry_after_seconds)
    """
    safe_ws = str(workspace_id or "ws-default").strip()
    now = time.time()
    
    tier_conf = TIER_LIMITS.get(str(tier or "").lower(), TIER_LIMITS["pro"])
    max_rpm = custom_rpm or tier_conf["rpm"]
    max_tpm = custom_tpm or tier_conf["tpm"]

    with _limiter_lock:
        # Periodic garbage collection of inactive workspaces (> 5 minutes idle)
        if len(_WORKSPACE_WINDOWS) > _MAX_TRACKED_WORKSPACES:
            stale_keys = [k for k, v in _WORKSPACE_WINDOWS.items() if now - v.get("window_start", 0) > 300]
            for k in stale_keys:
                _WORKSPACE_WINDOWS.pop(k, None)

        record = _WORKSPACE_WINDOWS.get(safe_ws)
        if record is None or (now - record.get("window_start", 0)) >= 60.0:
            # Start fresh 60-second window
            _WORKSPACE_WINDOWS[safe_ws] = {
                "window_start": now,
                "requests": 1,
                "tokens": max(0, int(estimated_tokens)),
            }
            return True, 0.0

        # Check existing window
        elapsed = now - record["window_start"]
        remaining_time = max(1.0, 60.0 - elapsed)

        if record["requests"] >= max_rpm:
            logger.warning(
                f"[AIRateLimiter] Workspace '{safe_ws}' hit RPM ceiling ({record['requests']}/{max_rpm}). "
                f"Retry after {remaining_time:.1f}s."
            )
            return False, remaining_time

        if (record["tokens"] + estimated_tokens) > max_tpm:
            logger.warning(
                f"[AIRateLimiter] Workspace '{safe_ws}' hit TPM ceiling ({record['tokens']}/{max_tpm}). "
                f"Retry after {remaining_time:.1f}s."
            )
            return False, remaining_time

        # Within budget: record usage
        record["requests"] += 1
        record["tokens"] += max(0, int(estimated_tokens))
        return True, 0.0


def reset_rate_limiter_state() -> None:
    """Hermetic reset helper for test suites."""
    with _limiter_lock:
        _WORKSPACE_WINDOWS.clear()
