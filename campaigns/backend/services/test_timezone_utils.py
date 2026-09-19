import pytest
import pytz
from datetime import datetime, timedelta
from campaigns.backend.services.timezone_utils import (
    is_valid_iana_timezone,
    resolve_target_timezone,
    calculate_next_run_at
)

def test_resolve_campaign_timezone_ignores_lead():
    # 1. resolve_target_timezone: campaign_timezone mode ignores lead timezone entirely
    campaign = {"metadata": {"scheduling_mode": "campaign_timezone", "timezone": "Europe/London"}}
    lead = {"timezone": "Asia/Tokyo"}
    assert resolve_target_timezone(campaign, lead) == "Europe/London"

def test_resolve_lead_local_valid():
    # 2. resolve_target_timezone: lead_local_time mode with a valid lead timezone uses it
    campaign = {"metadata": {"scheduling_mode": "lead_local_time", "timezone": "Europe/London"}}
    lead = {"timezone": "Asia/Tokyo"}
    assert resolve_target_timezone(campaign, lead) == "Asia/Tokyo"

def test_resolve_lead_local_none_fallback():
    # 3. resolve_target_timezone: lead_local_time mode with lead.timezone = None falls back to campaign timezone
    campaign = {"metadata": {"scheduling_mode": "lead_local_time", "timezone": "Europe/London"}}
    lead = {"timezone": None}
    assert resolve_target_timezone(campaign, lead) == "Europe/London"

def test_resolve_lead_local_invalid_fallback():
    # 4. resolve_target_timezone: lead_local_time mode with an invalid lead timezone string falls back to campaign timezone
    campaign = {"metadata": {"scheduling_mode": "lead_local_time", "timezone": "Europe/London"}}
    lead = {"timezone": "Invalid/Zone"}
    assert resolve_target_timezone(campaign, lead) == "Europe/London"

def test_calc_inside_window():
    # 5. calculate_next_run_at: a time already inside the window is returned unchanged
    # Wed, 2023-10-18 12:00:00 UTC
    base_time = datetime(2023, 10, 18, 12, 0, 0, tzinfo=pytz.UTC)
    result = calculate_next_run_at(base_time, "UTC")
    assert result == base_time

def test_calc_before_0900():
    # 6. calculate_next_run_at: a time before 09:00 local moves to 09:00 local same day
    # Wed, 2023-10-18 07:00:00 UTC
    base_time = datetime(2023, 10, 18, 7, 0, 0, tzinfo=pytz.UTC)
    result = calculate_next_run_at(base_time, "UTC")
    assert result == datetime(2023, 10, 18, 9, 0, 0, tzinfo=pytz.UTC)

def test_calc_after_1700():
    # 7. calculate_next_run_at: a time after 17:00 local moves to 09:00 local the next weekday
    # Wed, 2023-10-18 18:00:00 UTC
    base_time = datetime(2023, 10, 18, 18, 0, 0, tzinfo=pytz.UTC)
    result = calculate_next_run_at(base_time, "UTC")
    # Should move to Thursday 09:00
    assert result == datetime(2023, 10, 19, 9, 0, 0, tzinfo=pytz.UTC)
    
    # Friday, 2023-10-20 18:00:00 UTC
    base_time_fri = datetime(2023, 10, 20, 18, 0, 0, tzinfo=pytz.UTC)
    result_fri = calculate_next_run_at(base_time_fri, "UTC")
    # Should move to Monday 09:00
    assert result_fri == datetime(2023, 10, 23, 9, 0, 0, tzinfo=pytz.UTC)

def test_calc_saturday():
    # 8. calculate_next_run_at: a time on Saturday moves to Monday 09:00 local
    # Sat, 2023-10-21 12:00:00 UTC
    base_time = datetime(2023, 10, 21, 12, 0, 0, tzinfo=pytz.UTC)
    result = calculate_next_run_at(base_time, "UTC")
    # Should move to Monday 09:00
    assert result == datetime(2023, 10, 23, 9, 0, 0, tzinfo=pytz.UTC)

def test_calc_sunday():
    # 9. calculate_next_run_at: a time on Sunday moves to Monday 09:00 local
    # Sun, 2023-10-22 12:00:00 UTC
    base_time = datetime(2023, 10, 22, 12, 0, 0, tzinfo=pytz.UTC)
    result = calculate_next_run_at(base_time, "UTC")
    # Should move to Monday 09:00
    assert result == datetime(2023, 10, 23, 9, 0, 0, tzinfo=pytz.UTC)

def test_dst_spring_forward():
    # 10. DST test — America/New_York spring-forward (second Sunday in March)
    # Sunday, Mar 12, 2023. Spring forward happens at 2 AM local.
    # Base time: Sunday, Mar 12, 2023 12:00:00 UTC (08:00 AM NY - already EDT)
    # We test Saturday night transitioning to Monday morning.
    # Sat Mar 11 2023 20:00:00 local NY (EST) -> UTC is Mar 12 01:00:00
    base_time = datetime(2023, 3, 12, 1, 0, 0, tzinfo=pytz.UTC)
    
    # Needs to jump to Mon Mar 13 09:00:00 NY local (which is EDT, UTC-4)
    result = calculate_next_run_at(base_time, "America/New_York")
    
    # 09:00 EDT -> 13:00 UTC
    expected = datetime(2023, 3, 13, 13, 0, 0, tzinfo=pytz.UTC)
    assert result == expected

def test_dst_fall_back():
    # 11. DST test — Australia/Sydney fall-back (first Sunday in April)
    # Sunday, Apr 2, 2023. Fall back happens at 3 AM local.
    # We test Saturday afternoon transitioning to Monday morning.
    # Sat Apr 1 2023 18:00:00 local SYD (AEDT, UTC+11) -> UTC is Apr 1 07:00:00
    base_time = datetime(2023, 4, 1, 7, 0, 0, tzinfo=pytz.UTC)
    
    # Needs to jump to Mon Apr 3 09:00:00 SYD local (which is AEST, UTC+10)
    result = calculate_next_run_at(base_time, "Australia/Sydney")
    
    # 09:00 AEST -> 23:00 UTC on the previous day (Apr 2, 23:00 UTC)
    expected = datetime(2023, 4, 2, 23, 0, 0, tzinfo=pytz.UTC)
    assert result == expected
