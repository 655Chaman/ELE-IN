import pytz
from datetime import datetime, timedelta

def is_valid_iana_timezone(tz: str) -> bool:
    if not tz or not isinstance(tz, str):
        return False
    if tz.upper() in ["EST", "PST", "IST", "GMT"]:
        return False
    try:
        pytz.timezone(tz)
        return True
    except pytz.exceptions.UnknownTimeZoneError:
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

def calculate_next_run_at(base_time: datetime, target_tz: str) -> datetime:
    try:
        tz = pytz.timezone(target_tz)
    except pytz.exceptions.UnknownTimeZoneError:
        tz = pytz.UTC

    # Ensure base_time is UTC aware
    if base_time.tzinfo is None:
        base_time = pytz.UTC.localize(base_time)
    else:
        base_time = base_time.astimezone(pytz.UTC)

    # Convert to local time
    local_dt = base_time.astimezone(tz)
    weekday = local_dt.weekday()
    hour = local_dt.hour
    
    # In working window: Mon=0 to Fri=4, 09:00 <= hour < 17:00
    if 0 <= weekday <= 4 and 9 <= hour < 17:
        return base_time
    
    naive_local = local_dt.replace(tzinfo=None)
    
    if 0 <= weekday <= 4 and hour < 9:
        # Move to 09:00 local same day
        naive_target = naive_local.replace(hour=9, minute=0, second=0, microsecond=0)
    elif 0 <= weekday <= 4 and hour >= 17:
        # Move to 09:00 local next weekday
        days_ahead = 3 if weekday == 4 else 1
        naive_target = (naive_local + timedelta(days=days_ahead)).replace(hour=9, minute=0, second=0, microsecond=0)
    else:
        # Move to 09:00 local next Monday
        days_ahead = 7 - weekday
        naive_target = (naive_local + timedelta(days=days_ahead)).replace(hour=9, minute=0, second=0, microsecond=0)
        
    # Use the library's own DST-aware conversion
    target_local = tz.localize(naive_target)
    return target_local.astimezone(pytz.UTC)
