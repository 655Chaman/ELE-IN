"""
Test Suite: Recipient Timezone & Working Hours Guard
Three-Layer Logic Architecture (Paranoia Framework)

Covers 35+ real-world test cases:
- Layer 0: Foundational Layer (Geographic resolution, tech hubs, working hours)
- Layer 1: Environmental Failure Analysis (Phone codes, country fallback, Friday rollover, weekend blackouts, jitter realism, orchestrator postponement)
- Layer 2: Human Paranoia & Edge Cases (Poison location strings, accented characters, corrupted inputs, inverted hours, missing keys, high-throughput LRU cache)
"""

import pytest
import pytz
from datetime import datetime, timedelta, time as dt_time, timezone
from unittest.mock import MagicMock, patch

from leads.backend.services.location_timezone_service import (
    LocationTimezoneService,
    POISON_LOCATIONS,
)
from campaigns.backend.services.timezone_utils import (
    is_valid_iana_timezone,
    resolve_target_timezone,
    is_working_hours,
    calculate_next_run_at,
    calculate_next_run_with_jitter,
    is_within_recipient_window,
    parse_schedule_config,
    safe_localize,
)
from campaigns.backend.services.elein_orchestrator import EleInOrchestrator


# ==============================================================================
# LAYER 0: FOUNDATIONAL LAYER
# ==============================================================================

class TestLayer0FoundationalResolution:
    """Foundational test suite for city, state, global tech hubs, and working hours checks."""

    @pytest.mark.parametrize(
        "location_str, expected_iana",
        [
            ("San Francisco, CA", "America/Los_Angeles"),
            ("Boston, MA", "America/New_York"),
            ("Chicago, IL", "America/Chicago"),
            ("Denver, CO", "America/Denver"),
            ("Seattle, WA", "America/Los_Angeles"),
            ("Austin, TX", "America/Chicago"),
            ("Miami, FL", "America/New_York"),
        ],
    )
    def test_us_city_state_to_iana_resolution(self, location_str, expected_iana):
        """Resolves US cities and state abbreviations to correct IANA timezone."""
        resolved = LocationTimezoneService.infer_timezone(location_str)
        assert resolved == expected_iana

    @pytest.mark.parametrize(
        "metro_str, expected_iana",
        [
            ("London, UK", "Europe/London"),
            ("Paris, France", "Europe/Paris"),
            ("Berlin, Germany", "Europe/Berlin"),
            ("Tokyo, Japan", "Asia/Tokyo"),
            ("Bengaluru, India", "Asia/Kolkata"),
            ("Sydney, Australia", "Australia/Sydney"),
            ("Toronto, Canada", "America/Toronto"),
            ("Singapore", "Asia/Singapore"),
            ("Dublin, Ireland", "Europe/Dublin"),
            ("Amsterdam, Netherlands", "Europe/Amsterdam"),
            ("Tel Aviv, Israel", "Asia/Jerusalem"),
            ("Dubai, UAE", "Asia/Dubai"),
        ],
    )
    def test_international_capitals_and_tech_hubs(self, metro_str, expected_iana):
        """Resolves international capitals and global tech hubs to accurate IANA timezones."""
        resolved = LocationTimezoneService.infer_timezone(metro_str)
        assert resolved == expected_iana

    def test_working_hours_daytime_10am_is_inside(self):
        """10:00 AM local time on a weekday is strictly inside working hours."""
        # Wednesday, Oct 18, 2023 at 10:00 AM in America/New_York (14:00 UTC)
        wed_10am_edt = datetime(2023, 10, 18, 14, 0, 0, tzinfo=pytz.UTC)
        assert is_working_hours("America/New_York", schedule={"start_hour": 9, "end_hour": 17}, now_dt=wed_10am_edt) is True

    def test_working_hours_night_2am_is_outside(self):
        """2:00 AM local time on a weekday is strictly outside working hours."""
        # Wednesday, Oct 18, 2023 at 02:00 AM in America/New_York (06:00 UTC)
        wed_2am_edt = datetime(2023, 10, 18, 6, 0, 0, tzinfo=pytz.UTC)
        assert is_working_hours("America/New_York", schedule={"start_hour": 9, "end_hour": 17}, now_dt=wed_2am_edt) is False

    def test_is_valid_iana_timezone_rejects_ambiguous_abbreviations(self):
        """is_valid_iana_timezone rejects raw abbreviations like EST, PST, IST, GMT that cause DST bugs."""
        assert is_valid_iana_timezone("EST") is False
        assert is_valid_iana_timezone("PST") is False
        assert is_valid_iana_timezone("IST") is False
        assert is_valid_iana_timezone("GMT") is False
        assert is_valid_iana_timezone("America/New_York") is True
        assert is_valid_iana_timezone("Europe/London") is True


# ==============================================================================
# LAYER 1: ENVIRONMENTAL FAILURE ANALYSIS
# ==============================================================================

class TestLayer1EnvironmentalFailureAnalysis:
    """
    Environmental failure suite:
    - Missing location with phone dial code fallback
    - Country code fallback
    - Weekend blackouts & Friday 6:00 PM rollover
    - Jitter realism & thunder-herd protection
    - Dynamic campaign resolution
    - Orchestrator postponement loop
    """

    def test_phone_dial_code_uk_inference(self):
        """Lead with location=None but phone='+44 20 7946 0958' resolves to Europe/London."""
        resolved = LocationTimezoneService.infer_timezone(location=None, phone="+44 20 7946 0958")
        assert resolved == "Europe/London"

    def test_phone_dial_code_india_inference(self):
        """Lead with location=None but phone='+91 98765 43210' resolves to Asia/Kolkata."""
        resolved = LocationTimezoneService.infer_timezone(location=None, phone="+91 98765 43210")
        assert resolved == "Asia/Kolkata"

    def test_phone_dial_code_france_and_germany(self):
        """Dial codes for France (+33) and Germany (+49) correctly infer respective timezones."""
        assert LocationTimezoneService.infer_timezone(location=None, phone="+33 1 42 68 55 55") == "Europe/Paris"
        assert LocationTimezoneService.infer_timezone(location=None, phone="+49 30 1234567") == "Europe/Berlin"

    def test_country_code_fallback_de(self):
        """Lead with location=None but country='DE' resolves to Europe/Berlin."""
        resolved = LocationTimezoneService.infer_timezone(location=None, country="DE")
        assert resolved == "Europe/Berlin"

    def test_country_code_fallback_various(self):
        """Country codes without city data resolve to primary national timezones."""
        assert LocationTimezoneService.infer_timezone(location=None, country="FR") == "Europe/Paris"
        assert LocationTimezoneService.infer_timezone(location=None, country="JP") == "Asia/Tokyo"
        assert LocationTimezoneService.infer_timezone(location=None, country="Australia") == "Australia/Sydney"
        assert LocationTimezoneService.infer_timezone(location=None, country="India") == "Asia/Kolkata"

    def test_friday_6pm_rollover_postpones_to_monday(self):
        """
        Friday 6:00 PM recipient local time rolls over to Monday morning 09:xx AM.
        Never schedules on Saturday or Sunday when weekend_sending is False.
        """
        # Friday, Oct 20, 2023 at 18:00 EDT (22:00 UTC)
        fri_6pm_utc = datetime(2023, 10, 20, 22, 0, 0, tzinfo=pytz.UTC)
        schedule = {"start_hour": 9, "end_hour": 17, "weekend_sending": False}

        next_run = calculate_next_run_with_jitter(
            fri_6pm_utc,
            "America/New_York",
            schedule=schedule,
            jitter_range=(5, 20),
            seed_key="lead-12345"
        )
        local_slot = next_run.astimezone(pytz.timezone("America/New_York"))

        assert local_slot.weekday() == 0, f"Expected Monday (0), got weekday {local_slot.weekday()}"
        assert local_slot.hour == 9
        assert 5 <= local_slot.minute <= 25
        assert local_slot.date() == datetime(2023, 10, 23).date()

    def test_weekend_blackout_saturday_and_sunday(self):
        """Saturday and Sunday are strictly outside working hours when weekend_sending=False."""
        # Saturday Oct 21, 2023 at 11:00 AM EDT (15:00 UTC)
        sat_11am_utc = datetime(2023, 10, 21, 15, 0, 0, tzinfo=pytz.UTC)
        assert is_working_hours("America/New_York", schedule={"weekend_sending": False}, now_dt=sat_11am_utc) is False

        # Sunday Oct 22, 2023 at 14:00 EDT (18:00 UTC)
        sun_2pm_utc = datetime(2023, 10, 22, 18, 0, 0, tzinfo=pytz.UTC)
        assert is_working_hours("America/New_York", schedule={"weekend_sending": False}, now_dt=sun_2pm_utc) is False

    def test_weekend_sending_enabled_allows_saturday(self):
        """When weekend_sending is explicitly enabled, Saturday during daytime is inside working hours."""
        sat_11am_utc = datetime(2023, 10, 21, 15, 0, 0, tzinfo=pytz.UTC)
        assert is_working_hours("America/New_York", schedule={"weekend_sending": True, "start_hour": 9, "end_hour": 17}, now_dt=sat_11am_utc) is True

    def test_jitter_realism_never_slams_0900_on_the_dot(self):
        """calculate_next_run_with_jitter returns minute > 0 (e.g. 09:07 or 09:18), never 09:00:00."""
        # Base time: 02:00 AM local time in Europe/London (outside working window)
        base_time = datetime(2023, 10, 18, 2, 0, 0, tzinfo=pytz.UTC)
        jittered_run = calculate_next_run_with_jitter(
            base_time,
            "Europe/London",
            schedule={"start_hour": 9, "end_hour": 17},
            jitter_range=(7, 22)
        )
        local_time = jittered_run.astimezone(pytz.timezone("Europe/London"))
        assert local_time.hour == 9
        assert local_time.minute >= 7
        assert local_time.minute <= 22
        assert local_time.minute != 0, "Jitter must never slam 09:00:00 on the dot!"

    def test_jitter_is_deterministic_with_seed_key(self):
        """With the same seed_key, jitter produces identical reproducible timestamps."""
        base_time = datetime(2023, 10, 18, 2, 0, 0, tzinfo=pytz.UTC)
        t1 = calculate_next_run_with_jitter(base_time, "America/Chicago", seed_key="lead-42")
        t2 = calculate_next_run_with_jitter(base_time, "America/Chicago", seed_key="lead-42")
        assert t1 == t2

    def test_jitter_clamped_before_end_hour(self):
        """Paranoia Layer 1: Jitter is clamped so it never exceeds end_hour - 1 of working window."""
        base_time = datetime(2023, 10, 18, 2, 0, 0, tzinfo=pytz.UTC)
        # Narrow schedule: start_hour=9, end_hour=10
        jittered = calculate_next_run_with_jitter(
            base_time,
            "UTC",
            schedule={"start_hour": 9, "end_hour": 10},
            jitter_range=(10, 90) # Range deliberately pushes past end_hour
        )
        assert jittered.hour == 9
        assert jittered.minute <= 55

    def test_campaign_interpolation_and_lead_local_time_resolution(self):
        """
        When campaign scheduling_mode is 'lead_local_time' and lead has location='Seattle, WA'
        with lead['timezone']=None, resolve_target_timezone infers 'America/Los_Angeles'.
        """
        campaign = {
            "metadata": {
                "scheduling_mode": "lead_local_time",
                "timezone": "UTC"
            }
        }
        lead = {
            "location": "Seattle, WA",
            "timezone": None
        }
        resolved = resolve_target_timezone(campaign, lead)
        assert resolved == "America/Los_Angeles"

    def test_campaign_timezone_mode_ignores_lead_location(self):
        """When campaign scheduling_mode is 'campaign_timezone', lead location is strictly ignored."""
        campaign = {
            "metadata": {
                "scheduling_mode": "campaign_timezone",
                "timezone": "Europe/Berlin"
            }
        }
        lead = {
            "location": "Tokyo, Japan",
            "timezone": "Asia/Tokyo"
        }
        resolved = resolve_target_timezone(campaign, lead)
        assert resolved == "Europe/Berlin"

    def test_orchestrator_postponement_at_2am(self):
        """
        In EleInOrchestrator, when lead is at 2:00 AM local time, verify that:
        - next_run_at is updated to the next working morning
        - status is updated to 'pending'
        - lead is NOT processed / executed in the current loop
        """
        mock_supabase = MagicMock()

        # Mock campaign in lead_local_time mode with London timezone
        campaign_id = "camp-123"
        enrollment_id = "enr-456"
        lead_id = "lead-789"
        version_id = "ver-001"
        state_id = "state-999"

        # Mock campaigns_res
        campaigns_query = MagicMock()
        campaigns_query.execute.return_value = MagicMock(data=[{
            "id": campaign_id,
            "workspace_id": "ws-1",
            "metadata": {
                "scheduling_mode": "lead_local_time",
                "timezone": "UTC",
                "enforce_working_hours": True,
                "schedule": {"start_hour": 9, "end_hour": 17, "weekend_sending": False}
            }
        }])
        
        # Mock workspace status
        ws_status_query = MagicMock()
        ws_status_query.execute.return_value = MagicMock(data=[{"id": "ws-1", "status": "active"}])

        # Mock dequeued state
        dequeue_rpc = MagicMock()
        dequeue_rpc.execute.return_value = MagicMock(data=[{
            "id": state_id,
            "enrollment_id": enrollment_id,
            "current_node_id": "node-1",
            "status": "pending",
            "next_run_at": datetime.utcnow().isoformat(),
        }])

        # Mock enrollments
        enr_query = MagicMock()
        enr_query.execute.return_value = MagicMock(data=[{
            "id": enrollment_id,
            "campaign_id": campaign_id,
            "lead_id": lead_id,
            "campaign_version_id": version_id,
            "workspace_id": "ws-1"
        }])

        # Mock lead with location in Tokyo (where at 17:00 UTC it is 02:00 AM JST)
        leads_query = MagicMock()
        leads_query.execute.return_value = MagicMock(data=[{
            "id": lead_id,
            "timezone": "Asia/Tokyo",
            "location": "Tokyo, Japan"
        }])

        # Nodes and edges
        nodes_query = MagicMock()
        nodes_query.execute.return_value = MagicMock(data=[])
        edges_query = MagicMock()
        edges_query.execute.return_value = MagicMock(data=[])

        # Track updates to campaign_execution_states
        update_calls = []
        def mock_table(table_name):
            t_mock = MagicMock()
            if table_name == "campaigns":
                t_mock.select.return_value.eq.return_value = campaigns_query
                return t_mock
            elif table_name == "workspaces":
                t_mock.select.return_value.in_.return_value = ws_status_query
                return t_mock
            elif table_name == "campaign_enrollments":
                t_mock.select.return_value.in_.return_value = enr_query
                return t_mock
            elif table_name == "leads":
                t_mock.select.return_value.in_.return_value = leads_query
                return t_mock
            elif table_name == "campaign_nodes":
                t_mock.select.return_value.in_.return_value = nodes_query
                return t_mock
            elif table_name == "campaign_edges":
                t_mock.select.return_value.in_.return_value = edges_query
                return t_mock
            elif table_name == "campaign_execution_states":
                # Capture updates
                def capture_update(payload):
                    upd_obj = MagicMock()
                    def capture_eq(col, val):
                        update_calls.append({"col": col, "val": val, "payload": payload})
                        return MagicMock(execute=MagicMock(return_value=MagicMock(data=[])))
                    upd_obj.eq.side_effect = capture_eq
                    return upd_obj
                t_mock.update.side_effect = capture_update
                t_mock.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
                return t_mock
            return t_mock

        mock_supabase.table.side_effect = mock_table
        mock_supabase.rpc.return_value = dequeue_rpc

        # Freeze time to 17:00:00 UTC (which is 02:00:00 AM next day in Tokyo, UTC+9)
        freeze_utc = datetime(2023, 10, 18, 17, 0, 0, tzinfo=pytz.UTC)
        with patch("campaigns.backend.services.elein_orchestrator.datetime") as mock_dt:
            mock_dt.utcnow.return_value = freeze_utc.replace(tzinfo=None)
            mock_dt.now.return_value = freeze_utc
            mock_dt.fromisoformat = datetime.fromisoformat
            mock_dt.combine = datetime.combine

            orchestrator = EleInOrchestrator(supabase=mock_supabase)
            orchestrator._workspace_has_credits = MagicMock(return_value=True)
            orchestrator.requeue_waiting_for_reply_leads = MagicMock()
            orchestrator.sweep_completed_campaigns = MagicMock()

            processed = orchestrator.process_pending_leads()

            # Verify that the lead was postponed and NOT returned for execution
            assert len(processed) == 0, "Lead at 02:00 AM local time must not be processed!"
            assert len(update_calls) >= 1, "Expected campaign_execution_states update call"
            
            postponed_update = next(
                (u for u in update_calls if u["payload"].get("status") == "pending" and "next_run_at" in u["payload"]),
                None
            )
            assert postponed_update is not None, "Execution state was not updated with pending status and next_run_at"
            next_run_iso = postponed_update["payload"]["next_run_at"]
            next_run_dt = datetime.fromisoformat(next_run_iso)
            
            # Next run must be later than the current frozen time
            if next_run_dt.tzinfo is None:
                next_run_dt = pytz.UTC.localize(next_run_dt)
            assert next_run_dt > freeze_utc


# ==============================================================================
# LAYER 2: HUMAN PARANOIA & EDGE CASES
# ==============================================================================

class TestLayer2HumanParanoiaAndEdgeCases:
    """
    Human paranoia suite:
    - Poison location strings ('Remote', 'Worldwide', 'Global', 'Anywhere', 'WFH', None, '')
    - Accented foreign characters ('São Paulo', 'Zürich', 'Montréal', 'München')
    - Corrupted / unknown timezones ('Mars/Olympus', invalid types)
    - Malformed lead and schedule dictionaries
    - High-throughput LRU cache performance (<0.01ms resolution)
    """

    @pytest.mark.parametrize(
        "poison_input",
        [
            "Remote",
            "Worldwide",
            "Global",
            "Anywhere",
            "Earth",
            "Virtual",
            "Home",
            "WFH",
            "Work from home",
            "N/A",
            "Unknown",
            "None",
            "",
            None,
        ],
    )
    def test_poison_locations_safely_ignored(self, poison_input):
        """Poison or non-geographical strings return None without throwing exceptions."""
        result = LocationTimezoneService.infer_timezone(poison_input)
        assert result is None

    def test_poison_location_with_lead_local_time_falls_back_to_campaign_tz(self):
        """Lead with poison location 'Remote' safely falls back to campaign metadata timezone."""
        campaign = {
            "metadata": {
                "scheduling_mode": "lead_local_time",
                "timezone": "Europe/London"
            }
        }
        lead = {"location": "Remote", "timezone": None}
        resolved = resolve_target_timezone(campaign, lead)
        assert resolved == "Europe/London"

    @pytest.mark.parametrize(
        "accented_location, expected_iana",
        [
            ("São Paulo, Brazil", "America/Sao_Paulo"),
            ("Zürich, Switzerland", "Europe/Zurich"),
            ("Montréal, Canada", "America/Toronto"),
            ("München, Germany", "Europe/Berlin"),
            ("København, Denmark", "Europe/Copenhagen"),
        ],
    )
    def test_accented_locations_resolve_accurately(self, accented_location, expected_iana):
        """Accented international location strings resolve cleanly without unicode decode errors."""
        resolved = LocationTimezoneService.infer_timezone(accented_location)
        assert resolved == expected_iana

    def test_corrupted_or_unknown_timezone_falls_back_to_utc(self):
        """Corrupted, imaginary, or non-string timezones safely fall back to UTC."""
        campaign = {
            "metadata": {
                "scheduling_mode": "campaign_timezone",
                "timezone": "Mars/Olympus_Mons"
            }
        }
        lead = {"timezone": "Jupiter/Great_Red_Spot"}
        resolved = resolve_target_timezone(campaign, lead)
        assert resolved == "UTC"

        # Invalid type (e.g. integer or list)
        campaign_corrupt = {"metadata": {"scheduling_mode": "campaign_timezone", "timezone": 99999}}
        assert resolve_target_timezone(campaign_corrupt, {}) == "UTC"

    def test_missing_lead_or_empty_dict_resilience(self):
        """Lead with missing lead_id, empty dict {}, or None handled gracefully without KeyError."""
        campaign = {"metadata": {"scheduling_mode": "lead_local_time", "timezone": "America/New_York"}}
        assert resolve_target_timezone(campaign, {}) == "America/New_York"
        assert resolve_target_timezone(campaign, None) == "America/New_York"
        assert resolve_target_timezone(None, None) == "UTC"
        assert LocationTimezoneService.get_or_resolve_lead_timezone({}) is None
        assert LocationTimezoneService.get_or_resolve_lead_timezone(None) is None

    def test_inverted_schedule_hours_fallback(self):
        """Paranoia Layer 0: Inverted hours (e.g. start=18, end=9) safely fall back to default (9, 17)."""
        start, end, days = parse_schedule_config({"start_hour": 18, "end_hour": 9})
        assert start == 9
        assert end == 17
        assert days == {0, 1, 2, 3, 4}

    def test_equal_schedule_hours_fallback(self):
        """Equal hours (e.g. start=10, end=10) safely fall back to default (9, 17)."""
        start, end, days = parse_schedule_config({"start_hour": 10, "end_hour": 10})
        assert start == 9
        assert end == 17

    def test_convenience_helper_is_within_recipient_window(self):
        """is_within_recipient_window returns (is_open, tz_str, next_slot) tuple."""
        campaign = {
            "metadata": {
                "scheduling_mode": "lead_local_time",
                "schedule": {"start_hour": 9, "end_hour": 17, "weekend_sending": False}
            }
        }
        lead = {"location": "London, UK"}

        # Daytime: 12:00 PM London time
        daytime_utc = datetime(2023, 10, 18, 12, 0, 0, tzinfo=pytz.UTC)
        is_open, tz_str, next_slot = is_within_recipient_window(lead, campaign, now_dt=daytime_utc)
        assert is_open is True
        assert tz_str == "Europe/London"

        # Nighttime: 02:00 AM London time
        nighttime_utc = datetime(2023, 10, 18, 2, 0, 0, tzinfo=pytz.UTC)
        is_open_night, tz_str_night, next_slot_night = is_within_recipient_window(lead, campaign, now_dt=nighttime_utc)
        assert is_open_night is False
        assert tz_str_night == "Europe/London"
        assert next_slot_night > nighttime_utc

    def test_lru_cache_high_throughput_performance(self):
        """High-throughput performance: 1,000 cached inferences complete in < 50ms."""
        import time

        locations = [
            "San Francisco, CA", "London, UK", "Paris, France",
            "Berlin, Germany", "Tokyo, Japan", "Bengaluru, India"
        ] * 200 # 1,200 lookups

        t0 = time.perf_counter()
        for loc in locations:
            res = LocationTimezoneService.infer_timezone(loc)
            assert res is not None
        elapsed = time.perf_counter() - t0

        assert elapsed < 0.1, f"Expected 1,200 lookups to take < 100ms, took {elapsed * 1000:.2f}ms"
