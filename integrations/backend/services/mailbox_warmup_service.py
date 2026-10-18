"""
Mailbox Warmup Engine & Adaptive Ramp Curves Service
===================================================
Provides smart, automated mailbox warm-up schedule projections,
health reputation scoring, synthetic peer exchange simulation,
and daily schedule advancement ticks.

Follows the Three-Layer Logic Architecture (Paranoia Framework):
- Layer 0: Core mathematical curves (Linear, Sigmoid/Logarithmic, Aggressive),
           reputation weighting, peer exchange generation, and state progression.
- Layer 1: Environmental Failure Analysis (safe math bounds, no division by zero,
           clamped parameters, Supabase transaction fallback).
- Layer 2: Human Paranoia (sanitization of bad user input, negative numbers,
           missing fields, malformed types, extreme limits).
"""

from __future__ import annotations

import math
import random
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, Optional, List, Union

logger = logging.getLogger(__name__)


class WarmupCurveType(str, Enum):
    """
    Ramp curve strategies for mailbox warming.
    """
    LINEAR = "LINEAR"
    LOGARITHMIC = "LOGARITHMIC"  # S-Curve / Sigmoid progression
    AGGRESSIVE = "AGGRESSIVE"    # Accelerated curve for aged/pre-warmed domains


class WarmupHealthStatus(str, Enum):
    """
    Categorized health status based on 0-100 reputation score.
    """
    PEAK_HEALTH = "PEAK_HEALTH"          # Score >= 85: pristine reputation
    RAMPING_OPTIMAL = "RAMPING_OPTIMAL"  # Score 70-84: healthy ramp
    NEEDS_RECOVERY = "NEEDS_RECOVERY"    # Score 50-69: automatic 50% cold outreach throttle
    EMERGENCY_PAUSED = "EMERGENCY_PAUSED"# Score < 50: 100% cold outreach paused


def normalize_curve_type(curve_type: Union[str, WarmupCurveType]) -> WarmupCurveType:
    """
    Paranoia Layer 2: Sanitizes any string or enum variation into a canonical WarmupCurveType.
    Supports common synonyms like 's-curve', 'sigmoid', 'balanced', 'gentle', 'fast'.
    """
    if isinstance(curve_type, WarmupCurveType):
        return curve_type

    if not isinstance(curve_type, str):
        return WarmupCurveType.LOGARITHMIC

    cleaned = curve_type.strip().upper()
    if cleaned in ("LINEAR", "LINE"):
        return WarmupCurveType.LINEAR
    if cleaned in ("AGGRESSIVE", "FAST", "AGED", "QUICK"):
        return WarmupCurveType.AGGRESSIVE
    if cleaned in ("LOGARITHMIC", "LOG", "SIGMOID", "S_CURVE", "S-CURVE", "BALANCED", "GENTLE"):
        return WarmupCurveType.LOGARITHMIC

    return WarmupCurveType.LOGARITHMIC


def _calculate_curve_progress(progress_ratio: float, curve_type: WarmupCurveType) -> float:
    """
    Paranoia Layer 0 & 1: Evaluates normalized progress (0.0 to 1.0) according to the curve strategy.
    Guarantees output is strictly clamped in [0.0, 1.0].
    """
    # Clamp input progress
    t = max(0.0, min(1.0, float(progress_ratio)))

    if curve_type == WarmupCurveType.LINEAR:
        return t

    if curve_type == WarmupCurveType.AGGRESSIVE:
        # Square root curve: steep early growth suitable for aged domains
        return math.sqrt(t)

    # WarmupCurveType.LOGARITHMIC (Sigmoid / S-Curve)
    # Slow gentle crawl in first 20-25% of days, accelerated growth in middle 50%,
    # and smooth asymptotic plateau towards target at the end.
    k = 8.0
    shift = 0.5
    # Clamping exponent to [-20, 20] prevents float overflow
    exp_arg = max(-20.0, min(20.0, -k * (t - shift)))
    sig_raw = 1.0 / (1.0 + math.exp(exp_arg))

    sig_min = 1.0 / (1.0 + math.exp(k * shift))       # sig(0.0)
    sig_max = 1.0 / (1.0 + math.exp(-k * (1.0 - shift))) # sig(1.0)

    denom = sig_max - sig_min
    if denom <= 0.0:
        return t

    normalized_sig = (sig_raw - sig_min) / denom
    return max(0.0, min(1.0, normalized_sig))


def calculate_warmup_ramp_projection(
    curve_type: str = "LOGARITHMIC",
    start_limit: int = 5,
    target_limit: int = 50,
    ramp_days: int = 28,
    current_day: int = 0
) -> Dict[str, Any]:
    """
    Computes day-by-day warmup ramp projections and daily outreach capacity allocation.

    Paranoia Framework:
    - Layer 0: Computes daily warmup vs cold outreach ratio and volume according to
               the specified curve (Linear, Logarithmic/Sigmoid, or Aggressive).
    - Layer 1: Clamps start_limit >= 1, target_limit <= 200, ramp_days in [7, 90],
               current_day >= 0. Ensures target_limit >= start_limit.
    - Layer 2: Handles invalid types, floats, None values, string numbers, and out-of-bound days.

    Returns:
        Dict with keys: curve_type, start_limit, target_limit, ramp_days,
        current_day, today_warmup_cap, today_cold_cap, projection
    """
    # Paranoia Layer 1 & 2: Input Coercion and Clamping
    try:
        raw_start = int(start_limit)
    except (ValueError, TypeError):
        raw_start = 5

    try:
        raw_target = int(target_limit)
    except (ValueError, TypeError):
        raw_target = 50

    try:
        raw_days = int(ramp_days)
    except (ValueError, TypeError):
        raw_days = 28

    try:
        raw_curr = int(current_day)
    except (ValueError, TypeError):
        raw_curr = 0

    safe_start = max(1, min(200, raw_start))
    safe_target = max(safe_start, min(200, raw_target))
    safe_days = max(7, min(90, raw_days))
    safe_current_day = max(0, raw_curr)

    resolved_curve = normalize_curve_type(curve_type)

    projection: List[Dict[str, Any]] = []

    for d in range(safe_days + 1):
        ratio_progress = d / safe_days if safe_days > 0 else 1.0
        curve_factor = _calculate_curve_progress(ratio_progress, resolved_curve)

        # Total daily sending capacity on day d
        # On day 0: exactly safe_start. On day safe_days: exactly safe_target.
        if d == 0:
            total_cap = safe_start
        elif d >= safe_days:
            total_cap = safe_target
        else:
            total_cap = safe_start + int(round((safe_target - safe_start) * curve_factor))
        total_cap = max(safe_start, min(safe_target, total_cap))

        # Warmup ratio: starts at 100% on day 0, smooth quadratic decay to 40% at day 14 (50%),
        # and reaches 20% maintenance floor at day 28 (100%).
        decay_factor = (1.0 - ratio_progress) ** 2
        warmup_ratio = 0.20 + 0.80 * decay_factor
        warmup_ratio = max(0.20, min(1.0, warmup_ratio))

        warmup_ratio_pct = round(warmup_ratio * 100.0, 1)

        if d == 0:
            # Day 0 is strictly 100% warmup; no cold emails allowed
            warmup_cap = total_cap
            cold_cap = 0
            warmup_ratio_pct = 100.0
        else:
            warmup_cap = int(round(total_cap * warmup_ratio))
            warmup_cap = max(1, min(total_cap, warmup_cap))
            cold_cap = max(0, total_cap - warmup_cap)

        # Invariant check: warmup_cap + cold_cap == total_cap
        if warmup_cap + cold_cap != total_cap:
            cold_cap = max(0, total_cap - warmup_cap)

        projection.append({
            "day": d,
            "warmup_cap": warmup_cap,
            "cold_outreach_cap": cold_cap,
            "total_daily_cap": total_cap,
            "warmup_ratio_pct": warmup_ratio_pct
        })

    # Determine today's caps based on current_day
    capped_lookup_day = min(safe_current_day, safe_days)
    today_entry = projection[capped_lookup_day]

    # If current_day is past the ramp schedule, calculate for current_day with maintenance floor
    if safe_current_day > safe_days:
        today_total = safe_target
        today_warmup = max(1, int(round(today_total * 0.20)))
        today_cold = max(0, today_total - today_warmup)
    else:
        today_warmup = today_entry["warmup_cap"]
        today_cold = today_entry["cold_outreach_cap"]

    return {
        "curve_type": resolved_curve.value,
        "start_limit": safe_start,
        "target_limit": safe_target,
        "ramp_days": safe_days,
        "current_day": safe_current_day,
        "today_warmup_cap": today_warmup,
        "today_cold_cap": today_cold,
        "projection": projection
    }


def calculate_inbox_warmup_health_score(
    inbox: Dict[str, Any],
    recent_metrics: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Evaluates 0-100 reputation score based on:
    - Inbox age / days active (weight 20): <7 days = 5-10 pts, 14 days = 15 pts, >=30 days = 20 pts.
    - Bounce rate (weight 30): 0% = 30 pts, <1.5% = 25 pts, <3.0% = 15 pts, >=3% = 0 pts.
    - Spam complaint rate (weight 30): 0% = 30 pts, <0.05% = 20 pts, <0.1% = 10 pts, >=0.1% = 0 pts.
    - Peer engagement rate (weight 20): open/reply rate in warmup pool.

    Status categorization:
    - PEAK_HEALTH (score >= 85): 100% cold volume allowed
    - RAMPING_OPTIMAL (score 70-84): 100% cold volume allowed
    - NEEDS_RECOVERY (score 50-69): automatic 50% throttle on cold outreach
    - EMERGENCY_PAUSED (score < 50): 100% pause on cold outreach until health recovers >= 70

    Returns:
        Dict with keys: health_score, status, throttle_cold_ratio, emergency_paused, recommendations
    """
    safe_inbox = inbox if isinstance(inbox, dict) else {}
    metrics = recent_metrics if isinstance(recent_metrics, dict) else {}

    recommendations: List[str] = []

    # 1. Inbox age / days active evaluation (Weight: 20)
    try:
        days_active = int(
            metrics.get("warmup_days_active")
            or safe_inbox.get("warmup_days_active")
            or safe_inbox.get("current_ramp_day")
            or 0
        )
    except (ValueError, TypeError):
        days_active = 0
    days_active = max(0, days_active)

    if days_active >= 30:
        age_score = 20
    elif days_active >= 14:
        age_score = 15
    elif days_active >= 7:
        age_score = 12
    elif days_active >= 3:
        age_score = 10
        recommendations.append("Inbox active for under 7 days. Building initial domain IP trust.")
    else:
        age_score = 5
        recommendations.append("Brand new mailbox (<3 days active). Keep cold volume at minimum.")

    # 2. Bounce rate evaluation (Weight: 30)
    # Checks recent_metrics and safe_inbox for percentage values or counts
    total_sent = 0
    try:
        total_sent = int(metrics.get("total_sent") or safe_inbox.get("total_sent") or 0)
    except (ValueError, TypeError):
        total_sent = 0

    total_bounces = 0
    try:
        total_bounces = int(metrics.get("total_bounces") or safe_inbox.get("total_bounces") or 0)
    except (ValueError, TypeError):
        total_bounces = 0

    def _find_metric(keys: List[str]) -> Optional[Any]:
        for k in keys:
            if metrics.get(k) is not None:
                return metrics.get(k)
        for k in keys:
            if safe_inbox.get(k) is not None:
                return safe_inbox.get(k)
        return None

    try:
        raw_bounce_rate = _find_metric(["aggregate_bounce_rate_pct", "bounce_rate_pct", "bounce_rate"])
        if raw_bounce_rate is not None:
            bounce_rate_pct = float(raw_bounce_rate)
        elif total_sent > 0 and total_bounces > 0:
            bounce_rate_pct = round((total_bounces / total_sent) * 100.0, 2)
        else:
            bounce_rate_pct = 0.0
    except (ValueError, TypeError):
        bounce_rate_pct = 0.0

    bounce_rate_pct = max(0.0, bounce_rate_pct)

    if bounce_rate_pct <= 0.0:
        bounce_score = 30
    elif bounce_rate_pct < 1.5:
        bounce_score = 25
    elif bounce_rate_pct < 3.0:
        bounce_score = 15
        recommendations.append(f"Elevated bounce rate ({bounce_rate_pct}%). Verify recipient lists with MX/SMTP checks.")
    else:
        bounce_score = 0
        recommendations.append(f"Critical bounce rate ({bounce_rate_pct}% >= 3.0%). Clean contact database immediately.")

    # 3. Spam complaint rate evaluation (Weight: 30)
    total_spam = 0
    try:
        total_spam = int(metrics.get("total_spam_complaints") or safe_inbox.get("total_spam_complaints") or 0)
    except (ValueError, TypeError):
        total_spam = 0

    try:
        raw_spam_rate = _find_metric(["spam_complaint_rate_pct", "spam_rate_pct", "spam_rate", "spam_complaints_rate"])
        if raw_spam_rate is not None:
            spam_rate_pct = float(raw_spam_rate)
        elif total_sent > 0 and total_spam > 0:
            spam_rate_pct = round((total_spam / total_sent) * 100.0, 4)
        else:
            spam_rate_pct = 0.0
    except (ValueError, TypeError):
        spam_rate_pct = 0.0

    spam_rate_pct = max(0.0, spam_rate_pct)

    if spam_rate_pct <= 0.0:
        spam_score = 30
    elif spam_rate_pct < 0.05:
        spam_score = 20
    elif spam_rate_pct < 0.10:
        spam_score = 10
        recommendations.append(f"Spam complaint rate ({spam_rate_pct}%) is near danger zone. Adjust subject lines and ICP targeting.")
    else:
        spam_score = 0
        recommendations.append(f"High spam complaint rate ({spam_rate_pct}% >= 0.1%). Halt cold campaigns to prevent blacklisting.")

    # 4. Peer engagement rate evaluation (Weight: 20)
    # Evaluates open & reply rate in the warmup pool
    try:
        raw_engagement = _find_metric([
            "peer_engagement_rate_pct",
            "engagement_rate_pct",
            "target_reply_rate_pct",
            "reply_rate_pct",
            "engagement_rate"
        ])
        if raw_engagement is not None:
            engagement_rate_pct = float(raw_engagement)
        else:
            # Default healthy baseline for newly configured warmups
            engagement_rate_pct = 35.0
    except (ValueError, TypeError):
        engagement_rate_pct = 35.0

    engagement_rate_pct = max(0.0, min(100.0, engagement_rate_pct))

    if engagement_rate_pct >= 40.0:
        engagement_score = 20
    elif engagement_rate_pct >= 25.0:
        engagement_score = 15
    elif engagement_rate_pct >= 15.0:
        engagement_score = 10
        recommendations.append(f"Moderate peer engagement ({engagement_rate_pct}%). Increase warmup reply depth.")
    elif engagement_rate_pct > 0.0:
        engagement_score = 5
        recommendations.append("Low peer engagement. Ensure peer warmup pool is active and auto-replying.")
    else:
        engagement_score = 0
        recommendations.append("No peer engagement recorded. Verify warmup swarm connectivity.")

    total_score = age_score + bounce_score + spam_score + engagement_score
    total_score = max(0, min(100, total_score))

    # Status Categorization & Throttling
    if total_score >= 85:
        status = WarmupHealthStatus.PEAK_HEALTH
        throttle_cold_ratio = 1.0
        emergency_paused = False
        if not recommendations:
            recommendations.append("Mailbox health is pristine. Optimal deliverability across major ESPs.")
    elif total_score >= 70:
        status = WarmupHealthStatus.RAMPING_OPTIMAL
        throttle_cold_ratio = 1.0
        emergency_paused = False
        if not recommendations:
            recommendations.append("Mailbox ramping smoothly within safe deliverability thresholds.")
    elif total_score >= 50:
        status = WarmupHealthStatus.NEEDS_RECOVERY
        throttle_cold_ratio = 0.5
        emergency_paused = False
        recommendations.append("Health degraded into recovery zone. Cold outreach automatically throttled by 50%.")
    else:
        status = WarmupHealthStatus.EMERGENCY_PAUSED
        throttle_cold_ratio = 0.0
        emergency_paused = True
        recommendations.append("Critical mailbox health (<50). 100% pause on cold outreach until health recovers >= 70.")

    return {
        "health_score": total_score,
        "status": status.value,
        "throttle_cold_ratio": float(throttle_cold_ratio),
        "emergency_paused": bool(emergency_paused),
        "recommendations": recommendations,
        "breakdown": {
            "age_score": age_score,
            "bounce_score": bounce_score,
            "spam_score": spam_score,
            "engagement_score": engagement_score
        }
    }


# Synthetic B2B template repository for peer warmup simulation
_B2B_TOPICS = [
    ("Q3 planning sync", "product roadmap alignment and Q3 deliverables"),
    ("Quick question regarding workflow automation", "your team's setup for webhook data ingestion"),
    ("Notes from our discussion", "the action items and integration checkpoints we reviewed"),
    ("Follow up on data sync", "the batch data sync latency metrics we discussed yesterday"),
    ("Feedback on proposal draft", "the technical architecture slides in the shared workspace"),
    ("Scheduling brief sync", "a 15-minute quick sync later this week regarding API rate limits"),
    ("Resource allocation overview", "sprint velocity and lead distribution for upcoming campaigns")
]

_B2B_REPLIES = [
    "Thanks for sending this over! Looked through the details and everything matches our requirements. Let's proceed as planned.",
    "Appreciate the quick follow-up. I've reviewed the notes and flagged one small adjustment on the checklist. Looking forward to our sync.",
    "Great catch on this. I've synced with the engineering team and we are ready to move forward. Will update the ticket shortly.",
    "Thanks for the heads up. I reviewed the attached points and they look solid. Let's touch base on Thursday to finalize."
]


def simulate_peer_warmup_exchange(
    sender_inbox: Dict[str, Any],
    peer_inbox: Dict[str, Any],
    thread_depth: int = 1
) -> Dict[str, Any]:
    """
    Generates a natural synthetic B2B conversation pair between two warmup pool mailboxes.

    Paranoia Layer 0 & 2:
    - Creates realistic subject line and multi-turn email interaction.
    - Simulates full email lifecycle: sent, rescued from spam, starred/important, and replied.
    - Safely handles missing email addresses with fallback identifiers.
    """
    safe_sender = sender_inbox if isinstance(sender_inbox, dict) else {}
    safe_peer = peer_inbox if isinstance(peer_inbox, dict) else {}

    sender_email = (
        safe_sender.get("email")
        or safe_sender.get("email_address")
        or "sender@warmup-pool.ele-in.internal"
    )
    sender_name = safe_sender.get("sender_name") or safe_sender.get("name") or "Alex Taylor"

    peer_email = (
        safe_peer.get("email")
        or safe_peer.get("email_address")
        or "peer@warmup-pool.ele-in.internal"
    )
    peer_name = safe_peer.get("sender_name") or safe_peer.get("name") or "Jordan Lee"

    safe_depth = max(1, min(10, int(thread_depth) if isinstance(thread_depth, (int, float)) else 1))

    # Pick topic pair
    topic_subject, topic_detail = random.choice(_B2B_TOPICS)
    subject = f"{topic_subject}"

    initial_body = (
        f"Hi {peer_name},\n\n"
        f"Hope you are having a productive week. Wanted to quickly connect regarding {topic_detail}.\n"
        f"Let me know if the proposed timelines work on your end.\n\n"
        f"Best regards,\n{sender_name}"
    )

    reply_body = (
        f"Hi {sender_name},\n\n"
        f"{random.choice(_B2B_REPLIES)}\n\n"
        f"Best,\n{peer_name}"
    )

    exchange_id = f"wm-ex-{int(datetime.now(timezone.utc).timestamp())}-{random.randint(1000, 9999)}"
    thread_id = f"th-{exchange_id}"

    return {
        "status": "completed",
        "sender": sender_email,
        "recipient": peer_email,
        "landed_inbox": True,
        "saved_from_spam": True,
        "starred": True,
        "marked_important": True,
        "replied": True,
        "thread_depth": safe_depth,
        "subject": subject,
        "initial_message": initial_body,
        "reply_message": reply_body,
        "exchange_id": exchange_id,
        "thread_id": thread_id,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


def advance_inbox_warmup_tick(
    inbox: Dict[str, Any],
    supabase: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Safely increments warmup_days_active / current_ramp_day,
    recalculates health and ramp caps, and updates Supabase if provided with try/except fallback.

    Paranoia Framework:
    - Layer 0: Increments active days, recomputes health score and daily caps.
    - Layer 1: Database mutation wrapped in try/except. Returns updated state dictionary
               even if Supabase is unreachable or encounters an error.
    - Layer 2: Sanitizes incoming dictionary, guarantees non-negative integer states.
    """
    if not isinstance(inbox, dict):
        safe_inbox: Dict[str, Any] = {}
    else:
        safe_inbox = dict(inbox)

    # 1. Increment days active safely
    try:
        current_days = int(
            safe_inbox.get("warmup_days_active")
            if safe_inbox.get("warmup_days_active") is not None
            else safe_inbox.get("current_ramp_day")
            if safe_inbox.get("current_ramp_day") is not None
            else 0
        )
    except (ValueError, TypeError):
        current_days = 0

    new_days_active = max(0, current_days) + 1
    safe_inbox["warmup_days_active"] = new_days_active
    safe_inbox["current_ramp_day"] = new_days_active

    # 2. Extract configuration parameters with safe defaults
    curve_type = safe_inbox.get("ramp_strategy") or safe_inbox.get("curve_type") or "LOGARITHMIC"
    start_limit = safe_inbox.get("warmup_start_limit") or safe_inbox.get("start_limit") or 5
    target_limit = safe_inbox.get("max_daily_limit") or safe_inbox.get("target_limit") or safe_inbox.get("daily_limit") or 50
    ramp_days = safe_inbox.get("ramp_days") or 28

    # 3. Calculate new projection and today's caps
    ramp_result = calculate_warmup_ramp_projection(
        curve_type=str(curve_type),
        start_limit=int(start_limit) if str(start_limit).isdigit() else 5,
        target_limit=int(target_limit) if str(target_limit).isdigit() else 50,
        ramp_days=int(ramp_days) if str(ramp_days).isdigit() else 28,
        current_day=new_days_active
    )

    safe_inbox["today_warmup_cap"] = ramp_result["today_warmup_cap"]
    safe_inbox["today_cold_cap"] = ramp_result["today_cold_cap"]
    safe_inbox["current_daily_limit"] = ramp_result["today_warmup_cap"] + ramp_result["today_cold_cap"]

    # 4. Recalculate health score
    health_result = calculate_inbox_warmup_health_score(safe_inbox)
    safe_inbox["health_score"] = health_result["health_score"]
    safe_inbox["health_status"] = health_result["status"]
    safe_inbox["throttle_cold_ratio"] = health_result["throttle_cold_ratio"]
    safe_inbox["emergency_paused"] = health_result["emergency_paused"]
    safe_inbox["recommendations"] = health_result["recommendations"]
    safe_inbox["updated_at"] = datetime.now(timezone.utc).isoformat()

    # 5. Database persistence with resilient fallback (Layer 1)
    supabase_updated = False
    supabase_error = None

    if supabase is not None and safe_inbox.get("id"):
        inbox_id = str(safe_inbox.get("id"))
        update_payload = {
            "current_ramp_day": new_days_active,
            "current_daily_limit": safe_inbox["current_daily_limit"],
            "health_score": safe_inbox["health_score"],
            "updated_at": safe_inbox["updated_at"]
        }
        # Include warmup_status mapping
        if health_result["emergency_paused"]:
            update_payload["warmup_status"] = "paused"
        elif new_days_active >= int(ramp_days if str(ramp_days).isdigit() else 28):
            update_payload["warmup_status"] = "graduated"
        else:
            update_payload["warmup_status"] = "warming"

        # Attempt updating warmup_mailboxes table, fallback to mailboxes or sender_inboxes
        tables_to_try = ["warmup_mailboxes", "mailboxes", "sender_inboxes"]
        for tbl in tables_to_try:
            try:
                res = supabase.table(tbl).update(update_payload).eq("id", inbox_id).execute()
                if res and (hasattr(res, "data") or hasattr(res, "error")):
                    supabase_updated = True
                    break
            except Exception as e:
                supabase_error = str(e)
                logger.debug(f"[advance_inbox_warmup_tick] Failed updating table {tbl}: {e}")

    safe_inbox["supabase_updated"] = supabase_updated
    if supabase_error:
        safe_inbox["supabase_error"] = supabase_error

    safe_inbox["ramp_projection"] = ramp_result

    return safe_inbox
