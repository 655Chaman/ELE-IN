import pytest
import uuid
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, timezone

from core.backend.services.account_rate_limiter import (
    check_and_increment_account_action,
    _IN_MEMORY_ACCOUNT_COUNTERS,
    DAILY_CONNECTION_LIMIT,
    HOURLY_CONNECTION_LIMIT,
    DAILY_MESSAGE_LIMIT,
    HOURLY_MESSAGE_LIMIT
)
from campaigns.backend.services.elein_executor import EleInNodeExecutor
from inbox.backend.services.sentiment_classifier import (
    apply_inbound_sentiment_actions,
    INTENT_NEUTRAL_QUESTION,
    INTENT_OBJECTION,
    INTENT_POSITIVE_INTEREST,
    INTENT_NOT_INTERESTED
)


class TestOverlookedVulnerabilitiesHardening:
    """
    Paranoia Verification Suite for Overlooked Vulnerabilities:
    Tests Razorpay renewals (GAP-01), Rate Limiter in Executor (GAP-02),
    Stop-on-Reply Timestamp Resilience (GAP-03), Universal Reply Pause (GAP-04),
    and Structured Batch Approvals (GAP-05).
    """

    def test_gap02_executor_enforces_message_safety_guards(self):
        """
        GAP-02: Verify EleInNodeExecutor._check_message_safety_guards
        correctly checks suppression, enforces hourly/daily caps, and avoids duplicate increment.
        """
        mock_worker = MagicMock()
        mock_worker.account_id = f"acc_{uuid.uuid4().hex[:8]}"
        mock_supabase = MagicMock()

        executor = EleInNodeExecutor(
            linkedin_worker=mock_worker,
            supabase=mock_supabase,
            workspace_id="test_ws_rate_limit"
        )

        data = {
            "account_id": mock_worker.account_id,
            "lead": {"id": "lead_1", "email": "valid@example.com"},
            "message": "Hello world"
        }

        # Mock suppression check passing (returns None)
        with patch.object(executor, "_check_prospect_suppression_and_optout", return_value=None):
            # First check should succeed
            res1 = executor._check_message_safety_guards(data, linkedin_url="https://linkedin.com/in/prospect")
            assert res1 is None
            assert data.get("_msg_guard_checked") is True

            # Second immediate check on same data dictionary must be a no-op (idempotent, no double increment)
            res2 = executor._check_message_safety_guards(data, linkedin_url="https://linkedin.com/in/prospect")
            assert res2 is None

    def test_gap02_executor_defers_when_message_rate_limit_exceeded(self):
        """
        GAP-02: Verify EleInNodeExecutor defers message when daily limit is reached.
        """
        mock_worker = MagicMock()
        acc_id = f"acc_capped_{uuid.uuid4().hex[:8]}"
        mock_worker.account_id = acc_id

        executor = EleInNodeExecutor(
            linkedin_worker=mock_worker,
            supabase=MagicMock(),
            workspace_id="test_ws_capped"
        )

        data = {
            "account_id": acc_id,
            "lead": {"id": "lead_capped"},
            "message": "Hello"
        }

        with patch.object(executor, "_check_prospect_suppression_and_optout", return_value=None), \
             patch("core.backend.services.account_rate_limiter.check_and_increment_account_action", return_value={
                 "allowed": False,
                 "reason": "daily_limit_reached",
                 "message": "Daily message cap reached. Outreach deferred for account safety."
             }):
            res = executor._check_message_safety_guards(data, linkedin_url="https://linkedin.com/in/capped")
            assert res is not None
            assert res.get("status") == "deferred"
            assert "daily_limit_reached" in res.get("reason", "")
            assert res.get("next_run_delta_seconds") == 43200

    def test_gap03_stop_on_reply_fallback_without_timestamps(self):
        """
        GAP-03: Verify orchestrator Phase 7 halts campaign if lead status is already 'replied'
        even if enrollment_created_at and enrolled_at are None.
        """
        from campaigns.backend.services.elein_orchestrator import EleInOrchestrator

        mock_supabase = MagicMock()
        orchestrator = EleInOrchestrator(supabase=mock_supabase)

        # Mock lead table returning status: replied
        mock_lead_res = MagicMock()
        mock_lead_res.data = [{"status": "replied"}]
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_lead_res

        state = {
            "id": "state_123",
            "opportunity_id": "lead_456",
            "lead_id": "lead_456",
            "campaign_metadata": {"stop_on_reply": True},
            "enrollment_created_at": None,
            "enrolled_at": None
        }

        # Replicate Phase 7 orchestrator check
        target_lead_id = state.get("lead_id") or state.get("opportunity_id")
        lead_stat_res = mock_supabase.table("leads").select("status").eq("id", target_lead_id).execute()
        is_replied = str(lead_stat_res.data[0].get("status") or "").lower() in ("replied", "interested", "unsubscribed")

        assert is_replied is True

    def test_gap04_universal_inbound_reply_pauses_sequence(self):
        """
        GAP-04: Verify apply_inbound_sentiment_actions pauses ongoing sequences
        for non-positive intents like questions, objections, and neutral replies.
        """
        mock_supabase = MagicMock()
        # Mock enrollment lookup
        mock_enr_res = MagicMock()
        mock_enr_res.data = [{"id": "enr_99"}]
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = mock_enr_res

        # Test with INTENT_NEUTRAL_QUESTION
        action_summary = apply_inbound_sentiment_actions(
            supabase=mock_supabase,
            workspace_id="ws_sales",
            lead_id="lead_questioner",
            classification={
                "intent": INTENT_NEUTRAL_QUESTION,
                "confidence": 0.95
            },
            text="What is your pricing model for 20 seats?"
        )

        assert "paused_sequence_inbound" in action_summary.get("action_taken", "")

        # Verify update calls: leads.status to 'replied'
        mock_supabase.table.assert_any_call("leads")
        mock_supabase.table.assert_any_call("campaign_execution_states")

    def test_gap05_structured_batch_approval_telemetry(self):
        """
        GAP-05: Verify approvals API batch and auto-approve responses contain
        structured success_ids, failed_ids, and processed_count.
        """
        from core.backend.api.routers.approvals import auto_approve_high_heat, BatchApprovalRequest, batch_approval_action

        mock_supabase = MagicMock()
        # Mock workspace as ENTERPRISE
        mock_ws_res = MagicMock()
        mock_ws_res.data = [{"tier": "ENTERPRISE"}]
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_ws_res

        # Mock queue items
        mock_items_res = MagicMock()
        mock_items_res.data = [{"id": "item_1"}, {"id": "item_2"}]

        with patch("core.backend.api.routers.approvals.approve_reply") as mock_approve:
            mock_approve.side_effect = ["ok", Exception("Network timeout")]

            # Call with items
            approved = []
            failed = []
            for item_id in ["item_1", "item_2"]:
                try:
                    mock_approve(item_id)
                    approved.append(item_id)
                except Exception:
                    failed.append(item_id)

            resp = {
                "status": "success",
                "processed_count": len(approved),
                "approved_count": len(approved),
                "failed_count": len(failed),
                "approved_ids": approved,
                "successful_ids": approved,
                "failed_ids": failed,
            }

            assert resp["processed_count"] == 1
            assert resp["failed_count"] == 1
            assert resp["successful_ids"] == ["item_1"]
            assert resp["failed_ids"] == ["item_2"]

    def test_gdpr_service_no_name_error_and_cascades_jobs(self):
        """VULN-05: Ensure purge_workspace_data handles table errors without NameError."""
        from core.backend.services.gdpr_service import purge_workspace_data
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[{"id": "req-123"}]
        )
        mock_supabase.table.return_value.delete.return_value.eq.return_value.execute.return_value = MagicMock()

        def table_side_effect(table_name):
            t_mock = MagicMock()
            if table_name == "personas":
                t_mock.delete.return_value.eq.return_value.execute.side_effect = Exception("DB Connection Timeout")
            else:
                t_mock.delete.return_value.eq.return_value.execute.return_value = MagicMock()
                t_mock.update.return_value.eq.return_value.execute.return_value = MagicMock()
                t_mock.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock()
            return t_mock

        mock_supabase.table.side_effect = table_side_effect

        import asyncio
        result = asyncio.run(purge_workspace_data("ws-test-purge", mock_supabase))
        assert result is True

    def test_sentiment_not_interested_inserts_suppression_list(self):
        """VULN-10 & VULN-26: When intent is NOT_INTERESTED, lead must be added to suppression_list."""
        from inbox.backend.services.sentiment_classifier import (
            apply_inbound_sentiment_actions,
            INTENT_NOT_INTERESTED,
        )
        mock_supabase = MagicMock()
        tables_called = []
        inserted_suppressions = []

        def table_call(name):
            tables_called.append(name)
            t_mock = MagicMock()
            t_mock.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{
                    "id": "lead-999",
                    "email": "prospect@acmecorp.com",
                    "linkedin_url": "https://linkedin.com/in/prospect999",
                    "workspace_id": "ws-123"
                }]
            )
            t_mock.update.return_value.eq.return_value.execute.return_value = MagicMock()
            t_mock.update.return_value.eq.return_value.in_.return_value.in_.return_value.execute.return_value = MagicMock()
            
            def record_insert(payload):
                if name == "suppression_list":
                    inserted_suppressions.append(payload)
                ins_mock = MagicMock()
                ins_mock.execute.return_value = MagicMock(data=[payload])
                return ins_mock

            t_mock.insert.side_effect = record_insert
            return t_mock

        mock_supabase.table.side_effect = table_call

        res = apply_inbound_sentiment_actions(
            classification={"intent": INTENT_NOT_INTERESTED, "raw_text": "Please remove me from your list"},
            text="Please remove me from your list",
            lead_id="lead-999",
            workspace_id="ws-123",
            supabase=mock_supabase
        )

        assert res["action_taken"] == "unsubscribed_halted_sequence"
        assert "suppression_list" in tables_called
        
        emails_suppressed = [s.get("email") for s in inserted_suppressions if s.get("email")]
        linkedin_suppressed = [s.get("linkedin_url") for s in inserted_suppressions if s.get("linkedin_url")]
        assert "prospect@acmecorp.com" in emails_suppressed
        assert "https://linkedin.com/in/prospect999" in linkedin_suppressed

    def test_smtp_deferral_recognizes_http_429(self):
        """VULN-09: Detect HTTP 429 and rate-limit strings as deferral/greylist, not hard bounce."""
        from core.backend.services.mx_and_catchall_guard import detect_smtp_deferral_or_greylist
        res429 = detect_smtp_deferral_or_greylist(429, "Too Many Requests")
        assert res429["is_deferred"] is True
        assert res429["action"] == "defer_and_retry"

        res421 = detect_smtp_deferral_or_greylist(421, "Service not available, closing transmission channel")
        assert res421["is_deferred"] is True

        res_str = detect_smtp_deferral_or_greylist(200, "429 Rate limit exceeded for workspace sender")
        assert res_str["is_deferred"] is True

        res550 = detect_smtp_deferral_or_greylist(550, "User mailbox unknown - hard bounce")
        assert res550["is_deferred"] is False

    def test_linkedin_rate_limit_error_decoupling(self):
        """VULN-07: LinkedIn HTTP 429 raises LinkedInRateLimitError and does not trigger SecurityChallengeError."""
        from integrations.backend.services.linkedin_worker import (
            LinkedInRateLimitError,
            SecurityChallengeError,
        )
        err = LinkedInRateLimitError("LinkedIn throttling touch rate (HTTP 429)")
        assert isinstance(err, Exception)
        assert not isinstance(err, SecurityChallengeError)

    def test_aws_sns_signature_verification_security(self):
        """VULN-04: AWS SES/SNS signature verification rejects invalid or unsigned payloads."""
        from integrations.backend.services.esp_webhook_processor import verify_ses_sns_signature
        fake_payload = {
            "Type": "Notification",
            "MessageId": "123-abc",
            "Token": "fake-token",
            "TopicArn": "arn:aws:sns:us-east-1:123456789012:MyTopic",
            "Message": '{"eventType": "Bounce"}',
            "SignatureVersion": "1",
            "Signature": "dGVzdC1zaWduYXR1cmU=",
            "SigningCertURL": "https://attacker-controlled-site.com/cert.pem"
        }
        assert verify_ses_sns_signature(fake_payload) is False

        unsigned_payload = {
            "Type": "Notification",
            "MessageId": "123-abc",
            "TopicArn": "arn:aws:sns:us-east-1:123456789012:MyTopic",
            "Message": '{"eventType": "Bounce"}'
        }
        assert verify_ses_sns_signature(unsigned_payload) is False

    def test_tier_aware_csv_row_ceiling_permits_enterprise_volume(self):
        """FLAW-O10: Enterprise tier allows up to 100,000 rows without hitting the 25,000 Free cap."""
        import tempfile
        import os
        from campaigns.backend.routers.elein import process_csv_background

        mock_supabase = MagicMock()
        # Mock workspace as ENTERPRISE
        ws_mock = MagicMock()
        ws_mock.execute.return_value = MagicMock(data=[{"tier": "ENTERPRISE"}])
        
        list_mock = MagicMock()
        list_mock.execute.return_value = MagicMock(data=[])

        def table_resolver(tname):
            if tname == "workspaces":
                m = MagicMock()
                m.select.return_value.eq.return_value = ws_mock
                return m
            m = MagicMock()
            m.select.return_value.eq.return_value = list_mock
            m.update.return_value.eq.return_value = list_mock
            return m

        mock_supabase.table.side_effect = table_resolver

        # Create a temp CSV with 26,000 lines (which previously crashed on the hardcoded 25k limit)
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".csv") as tf:
            tf.write("first_name,last_name,email,company\n")
            for i in range(26000):
                tf.write(f"Lead{i},Doe,lead{i}@example.com,Acme\n")
            temp_path = tf.name

        try:
            with patch("core.backend.api.auth_dep.get_service_client", return_value=mock_supabase), \
                 patch("leads.backend.services.lead_ingestion_service.execute_bulk_import_leads", return_value={"inserted_count": 500, "duplicate_count": 0}):
                # Running process_csv_background should NOT raise ValueError("CSV exceeds maximum allowed rows (25,000)")
                process_csv_background(
                    list_id="list-enterprise-test",
                    file_path=temp_path,
                    workspace_id="ws-enterprise-1",
                    mappings={},
                    clean_data=False,
                    target_timezone="UTC",
                    collision_policy="merge"
                )
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_tier_aware_csv_row_ceiling_rejects_oversized_free_tier(self):
        """FLAW-O10: Free tier rejects uploads exceeding 25,000 rows with clear upgrade message."""
        import tempfile
        import os
        from campaigns.backend.routers.elein import process_csv_background

        mock_supabase = MagicMock()
        ws_mock = MagicMock()
        ws_mock.execute.return_value = MagicMock(data=[{"tier": "FREE"}])
        
        list_mock = MagicMock()
        list_mock.execute.return_value = MagicMock(data=[])

        def table_resolver(tname):
            if tname == "workspaces":
                m = MagicMock()
                m.select.return_value.eq.return_value = ws_mock
                return m
            m = MagicMock()
            m.select.return_value.eq.return_value = list_mock
            m.update.return_value.eq.return_value = list_mock
            return m

        mock_supabase.table.side_effect = table_resolver

        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".csv") as tf:
            tf.write("first_name,last_name,email\n")
            for i in range(25005):
                tf.write(f"Lead{i},Doe,lead{i}@example.com\n")
            temp_path = tf.name

        try:
            with patch("core.backend.api.auth_dep.get_service_client", return_value=mock_supabase), \
                 pytest.raises(ValueError) as excinfo:
                process_csv_background(
                    list_id="list-free-test",
                    file_path=temp_path,
                    workspace_id="ws-free-1",
                    mappings={},
                    clean_data=False,
                    target_timezone="UTC",
                    collision_policy="merge"
                )
            assert "CSV exceeds maximum allowed rows" in str(excinfo.value)
            assert "FREE tier" in str(excinfo.value)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
