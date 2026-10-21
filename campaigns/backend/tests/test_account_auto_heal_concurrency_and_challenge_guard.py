import unittest
from unittest.mock import MagicMock, patch
import json
from datetime import datetime, timezone, timedelta

from accounts.backend.services.account_auto_heal_service import (
    auto_heal_account,
    fleet_auto_heal,
    _active_heals,
    _heal_locks_mutex
)
from integrations.backend.services.linkedin_worker import SecurityChallengeError


class TestAccountAutoHealConcurrencyAndChallengeGuard(unittest.TestCase):
    """
    Test suite for Step 25: Account Auto-Heal & Reconnection Concurrency Lock Guard (Paranoia Framework).
    """

    def setUp(self):
        self.supabase = MagicMock()
        self.workspace_id = "ws_test_workspace"
        self.account_id = "acc_test_123"
        with _heal_locks_mutex:
            _active_heals.clear()

    def tearDown(self):
        with _heal_locks_mutex:
            _active_heals.clear()

    @patch("accounts.backend.services.account_auto_heal_service.LinkedInWorker")
    @patch("accounts.backend.services.account_auto_heal_service.crypto")
    def test_concurrent_auto_heal_rejection(self, mock_crypto, mock_worker_cls):
        """Test 1: If auto-heal is in progress on account A, a concurrent call immediately returns locked: True."""
        with _heal_locks_mutex:
            _active_heals[self.account_id] = datetime.now(timezone.utc).timestamp()

        res = auto_heal_account(self.account_id, self.workspace_id, self.supabase)
        self.assertTrue(res.get("locked"))
        self.assertEqual(res.get("recommendation"), "LOCKED_IN_PROGRESS")
        self.assertFalse(res.get("healed"))

    @patch("accounts.backend.services.account_auto_heal_service.LinkedInWorker")
    @patch("accounts.backend.services.account_auto_heal_service.crypto")
    def test_auto_heal_lock_released_after_completion(self, mock_crypto, mock_worker_cls):
        """Test 2: After call finishes, a subsequent call acquires the lock normally."""
        mock_crypto.pg_hex_to_bytes.return_value = b"bytes"
        mock_crypto.decrypt_bytes.return_value = b'[{"name": "li_at", "value": "123"}]'

        mock_acc_table = MagicMock()
        mock_acc_table.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{
                "id": self.account_id,
                "workspace_id": self.workspace_id,
                "status": "ACTIVE",
                "session_cookies_encrypted": "hex_abc",
                "cookie_secret_ref": "ref_1"
            }]
        )
        self.supabase.table.return_value = mock_acc_table

        mock_worker = MagicMock()
        mock_worker._http_get.return_value = MagicMock(status_code=200, text="OK")
        mock_worker_cls.return_value = mock_worker

        res1 = auto_heal_account(self.account_id, self.workspace_id, self.supabase)
        self.assertNotEqual(res1.get("recommendation"), "LOCKED_IN_PROGRESS")

        res2 = auto_heal_account(self.account_id, self.workspace_id, self.supabase)
        self.assertNotEqual(res2.get("recommendation"), "LOCKED_IN_PROGRESS")

    @patch("accounts.backend.services.account_auto_heal_service.LinkedInWorker")
    @patch("accounts.backend.services.account_auto_heal_service.crypto")
    def test_security_challenge_triggers_24h_quarantine_and_pauses_campaigns(self, mock_crypto, mock_worker_cls):
        """Test 3: When probe returns 999 or challenge, status transitions to CHALLENGE_REQUIRED, 24h quarantine, campaigns paused."""
        mock_crypto.pg_hex_to_bytes.return_value = b"bytes"
        mock_crypto.decrypt_bytes.return_value = b'[{"name": "li_at", "value": "123"}]'

        mock_acc_table = MagicMock()
        mock_acc_table.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{
                "id": self.account_id,
                "workspace_id": self.workspace_id,
                "status": "ACTIVE",
                "session_cookies_encrypted": "hex_abc",
                "cookie_secret_ref": "ref_1"
            }]
        )
        self.supabase.table.return_value = mock_acc_table

        mock_worker = MagicMock()
        mock_worker._http_get.return_value = MagicMock(status_code=999)
        mock_worker_cls.return_value = mock_worker

        res = auto_heal_account(self.account_id, self.workspace_id, self.supabase)
        self.assertEqual(res["new_status"], "CHALLENGE_REQUIRED")
        self.assertEqual(res["recommendation"], "CHALLENGE_QUARANTINED")
        self.assertTrue(any("CHALLENGE_REQUIRED" in a for a in res["actions_taken"]))

    @patch("accounts.backend.services.account_auto_heal_service.crypto")
    def test_quarantined_account_skips_automated_auto_heal(self, mock_crypto):
        """Test 4: Auto-heal rejects quarantined account without hitting LinkedIn."""
        future_iso = (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat()
        mock_acc_table = MagicMock()
        mock_acc_table.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{
                "id": self.account_id,
                "workspace_id": self.workspace_id,
                "status": "CHALLENGE_REQUIRED",
                "quarantined_until": future_iso,
                "quarantine_reason": "security_challenge"
            }]
        )
        self.supabase.table.return_value = mock_acc_table

        res = auto_heal_account(self.account_id, self.workspace_id, self.supabase, force=False)
        self.assertTrue(res.get("quarantined"))
        self.assertEqual(res.get("recommendation"), "CHALLENGE_QUARANTINED")

    @patch("accounts.backend.services.account_auto_heal_service.LinkedInWorker")
    @patch("accounts.backend.services.account_auto_heal_service.crypto")
    def test_force_flag_bypasses_quarantine(self, mock_crypto, mock_worker_cls):
        """Test 5: force=True clears quarantine and proceeds with healing."""
        mock_crypto.pg_hex_to_bytes.return_value = b"bytes"
        mock_crypto.decrypt_bytes.return_value = b'[{"name": "li_at", "value": "123"}]'

        future_iso = (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat()
        mock_acc_table = MagicMock()
        mock_acc_table.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{
                "id": self.account_id,
                "workspace_id": self.workspace_id,
                "status": "CHALLENGE_REQUIRED",
                "quarantined_until": future_iso,
                "quarantine_reason": "security_challenge",
                "session_cookies_encrypted": "hex_abc",
                "cookie_secret_ref": "ref_1"
            }]
        )
        self.supabase.table.return_value = mock_acc_table

        mock_worker = MagicMock()
        mock_worker._http_get.return_value = MagicMock(status_code=200, text="OK")
        mock_worker_cls.return_value = mock_worker

        res = auto_heal_account(self.account_id, self.workspace_id, self.supabase, force=True)
        self.assertTrue(res.get("healed"))
        self.assertEqual(res.get("new_status"), "ACTIVE")

    @patch("accounts.backend.services.account_auto_heal_service.crypto")
    def test_max_24h_attempts_rate_limits_auto_heal(self, mock_crypto):
        """Test 6: Exceeding 3 attempts in 24h returns rate_limited: True with recommendation MAX_ATTEMPTS_EXCEEDED."""
        mock_checks_res = MagicMock(data=[{"id": "1"}, {"id": "2"}, {"id": "3"}])
        
        def table_side_effect(name):
            t = MagicMock()
            if name == "accounts":
                t.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[{
                        "id": self.account_id,
                        "workspace_id": self.workspace_id,
                        "status": "DISCONNECTED",
                        "session_cookies_encrypted": "hex_abc"
                    }]
                )
            elif name == "account_health_checks":
                t.select.return_value.eq.return_value.eq.return_value.gte.return_value.execute.return_value = mock_checks_res
            return t

        self.supabase.table.side_effect = table_side_effect

        res = auto_heal_account(self.account_id, self.workspace_id, self.supabase, force=False)
        self.assertTrue(res.get("rate_limited"))
        self.assertEqual(res.get("recommendation"), "MAX_ATTEMPTS_EXCEEDED")

    @patch("accounts.backend.services.account_auto_heal_service.auto_heal_account")
    def test_fleet_auto_heal_skips_quarantined_accounts(self, mock_auto_heal):
        """Test 7: Fleet auto-heal skips quarantined accounts without calling auto_heal_account."""
        future_iso = (datetime.now(timezone.utc) + timedelta(hours=10)).isoformat()
        mock_acc_table = MagicMock()
        mock_acc_table.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[
                {"id": "acc_quarantined", "status": "CHALLENGE_REQUIRED", "quarantined_until": future_iso},
                {"id": "acc_healthy", "status": "ACTIVE"}
            ]
        )
        self.supabase.table.return_value = mock_acc_table
        mock_auto_heal.return_value = {"account_id": "acc_healthy", "healed": False, "new_status": "ACTIVE"}

        fleet_res = fleet_auto_heal(self.workspace_id, self.supabase)
        self.assertEqual(fleet_res["total_scanned"], 2)
        self.assertEqual(fleet_res["attention_count"], 1)
        mock_auto_heal.assert_called_once_with("acc_healthy", self.workspace_id, self.supabase)

    @patch("accounts.backend.services.account_auto_heal_service.LinkedInWorker")
    @patch("accounts.backend.services.account_auto_heal_service.crypto")
    def test_http_403_checkpoint_challenge_detection(self, mock_crypto, mock_worker_cls):
        """Test 8: 403 with checkpoint text sets CHALLENGE_REQUIRED."""
        mock_crypto.pg_hex_to_bytes.return_value = b"bytes"
        mock_crypto.decrypt_bytes.return_value = b'[{"name": "li_at", "value": "123"}]'

        mock_acc_table = MagicMock()
        mock_acc_table.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{
                "id": self.account_id,
                "workspace_id": self.workspace_id,
                "status": "ACTIVE",
                "session_cookies_encrypted": "hex_abc",
                "cookie_secret_ref": "ref_1"
            }]
        )
        self.supabase.table.return_value = mock_acc_table

        mock_worker = MagicMock()
        mock_worker._http_get.return_value = MagicMock(status_code=403, text="Please complete checkpoint verification")
        mock_worker_cls.return_value = mock_worker

        res = auto_heal_account(self.account_id, self.workspace_id, self.supabase)
        self.assertEqual(res["new_status"], "CHALLENGE_REQUIRED")
        self.assertEqual(res["recommendation"], "CHALLENGE_QUARANTINED")

    @patch("accounts.backend.services.account_auto_heal_service.LinkedInWorker")
    @patch("accounts.backend.services.account_auto_heal_service.crypto")
    def test_http_200_challenge_redirect_detection(self, mock_crypto, mock_worker_cls):
        """Test 9: 200 with checkpoint URL text sets CHALLENGE_REQUIRED."""
        mock_crypto.pg_hex_to_bytes.return_value = b"bytes"
        mock_crypto.decrypt_bytes.return_value = b'[{"name": "li_at", "value": "123"}]'

        mock_acc_table = MagicMock()
        mock_acc_table.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{
                "id": self.account_id,
                "workspace_id": self.workspace_id,
                "status": "ACTIVE",
                "session_cookies_encrypted": "hex_abc",
                "cookie_secret_ref": "ref_1"
            }]
        )
        self.supabase.table.return_value = mock_acc_table

        mock_worker = MagicMock()
        mock_worker._http_get.return_value = MagicMock(status_code=200, text="Redirected to /checkpoint/challenge/verify")
        mock_worker_cls.return_value = mock_worker

        res = auto_heal_account(self.account_id, self.workspace_id, self.supabase)
        self.assertEqual(res["new_status"], "CHALLENGE_REQUIRED")
        self.assertEqual(res["recommendation"], "CHALLENGE_QUARANTINED")

    @patch("accounts.backend.services.account_auto_heal_service.LinkedInWorker")
    @patch("accounts.backend.services.account_auto_heal_service.crypto")
    def test_security_challenge_error_exception_handled(self, mock_crypto, mock_worker_cls):
        """Test 10: SecurityChallengeError transitions to CHALLENGE_REQUIRED."""
        mock_crypto.pg_hex_to_bytes.return_value = b"bytes"
        mock_crypto.decrypt_bytes.return_value = b'[{"name": "li_at", "value": "123"}]'

        mock_acc_table = MagicMock()
        mock_acc_table.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{
                "id": self.account_id,
                "workspace_id": self.workspace_id,
                "status": "ACTIVE",
                "session_cookies_encrypted": "hex_abc",
                "cookie_secret_ref": "ref_1"
            }]
        )
        self.supabase.table.return_value = mock_acc_table

        mock_worker = MagicMock()
        mock_worker._http_get.side_effect = SecurityChallengeError("CAPTCHA detected")
        mock_worker_cls.return_value = mock_worker

        res = auto_heal_account(self.account_id, self.workspace_id, self.supabase)
        self.assertEqual(res["new_status"], "CHALLENGE_REQUIRED")
        self.assertEqual(res["recommendation"], "CHALLENGE_QUARANTINED")

    @patch("accounts.backend.services.account_auto_heal_service.LinkedInWorker")
    @patch("accounts.backend.services.account_auto_heal_service.crypto")
    def test_quarantine_expired_without_force_requires_manual_challenge_resolution(self, mock_crypto, mock_worker_cls):
        """Paranoia Layer 1 & 2: Quarantine expired on CHALLENGE_REQUIRED account blocks automated LinkedIn probe without force=True."""
        past_iso = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        mock_acc_table = MagicMock()
        mock_acc_table.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{
                "id": self.account_id,
                "workspace_id": self.workspace_id,
                "status": "CHALLENGE_REQUIRED",
                "quarantined_until": past_iso,
                "quarantine_reason": "security_challenge",
                "session_cookies_encrypted": "hex_abc",
                "cookie_secret_ref": "ref_1"
            }]
        )
        self.supabase.table.return_value = mock_acc_table

        res = auto_heal_account(self.account_id, self.workspace_id, self.supabase, force=False)
        self.assertEqual(res["new_status"], "NEEDS_ATTENTION")
        self.assertEqual(res["recommendation"], "MANUAL_CHALLENGE_RESOLUTION_REQUIRED")
        self.assertFalse(res["healed"])
        # LinkedInWorker must NOT have been called
        mock_worker_cls.assert_not_called()

    @patch("accounts.backend.services.account_auto_heal_service.LinkedInWorker")
    @patch("accounts.backend.services.account_auto_heal_service.crypto")
    def test_auto_heal_proxied_account_without_healthy_proxy_halts_safely(self, mock_crypto, mock_worker_cls):
        """Paranoia Layer 1: Configured proxy account halts with PROXY_FAILURE if proxy cannot be resolved, avoiding datacenter leak."""
        mock_crypto.pg_hex_to_bytes.return_value = b"bytes"
        mock_crypto.decrypt_bytes.return_value = b'[{"name": "li_at", "value": "123"}]'

        def table_side_effect(name):
            m = MagicMock()
            if name == "accounts":
                m.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[{
                        "id": self.account_id,
                        "workspace_id": self.workspace_id,
                        "status": "ACTIVE",
                        "session_cookies_encrypted": "hex_abc",
                        "cookie_secret_ref": "ref_1",
                        "proxy_id": "proxy_dead_999"
                    }]
                )
            elif name == "proxies":
                # Proxy not found / dead
                m.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
            elif name == "account_health_checks":
                m.select.return_value.eq.return_value.eq.return_value.gte.return_value.execute.return_value = MagicMock(data=[])
            return m

        self.supabase.table.side_effect = table_side_effect

        res = auto_heal_account(self.account_id, self.workspace_id, self.supabase)
        self.assertEqual(res["new_status"], "NEEDS_ATTENTION")
        self.assertEqual(res["recommendation"], "PROXY_FAILURE")
        self.assertFalse(res["healed"])
        # LinkedInWorker must NOT have been called
        mock_worker_cls.assert_not_called()


if __name__ == "__main__":
    unittest.main()
