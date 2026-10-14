import pytz
from datetime import datetime, timedelta, time as dt_time
from typing import Optional, Tuple, Set, Any
from core.backend.services.limits import get_effective_usage_date

def is_valid_iana_timezone(tz: str) -> bool:
    if not tz or not isinstance(tz, str):
        return False
    if tz.upper() in ["EST", "PST", "IST", "GMT"]:
        return False
    try:
        pytz.timezone(tz)
        return True
    except (pytz.exceptions.UnknownTimeZoneError, Exception):
        return False

def resolve_target_timezone(campaign: dict, lead: dict) -> str:
    metadata = campaign.get("metadata", {}) or {}
    mode = metadata.get("scheduling_mode", "campaign_timezone")
    
    if mode == "lead_local_time":
        lead_tz = lead.get("timezone")
        if is_valid_iana_timezone(lead_tz):
            return lead_tz
        
        # Fallback to campaign timezone
        fallback = metadata.get("timezone", "UTC")
        if not is_valid_iana_timezone(fallback):
            fallback = "UTC" # Fallback if missing or invalid
        return fallback

    # Default to campaign_timezone for any other scheduling_mode
    fallback = metadata.get("timezone", "UTC")
    if not is_valid_iana_timezone(fallback):
        fallback = "UTC" # Fallback if missing or invalid
    return fallback

def parse_schedule_config(schedule: Optional[dict] = None) -> Tuple[int, int, Set[int]]:
    """
    Parses campaign scheduling configuration.
    Returns (start_hour, end_hour, active_days_set).
    Applies Three-Layer Paranoia:
      - Validates and clamps hours: 0 <= start_hour <= 23, 1 <= end_hour <= 24
      - Inverted or equal hours (start_hour >= end_hour) safely fall back to (9, 17)
      - Empty or corrupted active_days list falls back to Mon-Fri (or Mon-Sun if weekend sending enabled)
    """
    if not isinstance(schedule, dict):
        schedule = {}

    raw_start = schedule.get("start_hour")
    try:
        start_hour = int(raw_start) if raw_start is not None else 9
    except (ValueError, TypeError):
        start_hour = 9

    raw_end = schedule.get("end_hour")
    try:
        end_hour = int(raw_end) if raw_end is not None else 17
    except (ValueError, TypeError):
        end_hour = 17

    # Clamped to 0 <= start_hour <= 23 and 1 <= end_hour <= 24
    start_hour = max(0, min(23, start_hour))
    end_hour = max(1, min(24, end_hour))

    # Inverted or equal hours -> fall back to default standard hours (9 and 17)
    if start_hour >= end_hour:
        start_hour = 9
        end_hour = 17

    weekend_sending = bool(schedule.get("weekend_sending") or schedule.get("weekend_sending_enabled"))
    default_active_days = set(range(7)) if weekend_sending else {0, 1, 2, 3, 4}

    raw_active_days = schedule.get("active_days")
    if raw_active_days is not None:
        parsed_days = set()
        if isinstance(raw_active_days, (list, tuple, set)):
            for d in raw_active_days:
                try:
                    di = int(d)
                    if 0 <= di <= 6:
                        parsed_days.add(di)
                except (ValueError, TypeError):
                    continue
        if parsed_days:
            active_days = parsed_days
        else:
            active_days = default_active_days
    else:
        active_days = default_active_days

    return (start_hour, end_hour, active_days)

def safe_localize(tz: Any, dt_naive: datetime) -> datetime:
    """
    Safely localizes a naive datetime into the given pytz timezone.
    Protects against:
      - pytz.exceptions.NonExistentTimeError (spring-forward gap -> advance by 1 hour)
      - pytz.exceptions.AmbiguousTimeError (fall-back overlap -> default to is_dst=False)
    """
    if isinstance(tz, str):
        try:
            tz = pytz.timezone(tz)
        except Exception:
            tz = pytz.UTC
    elif tz is None:
        tz = pytz.UTC

    if dt_naive.tzinfo is not None:
        dt_naive = dt_naive.replace(tzinfo=None)

    try:
        return tz.localize(dt_naive, is_dst=None)
    except pytz.exceptions.NonExistentTimeError:
        try:
            return tz.localize(dt_naive + timedelta(hours=1), is_dst=None)
        except (pytz.exceptions.NonExistentTimeError, pytz.exceptions.AmbiguousTimeError):
            return tz.localize(dt_naive + timedelta(hours=1), is_dst=False)
    except pytz.exceptions.AmbiguousTimeError:
        return tz.localize(dt_naive, is_dst=False)
    except Exception:
        try:
            return tz.localize(dt_naive, is_dst=False)
        except Exception:
            return dt_naive.replace(tzinfo=pytz.UTC)

def is_working_hours(tz_str: str, schedule: Optional[dict] = None, now_dt: Optional[datetime] = None) -> bool:
    """
    Evaluates whether current time in tz_str is on an active day and between start_hour <= now.hour < end_hour.
    Falls back safely to UTC if tz_str is invalid.
    """
    try:
        if not tz_str or not isinstance(tz_str, str):
            tz = pytz.UTC
        else:
            tz = pytz.timezone(tz_str)
    except Exception:
        tz = pytz.UTC

    if now_dt is not None:
        if now_dt.tzinfo is None:
            now = safe_localize(tz, now_dt)
        else:
            now = now_dt.astimezone(tz)
    else:
        now = datetime.now(tz)

    start_hour, end_hour, active_days = parse_schedule_config(schedule)

    if now.weekday() not in active_days:
        return False
    if not (start_hour <= now.hour < end_hour):
        return False
    return True

def calculate_next_run_at(base_time: datetime, target_tz: str, schedule: Optional[dict] = None) -> datetime:
    """
    Calculates the next working run time for a given base_time and target timezone.
    If base_time is already in the working window, returns base_time (UTC-aware).
    Otherwise, finds the next active slot at start_hour:00:00 local time,
    using safe_localize to avoid DST crashes, returning UTC-aware datetime.
    """
    try:
        if not target_tz or not isinstance(target_tz, str):
            tz = pytz.UTC
        else:
            tz = pytz.timezone(target_tz)
    except Exception:
        tz = pytz.UTC

    # Ensure base_time is UTC aware
    if base_time is None:
        base_time = datetime.utcnow().replace(tzinfo=pytz.UTC)
    elif base_time.tzinfo is None:
        base_time = pytz.UTC.localize(base_time)
    else:
        base_time = base_time.astimezone(pytz.UTC)

    # Convert to local time
    local_dt = base_time.astimezone(tz)
    weekday = local_dt.weekday()
    hour = local_dt.hour

    start_hour, end_hour, active_days = parse_schedule_config(schedule)

    # In working window:
    if weekday in active_days and (start_hour <= hour < end_hour):
        return base_time

    naive_local = local_dt.replace(tzinfo=None)

    if weekday in active_days and hour < start_hour:
        # Move to start_hour local same day
        naive_target = naive_local.replace(hour=start_hour, minute=0, second=0, microsecond=0)
    else:
        # Search next active day starting from tomorrow (bounded loop max 14 days)
        naive_target = None
        for days_ahead in range(1, 15):
            candidate_date = (naive_local + timedelta(days=days_ahead)).date()
            if candidate_date.weekday() in active_days:
                naive_target = datetime.combine(
                    candidate_date,
                    dt_time(hour=start_hour, minute=0, second=0, microsecond=0)
                )
                break
        if naive_target is None:
            candidate_date = (naive_local + timedelta(days=1)).date()
            naive_target = datetime.combine(
                candidate_date,
                dt_time(hour=start_hour, minute=0, second=0, microsecond=0)
            )

    target_local = safe_localize(tz, naive_target)
    return target_local.astimezone(pytz.UTC)

def adjust_to_working_hours(dt_utc: datetime, tz_str: str, schedule: Optional[dict] = None) -> datetime:
    """
    Calls calculate_next_run_at and returns naive UTC datetime
    (preserving backward compatibility with callers that expect naive UTC).
    """
    next_run = calculate_next_run_at(dt_utc, tz_str, schedule=schedule)
    return next_run.astimezone(pytz.UTC).replace(tzinfo=None)

def next_working_day_9am(tz_str: str = "UTC", schedule: Optional[dict] = None, now_dt: Optional[datetime] = None) -> datetime:
    """
    Finds the next active day (starting from tomorrow) at start_hour:00:00 local time,
    safely localized, returning naive UTC datetime.
    """
    try:
        if not tz_str or not isinstance(tz_str, str):
            tz = pytz.UTC
        else:
            tz = pytz.timezone(tz_str)
    except Exception:
        tz = pytz.UTC

    if now_dt is not None:
        if now_dt.tzinfo is None:
            now = safe_localize(tz, now_dt)
        else:
            now = now_dt.astimezone(tz)
    else:
        now = datetime.now(tz)

    start_hour, end_hour, active_days = parse_schedule_config(schedule)

    target_date = None
    for days_ahead in range(1, 15):
        cand = now.date() + timedelta(days=days_ahead)
        if cand.weekday() in active_days:
            target_date = cand
            break

    if target_date is None:
        target_date = now.date() + timedelta(days=1)

    naive_slot = datetime.combine(target_date, dt_time(hour=start_hour, minute=0, second=0, microsecond=0))
    local_dt = safe_localize(tz, naive_slot)
    return local_dt.astimezone(pytz.UTC).replace(tzinfo=None)


