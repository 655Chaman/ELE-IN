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
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from core.backend.services.deliverability_guard import (
    evaluate_inbox_deliverability_tripwire,
    sanitize_domain_input,
)
from integrations.backend.services.mailbox_warmup_service import (
    calculate_warmup_ramp_projection,
    calculate_inbox_warmup_health_score,
)

logger = logging.getLogger(__name__)

VALID_PROVIDERS = {"sendgrid", "ses", "smtp", "google_workspace", "resend", "custom"}
VALID_STRATEGIES = {"HEALTH_WEIGHTED", "ROUND_ROBIN", "CAPACITY_FIRST", "DOMAIN_BALANCED"}

_EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_DOMAIN_REGEX = re.compile(
    r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,63}$"
)

# Common two-part public suffixes across major ccTLDs
_TWO_PART_PUBLIC_SUFFIXES = {
    # United Kingdom
    "co.uk", "org.uk", "gov.uk", "ac.uk", "net.uk", "me.uk", "ltd.uk", "plc.uk",
    # Australia
    "com.au", "net.au", "org.au", "edu.au", "gov.au",
    # New Zealand
    "co.nz", "net.nz", "org.nz", "govt.nz", "ac.nz",
    # Brazil
    "com.br", "net.br", "org.br", "gov.br", "edu.br",
    # Japan
    "co.jp", "ne.jp", "or.jp", "ac.jp", "go.jp",
    # India
    "co.in", "net.in", "org.in", "gen.in", "ind.in", "firm.in", "gov.in", "ac.in",
    # South Africa
    "co.za", "org.za", "net.za", "gov.za",
    # Singapore
    "com.sg", "org.sg", "edu.sg", "gov.sg",
    # Mexico
    "com.mx", "org.mx", "gob.mx", "edu.mx",
    # Argentina
    "com.ar", "net.ar", "org.ar", "gob.ar",
    # Turkey
    "com.tr", "org.tr", "gov.tr", "edu.tr",
    # Taiwan
    "com.tw", "org.tw", "gov.tw", "edu.tw",
    # Hong Kong
    "com.hk", "org.hk", "gov.hk", "edu.hk",
    # South Korea
    "co.kr", "ne.kr", "re.kr", "go.kr", "or.kr",
    # Indonesia
    "co.id", "or.id", "go.id", "ac.id",
    # Germany / France / Spain / Israel / Thailand / Others
    "com.de", "com.fr", "com.es", "co.il", "co.th",
}

_SLD_PREFIXES = {
    "co", "com", "org", "net", "gov", "ac", "edu", "ne", "or", "ltd", "gen", "firm", "ind", "govt", "gob"
}


def extract_root_domain(email_or_domain: Optional[str]) -> Optional[str]:
    """
    Paranoia Layer 0, 1 & 2: Extracts the effective root domain (eTLD+1) from an email or domain string.
    - Uses sanitize_domain_input to strip protocols, paths, query strings, ports, leading 'www.', and whitespace.
    - Strips subdomains to extract root domain (e.g. mail.getacme.com -> getacme.com,
      outbound.sales.acme.co.uk -> acme.co.uk, tryacme.io -> tryacme.io).
    - Accurately handles common two-part public suffixes (.co.uk, .com.au, .co.nz, .com.br, etc.).
    - Handles email addresses (e.g. alex@mail.getacme.com -> getacme.com).
    - Paranoia Layer 2: Validates with regex and returns None on malformed inputs or localhost/private IPs.
    """
    if not email_or_domain or not isinstance(email_or_domain, str):
        return None

    clean = sanitize_domain_input(email_or_domain)
    if not clean:
        return None

    parts = clean.split(".")
    if len(parts) < 2:
        return None

    suffix_candidate = f"{parts[-2]}.{parts[-1]}"
    is_two_part = (
        suffix_candidate in _TWO_PART_PUBLIC_SUFFIXES
        or (len(parts[-1]) == 2 and parts[-2] in _SLD_PREFIXES)
    )

    if is_two_part:
        if len(parts) < 3:
            return None
        root_parts = parts[-3:]
    else:
        root_parts = parts[-2:]

    candidate_root = ".".join(root_parts)
    sanitized = sanitize_domain_input(candidate_root)
    if not sanitized or not _DOMAIN_REGEX.match(sanitized):
        return None

    return sanitized


def evaluate_domain_burnout_tripwire(
    domain_metrics: Dict[str, Any],
    bounce_threshold_pct: float = 3.0,
    spam_threshold_pct: float = 0.1,
    min_sample_size: int = 15,
    cooldown_hours: int = 24,
) -> Dict[str, Any]:
    """
    Paranoia Layer 0, 1 & 2: Domain-level Circuit Breaker & Burnout Protection.
    - Paranoia Layer 1: Small-sample false-positive guard: does not trip percentage-based burnout
      unless total_sent >= min_sample_size or absolute bounces >= 5 or absolute spam >= 2.
    - Trips burnout if aggregate_bounce_rate_pct >= bounce_threshold_pct
      or aggregate_spam_rate_pct >= spam_threshold_pct
      or if >= 50% of inboxes on the domain are individually quarantined.
    - Returns:
      {"should_quarantine": bool, "quarantine_reason": Optional[str], "quarantined_until": Optional[str], "status": "BURNOUT_QUARANTINED" | "HEALTHY"}
      with 24h default cooldown.
    """
    if not isinstance(domain_metrics, dict):
        domain_metrics = {}

    safe_bounce_threshold = max(0.5, min(25.0, float(bounce_threshold_pct or 3.0)))
    safe_spam_threshold = max(0.01, min(5.0, float(spam_threshold_pct or 0.1)))
    safe_min_sample = max(5, min(500, int(min_sample_size or 15)))
    safe_cooldown = max(1, min(168, int(cooldown_hours or 24)))

    total_sent = max(0, int(domain_metrics.get("total_sent", 0) or 0))
    total_bounces = max(0, int(domain_metrics.get("total_bounces", 0) or 0))
    total_spam = max(0, int(domain_metrics.get("total_spam_complaints", 0) or 0))
    inbox_count = max(0, int(domain_metrics.get("inbox_count", 0) or 0))
    active_inbox_count = max(0, int(domain_metrics.get("active_inbox_count", 0) or 0))

    bounce_rate_pct = float(domain_metrics.get("aggregate_bounce_rate_pct", 0.0) or 0.0)
    if bounce_rate_pct == 0.0 and total_sent > 0 and total_bounces > 0:
        bounce_rate_pct = round((total_bounces / total_sent) * 100.0, 2)

    spam_rate_pct = float(domain_metrics.get("aggregate_spam_rate_pct", 0.0) or 0.0)
    if spam_rate_pct == 0.0 and total_sent > 0 and total_spam > 0:
        spam_rate_pct = round((total_spam / total_sent) * 100.0, 3)

    # Check for active existing cooldown
    q_until_raw = domain_metrics.get("quarantined_until")
    if q_until_raw:
        try:
            clean_str = str(q_until_raw).replace("Z", "+00:00")
            q_dt = datetime.fromisoformat(clean_str)
            if q_dt.tzinfo is None:
                q_dt = q_dt.replace(tzinfo=timezone.utc)
            if q_dt > datetime.now(timezone.utc):
                return {
                    "should_quarantine": True,
                    "quarantine_reason": domain_metrics.get("quarantine_reason") or "DOMAIN_BURNOUT_ACTIVE_COOLDOWN",
                    "quarantined_until": q_until_raw,
                    "status": "BURNOUT_QUARANTINED",
                }
        except Exception:
            pass

    reasons: List[str] = []
    sample_reached = total_sent >= safe_min_sample

    # Absolute floors
    if total_bounces >= 5:
        reasons.append(f"DOMAIN_ABSOLUTE_BOUNCE_CEILING_EXCEEDED (bounces={total_bounces} >= 5)")
    elif sample_reached and bounce_rate_pct >= safe_bounce_threshold:
        reasons.append(
            f"DOMAIN_BOUNCE_RATE_EXCEEDED ({bounce_rate_pct}% >= {safe_bounce_threshold}%, count={total_bounces}/{total_sent})"
        )

    if total_spam >= 2:
        reasons.append(f"DOMAIN_ABSOLUTE_SPAM_CEILING_EXCEEDED (spam={total_spam} >= 2)")
    elif sample_reached and spam_rate_pct >= safe_spam_threshold:
        reasons.append(
            f"DOMAIN_SPAM_RATE_EXCEEDED ({spam_rate_pct}% >= {safe_spam_threshold}%, count={total_spam}/{total_sent})"
        )

    # Majority inboxes quarantined condition (>= 50% and at least 2 inboxes quarantined)
    if inbox_count > 1:
        quarantined_inboxes = inbox_count - active_inbox_count
        if quarantined_inboxes >= 2 and (quarantined_inboxes / float(inbox_count)) >= 0.5:
            reasons.append(
                f"DOMAIN_MAJORITY_INBOXES_QUARANTINED ({quarantined_inboxes}/{inbox_count} inboxes quarantined >= 50%)"
            )

    should_quarantine = len(reasons) > 0
    now_utc = datetime.now(timezone.utc)
    quarantined_until = (now_utc + timedelta(hours=safe_cooldown)).isoformat() if should_quarantine else None
    quarantine_reason = "; ".join(reasons) if should_quarantine else None
    status = "BURNOUT_QUARANTINED" if should_quarantine else "HEALTHY"

    return {
        "should_quarantine": should_quarantine,
        "quarantine_reason": quarantine_reason,
        "quarantined_until": quarantined_until,
        "status": status,
    }


def _safe_int(val: Any, default: int = 0) -> int:
    try:
        if val is None:
            return default
        return int(val)
    except (ValueError, TypeError):
        return default


def aggregate_domain_metrics(
    inboxes: List[Dict[str, Any]],
    domain_daily_cap: int = 150,
) -> Dict[str, Dict[str, Any]]:
    """
    Paranoia Layer 0, 1 & 2: Groups inboxes by root domain and computes aggregate volume, deliverability,
    and burnout metrics.
    Computes for each domain:
      - domain: root domain
      - inbox_count: number of inboxes
      - active_inbox_count: number of non-quarantined/non-paused inboxes
      - total_sent: sum of sent_count
      - total_sent_today: sum of sent_today
      - domain_daily_cap: maximum sends across all inboxes for this domain per day
      - remaining_domain_capacity: max(0, domain_daily_cap - total_sent_today)
      - total_bounces: sum of bounce_count
      - total_spam_complaints: sum of spam_complaint_count
      - aggregate_bounce_rate_pct: round((total_bounces / total_sent * 100), 2) if total_sent > 0 else 0.0
      - aggregate_spam_rate_pct: round((total_spam_complaints / total_sent * 100), 3) if total_sent > 0 else 0.0
      - domain_burnout_status: evaluates health ("HEALTHY", "AT_RISK", "BURNOUT_QUARANTINED")
      - quarantined_until: timestamp if domain is in burnout quarantine
    """
    if not inboxes or not isinstance(inboxes, list):
        return {}

    safe_domain_daily_cap = max(1, min(10000, _safe_int(domain_daily_cap, 150)))
    domain_groups: Dict[str, List[Dict[str, Any]]] = {}

    for inb in inboxes:
        if not isinstance(inb, dict):
            continue
        email_or_domain = (
            inb.get("sender_domain")
            or inb.get("domain")
            or inb.get("email")
            or inb.get("from_email")
        )
        root_dom = extract_root_domain(email_or_domain)
        if not root_dom:
            continue
        if root_dom not in domain_groups:
            domain_groups[root_dom] = []
        domain_groups[root_dom].append(inb)

    metrics_by_domain: Dict[str, Dict[str, Any]] = {}

    for root_dom, dom_inboxes in domain_groups.items():
        inbox_count = len(dom_inboxes)
        active_inbox_count = sum(
            1 for inb in dom_inboxes
            if not _is_inbox_currently_quarantined(inb)
        )

        total_sent = sum(max(0, _safe_int(inb.get("sent_count"), 0)) for inb in dom_inboxes)
        total_sent_today = sum(max(0, _safe_int(inb.get("sent_today"), 0)) for inb in dom_inboxes)
        total_bounces = sum(max(0, _safe_int(inb.get("bounce_count"), 0)) for inb in dom_inboxes)
        total_spam = sum(max(0, _safe_int(inb.get("spam_complaint_count"), 0)) for inb in dom_inboxes)

        remaining_domain_cap = max(0, safe_domain_daily_cap - total_sent_today)
        bounce_rate_pct = round((total_bounces / total_sent * 100.0), 2) if total_sent > 0 else 0.0
        spam_rate_pct = round((total_spam / total_sent * 100.0), 3) if total_sent > 0 else 0.0

        existing_q_until = None
        existing_q_reason = None
        for inb in dom_inboxes:
            b_status = str(inb.get("domain_burnout_status") or "").upper()
            dom_q = inb.get("domain_quarantined_until")
            if b_status == "BURNOUT_QUARANTINED":
                existing_q_until = dom_q or inb.get("quarantined_until")
                existing_q_reason = inb.get("quarantine_reason") or "DOMAIN_BURNOUT_PREVIOUS_QUARANTINE"
                break
            elif dom_q:
                existing_q_until = dom_q
                existing_q_reason = inb.get("quarantine_reason") or "DOMAIN_BURNOUT_PREVIOUS_QUARANTINE"
                break

        preliminary_metrics = {
            "domain": root_dom,
            "inbox_count": inbox_count,
            "active_inbox_count": active_inbox_count,
            "total_sent": total_sent,
            "total_sent_today": total_sent_today,
            "domain_daily_cap": safe_domain_daily_cap,
            "remaining_domain_capacity": remaining_domain_cap,
            "total_bounces": total_bounces,
            "total_spam_complaints": total_spam,
            "aggregate_bounce_rate_pct": bounce_rate_pct,
            "aggregate_spam_rate_pct": spam_rate_pct,
            "quarantined_until": existing_q_until,
            "quarantine_reason": existing_q_reason,
        }

        tripwire_res = evaluate_domain_burnout_tripwire(preliminary_metrics)

        if tripwire_res["should_quarantine"]:
            burnout_status = "BURNOUT_QUARANTINED"
            quarantined_until = tripwire_res["quarantined_until"]
            quarantine_reason = tripwire_res["quarantine_reason"]
        else:
            quarantined_until = None
            quarantine_reason = None
            if (
                (total_sent >= 15 and bounce_rate_pct >= 2.0)
                or (total_sent >= 15 and spam_rate_pct >= 0.05)
                or (inbox_count > 1 and active_inbox_count < inbox_count)
                or (total_sent < 15 and (total_bounces >= 3 or total_spam >= 1))
                or (remaining_domain_cap <= max(5, int(safe_domain_daily_cap * 0.15)))
            ):
                burnout_status = "AT_RISK"
            else:
                burnout_status = "HEALTHY"

        metrics_by_domain[root_dom] = {
            "domain": root_dom,
            "inbox_count": inbox_count,
            "active_inbox_count": active_inbox_count,
            "total_sent": total_sent,
            "total_sent_today": total_sent_today,
            "domain_daily_cap": safe_domain_daily_cap,
            "remaining_domain_capacity": remaining_domain_cap,
            "total_bounces": total_bounces,
            "total_spam_complaints": total_spam,
            "aggregate_bounce_rate_pct": bounce_rate_pct,
            "aggregate_spam_rate_pct": spam_rate_pct,
            "domain_burnout_status": burnout_status,
            "quarantined_until": quarantined_until,
            "quarantine_reason": quarantine_reason,
        }

    return metrics_by_domain


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
    Paranoia Layer 0, 1 & 2: Computes the effective daily cold outreach cap for a sender inbox.
    - If warmup_enabled is False, returns safe_daily_limit without ramp restrictions.
    - If warmup_enabled is True:
      - Reads curve_type = inbox.get("warmup_curve_type", "LOGARITHMIC").
      - Uses calculate_warmup_ramp_projection to compute current day's allocated cold outreach cap.
      - Evaluates calculate_inbox_warmup_health_score:
        - If NEEDS_RECOVERY: applies 50% throttle to cold cap.
        - If EMERGENCY_PAUSED: sets cold outreach cap to 0.
      - Clamps return between 0 and safe_daily_limit.
    """
    if not isinstance(inbox, dict):
        return 50

    try:
        raw_max = int(inbox.get("daily_limit", 50) or 50)
    except (ValueError, TypeError):
        raw_max = 50
    safe_daily_limit = max(1, min(2000, raw_max))

    # Check warmup status / enabled flag
    warmup_flag = inbox.get("warmup_enabled")
    if warmup_flag is False or str(warmup_flag).lower() in ("false", "0"):
        warmup_enabled = False
    elif warmup_flag is True or str(warmup_flag).lower() in ("true", "1"):
        warmup_enabled = True
    elif str(inbox.get("warmup_status", "")).lower() in ("warming", "active", "needs_recovery"):
        warmup_enabled = True
    else:
        warmup_enabled = False

    if not warmup_enabled:
        return safe_daily_limit

    curve_type = inbox.get("warmup_curve_type") or inbox.get("ramp_strategy") or "LOGARITHMIC"

    try:
        start_limit = max(1, min(safe_daily_limit, int(inbox.get("warmup_start_limit") or inbox.get("start_limit") or 5)))
    except (ValueError, TypeError):
        start_limit = min(5, safe_daily_limit)

    try:
        target_limit = max(start_limit, min(200, safe_daily_limit))
    except (ValueError, TypeError):
        target_limit = safe_daily_limit

    try:
        ramp_days = max(7, min(90, int(inbox.get("warmup_ramp_days") or inbox.get("ramp_days") or 28)))
    except (ValueError, TypeError):
        ramp_days = 28

    try:
        days_active = max(0, int(inbox.get("warmup_days_active") if inbox.get("warmup_days_active") is not None else (inbox.get("current_ramp_day") or 0)))
    except (ValueError, TypeError):
        days_active = 0

    # Legacy linear increment support: if warmup_increment_per_day is explicitly provided
    # and no adaptive warmup curve type is specified, maintain backward compatibility
    if "warmup_increment_per_day" in inbox and "warmup_curve_type" not in inbox and "ramp_strategy" not in inbox:
        try:
            increment = max(1, min(100, int(inbox.get("warmup_increment_per_day", 5) or 5)))
        except (ValueError, TypeError):
            increment = 5
        ramped_cap = start_limit + (days_active * increment)
        cold_cap = max(0, min(safe_daily_limit, ramped_cap))
    else:
        # Calculate ramp projection
        projection_data = calculate_warmup_ramp_projection(
            curve_type=str(curve_type),
            start_limit=start_limit,
            target_limit=target_limit,
            ramp_days=ramp_days,
            current_day=days_active,
        )
        cold_cap = int(projection_data.get("today_cold_cap", 0))

    # Evaluate health score
    health = calculate_inbox_warmup_health_score(inbox)
    status = str(health.get("status") or "").upper()
    emergency_paused = bool(health.get("emergency_paused", False)) or (status == "EMERGENCY_PAUSED")

    if emergency_paused or str(inbox.get("status") or "").upper() == "EMERGENCY_PAUSED" or str(inbox.get("warmup_status") or "").upper() == "EMERGENCY_PAUSED":
        cold_cap = 0
    elif status == "NEEDS_RECOVERY" or health.get("throttle_cold_ratio", 1.0) <= 0.5 or str(inbox.get("warmup_status") or "").upper() == "NEEDS_RECOVERY":
        cold_cap = int(cold_cap * 0.5)

    return max(0, min(safe_daily_limit, cold_cap))


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
    domain_daily_cap: int = 150,
    affinity_fallback_mode: str = "same_domain",
    campaign_type: str = "cold",
    is_warmup: bool = False,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Paranoia Layer 0, 1 & 2: Selects the optimal healthy sender inbox from the workspace pool.
    1. Enforces strict workspace_id tenant isolation (blocks cross-workspace inbox leakage).
    2. Groups inboxes by root domain, computing aggregate domain volume and burnout tripwires.
    3. Rejects inboxes belonging to burnout-quarantined domains or domains with exhausted daily capacity.
    4. Enforces hourly velocity limits and warmup ramp caps.
    5. Preserves Lead-to-Sender Thread Affinity with 'same_domain', 'any_healthy', or 'postpone' fallbacks.
    6. Dispatches via HEALTH_WEIGHTED, ROUND_ROBIN, CAPACITY_FIRST, or DOMAIN_BALANCED strategy.
    """
    if not workspace_id or not str(workspace_id).strip():
        return {"selected": None, "error": "workspace_id is required", "pool_summary": {}}

    clean_ws = str(workspace_id).strip()
    clean_strategy = str(strategy or "HEALTH_WEIGHTED").upper()
    if clean_strategy not in VALID_STRATEGIES:
        clean_strategy = "HEALTH_WEIGHTED"

    safe_domain_daily_cap = max(1, min(10000, int(domain_daily_cap or 150)))
    clean_fallback_mode = str(affinity_fallback_mode or "same_domain").strip().lower()
    if clean_fallback_mode not in ("same_domain", "any_healthy", "postpone"):
        clean_fallback_mode = "same_domain"

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

    # Compute aggregate domain metrics across all candidate inboxes
    domain_metrics_map = aggregate_domain_metrics(raw_inboxes, domain_daily_cap=safe_domain_daily_cap)

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
        root_dom = extract_root_domain(email_addr)
        if not is_valid_sender_email(email_addr) or not root_dom:
            rejected_inboxes.append({"id": inb_id, "reason": "INVALID_EMAIL_SYNTAX"})
            continue

        d_metrics = domain_metrics_map.get(root_dom, {})

        # Check domain-level burnout
        if d_metrics.get("domain_burnout_status") == "BURNOUT_QUARANTINED":
            rejected_inboxes.append({
                "id": inb_id,
                "email": email_addr,
                "domain": root_dom,
                "reason": "DOMAIN_BURNOUT_QUARANTINED",
                "domain_quarantine_reason": d_metrics.get("quarantine_reason"),
            })
            continue

        # Check domain daily cap
        if d_metrics.get("remaining_domain_capacity", 0) <= 0:
            rejected_inboxes.append({
                "id": inb_id,
                "email": email_addr,
                "domain": root_dom,
                "reason": "DOMAIN_DAILY_CAP_EXHAUSTED",
            })
            continue

        # Check inbox-level quarantine or pause
        if _is_inbox_currently_quarantined(inb):
            rejected_inboxes.append({"id": inb_id, "email": email_addr, "reason": "QUARANTINED_OR_PAUSED"})
            continue

        # Check hourly velocity limit
        hourly_limit = inb.get("hourly_limit")
        if hourly_limit is not None:
            try:
                h_lim = int(hourly_limit)
                s_hour = int(inb.get("sent_this_hour", 0) or 0)
                if h_lim > 0 and s_hour >= h_lim:
                    rejected_inboxes.append({
                        "id": inb_id,
                        "email": email_addr,
                        "reason": "HOURLY_LIMIT_EXHAUSTED",
                        "hourly_limit": h_lim,
                        "sent_this_hour": s_hour,
                    })
                    continue
            except (ValueError, TypeError):
                pass

        # Check live deliverability tripwire
        tripwire = evaluate_inbox_deliverability_tripwire(inb)
        if tripwire["should_quarantine"]:
            rejected_inboxes.append({
                "id": inb_id,
                "email": email_addr,
                "reason": "DELIVERABILITY_TRIPWIRE_TRIPPED",
                "tripwire_reason": tripwire["quarantine_reason"],
            })
            continue

        # Check warmup health status
        w_health = calculate_inbox_warmup_health_score(inb)
        w_status = str(w_health.get("status") or "PEAK_HEALTH").upper()
        current_health_score = int(w_health.get("health_score", 100))
        is_warmup_emergency_paused = False

        if w_status == "EMERGENCY_PAUSED" or w_health.get("emergency_paused"):
            is_warmup_emergency_paused = True
        elif (
            str(inb.get("warmup_status") or "").upper() == "EMERGENCY_PAUSED"
            or str(inb.get("warmup_health_status") or "").upper() == "EMERGENCY_PAUSED"
            or str(inb.get("status") or "").upper() == "EMERGENCY_PAUSED"
            or bool(inb.get("emergency_paused", False))
        ):
            # Auto-recovery: If health score has recovered to >= 70, emergency pause lifts
            if current_health_score < 70:
                is_warmup_emergency_paused = True

        # Check if cold campaign (default is cold unless explicitly warmup)
        is_cold_campaign = (str(campaign_type or "cold").lower() != "warmup") and not is_warmup
        if is_warmup_emergency_paused and is_cold_campaign:
            logger.warning(
                f"[EmailSenderPool] Mailbox {email_addr} rejected: WARMUP_EMERGENCY_PAUSED (health_score={current_health_score})"
            )
            rejected_inboxes.append({"id": inb_id, "email": email_addr, "reason": "WARMUP_EMERGENCY_PAUSED"})
            continue

        if w_status == "NEEDS_RECOVERY":
            logger.info(
                f"[EmailSenderPool] Mailbox {email_addr} is in NEEDS_RECOVERY (health_score={current_health_score}); respecting throttled capacity."
            )

        # Check warmup daily capacity
        effective_cap = calculate_warmup_daily_cap(inb)
        try:
            sent_today = max(0, int(inb.get("sent_today", 0) or 0))
        except (ValueError, TypeError):
            sent_today = 0

        remaining_today = max(0, effective_cap - sent_today)
        if remaining_today <= 0:
            rejected_inboxes.append({"id": inb_id, "email": email_addr, "reason": "DAILY_CAP_EXHAUSTED"})
            continue

        try:
            deliv_score = max(1, min(100, int(inb.get("deliverability_score", 95) or 95)))
        except (ValueError, TypeError):
            deliv_score = 95

        enriched = dict(inb)
        enriched["email"] = email_addr
        enriched["sender_domain"] = root_dom
        enriched["domain"] = root_dom
        enriched["effective_daily_limit"] = effective_cap
        enriched["remaining_capacity"] = remaining_today
        enriched["deliverability_score"] = deliv_score
        # Composite weight: remaining capacity * (deliverability_score / 100)^2
        enriched["composite_score"] = round(remaining_today * ((deliv_score / 100.0) ** 2), 3)
        enriched["domain_metrics"] = d_metrics
        enriched["domain_burnout_status"] = d_metrics.get("domain_burnout_status", "HEALTHY")
        curve_type_val = inb.get("warmup_curve_type") or inb.get("ramp_strategy") or "LOGARITHMIC"
        enriched["warmup_health_score"] = current_health_score
        enriched["warmup_curve_type"] = curve_type_val
        enriched["warmup_health_status"] = w_status
        enriched["warmup_days_active"] = inb.get("warmup_days_active") if inb.get("warmup_days_active") is not None else (inb.get("current_ramp_day") or 0)
        eligible_inboxes.append(enriched)

    pool_summary = {
        "total_candidates": len(raw_inboxes),
        "eligible_count": len(eligible_inboxes),
        "rejected_count": len(rejected_inboxes),
        "rejected": rejected_inboxes,
        "domain_metrics": domain_metrics_map,
    }

    # Check Lead-to-Sender Thread Affinity if lead_id is provided
    affinity_override_reason = None
    if lead_id:
        raw_map = {str(i.get("id")): i for i in raw_inboxes if isinstance(i, dict) and i.get("id")}
        eligible_map = {str(i["id"]): i for i in eligible_inboxes if i.get("id")}
        locked_inbox_id = None
        locked_inbox_record = None

        # Check explicit affinity on candidate metadata
        for inb in raw_inboxes:
            if not isinstance(inb, dict):
                continue
            assigned_leads = inb.get("affinity_lead_ids") or []
            if isinstance(assigned_leads, list) and str(lead_id) in [str(x) for x in assigned_leads]:
                locked_inbox_id = str(inb.get("id") or "")
                locked_inbox_record = inb
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
                    if cand_lock:
                        locked_inbox_id = cand_lock
                        locked_inbox_record = raw_map.get(cand_lock)
            except Exception:
                pass

        if locked_inbox_id:
            # 1. Healthy and eligible: return it directly
            if locked_inbox_id in eligible_map:
                chosen = eligible_map[locked_inbox_id]
                chosen_domain = chosen.get("sender_domain")
                d_metrics = domain_metrics_map.get(chosen_domain, {})
                return {
                    "selected": chosen,
                    "selection_reason": "THREAD_AFFINITY_LOCK",
                    "strategy_applied": clean_strategy,
                    "sender_domain": chosen_domain,
                    "domain_metrics": d_metrics,
                    "domain_burnout_status": d_metrics.get("domain_burnout_status", "HEALTHY"),
                    "warmup_health_score": chosen.get("warmup_health_score"),
                    "warmup_curve_type": chosen.get("warmup_curve_type"),
                    "warmup_days_active": chosen.get("warmup_days_active"),
                    "pool_summary": pool_summary,
                }

            # 2. Locked inbox is capped/quarantined or unavailable
            locked_domain = None
            if locked_inbox_record:
                locked_domain = extract_root_domain(
                    locked_inbox_record.get("sender_domain")
                    or locked_inbox_record.get("domain")
                    or locked_inbox_record.get("email")
                    or locked_inbox_record.get("from_email")
                )

            if clean_fallback_mode == "postpone":
                return {
                    "selected": None,
                    "selection_reason": "AFFINITY_INBOX_CAPPED_POSTPONE",
                    "postpone_required": True,
                    "sender_domain": locked_domain,
                    "domain_metrics": domain_metrics_map.get(locked_domain, {}) if locked_domain else {},
                    "domain_burnout_status": domain_metrics_map.get(locked_domain, {}).get("domain_burnout_status", "UNKNOWN") if locked_domain else "UNKNOWN",
                    "pool_summary": pool_summary,
                }
            elif clean_fallback_mode == "same_domain":
                same_domain_candidates = [
                    i for i in eligible_inboxes if i.get("sender_domain") == locked_domain
                ] if locked_domain else []
                if same_domain_candidates:
                    sorted_same = sorted(
                        same_domain_candidates,
                        key=lambda x: (
                            -int(x.get("remaining_capacity", 0) or 0),
                            -float(x.get("deliverability_score", 0) or 0),
                            str(x.get("id") or ""),
                        ),
                    )
                    chosen = sorted_same[0]
                    chosen_domain = chosen.get("sender_domain")
                    d_metrics = domain_metrics_map.get(chosen_domain, {})
                    return {
                        "selected": chosen,
                        "selection_reason": "THREAD_AFFINITY_SAME_DOMAIN_FALLBACK",
                        "strategy_applied": clean_strategy,
                        "sender_domain": chosen_domain,
                        "domain_metrics": d_metrics,
                        "domain_burnout_status": d_metrics.get("domain_burnout_status", "HEALTHY"),
                        "warmup_health_score": chosen.get("warmup_health_score"),
                        "warmup_curve_type": chosen.get("warmup_curve_type"),
                        "warmup_days_active": chosen.get("warmup_days_active"),
                        "pool_summary": pool_summary,
                    }
                else:
                    affinity_override_reason = "THREAD_AFFINITY_ANY_HEALTHY_FALLBACK"
            elif clean_fallback_mode == "any_healthy":
                affinity_override_reason = "THREAD_AFFINITY_ANY_HEALTHY_FALLBACK"

    if not eligible_inboxes:
        return {
            "selected": None,
            "selection_reason": "NO_HEALTHY_INBOXES_AVAILABLE",
            "sender_domain": None,
            "domain_metrics": domain_metrics_map,
            "domain_burnout_status": "UNKNOWN",
            "pool_summary": pool_summary,
        }

    # Apply Dispatch Strategy
    if clean_strategy == "DOMAIN_BALANCED":
        # Group eligible inboxes by root domain
        domain_to_inboxes: Dict[str, List[Dict[str, Any]]] = {}
        for inb in eligible_inboxes:
            d = inb.get("sender_domain") or extract_root_domain(inb.get("email")) or "unknown"
            if d not in domain_to_inboxes:
                domain_to_inboxes[d] = []
            domain_to_inboxes[d].append(inb)

        # Sort domains by (total_sent_today, -remaining_domain_capacity, domain)
        def domain_sort_key(d_name: str):
            m = domain_metrics_map.get(d_name, {})
            t_sent = int(m.get("total_sent_today", 0) or 0)
            rem_cap = int(m.get("remaining_domain_capacity", 0) or 0)
            return (t_sent, -rem_cap, d_name)

        sorted_domains = sorted(domain_to_inboxes.keys(), key=domain_sort_key)
        chosen_domain_name = sorted_domains[0]
        domain_inboxes = domain_to_inboxes[chosen_domain_name]

        # Within chosen domain, pick inbox with maximum remaining capacity or lowest sent_today
        sorted_domain_inboxes = sorted(
            domain_inboxes,
            key=lambda x: (
                -int(x.get("remaining_capacity", 0) or 0),
                int(x.get("sent_today", 0) or 0),
                str(x.get("id") or ""),
            ),
        )
        chosen = sorted_domain_inboxes[0]
        reason = "DOMAIN_BALANCED_OPTIMAL"

    elif clean_strategy == "ROUND_ROBIN":
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

    final_reason = affinity_override_reason if affinity_override_reason else reason
    chosen_domain = chosen.get("sender_domain") or extract_root_domain(chosen.get("email"))
    d_metrics = domain_metrics_map.get(chosen_domain, {})

    return {
        "selected": chosen,
        "selection_reason": final_reason,
        "strategy_applied": clean_strategy,
        "sender_domain": chosen_domain,
        "domain_metrics": d_metrics,
        "domain_burnout_status": d_metrics.get("domain_burnout_status", "HEALTHY"),
        "warmup_health_score": chosen.get("warmup_health_score"),
        "warmup_curve_type": chosen.get("warmup_curve_type"),
        "warmup_days_active": chosen.get("warmup_days_active"),
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
    domain_bounce_threshold_pct: float = 3.0,
    domain_spam_threshold_pct: float = 0.1,
    domain_daily_cap: int = 150,
) -> Dict[str, Any]:
    """
    Paranoia Layer 0, 1 & 2: Records an outbound email event ('sent', 'bounced', 'spam_complaint')
    against a sender inbox, evaluates deliverability tripwires, and checks domain-level aggregate health.
    If domain burnout tripwire triggers, flags domain burnout and transitions all inboxes sharing that
    domain to QUARANTINED in Supabase.
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

    # Evaluate individual inbox deliverability tripwire
    tripwire = evaluate_inbox_deliverability_tripwire(
        record,
        bounce_threshold_pct=bounce_threshold_pct,
        spam_threshold_pct=spam_threshold_pct,
    )

    # Evaluate domain aggregate burnout tripwire
    root_domain = extract_root_domain(
        record.get("sender_domain")
        or record.get("domain")
        or record.get("email")
        or record.get("from_email")
    )

    domain_inboxes_list: List[Dict[str, Any]] = [record]
    if supabase and root_domain:
        try:
            all_inb_res = (
                supabase.table("email_sender_inboxes")
                .select("*")
                .eq("workspace_id", clean_ws)
                .execute()
            )
            raw_list = getattr(all_inb_res, "data", None)
            if isinstance(raw_list, list):
                found_dom_inboxes = []
                replaced = False
                for item in raw_list:
                    if not isinstance(item, dict):
                        continue
                    item_dom = extract_root_domain(
                        item.get("sender_domain")
                        or item.get("domain")
                        or item.get("email")
                        or item.get("from_email")
                    )
                    if item_dom == root_domain:
                        if str(item.get("id")) == clean_id:
                            found_dom_inboxes.append(record)
                            replaced = True
                        else:
                            found_dom_inboxes.append(item)
                if not replaced:
                    found_dom_inboxes.append(record)
                domain_inboxes_list = found_dom_inboxes
        except Exception as exc:
            logger.debug(f"[EmailSenderPool] Domain inboxes lookup error: {exc}")

    domain_metrics_map = aggregate_domain_metrics(domain_inboxes_list, domain_daily_cap=domain_daily_cap)
    d_metrics = domain_metrics_map.get(root_domain, {}) if root_domain else {}
    domain_tripwire = (
        evaluate_domain_burnout_tripwire(
            d_metrics,
            bounce_threshold_pct=domain_bounce_threshold_pct,
            spam_threshold_pct=domain_spam_threshold_pct,
        )
        if d_metrics
        else {"should_quarantine": False, "quarantine_reason": None, "quarantined_until": None, "status": "HEALTHY"}
    )

    domain_burnout_triggered = bool(domain_tripwire.get("should_quarantine", False))

    if domain_burnout_triggered:
        new_status = "QUARANTINED"
        q_reason = f"DOMAIN_BURNOUT: {domain_tripwire.get('quarantine_reason')}"
        q_until = domain_tripwire.get("quarantined_until")
    elif tripwire["should_quarantine"]:
        new_status = "QUARANTINED"
        q_reason = tripwire["quarantine_reason"]
        q_until = tripwire["quarantined_until"]
    else:
        new_status = str(record.get("status") or "ACTIVE")
        q_reason = None
        q_until = None

    record["status"] = new_status
    if domain_burnout_triggered:
        record["domain_burnout_status"] = "BURNOUT_QUARANTINED"
        record["quarantine_reason"] = q_reason
        record["quarantined_until"] = q_until

    update_payload: Dict[str, Any] = {
        "sent_count": sent_count,
        "sent_today": sent_today,
        "bounce_count": bounce_count,
        "spam_complaint_count": spam_count,
        "status": new_status,
    }
    if q_reason:
        update_payload["quarantine_reason"] = q_reason
        update_payload["quarantined_until"] = q_until
    if domain_burnout_triggered:
        update_payload["domain_burnout_status"] = "BURNOUT_QUARANTINED"

    if supabase:
        try:
            supabase.table("email_sender_inboxes").update(update_payload).eq("id", clean_id).eq(
                "workspace_id", clean_ws
            ).execute()
        except Exception as exc:
            logger.debug(f"[EmailSenderPool] Could not persist inbox update for {clean_id}: {exc}")

        # If domain burnout tripwire triggers, update status for ALL inboxes sharing that domain
        if domain_burnout_triggered and root_domain:
            domain_update_payload = {
                "status": "QUARANTINED",
                "domain_burnout_status": "BURNOUT_QUARANTINED",
                "quarantine_reason": q_reason,
                "quarantined_until": q_until,
            }
            for dom_inb in domain_inboxes_list:
                d_inb_id = str(dom_inb.get("id") or "")
                if d_inb_id and d_inb_id != clean_id:
                    try:
                        supabase.table("email_sender_inboxes").update(domain_update_payload).eq(
                            "id", d_inb_id
                        ).eq("workspace_id", clean_ws).execute()
                    except Exception as dom_exc:
                        logger.debug(f"[EmailSenderPool] Could not quarantine inbox {d_inb_id} on domain {root_domain}: {dom_exc}")

            try:
                supabase.table("outbox_events").insert({
                    "workspace_id": clean_ws,
                    "event_type": "domain_burnout_tripwire_triggered",
                    "payload": {
                        "workspace_id": clean_ws,
                        "event_type": "domain_burnout_tripwire_triggered",
                        "title": f"Sender Domain {root_domain} Quarantined by Burnout Guard",
                        "body": f"All inboxes for domain {root_domain} quarantined: {domain_tripwire.get('quarantine_reason')}",
                        "domain": root_domain,
                        "quarantined_until": q_until,
                        "metrics": d_metrics,
                    },
                }).execute()
            except Exception as notif_exc:
                logger.debug(f"[EmailSenderPool] Could not insert domain burnout event: {notif_exc}")

        elif tripwire["should_quarantine"]:
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
        "quarantined": (tripwire["should_quarantine"] or domain_burnout_triggered),
        "quarantine_reason": q_reason,
        "quarantined_until": q_until,
        "metrics": tripwire["metrics"],
        "domain": root_domain,
        "domain_metrics": d_metrics,
        "domain_burnout_triggered": domain_burnout_triggered,
        "domain_burnout_status": d_metrics.get("domain_burnout_status", "HEALTHY") if d_metrics else "HEALTHY",
    }
