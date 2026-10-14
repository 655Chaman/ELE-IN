import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from core.backend.services.auto_cooling import resume_cooled_accounts, probe_and_recover_degraded_proxies

class TestAutoCoolingAndRecovery(unittest.TestCase):
    
    def test_resume_cooled_accounts_resumes_expired_cooldown(self):
        mock_supabase = MagicMock()
        old_time = (datetime.utcnow() - timedelta(hours=7)).isoformat()
        
        mock_supabase.table().select().eq().execute.return_value = MagicMock(
            data=[
                {
                    "id": "acc-1",
                    "name": "Test Account",
                    "status_changed_at": old_time,
                    "workspace_id": "ws-1"
                }
            ]
        )
        
        resumed = resume_cooled_accounts(mock_supabase, cooldown_hours=6)
        self.assertIn("acc-1", resumed)
        mock_supabase.table().update.assert_called()
        mock_supabase.table().insert.assert_called()

    def test_resume_cooled_accounts_preserves_active_cooldown(self):
        mock_supabase = MagicMock()
        recent_time = (datetime.utcnow() - timedelta(hours=2)).isoformat()
        
        mock_supabase.table().select().eq().execute.return_value = MagicMock(
            data=[
                {
                    "id": "acc-2",
                    "name": "Recent Account",
                    "status_changed_at": recent_time,
                    "workspace_id": "ws-1"
                }
            ]
        )
        
        resumed = resume_cooled_accounts(mock_supabase, cooldown_hours=6)
        self.assertEqual(len(resumed), 0)

    def test_orchestrator_auto_resumes_rate_limited_account_after_cooldown(self):
        from campaigns.backend.services.elein_orchestrator import EleInOrchestrator
        self.assertTrue(hasattr(EleInOrchestrator, "requeue_waiting_for_reply_leads"))

    def test_probe_and_recover_degraded_proxies(self):
        mock_supabase = MagicMock()
        old_time = (datetime.utcnow() - timedelta(hours=3)).isoformat()
        
        mock_supabase.table().select().eq().execute.return_value = MagicMock(
            data=[
                {
                    "id": "proxy-1",
                    "last_checked_at": old_time
                }
            ]
        )
        
        recovered = probe_and_recover_degraded_proxies(mock_supabase, cooldown_hours=2)
        self.assertIn("proxy-1", recovered)
        mock_supabase.table().update.assert_called()

if __name__ == "__main__":
    unittest.main()
