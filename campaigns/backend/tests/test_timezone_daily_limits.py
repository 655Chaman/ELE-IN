import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
import pytz

from core.backend.services.limits import get_effective_usage_date, check_and_increment_limit
from campaigns.backend.services.elein_executor import EleInNodeExecutor

class TestTimezoneDailyLimits(unittest.TestCase):

    def test_get_effective_usage_date_timezones(self):
        # Test valid timezones return YYYY-MM-DD format
        utc_date = get_effective_usage_date("UTC")
        self.assertRegex(utc_date, r"^\d{4}-\d{2}-\d{2}$")

        ny_date = get_effective_usage_date("America/New_York")
        self.assertRegex(ny_date, r"^\d{4}-\d{2}-\d{2}$")

        tokyo_date = get_effective_usage_date("Asia/Tokyo")
        self.assertRegex(tokyo_date, r"^\d{4}-\d{2}-\d{2}$")

        # Test invalid timezone falls back to UTC
        invalid_date = get_effective_usage_date("Invalid/Timezone")
        expected_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self.assertEqual(invalid_date, expected_utc)

        # Test None or non-string falls back to UTC
        none_date = get_effective_usage_date(None)
        self.assertEqual(none_date, expected_utc)

        non_str_date = get_effective_usage_date(12345)
        self.assertEqual(non_str_date, expected_utc)

    @patch("core.backend.services.limits.get_effective_usage_date")
    def test_check_limit_passes_usage_date_to_rpc(self, mock_get_date):
        mock_get_date.return_value = "2026-06-15"
        mock_supabase = MagicMock()
        mock_result = MagicMock()
        mock_result.data = True
        mock_supabase.rpc.return_value.execute.return_value = mock_result

        result = check_and_increment_limit(
            mock_supabase,
            account_id="acc-123",
            action_type="message",
            account_data={},
            tz_str="America/New_York"
        )
        self.assertTrue(result)
        mock_get_date.assert_called_once_with("America/New_York")
        mock_supabase.rpc.assert_called_with('try_consume_daily_action', {
            'p_account_id': 'acc-123',
            'p_action_type': 'message',
            'p_usage_date': '2026-06-15'
        })

    @patch("campaigns.backend.services.elein_executor.get_effective_usage_date")
    def test_release_limit_passes_consumed_usage_date(self, mock_get_date):
        mock_get_date.return_value = "2026-06-15"
        mock_worker = MagicMock()
        mock_worker.account_id = "acc-123"
        mock_supabase = MagicMock()

        executor = EleInNodeExecutor(linkedin_worker=mock_worker, supabase=mock_supabase)
        executor._release_limit("message", usage_date="2026-06-14")

        mock_supabase.rpc.assert_called_with("release_consumed_daily_action", {
            "p_account_id": "acc-123",
            "p_action_type": "message",
            "p_usage_date": "2026-06-14"
        })

    @patch("campaigns.backend.services.elein_executor.get_effective_usage_date")
    def test_midnight_crossover_reversal_uses_consumed_date(self, mock_get_date):
        # Simulate consumer consuming on D1 ("2026-06-14"), but system time crosses midnight to D2 ("2026-06-15")
        mock_worker = MagicMock()
        mock_worker.account_id = "acc-123"
        mock_supabase = MagicMock()
        mock_result = MagicMock()
        mock_result.data = True
        mock_supabase.rpc.return_value.execute.return_value = mock_result

        # Step 1: Consume on D1
        mock_get_date.return_value = "2026-06-14"
        executor = EleInNodeExecutor(linkedin_worker=mock_worker, supabase=mock_supabase)
        
        # Check limit returns D1
        limit_err, consumed_date = executor._check_limit("message", tz_str="America/New_York")
        self.assertIsNone(limit_err)
        self.assertEqual(consumed_date, "2026-06-14")

        # Step 2: Midnight crossover occurs -> system time is now D2 ("2026-06-15")
        mock_get_date.return_value = "2026-06-15"

        # Step 3: Release limit should use consumed_date ("2026-06-14"), NOT current system date ("2026-06-15")
        executor._release_limit("message", usage_date=consumed_date)

        mock_supabase.rpc.assert_called_with("release_consumed_daily_action", {
            "p_account_id": "acc-123",
            "p_action_type": "message",
            "p_usage_date": "2026-06-14"
        })

if __name__ == "__main__":
    unittest.main()
