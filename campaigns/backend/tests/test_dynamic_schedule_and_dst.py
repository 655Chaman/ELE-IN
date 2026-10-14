import unittest
from datetime import datetime, timedelta, time as dt_time
import pytz

from campaigns.backend.services.timezone_utils import (
    parse_schedule_config,
    safe_localize,
    is_working_hours,
    calculate_next_run_at,
    adjust_to_working_hours,
    next_working_day_9am,
)


class TestDynamicScheduleAndDST(unittest.TestCase):
    """
    Test suite for Step 20: Dynamic Working Hours, DST Boundary & Custom Schedule Pacing Guard.
    Validates Layer 0 (Mechanics), Layer 1 (Environmental Failures), and Layer 2 (Human Paranoia).
    """

    def test_default_schedule_baseline(self):
        """1. test_default_schedule_baseline: 9-17 Mon-Fri behavior when schedule=None."""
        start_h, end_h, active_days = parse_schedule_config(None)
        self.assertEqual(start_h, 9)
        self.assertEqual(end_h, 17)
        self.assertEqual(active_days, {0, 1, 2, 3, 4})

        # Wednesday 2026-10-07 10:00 UTC is inside window
        wed_10 = pytz.UTC.localize(datetime(2026, 10, 7, 10, 0))
        self.assertTrue(is_working_hours("UTC", schedule=None, now_dt=wed_10))
        next_run = calculate_next_run_at(wed_10, "UTC", schedule=None)
        self.assertEqual(next_run, wed_10)

        # Wednesday 08:00 UTC moves to Wednesday 09:00 UTC
        wed_08 = pytz.UTC.localize(datetime(2026, 10, 7, 8, 0))
        self.assertFalse(is_working_hours("UTC", schedule=None, now_dt=wed_08))
        next_run_08 = calculate_next_run_at(wed_08, "UTC", schedule=None)
        expected_09 = pytz.UTC.localize(datetime(2026, 10, 7, 9, 0))
        self.assertEqual(next_run_08, expected_09)

        # Wednesday 18:00 UTC moves to Thursday 09:00 UTC
        wed_18 = pytz.UTC.localize(datetime(2026, 10, 7, 18, 0))
        self.assertFalse(is_working_hours("UTC", schedule=None, now_dt=wed_18))
        next_run_18 = calculate_next_run_at(wed_18, "UTC", schedule=None)
        expected_thu_09 = pytz.UTC.localize(datetime(2026, 10, 8, 9, 0))
        self.assertEqual(next_run_18, expected_thu_09)

    def test_custom_hours_early_morning(self):
        """2. test_custom_hours_early_morning: start_hour=6, end_hour=14, 07:00 inside window, 05:00 rolls to 06:00 same day."""
        schedule = {"start_hour": 6, "end_hour": 14}
        start_h, end_h, active_days = parse_schedule_config(schedule)
        self.assertEqual(start_h, 6)
        self.assertEqual(end_h, 14)

        # Friday 2026-10-09 07:00 UTC is inside window
        fri_07 = pytz.UTC.localize(datetime(2026, 10, 9, 7, 0))
        self.assertTrue(is_working_hours("UTC", schedule=schedule, now_dt=fri_07))
        self.assertEqual(calculate_next_run_at(fri_07, "UTC", schedule=schedule), fri_07)

        # Friday 2026-10-09 05:00 UTC rolls to 06:00 same day
        fri_05 = pytz.UTC.localize(datetime(2026, 10, 9, 5, 0))
        self.assertFalse(is_working_hours("UTC", schedule=schedule, now_dt=fri_05))
        expected_06 = pytz.UTC.localize(datetime(2026, 10, 9, 6, 0))
        self.assertEqual(calculate_next_run_at(fri_05, "UTC", schedule=schedule), expected_06)

    def test_custom_hours_late_evening(self):
        """3. test_custom_hours_late_evening: start_hour=14, end_hour=22, 19:00 inside window, 10:00 rolls to 14:00 same day."""
        schedule = {"start_hour": 14, "end_hour": 22}
        start_h, end_h, active_days = parse_schedule_config(schedule)
        self.assertEqual(start_h, 14)
        self.assertEqual(end_h, 22)

        # Friday 2026-10-09 19:00 UTC is inside window
        fri_19 = pytz.UTC.localize(datetime(2026, 10, 9, 19, 0))
        self.assertTrue(is_working_hours("UTC", schedule=schedule, now_dt=fri_19))
        self.assertEqual(calculate_next_run_at(fri_19, "UTC", schedule=schedule), fri_19)

        # Friday 2026-10-09 10:00 UTC rolls to 14:00 same day
        fri_10 = pytz.UTC.localize(datetime(2026, 10, 9, 10, 0))
        self.assertFalse(is_working_hours("UTC", schedule=schedule, now_dt=fri_10))
        expected_14 = pytz.UTC.localize(datetime(2026, 10, 9, 14, 0))
        self.assertEqual(calculate_next_run_at(fri_10, "UTC", schedule=schedule), expected_14)

    def test_weekend_sending_enabled(self):
        """4. test_weekend_sending_enabled: weekend_sending=True, Friday 19:00 rolls to Saturday 09:00. Saturday 11:00 is active."""
        schedule = {"weekend_sending": True}
        start_h, end_h, active_days = parse_schedule_config(schedule)
        self.assertEqual(active_days, {0, 1, 2, 3, 4, 5, 6})

        # Friday 2026-10-09 19:00 UTC rolls to Saturday 2026-10-10 09:00 UTC
        fri_19 = pytz.UTC.localize(datetime(2026, 10, 9, 19, 0))
        expected_sat_09 = pytz.UTC.localize(datetime(2026, 10, 10, 9, 0))
        self.assertEqual(calculate_next_run_at(fri_19, "UTC", schedule=schedule), expected_sat_09)

        # Saturday 2026-10-10 11:00 UTC is active
        sat_11 = pytz.UTC.localize(datetime(2026, 10, 10, 11, 0))
        self.assertTrue(is_working_hours("UTC", schedule=schedule, now_dt=sat_11))
        self.assertEqual(calculate_next_run_at(sat_11, "UTC", schedule=schedule), sat_11)

    def test_weekend_sending_disabled(self):
        """5. test_weekend_sending_disabled: weekend_sending=False, Friday 19:00 rolls to Monday 09:00."""
        schedule = {"weekend_sending": False}
        start_h, end_h, active_days = parse_schedule_config(schedule)
        self.assertEqual(active_days, {0, 1, 2, 3, 4})

        # Friday 2026-10-09 19:00 UTC rolls to Monday 2026-10-12 09:00 UTC
        fri_19 = pytz.UTC.localize(datetime(2026, 10, 9, 19, 0))
        expected_mon_09 = pytz.UTC.localize(datetime(2026, 10, 12, 9, 0))
        self.assertEqual(calculate_next_run_at(fri_19, "UTC", schedule=schedule), expected_mon_09)

        # Saturday 2026-10-10 11:00 UTC is NOT active
        sat_11 = pytz.UTC.localize(datetime(2026, 10, 10, 11, 0))
        self.assertFalse(is_working_hours("UTC", schedule=schedule, now_dt=sat_11))

    def test_custom_active_days(self):
        """6. test_custom_active_days: active_days=[1, 3] (Tue & Thu only). Monday 10:00 rolls to Tuesday 09:00. Tuesday 18:00 rolls to Thursday 09:00."""
        schedule = {"active_days": [1, 3]}
        start_h, end_h, active_days = parse_schedule_config(schedule)
        self.assertEqual(active_days, {1, 3})

        # Monday 2026-10-05 10:00 UTC rolls to Tuesday 2026-10-06 09:00 UTC
        mon_10 = pytz.UTC.localize(datetime(2026, 10, 5, 10, 0))
        expected_tue_09 = pytz.UTC.localize(datetime(2026, 10, 6, 9, 0))
        self.assertFalse(is_working_hours("UTC", schedule=schedule, now_dt=mon_10))
        self.assertEqual(calculate_next_run_at(mon_10, "UTC", schedule=schedule), expected_tue_09)

        # Tuesday 2026-10-06 18:00 UTC rolls to Thursday 2026-10-08 09:00 UTC
        tue_18 = pytz.UTC.localize(datetime(2026, 10, 6, 18, 0))
        expected_thu_09 = pytz.UTC.localize(datetime(2026, 10, 8, 9, 0))
        self.assertFalse(is_working_hours("UTC", schedule=schedule, now_dt=tue_18))
        self.assertEqual(calculate_next_run_at(tue_18, "UTC", schedule=schedule), expected_thu_09)

    def test_human_paranoia_inverted_hours(self):
        """7. test_human_paranoia_inverted_hours: start_hour=18, end_hour=9, safely reverts to 9..17 without infinite loop."""
        schedule_inverted = {"start_hour": 18, "end_hour": 9}
        start_h, end_h, active_days = parse_schedule_config(schedule_inverted)
        self.assertEqual(start_h, 9)
        self.assertEqual(end_h, 17)

        schedule_equal = {"start_hour": 10, "end_hour": 10}
        start_eq, end_eq, _ = parse_schedule_config(schedule_equal)
        self.assertEqual(start_eq, 9)
        self.assertEqual(end_eq, 17)

        # Confirm calculation executes without hanging
        wed_18 = pytz.UTC.localize(datetime(2026, 10, 7, 18, 0))
        next_run = calculate_next_run_at(wed_18, "UTC", schedule=schedule_inverted)
        expected_thu_09 = pytz.UTC.localize(datetime(2026, 10, 8, 9, 0))
        self.assertEqual(next_run, expected_thu_09)

    def test_human_paranoia_out_of_bounds_hours(self):
        """8. test_human_paranoia_out_of_bounds_hours: start_hour=-5, end_hour=99, clamped safely."""
        schedule = {"start_hour": -5, "end_hour": 99}
        start_h, end_h, active_days = parse_schedule_config(schedule)
        self.assertEqual(start_h, 0)
        self.assertEqual(end_h, 24)

        # String representations safely parsed and clamped
        schedule_str = {"start_hour": "-10", "end_hour": "50"}
        start_s, end_s, _ = parse_schedule_config(schedule_str)
        self.assertEqual(start_s, 0)
        self.assertEqual(end_s, 24)

    def test_human_paranoia_empty_active_days(self):
        """9. test_human_paranoia_empty_active_days: active_days=[], defaults to Mon-Fri without infinite loop."""
        schedule = {"active_days": []}
        start_h, end_h, active_days = parse_schedule_config(schedule)
        self.assertEqual(active_days, {0, 1, 2, 3, 4})

        # Confirm calculate_next_run_at resolves safely without infinite while-loops
        sat_12 = pytz.UTC.localize(datetime(2026, 10, 10, 12, 0))
        next_run = calculate_next_run_at(sat_12, "UTC", schedule=schedule)
        expected_mon_09 = pytz.UTC.localize(datetime(2026, 10, 12, 9, 0))
        self.assertEqual(next_run, expected_mon_09)

        # Empty active_days with weekend sending enabled defaults to all 7 days
        schedule_wknd = {"active_days": [], "weekend_sending": True}
        _, _, active_wknd = parse_schedule_config(schedule_wknd)
        self.assertEqual(active_wknd, {0, 1, 2, 3, 4, 5, 6})

    def test_dst_spring_forward_gap_non_existent_time(self):
        """10. test_dst_spring_forward_gap_non_existent_time: Safe localization during spring forward avoids NonExistentTimeError."""
        tz_ny = pytz.timezone("America/New_York")
        # On 2024-03-10, 02:00 springs forward to 03:00 in America/New_York
        gap_dt = datetime(2024, 3, 10, 2, 30)

        # Direct localization with is_dst=None would raise NonExistentTimeError
        with self.assertRaises(pytz.exceptions.NonExistentTimeError):
            tz_ny.localize(gap_dt, is_dst=None)

        # safe_localize catches the gap and advances by 1 hour safely
        safe_dt = safe_localize(tz_ny, gap_dt)
        self.assertIsNotNone(safe_dt.tzinfo)
        self.assertEqual(safe_dt.hour, 3)
        self.assertEqual(safe_dt.minute, 30)

        # String timezone format also works safely
        safe_dt_str = safe_localize("America/New_York", gap_dt)
        self.assertEqual(safe_dt_str.hour, 3)

    def test_dst_fall_back_overlap_ambiguous_time(self):
        """11. test_dst_fall_back_overlap_ambiguous_time: Safe localization during fall back avoids AmbiguousTimeError."""
        tz_ny = pytz.timezone("America/New_York")
        # On 2024-11-03, 01:00 falls back to 01:00 in America/New_York (repeats 01:00-02:00)
        overlap_dt = datetime(2024, 11, 3, 1, 30)

        # Direct localization with is_dst=None would raise AmbiguousTimeError
        with self.assertRaises(pytz.exceptions.AmbiguousTimeError):
            tz_ny.localize(overlap_dt, is_dst=None)

        # safe_localize resolves ambiguity using is_dst=False without throwing
        safe_dt = safe_localize(tz_ny, overlap_dt)
        self.assertIsNotNone(safe_dt.tzinfo)
        self.assertEqual(safe_dt.hour, 1)
        self.assertEqual(safe_dt.minute, 30)

    def test_invalid_timezone_falls_back_to_utc(self):
        """12. test_invalid_timezone_falls_back_to_utc: Invalid timezone falls back to UTC without exception."""
        invalid_tz = "Invalid/Nonexistent_Timezone"
        base_dt = datetime(2026, 10, 7, 10, 0)

        # calculate_next_run_at should not throw UnknownTimeZoneError
        next_run = calculate_next_run_at(base_dt, invalid_tz)
        self.assertEqual(next_run.tzinfo, pytz.UTC)

        # is_working_hours should not throw
        self.assertIsInstance(is_working_hours(invalid_tz), bool)

        # adjust_to_working_hours should not throw and return naive UTC
        adjusted = adjust_to_working_hours(base_dt, invalid_tz)
        self.assertIsNone(adjusted.tzinfo)

        # next_working_day_9am should not throw
        next_9am = next_working_day_9am(invalid_tz)
        self.assertIsNone(next_9am.tzinfo)

        # Non-string and None inputs
        self.assertEqual(calculate_next_run_at(base_dt, None).tzinfo, pytz.UTC)
        self.assertEqual(calculate_next_run_at(base_dt, 12345).tzinfo, pytz.UTC)

    def test_next_working_day_9am_honors_schedule(self):
        """13. test_next_working_day_9am_honors_schedule: Weekend-enabled schedule rolls to Saturday instead of skipping to Monday."""
        # Friday 2026-10-09 15:00 UTC
        fri_now = datetime(2026, 10, 9, 15, 0)

        # Baseline: weekend_sending disabled skips to Monday 09:00 naive UTC
        next_mon_9am = next_working_day_9am("UTC", schedule=None, now_dt=fri_now)
        self.assertEqual(next_mon_9am, datetime(2026, 10, 12, 9, 0))

        # Weekend sending enabled: rolls to Saturday 09:00 naive UTC
        next_sat_9am = next_working_day_9am("UTC", schedule={"weekend_sending": True}, now_dt=fri_now)
        self.assertEqual(next_sat_9am, datetime(2026, 10, 10, 9, 0))

        # Custom start_hour=8 with weekend sending: rolls to Saturday 08:00 naive UTC
        next_sat_8am = next_working_day_9am("UTC", schedule={"weekend_sending": True, "start_hour": 8}, now_dt=fri_now)
        self.assertEqual(next_sat_8am, datetime(2026, 10, 10, 8, 0))


if __name__ == "__main__":
    unittest.main()
