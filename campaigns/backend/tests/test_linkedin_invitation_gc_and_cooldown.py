"""
Phase 41 — LinkedIn Pending Invitation GC & Algorithmic Connection Safety Cooldown
Three-Layer Paranoia Test Suite (40+ tests)

Layer 0 — Core Mechanics
Layer 1 — Environmental Failure Analysis
Layer 2 — Human Paranoia & Security
"""

import pytest
import sys
import os
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta

# ---------------------------------------------------------------------------
# Path bootstrap — makes both root and integrations/backend importable
# ---------------------------------------------------------------------------
for path in [
    os.path.join(os.path.dirname(__file__), "..", "..", ".."),
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "integrations", "backend"),
]:
    p = os.path.abspath(path)
    if p not in sys.path:
        sys.path.insert(0, p)

from integrations.backend.services.linkedin_invitation_manager import (
    LinkedInInvitationManager,
    AccountHealthRisk,
    CooldownReason,
    InvitationStatus,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _future_iso(days=1):
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def _past_iso(days=1):
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _stale_inv(lead_id="lead-1", days_pending=22):
    return {
        "id": lead_id,
        "lead_id": lead_id,
        "invitation_id": f"inv-{lead_id}",
        "days_pending": days_pending,
        "status": "PENDING",
    }


def _fresh_inv(lead_id="lead-fresh", days_pending=3):
    return {
        "id": lead_id,
        "lead_id": lead_id,
        "invitation_id": f"inv-{lead_id}",
        "days_pending": days_pending,
        "status": "PENDING",
    }


# ===========================================================================
# LAYER 0 — Core Mechanics (15+ tests)
# ===========================================================================


class TestEvaluateAccountConnectionHealth:
    """Layer 0: evaluate_account_connection_health thresholds."""

    def test_zero_pending_is_optimal(self):
        res = LinkedInInvitationManager.evaluate_account_connection_health(0)
        assert res["risk_level"] == AccountHealthRisk.OPTIMAL.value
        assert res["can_send_invitations"] is True
        assert res["health_score"] >= 85

    def test_low_pending_is_optimal(self):
        res = LinkedInInvitationManager.evaluate_account_connection_health(150)
        assert res["risk_level"] == AccountHealthRisk.OPTIMAL.value
        assert res["can_send_invitations"] is True

    def test_at_300_approaching_ceiling(self):
        res = LinkedInInvitationManager.evaluate_account_connection_health(300)
        assert res["risk_level"] == AccountHealthRisk.APPROACHING_CEILING.value
        assert res["can_send_invitations"] is True
        assert 50 <= res["health_score"] <= 84

    def test_at_499_approaching_ceiling(self):
        res = LinkedInInvitationManager.evaluate_account_connection_health(499)
        assert res["risk_level"] == AccountHealthRisk.APPROACHING_CEILING.value

    def test_at_500_critical_restriction_risk(self):
        res = LinkedInInvitationManager.evaluate_account_connection_health(500)
        assert res["risk_level"] == AccountHealthRisk.CRITICAL_RESTRICTION_RISK.value
        assert res["can_send_invitations"] is False
        assert res["health_score"] <= 49

    def test_high_pending_capped_critical(self):
        res = LinkedInInvitationManager.evaluate_account_connection_health(1500)
        assert res["risk_level"] == AccountHealthRisk.CRITICAL_RESTRICTION_RISK.value
        assert res["can_send_invitations"] is False
        assert res["health_score"] >= 0

    def test_pending_count_in_result(self):
        res = LinkedInInvitationManager.evaluate_account_connection_health(200)
        assert res["pending_count"] == 200

    def test_none_pending_safe_default(self):
        res = LinkedInInvitationManager.evaluate_account_connection_health(None)
        assert res["pending_count"] == 0
        assert res["risk_level"] == AccountHealthRisk.OPTIMAL.value


class TestFilterStaleInvitations:
    """Layer 0: filter_stale_invitations clamp and logic."""

    def test_stale_inv_returned(self):
        invs = [_stale_inv(days_pending=22)]
        result = LinkedInInvitationManager.filter_stale_invitations(invs, max_age_days=21)
        assert len(result) == 1

    def test_fresh_inv_not_returned(self):
        invs = [_fresh_inv(days_pending=5)]
        result = LinkedInInvitationManager.filter_stale_invitations(invs, max_age_days=21)
        assert len(result) == 0

    def test_max_age_clamped_below_7_becomes_7(self):
        # With max_age_days=3, clamped to 7 → invitation with 8 days IS stale
        invs = [_stale_inv(days_pending=8)]
        result = LinkedInInvitationManager.filter_stale_invitations(invs, max_age_days=3)
        assert len(result) == 1

    def test_max_age_clamped_above_90_becomes_90(self):
        # With max_age_days=200, clamped to 90 → invitation with 91 days IS stale
        invs = [_stale_inv(days_pending=91)]
        result = LinkedInInvitationManager.filter_stale_invitations(invs, max_age_days=200)
        assert len(result) == 1

    def test_max_age_clamp_200_means_89_day_inv_fresh(self):
        # With max_age_days=200 clamped to 90, an 89-day invitation is NOT stale
        invs = [_stale_inv(days_pending=89)]
        result = LinkedInInvitationManager.filter_stale_invitations(invs, max_age_days=200)
        assert len(result) == 0

    def test_empty_list_returns_empty(self):
        result = LinkedInInvitationManager.filter_stale_invitations([], max_age_days=21)
        assert result == []

    def test_none_input_returns_empty(self):
        result = LinkedInInvitationManager.filter_stale_invitations(None, max_age_days=21)
        assert result == []

    def test_non_list_input_returns_empty(self):
        result = LinkedInInvitationManager.filter_stale_invitations("not-a-list", max_age_days=21)
        assert result == []

    def test_terminal_status_skipped(self):
        withdrawn = {"id": "w1", "days_pending": 30, "status": "WITHDRAWN"}
        accepted = {"id": "a1", "days_pending": 30, "status": "ACCEPTED"}
        result = LinkedInInvitationManager.filter_stale_invitations([withdrawn, accepted])
        assert len(result) == 0

    def test_sent_at_field_used_for_age(self):
        old_date = (datetime.now(timezone.utc) - timedelta(days=25)).isoformat()
        inv = {"id": "x1", "sent_at": old_date, "status": "PENDING"}
        result = LinkedInInvitationManager.filter_stale_invitations([inv], max_age_days=21)
        assert len(result) == 1


class TestWithdrawStaleInvitations:
    """Layer 0: withdraw_stale_invitations batch mechanics."""

    def test_batch_limit_25_withdraws_at_most_25(self):
        invs = [_stale_inv(lead_id=f"lead-{i}", days_pending=30) for i in range(50)]
        result = LinkedInInvitationManager.withdraw_stale_invitations(
            account={"id": "acc-1"},
            max_age_days=21,
            batch_limit=25,
            mock_invitations=invs,
        )
        assert result["withdrawn_count"] == 25

    def test_withdrawal_stamps_cooldown_on_lead(self):
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()
        invs = [_stale_inv(lead_id="lead-99", days_pending=30)]
        result = LinkedInInvitationManager.withdraw_stale_invitations(
            account={"id": "acc-1"},
            max_age_days=21,
            batch_limit=25,
            mock_invitations=invs,
            supabase=mock_supabase,
        )
        assert result["withdrawn_count"] == 1
        # Supabase update should have been called with linkedin_reconnect_cooldown_until
        call_args = mock_supabase.table.return_value.update.call_args
        update_data = call_args[0][0]
        assert "linkedin_reconnect_cooldown_until" in update_data
        assert result["cooldown_enforced_days"] == 21

    def test_cooldown_enforced_days_is_21(self):
        invs = [_stale_inv(days_pending=30)]
        result = LinkedInInvitationManager.withdraw_stale_invitations(
            account={"id": "acc-1"},
            mock_invitations=invs,
        )
        assert result["cooldown_enforced_days"] == 21


class TestIsAccountInCooldown:
    """Layer 0: is_account_in_cooldown logic."""

    def test_future_cooldown_until_is_in_cooldown(self):
        account = {"cooldown_until": _future_iso(days=1)}
        in_cd, reason = LinkedInInvitationManager.is_account_in_cooldown(account)
        assert in_cd is True

    def test_past_cooldown_until_not_in_cooldown(self):
        account = {"cooldown_until": _past_iso(days=1)}
        in_cd, _ = LinkedInInvitationManager.is_account_in_cooldown(account)
        assert in_cd is False

    def test_boolean_is_in_cooldown_true(self):
        account = {"is_in_cooldown": True}
        in_cd, _ = LinkedInInvitationManager.is_account_in_cooldown(account)
        assert in_cd is True

    def test_no_cooldown_fields_false(self):
        account = {"id": "acc-clean"}
        in_cd, _ = LinkedInInvitationManager.is_account_in_cooldown(account)
        assert in_cd is False


class TestCheck3WeekResendCooldown:
    """Layer 0: check_linkedin_3week_resend_cooldown."""

    def test_future_cooldown_active(self):
        lead = {"linkedin_reconnect_cooldown_until": _future_iso(days=10)}
        in_cd, msg = LinkedInInvitationManager.check_linkedin_3week_resend_cooldown(lead)
        assert in_cd is True
        assert "21-day" in msg

    def test_past_cooldown_not_active(self):
        lead = {"linkedin_reconnect_cooldown_until": _past_iso(days=1)}
        in_cd, msg = LinkedInInvitationManager.check_linkedin_3week_resend_cooldown(lead)
        assert in_cd is False


class TestTriggerAccountCooldown:
    """Layer 0: trigger_account_cooldown."""

    def test_returns_cooldown_until_and_reason(self):
        result = LinkedInInvitationManager.trigger_account_cooldown(
            account_id="acc-1",
            reason=CooldownReason.HIGH_PENDING_CEILING,
            duration_hours=48,
        )
        assert result["in_cooldown"] is True
        assert "cooldown_until" in result
        assert result["reason"] == CooldownReason.HIGH_PENDING_CEILING.value
        assert result["duration_hours"] == 48

    def test_duration_hours_clamped_below_1_becomes_1(self):
        result = LinkedInInvitationManager.trigger_account_cooldown(
            account_id="acc-1", reason="test_reason", duration_hours=0
        )
        assert result["duration_hours"] == 1

    def test_duration_hours_clamped_above_720_becomes_720(self):
        result = LinkedInInvitationManager.trigger_account_cooldown(
            account_id="acc-1", reason="test_reason", duration_hours=9999
        )
        assert result["duration_hours"] == 720


# ===========================================================================
# LAYER 1 — Environmental Failures (15+ tests)
# ===========================================================================


class TestWithdrawStaleInvitationsLayer1:
    """Layer 1: Environmental edge cases for withdraw_stale_invitations."""

    def test_batch_limit_clamped_below_1_becomes_1(self):
        invs = [_stale_inv(days_pending=30) for _ in range(5)]
        result = LinkedInInvitationManager.withdraw_stale_invitations(
            account={"id": "acc-1"},
            batch_limit=0,
            mock_invitations=invs,
        )
        assert result["withdrawn_count"] == 1

    def test_batch_limit_clamped_above_50_becomes_50(self):
        invs = [_stale_inv(lead_id=f"l{i}", days_pending=30) for i in range(100)]
        result = LinkedInInvitationManager.withdraw_stale_invitations(
            account={"id": "acc-1"},
            batch_limit=200,
            mock_invitations=invs,
        )
        assert result["withdrawn_count"] == 50

    def test_zero_pending_invitations_returns_empty_withdrawn(self):
        result = LinkedInInvitationManager.withdraw_stale_invitations(
            account={"id": "acc-1"},
            mock_invitations=[],
        )
        assert result["withdrawn_count"] == 0
        assert result["withdrawn_items"] == []

    def test_supabase_failure_does_not_crash_returns_partial(self):
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.update.return_value.eq.return_value.execute.side_effect = Exception(
            "DB down"
        )
        invs = [_stale_inv(lead_id="l1", days_pending=30), _stale_inv(lead_id="l2", days_pending=30)]
        result = LinkedInInvitationManager.withdraw_stale_invitations(
            account={"id": "acc-1"},
            mock_invitations=invs,
            supabase=mock_supabase,
        )
        # Should still report withdrawals even if DB update failed
        assert result["withdrawn_count"] == 2

    def test_batch_limit_10_from_50_stale_withdraws_only_10(self):
        invs = [_stale_inv(lead_id=f"l{i}", days_pending=30) for i in range(50)]
        result = LinkedInInvitationManager.withdraw_stale_invitations(
            account={"id": "acc-1"},
            batch_limit=10,
            mock_invitations=invs,
        )
        assert result["withdrawn_count"] == 10


class TestTriggerAccountCooldownLayer1:
    """Layer 1: Environmental failures in trigger_account_cooldown."""

    def test_supabase_failure_gracefully_handled(self):
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.update.return_value.eq.return_value.execute.side_effect = Exception(
            "Supabase unavailable"
        )
        # Should NOT raise, still return result
        result = LinkedInInvitationManager.trigger_account_cooldown(
            account_id="acc-1",
            reason=CooldownReason.CAPTCHA_CHALLENGE,
            duration_hours=24,
            supabase=mock_supabase,
        )
        assert result["in_cooldown"] is True
        assert result["account_id"] == "acc-1"

    def test_none_duration_uses_default_48(self):
        result = LinkedInInvitationManager.trigger_account_cooldown(
            account_id="acc-1", reason="test", duration_hours=None
        )
        assert result["duration_hours"] == 48

    def test_string_reason_accepted(self):
        result = LinkedInInvitationManager.trigger_account_cooldown(
            account_id="acc-1", reason="CUSTOM_REASON", duration_hours=12
        )
        assert result["reason"] == "CUSTOM_REASON"


class TestIsAccountInCooldownLayer1:
    """Layer 1: Environmental edge cases for is_account_in_cooldown."""

    def test_malformed_cooldown_until_string_safe_false(self):
        account = {"cooldown_until": "not-a-date"}
        in_cd, _ = LinkedInInvitationManager.is_account_in_cooldown(account)
        assert in_cd is False

    def test_empty_string_cooldown_until_falls_through(self):
        account = {"cooldown_until": ""}
        in_cd, _ = LinkedInInvitationManager.is_account_in_cooldown(account)
        assert in_cd is False

    def test_non_dict_account_returns_false(self):
        in_cd, _ = LinkedInInvitationManager.is_account_in_cooldown("not-a-dict")
        assert in_cd is False

    def test_none_account_returns_false(self):
        in_cd, _ = LinkedInInvitationManager.is_account_in_cooldown(None)
        assert in_cd is False


class TestCheck3WeekCooldownLayer1:
    """Layer 1: Environmental edge cases for check_linkedin_3week_resend_cooldown."""

    def test_malformed_date_string_safe_false(self):
        lead = {"linkedin_reconnect_cooldown_until": "not-a-valid-date"}
        in_cd, _ = LinkedInInvitationManager.check_linkedin_3week_resend_cooldown(lead)
        assert in_cd is False

    def test_lead_without_cooldown_field_false(self):
        lead = {"id": "lead-x", "name": "Jane Doe"}
        in_cd, msg = LinkedInInvitationManager.check_linkedin_3week_resend_cooldown(lead)
        assert in_cd is False
        assert msg is None

    def test_empty_lead_dict_false(self):
        in_cd, _ = LinkedInInvitationManager.check_linkedin_3week_resend_cooldown({})
        assert in_cd is False

    def test_non_dict_lead_safe_false(self):
        in_cd, _ = LinkedInInvitationManager.check_linkedin_3week_resend_cooldown("bad-input")
        assert in_cd is False

    def test_reconnect_cooldown_until_alternate_key(self):
        lead = {"reconnect_cooldown_until": _future_iso(days=5)}
        in_cd, _ = LinkedInInvitationManager.check_linkedin_3week_resend_cooldown(lead)
        assert in_cd is True

    def test_cooldown_until_fallback_key(self):
        lead = {"cooldown_until": _future_iso(days=5)}
        in_cd, _ = LinkedInInvitationManager.check_linkedin_3week_resend_cooldown(lead)
        assert in_cd is True


class TestEvaluateHealthLayer1:
    """Layer 1: Environmental edge cases for evaluate_account_connection_health."""

    def test_none_pending_count_safe_default_optimal(self):
        res = LinkedInInvitationManager.evaluate_account_connection_health(None)
        assert res["risk_level"] == AccountHealthRisk.OPTIMAL.value
        assert res["pending_count"] == 0

    def test_negative_pending_clamped_to_zero(self):
        res = LinkedInInvitationManager.evaluate_account_connection_health(-50)
        assert res["pending_count"] == 0

    def test_string_pending_safe_zero(self):
        res = LinkedInInvitationManager.evaluate_account_connection_health("bad")
        assert res["pending_count"] == 0


# ===========================================================================
# LAYER 2 — Human Paranoia & Security (10+ tests)
# ===========================================================================


class TestExecutorConnectionSafety:
    """Layer 2: EleInNodeExecutor handle_connection_request safety guards."""

    def _make_executor(self, supabase=None):
        from campaigns.backend.services.elein_executor import EleInNodeExecutor

        mock_worker = MagicMock()
        mock_worker.account_id = "acc-test"
        mock_worker.selected_account = None
        mock_worker.account = None
        mock_worker.send_connection_request.return_value = {
            "status": "success",
            "branch": "THEN",
        }
        return EleInNodeExecutor(
            linkedin_worker=mock_worker,
            supabase=supabase,
            workspace_id="ws-test",
        )

    def test_account_in_cooldown_returns_deferred(self):
        from campaigns.backend.services.elein_executor import EleInNodeExecutor

        executor = self._make_executor()
        with patch(
            "integrations.backend.services.linkedin_invitation_manager.is_account_in_cooldown",
            return_value=(True, "HIGH_PENDING_CEILING"),
        ):
            data = {
                "selected_account": {
                    "id": "acc-1",
                    "is_in_cooldown": True,
                    "cooldown_until": _future_iso(1),
                },
                "note_strategy": "Fixed note",
                "note": "Hi",
            }
            result = executor.handle_connection_request(data, "https://linkedin.com/in/alice")
        assert result["status"] == "deferred"
        assert result["reason"] == "account_in_cooldown"

    def test_lead_in_3week_cooldown_returns_skipped(self):
        executor = self._make_executor()
        future_cd = _future_iso(days=10)
        with patch(
            "integrations.backend.services.linkedin_invitation_manager.is_account_in_cooldown",
            return_value=(False, None),
        ):
            with patch(
                "integrations.backend.services.linkedin_invitation_manager.check_linkedin_3week_resend_cooldown",
                return_value=(True, f"Recipient is in LinkedIn 21-day anti-resend cooldown until {future_cd}."),
            ):
                data = {
                    "selected_account": {
                        "id": "acc-2",
                        "is_in_cooldown": False,
                        "cooldown_until": _past_iso(1),
                    },
                    "lead": {
                        "id": "lead-5",
                        "linkedin_reconnect_cooldown_until": future_cd,
                    },
                    "note_strategy": "Fixed note",
                    "note": "Hi",
                }
                result = executor.handle_connection_request(data, "https://linkedin.com/in/bob")
        assert result["status"] == "skipped"
        assert result["reason"] == "linkedin_3week_withdrawal_cooldown"

    def test_no_cooldown_returns_none_from_safety_guard(self):
        executor = self._make_executor()
        with patch(
            "integrations.backend.services.linkedin_invitation_manager.is_account_in_cooldown",
            return_value=(False, None),
        ), patch(
            "integrations.backend.services.linkedin_invitation_manager.check_linkedin_3week_resend_cooldown",
            return_value=(False, None),
        ):
            guard = executor._check_connection_safety_guards(
                {
                    "selected_account": {"id": "acc-3", "is_in_cooldown": False, "cooldown_until": _past_iso(1)},
                    "lead": {"id": "lead-6", "linkedin_reconnect_cooldown_until": _past_iso(1)},
                },
                "https://linkedin.com/in/charlie",
            )
        assert guard is None


class TestRouterEndpoints:
    """Layer 2: FastAPI router endpoint contract tests."""

    @pytest.fixture(autouse=True)
    def setup_client(self):
        from fastapi.testclient import TestClient
        from campaigns.backend.routers.elein import router
        from core.backend.api.auth_dep import get_current_workspace, get_service_client
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(router, prefix="/api/elein")

        self.mock_db = MagicMock()
        # Default: account exists in workspace
        self.mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "acc-test"}]
        )
        self.mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()

        mock_db = self.mock_db

        app.dependency_overrides[get_current_workspace] = lambda: "ws-test"
        app.dependency_overrides[get_service_client] = lambda: mock_db

        self.client = TestClient(app, raise_server_exceptions=False)

    def test_audit_returns_account_health(self):
        resp = self.client.post(
            "/api/elein/linkedin/pending-invitations/audit",
            json={"account_id": "acc-test", "pending_count": 150},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "account_health" in data
        assert data["account_health"]["risk_level"] == AccountHealthRisk.OPTIMAL.value

    def test_audit_returns_stale_count(self):
        stale_inv = {"id": "inv-1", "days_pending": 30, "status": "PENDING"}
        resp = self.client.post(
            "/api/elein/linkedin/pending-invitations/audit",
            json={"account_id": "acc-test", "pending_invitations": [stale_inv]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["stale_count"] >= 1

    def test_withdraw_stale_returns_withdrawal_result(self):
        stale_inv = {"id": "inv-2", "lead_id": "lead-2", "days_pending": 30, "status": "PENDING"}
        resp = self.client.post(
            "/api/elein/linkedin/pending-invitations/withdraw-stale",
            json={
                "account_id": "acc-test",
                "max_age_days": 21,
                "batch_limit": 25,
                "pending_invitations": [stale_inv],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "withdrawn_count" in data
        assert data["withdrawn_count"] == 1
        assert data["cooldown_enforced_days"] == 21

    def test_set_cooldown_returns_cooldown_result(self):
        resp = self.client.post(
            "/api/elein/linkedin/account-cooldown/set",
            json={"account_id": "acc-test", "reason": "HIGH_PENDING_CEILING", "duration_hours": 48},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["in_cooldown"] is True
        assert "cooldown_until" in data

    def test_cooldown_status_returns_in_cooldown_field(self):
        resp = self.client.post(
            "/api/elein/linkedin/account-cooldown/status",
            json={
                "account_id": "acc-test",
                "cooldown_until": _future_iso(days=1),
                "is_in_cooldown": True,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "in_cooldown" in data

    def test_audit_returns_404_when_account_not_in_workspace(self):
        # Override to simulate account not found
        self.mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[]
        )
        resp = self.client.post(
            "/api/elein/linkedin/pending-invitations/audit",
            json={"account_id": "acc-unknown", "pending_count": 0},
        )
        assert resp.status_code == 404

    def test_withdraw_returns_404_when_account_not_in_workspace(self):
        self.mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[]
        )
        resp = self.client.post(
            "/api/elein/linkedin/pending-invitations/withdraw-stale",
            json={"account_id": "acc-unknown"},
        )
        assert resp.status_code == 404

    def test_set_cooldown_returns_404_when_account_not_in_workspace(self):
        self.mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[]
        )
        resp = self.client.post(
            "/api/elein/linkedin/account-cooldown/set",
            json={"account_id": "acc-unknown"},
        )
        assert resp.status_code == 404

    def test_audit_returns_422_for_empty_account_id(self):
        resp = self.client.post(
            "/api/elein/linkedin/pending-invitations/audit",
            json={"account_id": ""},
        )
        assert resp.status_code == 422

    def test_withdraw_returns_422_for_empty_account_id(self):
        resp = self.client.post(
            "/api/elein/linkedin/pending-invitations/withdraw-stale",
            json={"account_id": ""},
        )
        assert resp.status_code == 422

    def test_set_cooldown_returns_422_for_empty_account_id(self):
        resp = self.client.post(
            "/api/elein/linkedin/account-cooldown/set",
            json={"account_id": ""},
        )
        assert resp.status_code == 422
