import hashlib
import random
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
    campaign = campaign if isinstance(campaign, dict) else {}
    lead = lead if isinstance(lead, dict) else {}

    metadata = campaign.get("metadata", {}) or {}
    mode = metadata.get("scheduling_mode", "campaign_timezone")
    
    fallback = metadata.get("timezone", "UTC")
    if not is_valid_iana_timezone(fallback):
        fallback = "UTC" # Fallback if missing or invalid

    if mode == "lead_local_time":
        lead_tz = lead.get("timezone")
        if is_valid_iana_timezone(lead_tz):
            return lead_tz
        
        # If empty or invalid, try inferring timezone using LocationTimezoneService
        try:
            from leads.backend.services.location_timezone_service import LocationTimezoneService
            loc = lead.get("location") or lead.get("p_location") or lead.get("city")
            country = lead.get("country")
            phone = lead.get("phone")
            inferred = LocationTimezoneService.infer_timezone(
                location=loc,
                country=country,
                phone=phone
            )
            if is_valid_iana_timezone(inferred):
                return inferred
        except Exception:
            pass

        return fallback

    # Default to campaign_timezone for any other scheduling_mode
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
    # unless overnight cross-midnight sending is explicitly permitted (Leak 7 Fix)
    allow_overnight = bool(
        schedule.get("overnight_sending")
        or schedule.get("overnight_sending_enabled")
        or schedule.get("cross_midnight")
        or schedule.get("allow_overnight")
    )
    if start_hour >= end_hour and not (allow_overnight and start_hour > end_hour):
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

WEEKDAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

def is_national_holiday(dt: datetime, country_code: str = "US") -> bool:
    """
    Checks if a given date is a national public holiday in the specified country.
    Three-layer paranoia:
      - Gracefully falls back to False if holidays library fails or country code is invalid.
      - Normalizes UK -> GB.
    """
    try:
        import holidays
        cc = (country_code or "US").strip().upper()
        if cc == "UK":
            cc = "GB"
        year = dt.year
        country_holidays = holidays.country_holidays(cc, years=[year, year + 1])
        return dt.date() in country_holidays
    except Exception:
        return False

def get_day_override_window(
    dt_local: datetime,
    day_overrides: Optional[dict]
) -> Optional[Tuple[bool, int, int, int, int]]:
    """
    Parses day-specific operational window from day_schedule_overrides.
    Returns (enabled, start_hour, start_minute, end_hour, end_minute) or None if no override.
    """
    if not isinstance(day_overrides, dict) or not day_overrides:
        return None
    
    day_idx = dt_local.weekday()
    day_name = WEEKDAY_NAMES[day_idx]
    
    day_config = day_overrides.get(day_name)
    if day_config is None:
        day_config = day_overrides.get(str(day_idx))
    if not isinstance(day_config, dict):
        return None
    
    enabled = bool(day_config.get("enabled", True))
    raw_start = str(day_config.get("start", "08:00"))
    raw_end = str(day_config.get("end", "18:00"))
    
    try:
        s_parts = raw_start.split(":")
        s_h = max(0, min(23, int(s_parts[0])))
        s_m = max(0, min(59, int(s_parts[1]))) if len(s_parts) > 1 else 0
    except Exception:
        s_h, s_m = 8, 0

    try:
        e_parts = raw_end.split(":")
        e_h = max(0, min(24, int(e_parts[0])))
        e_m = max(0, min(59, int(e_parts[1]))) if len(e_parts) > 1 else 0
    except Exception:
        e_h, e_m = 18, 0

    return (enabled, s_h, s_m, e_h, e_m)

def is_working_hours(
    tz_str: str,
    schedule: Optional[dict] = None,
    now_dt: Optional[datetime] = None,
    guardrails: Optional[dict] = None
) -> bool:
    """
    Evaluates whether current time in tz_str is within active working hours.
    Three-Layer Paranoia:
      - Layer 0: Checks active days and start_hour <= hour < end_hour.
      - Layer 1: Evaluates day_schedule_overrides (day-specific enabled flag and start/end minutes).
      - Layer 2: Evaluates pause_on_national_holidays using official country holiday calendars.
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

    effective_guardrails = guardrails if isinstance(guardrails, dict) else {}
    if not effective_guardrails and isinstance(schedule, dict):
        effective_guardrails = (
            schedule.get("deliverability_guardrails")
            or schedule.get("guardrails")
            or schedule
        )

    # 1. National Holiday Auto-Pause check
    pause_holidays = bool(
        effective_guardrails.get("pause_on_national_holidays")
        or (isinstance(schedule, dict) and schedule.get("pause_on_national_holidays"))
    )
    if pause_holidays:
        country = (
            effective_guardrails.get("national_holiday_country")
            or (isinstance(schedule, dict) and schedule.get("national_holiday_country"))
            or "US"
        )
        if is_national_holiday(now, country):
            return False

    # 2. Granular Day Matrix (day_schedule_overrides) check
    day_overrides = (
        effective_guardrails.get("day_schedule_overrides")
        or (isinstance(schedule, dict) and schedule.get("day_schedule_overrides"))
    )
    override = get_day_override_window(now, day_overrides)
    if override is not None:
        enabled, s_h, s_m, e_h, e_m = override
        if not enabled:
            return False
        
        start_minute = s_h * 60 + s_m
        end_minute = e_h * 60 + e_m
        current_minute = now.hour * 60 + now.minute
        
        if start_minute < end_minute:
            return start_minute <= current_minute < end_minute
        else:
            # Cross-midnight window
            return current_minute >= start_minute or current_minute < end_minute

    # 3. Standard schedule fallback
    start_hour, end_hour, active_days = parse_schedule_config(schedule)

    if now.weekday() not in active_days:
        return False
    if start_hour < end_hour:
        if not (start_hour <= now.hour < end_hour):
            return False
    else:
        # Cross-midnight window (Leak 7 Fix)
        if not (now.hour >= start_hour or now.hour < end_hour):
            return False
    return True

def calculate_next_run_at(
    base_time: datetime,
    target_tz: str,
    schedule: Optional[dict] = None,
    guardrails: Optional[dict] = None
) -> datetime:
    """
    Calculates the next working run time for a given base_time and target timezone.
    If base_time is already in the working window, returns base_time (UTC-aware).
    Otherwise, finds the next active slot taking into account day-by-day overrides and national holidays,
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
        base_time = datetime.now(timezone.utc)
    elif base_time.tzinfo is None:
        base_time = pytz.UTC.localize(base_time)
    else:
        base_time = base_time.astimezone(pytz.UTC)

    # Convert to local time
    local_dt = base_time.astimezone(tz)

    effective_guardrails = guardrails if isinstance(guardrails, dict) else {}
    if not effective_guardrails and isinstance(schedule, dict):
        effective_guardrails = (
            schedule.get("deliverability_guardrails")
            or schedule.get("guardrails")
            or schedule
        )

    pause_holidays = bool(
        effective_guardrails.get("pause_on_national_holidays")
        or (isinstance(schedule, dict) and schedule.get("pause_on_national_holidays"))
    )
    country = (
        effective_guardrails.get("national_holiday_country")
        or (isinstance(schedule, dict) and schedule.get("national_holiday_country"))
        or "US"
    )
    day_overrides = (
        effective_guardrails.get("day_schedule_overrides")
        or (isinstance(schedule, dict) and schedule.get("day_schedule_overrides"))
    )

    # In working window check
    if is_working_hours(target_tz, schedule=schedule, now_dt=base_time, guardrails=guardrails):
        return base_time

    naive_local = local_dt.replace(tzinfo=None)

    # Check if today still has an upcoming window
    today_override = get_day_override_window(local_dt, day_overrides)
    today_is_holiday = pause_holidays and is_national_holiday(local_dt, country)
    start_hour, end_hour, active_days = parse_schedule_config(schedule)

    can_run_today = False
    today_start_h = start_hour
    today_start_m = 0

    if not today_is_holiday:
        if today_override is not None:
            t_enabled, t_sh, t_sm, t_eh, t_em = today_override
            if t_enabled:
                curr_min = local_dt.hour * 60 + local_dt.minute
                start_min = t_sh * 60 + t_sm
                if curr_min < start_min:
                    can_run_today = True
                    today_start_h = t_sh
                    today_start_m = t_sm
        elif local_dt.weekday() in active_days and local_dt.hour < start_hour:
            can_run_today = True
            today_start_h = start_hour
            today_start_m = 0

    if can_run_today:
        naive_target = naive_local.replace(hour=today_start_h, minute=today_start_m, second=0, microsecond=0)
    else:
        # Search next active day starting from tomorrow (bounded loop max 14 days)
        naive_target = None
        for days_ahead in range(1, 15):
            candidate_date = (naive_local + timedelta(days=days_ahead)).date()
            candidate_dummy_dt = datetime.combine(candidate_date, dt_time(12, 0))
            if pause_holidays and is_national_holiday(candidate_dummy_dt, country):
                continue
            
            cand_override = get_day_override_window(candidate_dummy_dt, day_overrides)
            if cand_override is not None:
                c_enabled, c_sh, c_sm, _, _ = cand_override
                if c_enabled:
                    naive_target = datetime.combine(
                        candidate_date,
                        dt_time(hour=c_sh, minute=c_sm, second=0, microsecond=0)
                    )
                    break
            elif candidate_date.weekday() in active_days:
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

def adjust_to_working_hours(dt_utc: datetime, tz_str: str, schedule: Optional[dict] = None, guardrails: Optional[dict] = None) -> datetime:
    """
    Calls calculate_next_run_at and returns naive UTC datetime
    (preserving backward compatibility with callers that expect naive UTC).
    """
    next_run = calculate_next_run_at(dt_utc, tz_str, schedule=schedule, guardrails=guardrails)
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

def calculate_next_run_with_jitter(
    base_time: datetime,
    target_tz: str,
    schedule: Optional[dict] = None,
    jitter_range: Tuple[int, int] = (5, 25),
    seed_key: Optional[str] = None,
    lead_id: Optional[str] = None,
    campaign_id: Optional[str] = None,
    guardrails: Optional[dict] = None,
    **kwargs: Any
) -> datetime:
    """
    Calculates the next working run time for a given base_time and target timezone,
    adding pseudo-random jitter when postponed to a future start window to prevent thunder-herd bursts.
    Applies Three-Layer Paranoia:
      - Paranoia Layer 1: Clamps jitter so it NEVER pushes the time past end_hour - 1 hour of the working window.
      - Paranoia Layer 2: Safely handles weekend rollover: if Friday after 5:00 PM, rolls to Monday morning with jitter, NEVER Saturday or Sunday.
    """
    if base_time is None:
        base_time = datetime.now(timezone.utc)
    elif base_time.tzinfo is None:
        base_time = pytz.UTC.localize(base_time)
    else:
        base_time = base_time.astimezone(pytz.UTC)

    next_run = calculate_next_run_at(base_time, target_tz, schedule=schedule, guardrails=guardrails)

    # If base_time is already within working hours, it was not moved to a future start window
    if is_working_hours(target_tz, schedule=schedule, now_dt=base_time, guardrails=guardrails):
        return next_run

    try:
        if not target_tz or not isinstance(target_tz, str):
            tz = pytz.UTC
        else:
            tz = pytz.timezone(target_tz)
    except Exception:
        tz = pytz.UTC

    start_hour, end_hour, active_days = parse_schedule_config(schedule)
    weekend_sending = bool(schedule.get("weekend_sending") or schedule.get("weekend_sending_enabled")) if isinstance(schedule, dict) else False

    local_dt = next_run.astimezone(tz)

    # Paranoia Layer 2: Safely handles weekend rollover:
    # If Friday after 5:00 PM or on a weekend, rolls to Monday morning with jitter, NEVER Saturday or Sunday.
    if not weekend_sending and local_dt.weekday() in (5, 6):
        days_to_monday = 7 - local_dt.weekday()
        naive_monday = (local_dt.replace(tzinfo=None) + timedelta(days=days_to_monday)).replace(
            hour=start_hour, minute=0, second=0, microsecond=0
        )
        local_dt = safe_localize(tz, naive_monday)
    elif local_dt.weekday() not in active_days:
        naive_curr = local_dt.replace(tzinfo=None)
        found = False
        for d in range(1, 15):
            cand_date = (naive_curr + timedelta(days=d)).date()
            if cand_date.weekday() in active_days and (weekend_sending or cand_date.weekday() not in (5, 6)):
                naive_curr = datetime.combine(cand_date, dt_time(hour=start_hour, minute=0, second=0, microsecond=0))
                found = True
                break
        if not found:
            cand_date = (naive_curr + timedelta(days=1)).date()
            naive_curr = datetime.combine(cand_date, dt_time(hour=start_hour, minute=0, second=0, microsecond=0))
        local_dt = safe_localize(tz, naive_curr)

    # Parse and clamp jitter_range
    try:
        j_min = int(jitter_range[0])
        j_max = int(jitter_range[1])
    except (ValueError, TypeError, IndexError):
        j_min, j_max = 5, 25

    if j_min > j_max:
        j_min, j_max = j_max, j_min
    j_min = max(0, j_min)
    j_max = max(j_min, j_max)

    seed_val = seed_key or lead_id or campaign_id or kwargs.get("lead") or kwargs.get("id")
    if seed_val:
        h = int(hashlib.sha256(str(seed_val).encode("utf-8")).hexdigest(), 16)
        jitter_minutes = j_min + (h % (j_max - j_min + 1)) if j_max > j_min else j_min
    else:
        jitter_minutes = random.randint(j_min, j_max) if j_max > j_min else j_min

    local_jittered = local_dt + timedelta(minutes=jitter_minutes)

    # Paranoia Layer 1: Clamps jitter so it NEVER pushes the time past end_hour - 1 hour of the working window.
    cutoff_hour = max(start_hour, end_hour - 1)
    if cutoff_hour > start_hour:
        max_allowed_local = local_dt.replace(hour=cutoff_hour, minute=0, second=0, microsecond=0)
    else:
        max_allowed_local = local_dt.replace(hour=start_hour, minute=55, second=0, microsecond=0)

    if local_jittered > max_allowed_local:
        local_jittered = max_allowed_local

    final_dt = safe_localize(tz, local_jittered.replace(tzinfo=None))
    return final_dt.astimezone(pytz.UTC)

def is_within_recipient_window(
    lead: dict,
    campaign: dict,
    now_dt: Optional[datetime] = None
) -> Tuple[bool, str, datetime]:
    """
    Convenience helper that resolves recipient timezone, checks working hours,
    and returns (is_open, tz_str, next_available_slot).
    """
    campaign = campaign if isinstance(campaign, dict) else {}
    lead = lead if isinstance(lead, dict) else {}

    tz_str = resolve_target_timezone(campaign, lead)
    meta = campaign.get("metadata", {}) or {}
    schedule = meta.get("schedule") or {}

    if now_dt is None:
        now_utc = datetime.now(timezone.utc)
    elif now_dt.tzinfo is None:
        now_utc = pytz.UTC.localize(now_dt)
    else:
        now_utc = now_dt.astimezone(pytz.UTC)

    is_open = is_working_hours(tz_str, schedule=schedule, now_dt=now_utc)
    seed = str(lead.get("id") or lead.get("lead_id") or "")
    next_available_slot = calculate_next_run_with_jitter(
        now_utc,
        tz_str,
        schedule=schedule,
        seed_key=seed
    )
    return (is_open, tz_str, next_available_slot)



