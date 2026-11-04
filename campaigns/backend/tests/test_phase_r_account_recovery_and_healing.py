import unittest
import json
import base64
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from accounts.backend.services.account_auto_heal_service import (
    detect_session_death_and_validate_cookies,
    rotate_account_credential_dek,
    dispatch_challenge_verification_alert,
    evaluate_and_gracefully_pause_mailbox,
    _active_heals,
    _heal_locks_mutex
)
from campaigns.backend.routers.elein import (
    check_account_session_death,
    rotate_account_dek_endpoint,
    trigger_challenge_alert_endpoint,
    check_mailbox_reputation_endpoint,
    ChallengeAlertRequest,
    MailboxReputationCheckRequest
)


class TestPhaseRAccountRecoveryAndHealing(unittest.TestCase):

    def setUp(self):
        self.workspace_id = "ws-phase-r"
        self.account_id = "acc-phase-r-01"
        self.supabase = MagicMock()
        with _heal_locks_mutex:
            _active_heals.clear()

    def tearDown(self):
        with _heal_locks_mutex:
            _active_heals.clear()

    # ── 1. ACTIVE COOKIE SESSION VALIDATION & SESSION-DEATH DETECTION ──────────

    def test_detect_session_death_missing_cookies(self):
        """Paranoia Layer 0: Detects missing cookies as session death."""
        mock_acc = {
            "id": self.account_id,
            "workspace_id": self.workspace_id,
            "name": "Sender 1",
            "status": "ACTIVE",
            "session_cookies_encrypted": None
        }
        self.supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [mock_acc]

        res = detect_session_death_and_validate_cookies(self.account_id, self.workspace_id, self.supabase)
        self.assertFalse(res["session_valid"])
        self.assertTrue(res["session_death"])
        self.assertEqual(res["reason"], "MISSING_SESSION_COOKIES")
        self.assertEqual(res["status"], "DISCONNECTED")

    def test_detect_session_death_missing_li_at(self):
        """Paranoia Layer 1: Missing li_at token indicates invalid/dead session."""
        mock_acc = {
            "id": self.account_id,
            "workspace_id": self.workspace_id,
            "name": "Sender 1",
            "status": "ACTIVE",
            "session_cookies_encrypted": "hex_abc",
            "cookie_secret_ref": "ref_1"
        }
        self.supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [mock_acc]

        # Return cookie list without li_at
        with patch("accounts.backend.services.account_auto_heal_service.crypto") as mock_crypto:
            mock_crypto.pg_hex_to_bytes.return_value = b"encrypted"
            mock_crypto.decrypt_bytes.return_value = b'[{"name": "other_cookie", "value": "xyz"}]'
            res = detect_session_death_and_validate_cookies(self.account_id, self.workspace_id, self.supabase)
            self.assertFalse(res["session_valid"])
            self.assertTrue(res["session_death"])
            self.assertEqual(res["reason"], "MISSING_LI_AT_TOKEN")

    def test_detect_session_death_expired_cookie(self):
        """Paranoia Layer 1: Expired cookie timestamp marks session death."""
        past_date = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        mock_acc = {
            "id": self.account_id,
            "workspace_id": self.workspace_id,
            "name": "Sender 1",
            "status": "ACTIVE",
            "session_cookies_encrypted": "hex_abc",
            "cookie_expires_at": past_date
        }
        self.supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [mock_acc]

        with patch("accounts.backend.services.account_auto_heal_service.crypto") as mock_crypto:
            mock_crypto.pg_hex_to_bytes.return_value = b"encrypted"
            mock_crypto.decrypt_bytes.return_value = b'[{"name": "li_at", "value": "token_val"}]'
            res = detect_session_death_and_validate_cookies(self.account_id, self.workspace_id, self.supabase)
            self.assertFalse(res["session_valid"])
            self.assertTrue(res["session_death"])
            self.assertEqual(res["reason"], "COOKIE_EXPIRED")

    def test_detect_session_death_401_probe_pauses_campaigns(self):
        """Paranoia Layer 0 & 1: 401 Voyager probe marks session death and pauses tied campaigns."""
        mock_acc = {
            "id": self.account_id,
            "workspace_id": self.workspace_id,
            "name": "Sender 1",
            "status": "ACTIVE",
            "session_cookies_encrypted": "hex_abc",
            "cookie_expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        }
        self.supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [mock_acc]

        # Tied campaign accounts
        self.supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {"campaign_id": "camp-1"},
            {"campaign_id": "camp-2"}
        ]

        with patch("accounts.backend.services.account_auto_heal_service.crypto") as mock_crypto, \
             patch("accounts.backend.services.account_auto_heal_service.LinkedInWorker") as mock_worker_cls:
            mock_crypto.pg_hex_to_bytes.return_value = b"encrypted"
            mock_crypto.decrypt_bytes.return_value = b'[{"name": "li_at", "value": "token_val"}]'

            mock_worker = MagicMock()
            mock_resp = MagicMock()
            mock_resp.status_code = 401
            mock_resp.text = "Unauthorized"
            mock_worker._http_get.return_value = mock_resp
            mock_worker_cls.return_value = mock_worker

            res = detect_session_death_and_validate_cookies(self.account_id, self.workspace_id, self.supabase, force_probe=True)
            self.assertFalse(res["session_valid"])
            self.assertTrue(res["session_death"])
            self.assertEqual(res["reason"], "HTTP_401_UNAUTHORIZED")
            self.assertEqual(res["status"], "DISCONNECTED")

            # Verify campaigns were paused
            self.supabase.table.assert_any_call("campaigns")

    def test_detect_session_probe_proxy_failure_does_not_declare_death(self):
        """Paranoia Layer 1: Proxy timeout does NOT declare session death."""
        mock_acc = {
            "id": self.account_id,
            "workspace_id": self.workspace_id,
            "name": "Sender 1",
            "status": "ACTIVE",
            "session_cookies_encrypted": "hex_abc",
            "cookie_expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        }
        self.supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [mock_acc]

        with patch("accounts.backend.services.account_auto_heal_service.crypto") as mock_crypto, \
             patch("accounts.backend.services.account_auto_heal_service.LinkedInWorker") as mock_worker_cls:
            mock_crypto.pg_hex_to_bytes.return_value = b"encrypted"
            mock_crypto.decrypt_bytes.return_value = b'[{"name": "li_at", "value": "token_val"}]'

            mock_worker = MagicMock()
            mock_worker._http_get.side_effect = Exception("Proxy ConnectTimeout: connection timed out")
            mock_worker_cls.return_value = mock_worker

            res = detect_session_death_and_validate_cookies(self.account_id, self.workspace_id, self.supabase, force_probe=True)
            # Session is valid, proxy failed
            self.assertTrue(res["session_valid"])
            self.assertFalse(res["session_death"])

    # ── 2. VAULT DEK ROTATION & CHALLENGE VERIFICATION ALERTS ─────────────────

    def test_rotate_account_credential_dek_success(self):
        """Paranoia Layer 0 & 1: Rotates DEK via Vault RPC and updates database atomically."""
        mock_acc = {
            "id": self.account_id,
            "workspace_id": self.workspace_id,
            "session_cookies_encrypted": "hex_old",
            "cookie_secret_ref": "vault-ref-old"
        }
        self.supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [mock_acc]

        # Mock Vault RPCs
        rpc_mock = MagicMock()
        rpc_mock.execute.return_value.data = {"dek": base64.b64encode(b"0" * 32).decode("utf-8")}
        store_rpc_mock = MagicMock()
        store_rpc_mock.execute.return_value.data = "vault-ref-new"

        def rpc_side_effect(fn_name, args):
            if fn_name == "get_decrypted_account_payload":
                return rpc_mock
            elif fn_name == "store_account_secret":
                return store_rpc_mock
            return MagicMock()

        self.supabase.rpc.side_effect = rpc_side_effect

        with patch("accounts.backend.services.account_auto_heal_service.crypto") as mock_crypto:
            mock_crypto.pg_hex_to_bytes.return_value = b"encrypted_old"
            mock_crypto.decrypt_bytes.return_value = b'[{"name": "li_at", "value": "token"}]'
            mock_crypto.generate_dek.return_value = base64.b64encode(b"1" * 32).decode("utf-8")
            mock_crypto.encrypt_bytes.return_value = b"encrypted_new"
            mock_crypto.bytes_to_pg_hex.return_value = "hex_new"

            res = rotate_account_credential_dek(self.account_id, self.workspace_id, self.supabase)
            self.assertEqual(res["status"], "success")
            self.assertTrue(res["vault_secured"])
            self.assertIn("rotated_at", res)

            # Check that accounts table update received new hex and new ref
            self.supabase.table().update.assert_called()
            update_call = self.supabase.table().update.call_args[0][0]
            self.assertEqual(update_call["session_cookies_encrypted"], "hex_new")
            self.assertEqual(update_call["cookie_secret_ref"], "vault-ref-new")

    def test_rotate_account_credential_dek_zero_leakage(self):
        """Paranoia Layer 2: DEK and decrypted plaintext are never returned in response."""
        mock_acc = {
            "id": self.account_id,
            "workspace_id": self.workspace_id,
            "session_cookies_encrypted": "hex_old"
        }
        self.supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [mock_acc]

        with patch("accounts.backend.services.account_auto_heal_service.crypto") as mock_crypto:
            mock_crypto.pg_hex_to_bytes.return_value = b"old"
            mock_crypto.decrypt_bytes.return_value = b"secret_plaintext"
            mock_crypto.generate_dek.return_value = "secret_dek_b64"
            mock_crypto.encrypt_bytes.return_value = b"new"
            mock_crypto.bytes_to_pg_hex.return_value = "hex_new"

            res = rotate_account_credential_dek(self.account_id, self.workspace_id, self.supabase)
            serialized = json.dumps(res)
            self.assertNotIn("secret_plaintext", serialized)
            self.assertNotIn("secret_dek_b64", serialized)

    def test_dispatch_challenge_verification_alert(self):
        """Paranoia Layer 0 & 1: Quarantines challenged account, associated proxy, and pauses tied campaigns."""
        # Account has an assigned proxy
        self.supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {"proxy_id": "px-challenge-1"}
        ]

        with patch("core.backend.services.proxy_routing.quarantine_proxy") as mock_quarantine_proxy:
            res = dispatch_challenge_verification_alert(
                account_id=self.account_id,
                workspace_id=self.workspace_id,
                challenge_type="PIN_VERIFICATION",
                detail="Email verification PIN code required",
                supabase=self.supabase
            )

            self.assertEqual(res["status"], "alert_dispatched")
            self.assertEqual(res["challenge_type"], "PIN_VERIFICATION")
            self.assertIn("quarantined_until", res)

            # Accounts table updated to CHALLENGE_REQUIRED
            update_call = self.supabase.table().update.call_args[0][0]
            self.assertEqual(update_call["status"], "CHALLENGE_REQUIRED")

            # Proxy quarantine called
            mock_quarantine_proxy.assert_called_with(
                self.supabase, "px-challenge-1", reason="account_challenge_pin_verification", cooldown_hours=24
            )

            # Outbox alert queued
            self.supabase.table.assert_any_call("outbox_events")

    # ── 3. GRACEFUL ACCOUNT PAUSING ON MAILBOX REPUTATION BREACH ─────────────

    def test_evaluate_and_gracefully_pause_mailbox_healthy(self):
        """Paranoia Layer 0: Healthy mailbox with zero bounces remains ACTIVE."""
        # Mock 50 delivered email events
        self.supabase.table.return_value.select.return_value.eq.return_value.gte.return_value.execute.return_value.data = [
            {"event_type": "delivered"} for _ in range(50)
        ]

        res = evaluate_and_gracefully_pause_mailbox(
            account_id=self.account_id,
            workspace_id=self.workspace_id,
            supabase=self.supabase
        )
        self.assertFalse(res["paused"])
        self.assertEqual(res["status"], "ACTIVE")
        self.assertEqual(res["bounce_rate_pct"], 0.0)
        self.assertEqual(res["deliverability_score"], 100.0)

    def test_evaluate_and_gracefully_pause_mailbox_bounce_threshold_breach(self):
        """Paranoia Layer 1: Exceeding bounce threshold gracefully pauses mailbox and campaigns."""
        # Mock 100 emails with 8 bounces (8% bounce rate > 5% threshold)
        events = [{"event_type": "delivered"} for _ in range(92)] + [{"event_type": "hard_bounce"} for _ in range(8)]
        self.supabase.table.return_value.select.return_value.eq.return_value.gte.return_value.execute.return_value.data = events

        # Mock tied campaigns
        self.supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {"campaign_id": "camp-email-1"}
        ]

        res = evaluate_and_gracefully_pause_mailbox(
            account_id=self.account_id,
            workspace_id=self.workspace_id,
            supabase=self.supabase,
            deliverability_score_threshold=70.0,
            max_bounce_rate_pct=5.0
        )

        self.assertTrue(res["paused"])
        self.assertEqual(res["status"], "COOLDOWN")
        self.assertEqual(res["bounce_rate_pct"], 8.0)
        self.assertTrue(len(res["breaches"]) > 0)
        
        # Verify accounts table received quarantined_until
        all_update_calls = [c[0][0] for c in self.supabase.table().update.call_args_list]
        has_quarantined_until = any("quarantined_until" in call for call in all_update_calls)
        self.assertTrue(has_quarantined_until)

        # Verify tied campaigns were paused with MAILBOX_REPUTATION_PROTECT
        self.supabase.table.assert_any_call("campaigns")
        camp_update = self.supabase.table().update.call_args[0][0]
        self.assertEqual(camp_update["pod_pause_reason"], "MAILBOX_REPUTATION_PROTECT")

    def test_evaluate_and_gracefully_pause_mailbox_small_sample_size_protection(self):
        """Paranoia Layer 1: Sample size < 10 does not trip percentage-based pause for 1 bounce."""
        # 3 emails sent, 1 bounce (33.3% but only 3 sample size)
        events = [{"event_type": "delivered"}, {"event_type": "delivered"}, {"event_type": "soft_bounce"}]
        self.supabase.table.return_value.select.return_value.eq.return_value.gte.return_value.execute.return_value.data = events

        res = evaluate_and_gracefully_pause_mailbox(
            account_id=self.account_id,
            workspace_id=self.workspace_id,
            supabase=self.supabase,
            min_sample_size=10
        )
        self.assertFalse(res["paused"])
        self.assertFalse(res["sample_reached"])

    # ── 4. FASTAPI ROUTER ENDPOINTS FOR PHASE R ───────────────────────────────

    def test_router_session_death_check_endpoint(self):
        """Paranoia Layer 0: Tests check_account_session_death router endpoint."""
        mock_acc = {
            "id": self.account_id,
            "workspace_id": self.workspace_id,
            "status": "ACTIVE",
            "session_cookies_encrypted": None
        }
        def table_side_effect(tbl_name):
            t = MagicMock()
            if tbl_name == "workspaces":
                t.select.return_value.eq.return_value.execute.return_value.data = [{"tier": "ENTERPRISE"}]
            else:
                t.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [mock_acc]
            return t
        self.supabase.table.side_effect = table_side_effect

        res = check_account_session_death(
            account_id=self.account_id,
            force_probe=False,
            supabase=self.supabase,
            workspace_id=self.workspace_id
        )
        self.assertTrue(res["session_death"])

    def test_router_rotate_dek_endpoint(self):
        """Paranoia Layer 0: Tests rotate_account_dek_endpoint router endpoint."""
        mock_acc = {
            "id": self.account_id,
            "workspace_id": self.workspace_id,
            "session_cookies_encrypted": "hex_old"
        }
        self.supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [mock_acc]

        with patch("accounts.backend.services.account_auto_heal_service.crypto") as mock_crypto:
            mock_crypto.pg_hex_to_bytes.return_value = b"old"
            mock_crypto.decrypt_bytes.return_value = b"plaintext"
            mock_crypto.generate_dek.return_value = base64.b64encode(b"2" * 32).decode("utf-8")
            mock_crypto.encrypt_bytes.return_value = b"new"
            mock_crypto.bytes_to_pg_hex.return_value = "hex_new"

            res = rotate_account_dek_endpoint(
                account_id=self.account_id,
                supabase=self.supabase,
                workspace_id=self.workspace_id
            )
            self.assertEqual(res["status"], "success")

    def test_router_challenge_alert_endpoint(self):
        """Paranoia Layer 0: Tests trigger_challenge_alert_endpoint router endpoint."""
        payload = ChallengeAlertRequest(challenge_type="SMS_OTP", detail="SMS code requested")
        res = trigger_challenge_alert_endpoint(
            account_id=self.account_id,
            payload=payload,
            supabase=self.supabase,
            workspace_id=self.workspace_id
        )
        self.assertEqual(res["status"], "alert_dispatched")
        self.assertEqual(res["challenge_type"], "SMS_OTP")

    def test_router_mailbox_reputation_check_endpoint(self):
        """Paranoia Layer 0: Tests check_mailbox_reputation_endpoint router endpoint."""
        payload = MailboxReputationCheckRequest(deliverability_score_threshold=70.0)
        self.supabase.table.return_value.select.return_value.eq.return_value.gte.return_value.execute.return_value.data = []

        res = check_mailbox_reputation_endpoint(
            account_id=self.account_id,
            payload=payload,
            supabase=self.supabase,
            workspace_id=self.workspace_id
        )
        self.assertFalse(res["paused"])
        self.assertEqual(res["deliverability_score"], 100.0)


if __name__ == "__main__":
    unittest.main()
