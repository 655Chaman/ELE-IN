import hashlib
import logging
import math
from datetime import datetime, timedelta, time as dt_time, timezone
from typing import Optional, Dict, Any, Tuple, List
import pytz

from campaigns.backend.services.timezone_utils import (
    is_valid_iana_timezone,
    safe_localize,
    parse_schedule_config,
    is_working_hours,
)

logger = logging.getLogger(__name__)

# B2B Engagement Baseline: 10:00 AM (Morning Peak) and 14:00 PM (Afternoon Peak)
DEFAULT_B2B_PEAK_HOURS = [10, 14]


def compute_lead_jitter_minutes(lead_id: Optional[str], min_jitter: int = 5, max_jitter: int = 25) -> int:
    """
    Horizon 28: Anti-bot human pacing jitter.
    Layer 0 (Foundational): Computes deterministic pseudo-random minute offset from lead ID hash.
    Layer 1 (Environmental): Ensures spread between min_jitter and max_jitter to eliminate burst dispatch.
    Layer 2 (Paranoia): Safely handles None or empty lead_id with standard fallback.
    """
    if not lead_id or not isinstance(lead_id, str):
        return 12
    try:
        h = int(hashlib.md5(f"sto_jitter_{lead_id}".encode("utf-8")).hexdigest(), 16)
        span = max(1, max_jitter - min_jitter + 1)
        return min_jitter + (h % span)
    except Exception as e:
        logger.debug(f"compute_lead_jitter_minutes hash fallback: {e}")
        return 12


def compute_lead_sto_window(
    supabase=None,
    lead_id: Optional[str] = None,
    tz_str: str = "UTC",
    schedule: Optional[dict] = None
) -> Dict[str, Any]:
    """
    Horizon 28: Prospect Activity-Aware Send-Time Optimization Analysis.
    Layer 0 (Foundational): Analyzes historical email_events and inbound messages in lead's local timezone.
                            Clusters events into hours of the day and finds peak engagement hour.
    Layer 1 (Environmental): Catches missing tables, database connection errors, and query timeouts.
                             Falls back to B2B Industry Prior distributions seamlessly.
    Layer 2 (Paranoia): Bounds recommended hour to active working hours (start_hour <= hour < end_hour).
    """
    start_hour, end_hour, active_days = parse_schedule_config(schedule)
    valid_tz = tz_str if is_valid_iana_timezone(tz_str) else "UTC"

    try:
        local_tz = pytz.timezone(valid_tz)
    except Exception:
        local_tz = pytz.UTC

    hourly_scores: Dict[int, float] = {h: 0.0 for h in range(start_hour, end_hour)}
    total_data_points = 0

    if supabase and lead_id:
        try:
            # 1. Query email engagement events (opens = 1.0, clicks = 2.0)
            ev_res = supabase.table("email_events").select("created_at, event_type") \
                .eq("lead_id", lead_id).in_("event_type", ["open", "click"]).limit(100).execute()
            if isinstance(ev_res.data, list):
                for ev in ev_res.data:
                    dt_str = ev.get("created_at")
                    if not dt_str:
                        continue
                    try:
                        # Normalize ISO string
                        dt_clean = str(dt_str).replace("Z", "+00:00")
                        ev_dt = datetime.fromisoformat(dt_clean)
                        if ev_dt.tzinfo is None:
                            ev_dt = pytz.UTC.localize(ev_dt)
                        loc_dt = ev_dt.astimezone(local_tz)
                        h = loc_dt.hour
                        if start_hour <= h < end_hour:
                            weight = 2.0 if ev.get("event_type") == "click" else 1.0
                            hourly_scores[h] = hourly_scores.get(h, 0.0) + weight
                            total_data_points += 1
                    except Exception:
                        continue
        except Exception as e:
            logger.debug(f"compute_lead_sto_window email_events query error: {e}")

        try:
            # 2. Query inbound messages (reply = 3.0 weight)
            msg_res = supabase.table("messages").select("created_at") \
                .eq("lead_id", lead_id).eq("direction", "inbound").limit(50).execute()
            if isinstance(msg_res.data, list):
                for msg in msg_res.data:
                    dt_str = msg.get("created_at")
                    if not dt_str:
                        continue
                    try:
                        dt_clean = str(dt_str).replace("Z", "+00:00")
                        msg_dt = datetime.fromisoformat(dt_clean)
                        if msg_dt.tzinfo is None:
                            msg_dt = pytz.UTC.localize(msg_dt)
                        loc_dt = msg_dt.astimezone(local_tz)
                        h = loc_dt.hour
                        if start_hour <= h < end_hour:
                            hourly_scores[h] = hourly_scores.get(h, 0.0) + 3.0
                            total_data_points += 1
                    except Exception:
                        continue
        except Exception as e:
            logger.debug(f"compute_lead_sto_window messages query error: {e}")

    # If historical data points exist within working hours
    if total_data_points > 0:
        best_hour = max(hourly_scores, key=hourly_scores.get)
        confidence = min(0.95, round(1.0 - math.exp(-total_data_points / 3.0), 2))
        return {
            "best_hour": best_hour,
            "confidence": confidence,
            "data_points": total_data_points,
            "source": "historical_engagement",
            "scores": hourly_scores
        }

    # Cold lead fallback: Industry Prior B2B Distribution
    prior_idx = 0
    if lead_id:
        prior_idx = int(hashlib.md5(f"sto_prior_{lead_id}".encode("utf-8")).hexdigest(), 16) % len(DEFAULT_B2B_PEAK_HOURS)
    prior_hour = DEFAULT_B2B_PEAK_HOURS[prior_idx]

    # Bound to configured working hours
    if prior_hour < start_hour:
        prior_hour = start_hour
    elif prior_hour >= end_hour:
        prior_hour = max(start_hour, end_hour - 1)

    return {
        "best_hour": prior_hour,
        "confidence": 0.35,
        "data_points": 0,
        "source": "industry_prior",
        "scores": hourly_scores
    }


def calculate_sto_next_run(
    base_time: Optional[datetime],
    target_tz: str,
    lead_id: Optional[str] = None,
    schedule: Optional[dict] = None,
    supabase=None,
    min_gap_minutes: int = 15
) -> datetime:
    """
    Horizon 28: Calculates the optimal next run time using Send-Time Optimization.
    Layer 0 (Foundational): Computes best engagement hour + anti-bot jitter, targeting peak engagement.
    Layer 1 (Environmental): Localizes cleanly with safe_localize across DST shifts; enforces active days.
    Layer 2 (Paranoia): Clamps to working window and ensures next_run is strictly in the future.
    """
    valid_tz = target_tz if is_valid_iana_timezone(target_tz) else "UTC"
    try:
        tz = pytz.timezone(valid_tz)
    except Exception:
        tz = pytz.UTC

    # Ensure base_time is UTC-aware
    if base_time is None:
        base_time = datetime.utcnow().replace(tzinfo=pytz.UTC)
    elif base_time.tzinfo is None:
        base_time = pytz.UTC.localize(base_time)
    else:
        base_time = base_time.astimezone(pytz.UTC)

    local_dt = base_time.astimezone(tz)
    start_hour, end_hour, active_days = parse_schedule_config(schedule)

    # 1. Compute lead STO window and anti-bot jitter
    sto_info = compute_lead_sto_window(supabase=supabase, lead_id=lead_id, tz_str=valid_tz, schedule=schedule)
    best_hour = sto_info["best_hour"]
    jitter_mins = compute_lead_jitter_minutes(lead_id)

    # 2. Clamp target minute so it never overflows past end_hour
    target_minute = jitter_mins
    if best_hour == (end_hour - 1) and target_minute > 55:
        target_minute = 55

    # 3. Determine target date (today if still in the future, otherwise next active day)
    naive_local = local_dt.replace(tzinfo=None)
    slot_time_naive = dt_time(hour=best_hour, minute=target_minute, second=0)

    target_date = None
    if naive_local.weekday() in active_days:
        if (naive_local.hour < best_hour) or (naive_local.hour == best_hour and naive_local.minute < target_minute):
            # Target slot is later today!
            target_date = naive_local.date()

    if target_date is None:
        # Search next active day starting tomorrow
        for days_ahead in range(1, 15):
            candidate = naive_local.date() + timedelta(days=days_ahead)
            if candidate.weekday() in active_days:
                target_date = candidate
                break

    if target_date is None:
        target_date = naive_local.date() + timedelta(days=1)

    # 4. Localize target slot
    naive_target = datetime.combine(target_date, slot_time_naive)
    localized_target = safe_localize(tz, naive_target)
    utc_target = localized_target.astimezone(pytz.UTC)

    # 5. Ensure minimum gap from base_time
    min_required_time = base_time + timedelta(minutes=min_gap_minutes)
    if utc_target < min_required_time:
        # If target has passed or is too close, advance to next active day
        next_day = None
        for days_ahead in range(1, 15):
            candidate = target_date + timedelta(days=days_ahead)
            if candidate.weekday() in active_days:
                next_day = candidate
                break
        if next_day is None:
            next_day = target_date + timedelta(days=1)
        naive_target_next = datetime.combine(next_day, slot_time_naive)
        utc_target = safe_localize(tz, naive_target_next).astimezone(pytz.UTC)

    return utc_target


def should_use_sto(campaign: Optional[dict] = None, schedule: Optional[dict] = None) -> bool:
    """
    Checks if Send-Time Optimization is enabled for a given campaign or schedule.
    """
    if not campaign and not schedule:
        return False

    meta = (campaign or {}).get("metadata") or {}
    sched = schedule or meta.get("schedule") or {}

    scheduling_mode = str(meta.get("scheduling_mode", "")).strip().lower()
    if scheduling_mode in ("ai_sto", "sto_predictive", "send_time_optimization"):
        return True

    if meta.get("ai_sto_enabled") is True or meta.get("sto_enabled") is True:
        return True

    if sched.get("ai_sto_enabled") is True or sched.get("sto_enabled") is True:
        return True

    return False
