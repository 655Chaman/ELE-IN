"""
account_rate_limiter.py — Strict Account Rate Limiting & Algorithmic Cooldown Matrix
Pillar 7 (Phase 7.4) — Master Platform Hardening & Execution Plan

Rigorously designed under the Three-Layer Logic Architecture (Paranoia Framework):
  - Layer 0 (Foundational):
      * Strict ceilings: 50 connection requests / 100 messages per rolling day.
      * Hourly pacing: 10 connection requests / 20 messages per rolling hour.
      * Atomic action accounting per (account_id, period_date, period_hour).
  - Layer 1 (Environmental Failure Analysis — Algorithmic Cooling):
      * 48-hour automated account cooldown when LinkedIn returns HTTP 429, 999, CAPTCHA, or checkpoint challenge.
      * Automatic cascade: reschedules in-flight campaign jobs for cooling account by 48 hours.
  - Layer 2 (Human Paranoia — Attempt 51 Deferral & Burst Dampening):
      * Preflight check: attempt 51 is cleanly deferred without hitting external servers or consuming credits.
      * Transparent fallback: maintains thread-safe in-memory rate limit records if DB is offline.
"""

import logging
import threading
from datetime import datetime, date, timedelta, timezone
from typing import Optional, Dict, Any, Tuple, List

logger = logging.getLogger(__name__)

# Standard Hard Ceilings
DAILY_CONNECTION_LIMIT = 50
DAILY_MESSAGE_LIMIT = 100
HOURLY_CONNECTION_LIMIT = 10
HOURLY_MESSAGE_LIMIT = 20
DEFAULT_CHECKPOINT_COOLDOWN_HOURS = 48

_rate_limit_lock = threading.Lock()
# account_id -> { "cooldown_until": iso_str, "status": str, "reason": str, ... }
_IN_MEMORY_ACCOUNT_COOLDOWNS: Dict[str, Dict[str, Any]] = {}
# (account_id, date_str, hour_int) -> { "conn_daily": int, "msg_daily": int, "conn_hourly": int, "msg_hourly": int }
_IN_MEMORY_ACCOUNT_COUNTERS: Dict[Tuple[str, str, int], Dict[str, int]] = {}


def is_account_in_cooldown(
    account_id: str,
    supabase: Optional[Any] = None
) -> Tuple[bool, Optional[str], Optional[datetime]]:
    """
    Paranoia Layer 0 & 1: Checks whether an account is currently in security cooldown.
    Returns (is_cooling, reason, cooldown_until_dt).
    """
    clean_id = str(account_id or "").strip()
    if not clean_id:
        return False, None, None

    now_utc = datetime.now(timezone.utc)

    # 1. Check in-memory store
    with _rate_limit_lock:
        if clean_id in _IN_MEMORY_ACCOUNT_COOLDOWNS:
            entry = _IN_MEMORY_ACCOUNT_COOLDOWNS[clean_id]
            cd_until_str = entry.get("cooldown_until")
            if cd_until_str:
                try:
                    cd_dt = datetime.fromisoformat(cd_until_str.replace("Z", "+00:00"))
                    if cd_dt.tzinfo is None:
                        cd_dt = cd_dt.replace(tzinfo=timezone.utc)
                    if cd_dt > now_utc:
                        return True, entry.get("cooldown_reason") or entry.get("reason", "SECURITY_COOLDOWN_ACTIVE"), cd_dt
                    else:
                        del _IN_MEMORY_ACCOUNT_COOLDOWNS[clean_id]
                except Exception:
                    pass

    # 2. Check Supabase account_rate_limits or accounts table
    if supabase:
        try:
            res = (
                supabase.table("account_rate_limits")
                .select("cooldown_until, cooldown_reason, status")
                .eq("account_id", clean_id)
                .order("updated_at", desc=True)
                .limit(1)
                .execute()
            )
            rows = getattr(res, "data", []) or []
            if rows and isinstance(rows[0], dict):
                cd_until_str = rows[0].get("cooldown_until")
                if cd_until_str:
                    cd_dt = datetime.fromisoformat(cd_until_str.replace("Z", "+00:00"))
                    if cd_dt.tzinfo is None:
                        cd_dt = cd_dt.replace(tzinfo=timezone.utc)
                    if cd_dt > now_utc:
                        with _rate_limit_lock:
                            _IN_MEMORY_ACCOUNT_COOLDOWNS[clean_id] = {
                                "cooldown_until": cd_until_str,
                                "reason": rows[0].get("cooldown_reason"),
                                "status": rows[0].get("status", "cooling_challenge")
                            }
                        return True, rows[0].get("cooldown_reason", "SECURITY_COOLDOWN_ACTIVE"), cd_dt
        except Exception as e:
            logger.debug(f"[AccountRateLimiter] DB cooldown check notice: {e}")

    return False, None, None


def trigger_account_security_cooldown(
    account_id: str,
    workspace_id: str,
    trigger_reason: str,
    cooldown_hours: int = DEFAULT_CHECKPOINT_COOLDOWN_HOURS,
    supabase: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Paranoia Layer 1: Activates automated 48-hour algorithmic cooldown upon security challenge.
    - Halts all outbound dispatch for this account.
    - Sets account status to 'cooling_challenge'.
    - Automatically reschedules queued campaign jobs for this account by 48 hours.
    """
    clean_id = str(account_id or "").strip()
    clean_ws = str(workspace_id or "").strip()
    now_utc = datetime.now(timezone.utc)
    cooldown_until = now_utc + timedelta(hours=cooldown_hours)
    cd_until_iso = cooldown_until.isoformat()

    record = {
        "account_id": clean_id,
        "workspace_id": clean_ws,
        "cooldown_until": cd_until_iso,
        "cooldown_reason": str(trigger_reason)[:255],
        "status": "cooling_challenge",
        "updated_at": now_utc.isoformat()
    }

    with _rate_limit_lock:
        _IN_MEMORY_ACCOUNT_COOLDOWNS[clean_id] = record

    if supabase:
        try:
            # Update account_rate_limits
            today = now_utc.date().isoformat()
            hour = now_utc.hour
            supabase.table("account_rate_limits").upsert({
                "account_id": clean_id,
                "workspace_id": clean_ws,
                "period_date": today,
                "period_hour": hour,
                "cooldown_until": cd_until_iso,
                "cooldown_reason": record["cooldown_reason"],
                "status": "cooling_challenge",
                "updated_at": now_utc.isoformat()
            }).execute()

            # Update accounts table status
            supabase.table("accounts").update({
                "status": "cooling_challenge",
                "cooldown_until": cd_until_iso,
                "cooldown_reason": record["cooldown_reason"],
                "updated_at": now_utc.isoformat()
            }).eq("id", clean_id).execute()

            # Cascade: Reschedule active queued campaign jobs for this account by 48 hours
            supabase.table("campaign_execution_states").update({
                "next_run_at": cd_until_iso,
                "lease_token": None,
                "lease_expires_at": None,
                "updated_at": now_utc.isoformat()
            }).eq("account_id", clean_id).in_("status", ["pending", "waiting_for_reply", "running"]).execute()

        except Exception as e:
            logger.warning(f"[AccountRateLimiter] DB trigger cooldown error: {e}")

    logger.warning(
        f"[AccountRateLimiter] Triggered {cooldown_hours}h cooldown for account {clean_id} "
        f"until {cd_until_iso}. Reason: {trigger_reason}"
    )

    return {
        "status": "cooling_challenge",
        "account_id": clean_id,
        "workspace_id": clean_ws,
        "cooldown_until": cd_until_iso,
        "cooldown_hours": cooldown_hours,
        "reason": record["cooldown_reason"]
    }


def check_and_increment_account_action(
    account_id: str,
    workspace_id: str,
    action_type: str,  # 'connection_request' or 'message'
    supabase: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Paranoia Layer 0 & 2: Pre-flight ceiling check & atomic increment.
    - If in cooldown, rejects immediately.
    - If daily connection >= 50 or daily message >= 100, rejects cleanly as attempt 51 deferral.
    - If hourly connection >= 10 or hourly message >= 20, rejects cleanly as hourly deferral.
    - If allowed, atomically increments counters.
    """
    clean_id = str(account_id or "").strip()
    clean_ws = str(workspace_id or "").strip()
    clean_action = str(action_type or "message").strip().lower()
    now_utc = datetime.now(timezone.utc)

    # 1. Check active cooldown
    is_cooling, cd_reason, cd_until = is_account_in_cooldown(clean_id, supabase=supabase)
    if is_cooling:
        return {
            "allowed": False,
            "account_id": clean_id,
            "status": "deferred_cooldown",
            "reason": cd_reason,
            "cooldown_until": cd_until.isoformat() if cd_until else None,
            "message": f"Account is cooling until {cd_until}. Outreach deferred for safety."
        }

    # 2. Check and increment atomic counters under lock
    today_str = now_utc.date().isoformat()
    hour_int = now_utc.hour
    counter_key = (clean_id, today_str, hour_int)

    with _rate_limit_lock:
        # Paranoia Layer 1: Bound in-memory footprint; evict entries from past days to prevent memory leaks
        if len(_IN_MEMORY_ACCOUNT_COUNTERS) > 5000:
            stale_keys = [k for k in _IN_MEMORY_ACCOUNT_COUNTERS if k[1] < today_str]
            for k in stale_keys:
                _IN_MEMORY_ACCOUNT_COUNTERS.pop(k, None)

        if counter_key not in _IN_MEMORY_ACCOUNT_COUNTERS:
            # Correct arithmetic: take the maximum of the sum of hourly counts or any recorded cumulative daily total from today
            existing_daily_conn = max(
                sum(val.get("conn_hourly", 0) for (a_id, d_str, h), val in _IN_MEMORY_ACCOUNT_COUNTERS.items() if a_id == clean_id and d_str == today_str),
                max((val.get("conn_daily", 0) for (a_id, d_str, h), val in _IN_MEMORY_ACCOUNT_COUNTERS.items() if a_id == clean_id and d_str == today_str), default=0)
            )
            existing_daily_msg = max(
                sum(val.get("msg_hourly", 0) for (a_id, d_str, h), val in _IN_MEMORY_ACCOUNT_COUNTERS.items() if a_id == clean_id and d_str == today_str),
                max((val.get("msg_daily", 0) for (a_id, d_str, h), val in _IN_MEMORY_ACCOUNT_COUNTERS.items() if a_id == clean_id and d_str == today_str), default=0)
            )
            _IN_MEMORY_ACCOUNT_COUNTERS[counter_key] = {
                "conn_daily": existing_daily_conn,
                "msg_daily": existing_daily_msg,
                "conn_hourly": 0,
                "msg_hourly": 0
            }

        counts = _IN_MEMORY_ACCOUNT_COUNTERS[counter_key]

        # Evaluate against ceilings
        if clean_action in ("connection_request", "invite"):
            if counts["conn_daily"] >= DAILY_CONNECTION_LIMIT:
                next_day_iso = (datetime.combine(now_utc.date() + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)).isoformat()
                return {
                    "allowed": False,
                    "account_id": clean_id,
                    "status": "deferred_daily_limit",
                    "reason": f"Daily connection limit reached ({DAILY_CONNECTION_LIMIT}/day). Attempt deferred.",
                    "cooldown_until": next_day_iso
                }
            if counts["conn_hourly"] >= HOURLY_CONNECTION_LIMIT:
                next_hour_iso = (now_utc.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)).isoformat()
                return {
                    "allowed": False,
                    "account_id": clean_id,
                    "status": "deferred_hourly_limit",
                    "reason": f"Hourly connection rate limit reached ({HOURLY_CONNECTION_LIMIT}/hour). Attempt paced.",
                    "cooldown_until": next_hour_iso
                }

            # Increment
            counts["conn_daily"] += 1
            counts["conn_hourly"] += 1
            remaining_daily = DAILY_CONNECTION_LIMIT - counts["conn_daily"]
            remaining_hourly = HOURLY_CONNECTION_LIMIT - counts["conn_hourly"]

        else:  # message
            if counts["msg_daily"] >= DAILY_MESSAGE_LIMIT:
                next_day_iso = (datetime.combine(now_utc.date() + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)).isoformat()
                return {
                    "allowed": False,
                    "account_id": clean_id,
                    "status": "deferred_daily_limit",
                    "reason": f"Daily message limit reached ({DAILY_MESSAGE_LIMIT}/day). Attempt deferred.",
                    "cooldown_until": next_day_iso
                }
            if counts["msg_hourly"] >= HOURLY_MESSAGE_LIMIT:
                next_hour_iso = (now_utc.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)).isoformat()
                return {
                    "allowed": False,
                    "account_id": clean_id,
                    "status": "deferred_hourly_limit",
                    "reason": f"Hourly message rate limit reached ({HOURLY_MESSAGE_LIMIT}/hour). Attempt paced.",
                    "cooldown_until": next_hour_iso
                }

            # Increment
            counts["msg_daily"] += 1
            counts["msg_hourly"] += 1
            remaining_daily = DAILY_MESSAGE_LIMIT - counts["msg_daily"]
            remaining_hourly = HOURLY_MESSAGE_LIMIT - counts["msg_hourly"]

    return {
        "allowed": True,
        "account_id": clean_id,
        "workspace_id": clean_ws,
        "action_type": clean_action,
        "remaining_daily": max(0, remaining_daily),
        "remaining_hourly": max(0, remaining_hourly),
        "status": "dispatched"
    }
