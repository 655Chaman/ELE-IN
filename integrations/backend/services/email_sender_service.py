"""
email_sender_service.py — Multi-Inbox Cold-Email Deliverability Pool, Warmup Ramp & Tripwire Failover
Rigorously designed under the Three-Layer Logic Architecture (Paranoia Framework):
  - Layer 0: Multi-inbox rotation (SMTP/SES/SendGrid/Google Workspace/Resend), lead-to-sender thread affinity,
             gradual warmup daily ramp calculation, and real-time bounce/spam tripwire quarantine.
  - Layer 1: Expired quarantine auto-recovery, database outage fallback, and zero-division guards.
  - Layer 2: Cross-tenant IDOR prevention, daily limit clamping, and malformed email syntax rejection.
"""

import hashlib
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.backend.services.deliverability_guard import (
    evaluate_inbox_deliverability_tripwire,
    sanitize_domain_input,
)

logger = logging.getLogger(__name__)

VALID_PROVIDERS = {"sendgrid", "ses", "smtp", "google_workspace", "resend", "custom"}
VALID_STRATEGIES = {"HEALTH_WEIGHTED", "ROUND_ROBIN", "CAPACITY_FIRST"}

_EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_valid_sender_email(email: Optional[str]) -> bool:
    if not email or not isinstance(email, str):
        return False
    cleaned = email.strip()
    if not _EMAIL_REGEX.match(cleaned):
        return False
    domain = cleaned.split("@")[-1]
    return sanitize_domain_input(domain) is not None


def calculate_warmup_daily_cap(inbox: Dict[str, Any]) -> int:
    """
    Paranoia Layer 0 & 2: Computes the effective daily sending cap for a sender inbox.
    If warmup_enabled is True, ramps linearly from warmup_start_limit (default 15)
    by warmup_increment_per_day (default 5) * warmup_days_active, capped at daily_limit.
    Clamps values against human misconfiguration (e.g. negative limits or 100,000/day).
    """
    if not isinstance(inbox, dict):
        return 50

    try:
        raw_max = int(inbox.get("daily_limit", 50) or 50)
    except (ValueError, TypeError):
        raw_max = 50
    safe_daily_limit = max(1, min(2000, raw_max))

    warmup_enabled = bool(inbox.get("warmup_enabled", False))
    if not warmup_enabled:
        return safe_daily_limit

    try:
        start_limit = max(1, min(safe_daily_limit, int(inbox.get("warmup_start_limit", 15) or 15)))
    except (ValueError, TypeError):
        start_limit = min(15, safe_daily_limit)

    try:
        increment = max(1, min(100, int(inbox.get("warmup_increment_per_day", 5) or 5)))
    except (ValueError, TypeError):
        increment = 5

    try:
        days_active = max(0, min(365, int(inbox.get("warmup_days_active", 0) or 0)))
    except (ValueError, TypeError):
        days_active = 0

    ramped_cap = start_limit + (days_active * increment)
    return max(1, min(safe_daily_limit, ramped_cap))


def _is_inbox_currently_quarantined(inbox: Dict[str, Any]) -> bool:
    """
    Paranoia Layer 1: Checks status and quarantined_until timestamp.
    If status is QUARANTINED but quarantined_until has already passed in UTC,
    allows automatic recovery unless status is permanently DISCONNECTED or PAUSED.
    """
    status = str(inbox.get("status") or "ACTIVE").upper()
    if status in ("DISCONNECTED", "PAUSED", "REVOKED"):
        return True

    q_until_raw = inbox.get("quarantined_until")
    if q_until_raw:
        try:
            clean_str = str(q_until_raw).replace("Z", "+00:00")
            q_dt = datetime.fromisoformat(clean_str)
            if q_dt.tzinfo is None:
                q_dt = q_dt.replace(tzinfo=timezone.utc)
            if q_dt > datetime.now(timezone.utc):
                return True
            # Cooldown expired! If status was QUARANTINED, treat as recovered
            if status == "QUARANTINED":
                return False
        except Exception:
            pass

    return status == "QUARANTINED"


def select_rotating_sender_inbox(
    supabase: Optional[Any],
    workspace_id: str,
    campaign_id: Optional[str] = None,
    lead_id: Optional[str] = None,
    candidate_inboxes: Optional[List[Dict[str, Any]]] = None,
    strategy: str = "HEALTH_WEIGHTED",
) -> Dict[str, Any]:
    """
    Paranoia Layer 0, 1 & 2: Selects the optimal healthy sender inbox from the workspace pool.
    1. Enforces strict workspace_id tenant isolation (blocks cross-workspace inbox leakage).
    2. Evaluates real-time bounce/spam tripwires and warmup daily capacity limits.
    3. Preserves Lead-to-Sender Thread Affinity when the lead has an existing healthy sender lock.
    4. Dispatches via HEALTH_WEIGHTED, ROUND_ROBIN, or CAPACITY_FIRST strategy.
    """
    if not workspace_id or not str(workspace_id).strip():
        return {"selected": None, "error": "workspace_id is required", "pool_summary": {}}

    clean_ws = str(workspace_id).strip()
    clean_strategy = str(strategy or "HEALTH_WEIGHTED").upper()
    if clean_strategy not in VALID_STRATEGIES:
        clean_strategy = "HEALTH_WEIGHTED"

    # Load candidate inboxes from argument or Supabase
    raw_inboxes: List[Dict[str, Any]] = []
    if candidate_inboxes is not None and isinstance(candidate_inboxes, list):
        raw_inboxes = candidate_inboxes
    elif supabase:
        try:
            res = (
                supabase.table("email_sender_inboxes")
                .select("*")
                .eq("workspace_id", clean_ws)
                .execute()
            )
            if res and isinstance(getattr(res, "data", None), list):
                raw_inboxes = res.data
        except Exception as exc:
            logger.debug(f"[EmailSenderPool] Could not query email_sender_inboxes: {exc}")

    eligible_inboxes: List[Dict[str, Any]] = []
    rejected_inboxes: List[Dict[str, Any]] = []

    for inb in raw_inboxes:
        if not isinstance(inb, dict):
            continue

        inb_id = str(inb.get("id") or "")
        inb_ws = inb.get("workspace_id")
        # Layer 2 Paranoia: Cross-tenant IDOR barrier
        if inb_ws and str(inb_ws).strip() != clean_ws:
            rejected_inboxes.append({"id": inb_id, "reason": "CROSS_TENANT_MISMATCH"})
            continue

        email_addr = str(inb.get("email") or inb.get("from_email") or "").strip()
        if not is_valid_sender_email(email_addr):
            rejected_inboxes.append({"id": inb_id, "reason": "INVALID_EMAIL_SYNTAX"})
            continue

        if _is_inbox_currently_quarantined(inb):
            rejected_inboxes.append({"id": inb_id, "reason": "QUARANTINED_OR_PAUSED"})
            continue

        # Check live deliverability tripwire
        tripwire = evaluate_inbox_deliverability_tripwire(inb)
        if tripwire["should_quarantine"]:
            rejected_inboxes.append({
                "id": inb_id,
                "reason": "DELIVERABILITY_TRIPWIRE_TRIPPED",
                "tripwire_reason": tripwire["quarantine_reason"],
            })
            continue

        effective_cap = calculate_warmup_daily_cap(inb)
        try:
            sent_today = max(0, int(inb.get("sent_today", 0) or 0))
        except (ValueError, TypeError):
            sent_today = 0

        remaining_today = max(0, effective_cap - sent_today)
        if remaining_today <= 0:
            rejected_inboxes.append({"id": inb_id, "reason": "DAILY_CAP_EXHAUSTED"})
            continue

        try:
            deliv_score = max(1, min(100, int(inb.get("deliverability_score", 95) or 95)))
        except (ValueError, TypeError):
            deliv_score = 95

        enriched = dict(inb)
        enriched["email"] = email_addr
        enriched["effective_daily_limit"] = effective_cap
        enriched["remaining_capacity"] = remaining_today
        enriched["deliverability_score"] = deliv_score
        # Composite weight: remaining capacity * (deliverability_score / 100)^2
        enriched["composite_score"] = round(remaining_today * ((deliv_score / 100.0) ** 2), 3)
        eligible_inboxes.append(enriched)

    pool_summary = {
        "total_candidates": len(raw_inboxes),
        "eligible_count": len(eligible_inboxes),
        "rejected_count": len(rejected_inboxes),
        "rejected": rejected_inboxes,
    }

    if not eligible_inboxes:
        return {
            "selected": None,
            "selection_reason": "NO_HEALTHY_INBOXES_AVAILABLE",
            "pool_summary": pool_summary,
        }

    # Check Lead-to-Sender Thread Affinity if lead_id is provided
    if lead_id:
        eligible_map = {str(i["id"]): i for i in eligible_inboxes if i.get("id")}
        locked_inbox_id = None

        # Check explicit affinity on candidate metadata or Supabase
        for inb in eligible_inboxes:
            assigned_leads = inb.get("affinity_lead_ids") or []
            if isinstance(assigned_leads, list) and str(lead_id) in [str(x) for x in assigned_leads]:
                locked_inbox_id = str(inb["id"])
                break

        if not locked_inbox_id and supabase:
            try:
                lock_q = (
                    supabase.table("campaign_lead_sender_locks")
                    .select("account_id, inbox_id")
                    .eq("workspace_id", clean_ws)
                    .eq("lead_id", str(lead_id))
                    .limit(1)
                    .execute()
                )
                if lock_q and getattr(lock_q, "data", None) and isinstance(lock_q.data, list) and len(lock_q.data) > 0:
                    row = lock_q.data[0]
                    cand_lock = str(row.get("inbox_id") or row.get("account_id") or "")
                    if cand_lock in eligible_map:
                        locked_inbox_id = cand_lock
            except Exception:
                pass

        if locked_inbox_id and locked_inbox_id in eligible_map:
            return {
                "selected": eligible_map[locked_inbox_id],
                "selection_reason": "THREAD_AFFINITY_LOCK",
                "strategy_applied": clean_strategy,
                "pool_summary": pool_summary,
            }

    # Apply Dispatch Strategy
    if clean_strategy == "ROUND_ROBIN":
        # Deterministic ordering by ID, then hash selection based on lead_id or campaign_id
        sorted_pool = sorted(eligible_inboxes, key=lambda x: str(x.get("id") or x.get("email")))
        seed_str = f"{clean_ws}:{campaign_id or ''}:{lead_id or datetime.now(timezone.utc).microsecond}"
        digest = int(hashlib.md5(seed_str.encode("utf-8")).hexdigest()[:8], 16)
        chosen = sorted_pool[digest % len(sorted_pool)]
        reason = "ROUND_ROBIN_HASH"
    elif clean_strategy == "CAPACITY_FIRST":
        sorted_pool = sorted(
            eligible_inboxes,
            key=lambda x: (x["remaining_capacity"], x["deliverability_score"], str(x.get("id") or "")),
            reverse=True,
        )
        chosen = sorted_pool[0]
        reason = "CAPACITY_FIRST_MAX_HEADROOM"
    else:
        # HEALTH_WEIGHTED default
        sorted_pool = sorted(
            eligible_inboxes,
            key=lambda x: (x["composite_score"], x["deliverability_score"], x["remaining_capacity"]),
            reverse=True,
        )
        chosen = sorted_pool[0]
        reason = "HEALTH_WEIGHTED_OPTIMAL"

    return {
        "selected": chosen,
        "selection_reason": reason,
        "strategy_applied": clean_strategy,
        "pool_summary": pool_summary,
    }


def record_inbox_delivery_outcome(
    supabase: Optional[Any],
    workspace_id: str,
    inbox_id: str,
    event_type: str,
    inbox_record: Optional[Dict[str, Any]] = None,
    bounce_threshold_pct: float = 2.5,
    spam_threshold_pct: float = 0.1,
) -> Dict[str, Any]:
    """
    Paranoia Layer 0, 1 & 2: Records an outbound email event ('sent', 'bounced', 'spam_complaint')
    against a sender inbox and immediately evaluates the deliverability tripwire.
    If tripped, transitions the inbox to QUARANTINED in Supabase and queues an outbox alert.
    Enforces strict IDOR tenant isolation.
    """
    if not workspace_id or not inbox_id:
        raise ValueError("workspace_id and inbox_id are required")

    clean_ws = str(workspace_id).strip()
    clean_id = str(inbox_id).strip()
    norm_event = str(event_type or "sent").strip().lower()

    record = dict(inbox_record) if isinstance(inbox_record, dict) else None
    if record is None and supabase:
        try:
            res = (
                supabase.table("email_sender_inboxes")
                .select("*")
                .eq("id", clean_id)
                .limit(1)
                .execute()
            )
            if res and getattr(res, "data", None) and isinstance(res.data, list) and len(res.data) > 0:
                record = dict(res.data[0])
        except Exception as exc:
            logger.debug(f"[EmailSenderPool] Lookup error for inbox {clean_id}: {exc}")

    if record is not None:
        rec_ws = record.get("workspace_id")
        if rec_ws and str(rec_ws).strip() != clean_ws:
            raise PermissionError("Cross-workspace access denied for sender inbox")
    else:
        record = {
            "id": clean_id,
            "workspace_id": clean_ws,
            "sent_count": 0,
            "sent_today": 0,
            "bounce_count": 0,
            "spam_complaint_count": 0,
            "status": "ACTIVE",
        }

    sent_count = max(0, int(record.get("sent_count", 0) or 0))
    sent_today = max(0, int(record.get("sent_today", 0) or 0))
    bounce_count = max(0, int(record.get("bounce_count", 0) or 0))
    spam_count = max(0, int(record.get("spam_complaint_count", 0) or 0))

    if norm_event in ("sent", "delivered"):
        sent_count += 1
        sent_today += 1
    elif norm_event in ("bounce", "bounced", "hard_bounce", "dropped"):
        bounce_count += 1
        if sent_count == 0:
            sent_count = 1
    elif norm_event in ("spam", "spam_complaint", "complained"):
        spam_count += 1
        if sent_count == 0:
            sent_count = 1

    record["sent_count"] = sent_count
    record["sent_today"] = sent_today
    record["bounce_count"] = bounce_count
    record["spam_complaint_count"] = spam_count

    tripwire = evaluate_inbox_deliverability_tripwire(
        record,
        bounce_threshold_pct=bounce_threshold_pct,
        spam_threshold_pct=spam_threshold_pct,
    )

    new_status = "QUARANTINED" if tripwire["should_quarantine"] else str(record.get("status") or "ACTIVE")
    update_payload: Dict[str, Any] = {
        "sent_count": sent_count,
        "sent_today": sent_today,
        "bounce_count": bounce_count,
        "spam_complaint_count": spam_count,
        "status": new_status,
    }
    if tripwire["should_quarantine"]:
        update_payload["quarantine_reason"] = tripwire["quarantine_reason"]
        update_payload["quarantined_until"] = tripwire["quarantined_until"]

    if supabase:
        try:
            supabase.table("email_sender_inboxes").update(update_payload).eq("id", clean_id).eq(
                "workspace_id", clean_ws
            ).execute()
        except Exception as exc:
            logger.debug(f"[EmailSenderPool] Could not persist inbox update for {clean_id}: {exc}")

        if tripwire["should_quarantine"]:
            try:
                supabase.table("outbox_events").insert({
                    "workspace_id": clean_ws,
                    "event_type": "deliverability_tripwire_triggered",
                    "payload": {
                        "workspace_id": clean_ws,
                        "event_type": "deliverability_tripwire_triggered",
                        "title": "Sender Inbox Quarantined by Deliverability Guard",
                        "body": f"Inbox {record.get('email', clean_id)} was automatically quarantined: {tripwire['quarantine_reason']}",
                        "inbox_id": clean_id,
                    },
                }).execute()
            except Exception as notif_exc:
                logger.debug(f"[EmailSenderPool] Could not insert tripwire notification: {notif_exc}")

    return {
        "inbox_id": clean_id,
        "workspace_id": clean_ws,
        "status": new_status,
        "quarantined": tripwire["should_quarantine"],
        "quarantine_reason": tripwire["quarantine_reason"],
        "quarantined_until": tripwire["quarantined_until"],
        "metrics": tripwire["metrics"],
    }
