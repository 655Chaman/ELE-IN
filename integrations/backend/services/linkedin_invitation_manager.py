"""
linkedin_invitation_manager.py — LinkedIn Pending Invitation Garbage Collector & Algorithmic Connection Safety Cooldown.

Phase 41: Advanced LinkedIn Health & Garbage Collection Service.
Architected according to the Three-Layer Logic Architecture (Paranoia Framework):
  - Layer 0: Foundational Layer
      * Evaluates account connection health based on pending invitations and weekly throughput.
      * Filters stale pending invitations older than threshold.
      * Batched withdrawal of stale invitations with recipient cooldown enforcement.
      * Prevents re-inviting withdrawn leads within LinkedIn's mandatory 21-day cooldown period.
      * Dynamic account safety cooldown triggering and state checking.
  - Layer 1: Environmental Failure Analysis
      * Clamping of max_age_days [7, 90] prevents catastrophic premature withdrawal of recent invites.
      * Clamping of batch_limit [1, 50] prevents rate-limit bot triggers on LinkedIn.
      * Python 3.9+ robust UTC ISO-8601 parsing (handles trailing 'Z', offsets, and naive timestamps).
      * Supabase database error containment: isolates network/DB drops so execution continues safely.
      * Mandatory 21-day LinkedIn anti-resend cooldown stamped on every withdrawn recipient.
  - Layer 2: Human Paranoia
      * Defensive input sanitation against None, invalid numeric strings, negative pending counts.
      * Prevents double-withdrawing already accepted, expired, or withdrawn invitations.
      * Multi-key attribute tolerance (handles id, invitation_id, lead_id, recipient_id, public_identifier).
"""

import logging
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS
# =============================================================================

class InvitationStatus(str, Enum):
    """Lifecycle status of a LinkedIn connection invitation."""
    PENDING = "PENDING"
    WITHDRAWN = "WITHDRAWN"
    ACCEPTED = "ACCEPTED"
    EXPIRED = "EXPIRED"


class AccountHealthRisk(str, Enum):
    """Risk tier indicating likelihood of LinkedIn connection or account restrictions."""
    OPTIMAL = "OPTIMAL"
    APPROACHING_CEILING = "APPROACHING_CEILING"
    CRITICAL_RESTRICTION_RISK = "CRITICAL_RESTRICTION_RISK"


class CooldownReason(str, Enum):
    """Reason for placing a LinkedIn account or lead into safety cooldown."""
    INVITATION_LIMIT_REACHED = "INVITATION_LIMIT_REACHED"
    CAPTCHA_CHALLENGE = "CAPTCHA_CHALLENGE"
    HIGH_PENDING_CEILING = "HIGH_PENDING_CEILING"
    RAPID_DISPATCH_RESTRICTION = "RAPID_DISPATCH_RESTRICTION"


# =============================================================================
# INTERNAL UTILITIES
# =============================================================================

def _parse_utc_datetime(val: Any) -> Optional[datetime]:
    """
    Safely parses diverse datetime representations into timezone-aware UTC datetime.
    Supports ISO strings with 'Z' or offset, Unix timestamps, and datetime objects.
    Paranoia Layer 1: Python 3.9 compatibility for ISO strings with 'Z'.
    """
    if val is None:
        return None
    if isinstance(val, datetime):
        if val.tzinfo is None:
            return val.replace(tzinfo=timezone.utc)
        return val.astimezone(timezone.utc)
    if isinstance(val, (int, float)):
        try:
            return datetime.fromtimestamp(float(val), tz=timezone.utc)
        except Exception:
            return None
    if isinstance(val, str):
        val_clean = val.strip()
        if not val_clean:
            return None
        # Replace trailing 'Z' / 'z' with '+00:00' for Python < 3.11 fromisoformat support
        if val_clean.endswith("Z") or val_clean.endswith("z"):
            val_clean = val_clean[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(val_clean)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            pass
        # Fallback: check if the string is numeric timestamp
        try:
            num = float(val_clean)
            return datetime.fromtimestamp(num, tz=timezone.utc)
        except Exception:
            pass
    return None


# =============================================================================
# CORE LOGIC IMPLEMENTATIONS
# =============================================================================

def evaluate_account_connection_health(
    pending_count: int,
    weekly_sent_count: int = 0
) -> Dict[str, Any]:
    """
    Evaluates LinkedIn account connection health and risk tier based on pending invitations.

    Thresholds:
      - OPTIMAL (score 85-100): pending < 300.
      - APPROACHING_CEILING (score 50-84): 300 <= pending < 500. Action: Recommend GC > 14 days.
      - CRITICAL_RESTRICTION_RISK (score < 50): pending >= 500. Action: Aggressive GC required.

    Paranoia Layer 1 & 2:
      - Clamps pending_count and weekly_sent_count to non-negative integers.
      - Enforces can_send_invitations=False when risk level is CRITICAL_RESTRICTION_RISK.
    """
    try:
        safe_pending = max(0, int(pending_count if pending_count is not None else 0))
    except (ValueError, TypeError):
        safe_pending = 0

    try:
        safe_weekly = max(0, int(weekly_sent_count if weekly_sent_count is not None else 0))
    except (ValueError, TypeError):
        safe_weekly = 0

    if safe_pending < 300:
        # Score spans 85-100
        score = max(85, min(100, int(100 - (safe_pending / 300.0) * 15)))
        risk = AccountHealthRisk.OPTIMAL
        can_send = True
        recommendation = "Account connection health is optimal. Safe to continue sending invitations."
    elif 300 <= safe_pending < 500:
        # Score spans 50-84
        score = max(50, min(84, int(84 - ((safe_pending - 300) / 200.0) * 34)))
        risk = AccountHealthRisk.APPROACHING_CEILING
        can_send = True
        recommendation = (
            "Approaching pending invitation ceiling. Recommend withdrawing stale invitations "
            "older than 14 days to prevent LinkedIn account restrictions."
        )
    else:
        # Score < 50 (spans 0-49)
        score = max(0, min(49, int(45 - ((safe_pending - 500) / 200.0) * 45)))
        risk = AccountHealthRisk.CRITICAL_RESTRICTION_RISK
        can_send = False
        recommendation = (
            "Critical restriction risk! Pending invitations exceed safe threshold (>= 500). "
            "Aggressive garbage collection required; new invitations paused to avoid account lock."
        )

    return {
        "health_score": score,
        "risk_level": risk.value,
        "pending_count": safe_pending,
        "weekly_sent_count": safe_weekly,
        "can_send_invitations": can_send,
        "recommendation": recommendation,
    }


def filter_stale_invitations(
    invitations: List[Dict[str, Any]],
    max_age_days: int = 14
) -> List[Dict[str, Any]]:
    """
    Filters pending invitations that have exceeded the safe age threshold.

    Paranoia Layer 1 & 2:
      - Clamps max_age_days between 7 and 90 days.
        Prevents withdrawing invitations younger than 7 days by accident (human or config mistake).
      - Automatically ignores invitations already in terminal state (WITHDRAWN, ACCEPTED, EXPIRED).
      - Resiliently inspects `days_pending`, `sent_at`, and nested timestamps.
    """
    if not invitations:
        return []

    try:
        safe_max_age = max(7, min(90, int(max_age_days if max_age_days is not None else 14)))
    except (ValueError, TypeError):
        safe_max_age = 14

    now_utc = datetime.now(timezone.utc)
    stale: List[Dict[str, Any]] = []

    for item in invitations:
        if not isinstance(item, dict):
            continue

        # Skip terminal statuses
        status = str(item.get("status") or item.get("invitation_status") or "").upper()
        if status in (InvitationStatus.WITHDRAWN.value, InvitationStatus.ACCEPTED.value, InvitationStatus.EXPIRED.value):
            continue

        age_days: Optional[float] = None

        # 1. Direct days_pending field
        if item.get("days_pending") is not None:
            try:
                age_days = float(item["days_pending"])
            except (ValueError, TypeError):
                age_days = None

        # 2. Sent timestamp field
        if age_days is None:
            sent_at_val = item.get("sent_at") or item.get("created_at") or item.get("invited_at")
            sent_dt = _parse_utc_datetime(sent_at_val)
            if sent_dt is not None:
                delta = now_utc - sent_dt
                age_days = max(0.0, delta.total_seconds() / 86400.0)

        if age_days is not None and age_days >= safe_max_age:
            # Attach computed age_days for downstream visibility
            item_copy = dict(item)
            item_copy["computed_age_days"] = round(age_days, 1)
            stale.append(item_copy)

    return stale


def withdraw_stale_invitations(
    account: Dict[str, Any],
    max_age_days: int = 14,
    batch_limit: int = 25,
    mock_invitations: Optional[List[Dict[str, Any]]] = None,
    supabase: Any = None
) -> Dict[str, Any]:
    """
    Withdraws stale invitations in a bounded batch to protect the LinkedIn account.

    Paranoia Layer 1:
      - Clamps batch_limit between 1 and 50 to avoid burst withdrawal bot triggers.
      - Enforces the LinkedIn 3-Week Rule:
          Any withdrawn invitation stamps `cooldown_until = now + 21 days` and `status = WITHDRAWN`.
      - Database updates are isolated in try/except blocks to preserve batch reporting.

    Returns:
      {
        "account_id": str,
        "withdrawn_count": int,
        "remaining_pending": int,
        "withdrawn_items": [...],
        "cooldown_enforced_days": 21
      }
    """
    account_id = account.get("id") or account.get("account_id") or "unknown_account"

    # Paranoia Layer 1: Clamp batch limit [1, 50]
    try:
        safe_batch_limit = max(1, min(50, int(batch_limit if batch_limit is not None else 25)))
    except (ValueError, TypeError):
        safe_batch_limit = 25

    # Retrieve candidate invitations
    if mock_invitations is not None:
        candidates = list(mock_invitations)
    else:
        candidates = (
            account.get("pending_invitations")
            or account.get("invitations")
            or []
        )
        if not candidates and supabase and account_id != "unknown_account":
            try:
                res = (
                    supabase.table("leads")
                    .select("*")
                    .eq("account_id", account_id)
                    .eq("status", InvitationStatus.PENDING.value)
                    .execute()
                )
                candidates = res.data or []
            except Exception as e:
                logger.warning(f"Error fetching pending leads for account {account_id} from Supabase: {e}")
                candidates = []

    # Filter stale invitations
    stale_items = filter_stale_invitations(candidates, max_age_days=max_age_days)
    batch_to_withdraw = stale_items[:safe_batch_limit]

    now = datetime.now(timezone.utc)
    withdrawn_at_iso = now.isoformat()
    # LinkedIn 3-Week Rule: 21 days anti-resend cooldown
    cooldown_until_iso = (now + timedelta(days=21)).isoformat()

    withdrawn_items: List[Dict[str, Any]] = []

    for item in batch_to_withdraw:
        lead_id = item.get("lead_id") or item.get("id")
        invitation_id = item.get("invitation_id") or item.get("id")
        recipient_id = item.get("recipient_id") or item.get("public_identifier") or lead_id
        recipient_name = item.get("recipient_name") or item.get("name") or item.get("full_name")

        record = {
            "invitation_id": invitation_id,
            "lead_id": lead_id,
            "recipient_id": recipient_id,
            "recipient_name": recipient_name,
            "status": InvitationStatus.WITHDRAWN.value,
            "withdrawn_at": withdrawn_at_iso,
            "cooldown_until": cooldown_until_iso,
            "cooldown_days": 21,
        }
        withdrawn_items.append(record)

        # Update in Supabase if client and lead_id are available
        if supabase and lead_id:
            try:
                supabase.table("leads").update({
                    "status": InvitationStatus.WITHDRAWN.value,
                    "linkedin_reconnect_cooldown_until": cooldown_until_iso,
                    "withdrawn_at": withdrawn_at_iso,
                }).eq("id", lead_id).execute()
            except Exception as e:
                logger.error(f"Failed to update lead {lead_id} status to WITHDRAWN in Supabase: {e}")

    # Determine remaining pending count
    if account.get("pending_count") is not None:
        try:
            total_pending = int(account["pending_count"])
        except (ValueError, TypeError):
            total_pending = len(candidates)
    else:
        total_pending = len(candidates)

    remaining_pending = max(0, total_pending - len(withdrawn_items))

    return {
        "account_id": account_id,
        "withdrawn_count": len(withdrawn_items),
        "remaining_pending": remaining_pending,
        "withdrawn_items": withdrawn_items,
        "cooldown_enforced_days": 21,
    }


def check_linkedin_3week_resend_cooldown(
    lead: Dict[str, Any]
) -> Tuple[bool, Optional[str]]:
    """
    Checks if a lead/recipient is currently in LinkedIn's 21-day anti-resend cooldown.

    Paranoia Layer 1:
      - Validates cooldown expiration timestamp against current UTC time.
      - Tolerates multiple possible attribute names (`linkedin_reconnect_cooldown_until`,
        `reconnect_cooldown_until`, `cooldown_until`).

    Returns:
      (True, f"Recipient is in LinkedIn 21-day anti-resend cooldown until {cooldown_until}.") if active.
      (False, None) if not in cooldown.
    """
    if not isinstance(lead, dict):
        return False, None

    cooldown_val = (
        lead.get("linkedin_reconnect_cooldown_until")
        or lead.get("reconnect_cooldown_until")
        or lead.get("cooldown_until")
    )
    if not cooldown_val:
        return False, None

    cooldown_dt = _parse_utc_datetime(cooldown_val)
    if cooldown_dt is None:
        return False, None

    now_utc = datetime.now(timezone.utc)
    if cooldown_dt > now_utc:
        cooldown_str = str(cooldown_val)
        return True, f"Recipient is in LinkedIn 21-day anti-resend cooldown until {cooldown_str}."

    return False, None


def trigger_account_cooldown(
    account_id: str,
    reason: Union[CooldownReason, str],
    duration_hours: int = 48,
    supabase: Any = None
) -> Dict[str, Any]:
    """
    Enforces an algorithmic safety cooldown on a LinkedIn account.

    Paranoia Layer 1 & 2:
      - Clamps duration_hours between 1 and 720 (30 days).
      - Converts CooldownReason Enum or string to standard string representation.
      - Optionally persists cooldown state to the Supabase accounts table.

    Returns:
      {
        "account_id": str,
        "in_cooldown": True,
        "cooldown_until": str,
        "reason": str,
        "duration_hours": int
      }
    """
    try:
        safe_hours = max(1, min(720, int(duration_hours if duration_hours is not None else 48)))
    except (ValueError, TypeError):
        safe_hours = 48

    reason_val = reason.value if hasattr(reason, "value") else str(reason)

    now = datetime.now(timezone.utc)
    cooldown_until_iso = (now + timedelta(hours=safe_hours)).isoformat()

    if supabase and account_id:
        try:
            supabase.table("accounts").update({
                "is_in_cooldown": True,
                "cooldown_until": cooldown_until_iso,
                "cooldown_reason": reason_val,
                "updated_at": now.isoformat(),
            }).eq("id", account_id).execute()
        except Exception as e:
            logger.error(f"Failed to update cooldown for account {account_id} in Supabase: {e}")

    return {
        "account_id": str(account_id),
        "in_cooldown": True,
        "cooldown_until": cooldown_until_iso,
        "reason": reason_val,
        "duration_hours": safe_hours,
    }


def is_account_in_cooldown(
    account: Dict[str, Any]
) -> Tuple[bool, Optional[str]]:
    """
    Checks if a LinkedIn account is currently restricted or in safety cooldown.

    Paranoia Layer 1 & 2:
      - Inspects cooldown expiration timestamp.
      - Inspects fallback boolean flags (`in_cooldown`, `is_in_cooldown`).

    Returns:
      (True, reason) if account is in active cooldown.
      (False, None) if account is free to operate.
    """
    if not isinstance(account, dict):
        return False, None

    reason = (
        account.get("cooldown_reason")
        or account.get("reason")
        or "Active safety cooldown"
    )

    cooldown_val = account.get("cooldown_until")
    if cooldown_val:
        cooldown_dt = _parse_utc_datetime(cooldown_val)
        if cooldown_dt is not None:
            now_utc = datetime.now(timezone.utc)
            if cooldown_dt > now_utc:
                return True, str(reason)
            # If timestamp has elapsed, cooldown is over
            return False, None

    # Fallback: check boolean flag if timestamp was not provided
    if account.get("in_cooldown") is True or account.get("is_in_cooldown") is True:
        return True, str(reason)

    return False, None


# =============================================================================
# FACADE CLASS
# =============================================================================

class LinkedInInvitationManager:
    """
    Unified static facade for LinkedIn Pending Invitation GC & Algorithmic Safety Cooldown.
    Provides clean static invocation patterns across workers, background jobs, and test runners.
    """

    evaluate_account_connection_health = staticmethod(evaluate_account_connection_health)
    filter_stale_invitations = staticmethod(filter_stale_invitations)
    withdraw_stale_invitations = staticmethod(withdraw_stale_invitations)
    check_linkedin_3week_resend_cooldown = staticmethod(check_linkedin_3week_resend_cooldown)
    trigger_account_cooldown = staticmethod(trigger_account_cooldown)
    is_account_in_cooldown = staticmethod(is_account_in_cooldown)
