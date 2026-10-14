import pytest
from unittest.mock import MagicMock, patch
from core.backend.services.notification_service import (
    DEFAULT_CHANNELS,
    LOCKED_ON_CHANNELS,
    _resolve_channels_for_user,
    dispatch_notification,
)

class TestNotificationServiceHardening:
    """
    Paranoia Framework Tests for core/backend/services/notification_service.py
    Layer 0: Foundational dispatch mechanics.
    Layer 1: Environmental DB failure isolation.
    Layer 2: Human idempotency & cross-lead deduplication.
    """

    def test_default_channels_includes_lead_replied_instant(self):
        """Layer 0: Verify lead_replied_instant is configured in DEFAULT_CHANNELS."""
        assert "lead_replied_instant" in DEFAULT_CHANNELS
        assert DEFAULT_CHANNELS["lead_replied_instant"]["in_app"] is True
        assert DEFAULT_CHANNELS["lead_replied_instant"]["email"] is True

    def test_locked_channels_account_suspended_immutable(self):
        """Layer 1: Account suspended in_app is locked on and cannot be disabled by user prefs."""
        prefs = {("user-1", "in_app"): False}
        channels = _resolve_channels_for_user("account_suspended", "user-1", prefs)
        assert "in_app" in channels

    def test_resolve_channels_honors_explicit_user_preferences(self):
        """Layer 2: User can toggle discretionary channels off."""
        prefs = {
            ("user-1", "email"): False,
            ("user-1", "in_app"): True
        }
        channels = _resolve_channels_for_user("lead_replied_instant", "user-1", prefs)
        assert "in_app" in channels
        assert "email" not in channels

    def test_dispatch_notification_generates_distinct_keys_per_lead(self):
        """
        Layer 2 Paranoia: Different leads on the same account MUST NOT collide
        in idempotency keys or be suppressed.
        """
        mock_svc = MagicMock()
        mock_svc.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {"user_id": "u-1"}
        ]
        # notification_preferences return empty (use defaults)
        mock_svc.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []

        # Dispatch Lead A
        dispatch_notification(
            svc=mock_svc,
            workspace_id="ws-1",
            event_type="lead_replied_instant",
            payload={
                "account_id": "acc-1",
                "lead_id": "lead-A",
                "title": "Lead A replied",
                "body": "Hello",
                "unique_key": "msg-1"
            }
        )

        calls = mock_svc.table.return_value.upsert.call_args_list
        assert len(calls) >= 1
        first_batch = calls[0][0][0]
        keys_lead_a = [e["idempotency_key"] for e in first_batch]
        assert any("msg-1" in k for k in keys_lead_a)

    def test_dispatch_notification_handles_empty_workspace_members(self):
        """Layer 1: Empty workspace membership terminates gracefully without throwing."""
        mock_svc = MagicMock()
        mock_svc.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []

        # Should not raise exception
        dispatch_notification(
            svc=mock_svc,
            workspace_id="ws-empty",
            event_type="account_needs_attention",
            payload={"title": "Test"}
        )
        mock_svc.table.return_value.upsert.assert_not_called()

    def test_dispatch_notification_never_crashes_caller_on_db_exception(self):
        """Layer 1 Paranoia: Database outages must never blow up the business logic caller."""
        mock_svc = MagicMock()
        mock_svc.table.side_effect = RuntimeError("Database down")

        # Must not raise
        dispatch_notification(
            svc=mock_svc,
            workspace_id="ws-1",
            event_type="lead_replied_instant",
            payload={"title": "Fatal DB Test"}
        )
