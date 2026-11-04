import os
import sys
import time
import uuid
import hmac
import hashlib
import json
import unittest
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers
from io import BytesIO

from campaigns.backend.routers.elein import (
    _sanitize_csv_formula_val,
    _mask_export_email,
    _mask_export_phone,
    api_export_workspace_leads,
    upload_campaign_attachment,
    upload_csv,
    _activate_campaign_core
)
from campaigns.backend.services.elein_executor import EleInNodeExecutor, Branch
from core.backend.api.routers.billing import (
    verify_stripe_signature,
    cancel_subscription,
    reactivate_subscription,
    CancelSubscriptionRequest
)
from inbox.backend.routers.inbox import (
    send_inbox_reply,
    SendReplyPayload
)
from inbox.backend.services.inbox_lock_service import (
    acquire_thread_reply_lease,
    release_thread_reply_lease
)


# ==============================================================================
# Vector 1: Lead Export Security & Privacy (CWE-1236 & Cross-Tenant Data Leaks)
# ==============================================================================
class TestVector1LeadExportSecurityAndPrivacy(unittest.TestCase):

    def test_sanitize_csv_formula_val_neutralizes_injection_operators(self):
        """Layer 0 & 2: Formulas starting with =, +, -, @, \\t, \\r are safely prefixed with single quote."""
        self.assertEqual(_sanitize_csv_formula_val("=cmd|' /C calc'!A0"), "'=cmd|' /C calc'!A0")
        self.assertEqual(_sanitize_csv_formula_val("+123456"), "'+123456")
        self.assertEqual(_sanitize_csv_formula_val("-SUM(A1:B2)"), "'-SUM(A1:B2)")
        self.assertEqual(_sanitize_csv_formula_val("@SUM(1,2)"), "'@SUM(1,2)")
        self.assertEqual(_sanitize_csv_formula_val("\tmalicious_tab"), "'\tmalicious_tab")
        self.assertEqual(_sanitize_csv_formula_val("\rmalicious_cr"), "'\rmalicious_cr")

        # Safe values must not be modified
        self.assertEqual(_sanitize_csv_formula_val("Alice Johnson"), "Alice Johnson")
        self.assertEqual(_sanitize_csv_formula_val("alice@example.com"), "alice@example.com")
        self.assertEqual(_sanitize_csv_formula_val(None), "")

        # Already quoted strings must not be double escaped
        self.assertEqual(_sanitize_csv_formula_val("''=safe"), "''=safe")

    def test_mask_export_email_and_phone(self):
        """Layer 1: Free tier privacy masking obscures contact info."""
        # Email masking
        self.assertEqual(_mask_export_email("john.doe@company.com"), "j***e@company.com")
        self.assertEqual(_mask_export_email("ab@company.com"), "a***@company.com")
        self.assertEqual(_mask_export_email("invalid-email"), "")

        # Phone masking
        self.assertEqual(_mask_export_phone("+1 (555) 123-4567"), "***-***-4567")
        self.assertEqual(_mask_export_phone("123"), "***")
        self.assertEqual(_mask_export_phone(None), "")

    def test_api_export_workspace_leads_rbac_denial_for_unauthorized_roles(self):
        """Layer 2: Analysts and unprivileged roles receive HTTP 403 on export attempt."""
        mock_req = MagicMock()
        mock_req.client.host = "127.0.0.1"
        mock_req.headers = {"user-agent": "test-agent"}

        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"role": "analyst"}]
        )

        with self.assertRaises(HTTPException) as ctx:
            api_export_workspace_leads(
                request=mock_req,
                list_id=None,
                workspace_id="ws_test_1",
                user_id="user_analyst_1",
                db=mock_db
            )
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("strictly prohibited from exporting leads", ctx.exception.detail)

    def test_api_export_workspace_leads_free_tier_masks_and_sanitizes(self):
        """Layer 1 & 2: Free tier export returns masked emails/phones and formula-sanitized values."""
        mock_req = MagicMock()
        mock_req.client.host = "127.0.0.1"
        mock_req.headers = {"user-agent": "test-agent"}

        mock_db = MagicMock()
        # Mock role query: caller is owner
        def mock_table(table_name):
            t = MagicMock()
            if table_name == "workspace_members":
                t.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[{"role": "owner"}]
                )
            elif table_name == "workspaces":
                # Free tier
                t.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=[{"tier": "FREE"}]
                )
            elif table_name == "leads":
                t.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=[
                        {
                            "id": "lead_1",
                            "first_name": "=cmd|'calc'!A0",
                            "last_name": "Smith",
                            "company": "+Acme Corp",
                            "title": "VP Sales",
                            "email": "sarah.smith@acme.com",
                            "linkedin_url": "https://linkedin.com/in/sarahsmith",
                            "status": "lead"
                        }
                    ]
                )
            return t

        mock_db.table.side_effect = mock_table

        res = api_export_workspace_leads(
            request=mock_req,
            list_id=None,
            workspace_id="ws_free_1",
            user_id="user_owner_1",
            db=mock_db
        )

        self.assertEqual(res["status"], "success")
        leads = res["leads"]
        self.assertEqual(len(leads), 1)
        lead = leads[0]

        # Email must be masked for Free tier
        self.assertEqual(lead["email"], "s***h@acme.com")
        # Formula injection characters must be escaped
        self.assertEqual(lead["first_name"], "'=cmd|'calc'!A0")
        self.assertEqual(lead["company"], "'+Acme Corp")


from starlette.datastructures import Headers


# ==============================================================================
# Vector 2: Campaign Attachment & Upload Verification (CWE-434)
# ==============================================================================
class TestVector2AttachmentAndUploadVerification(unittest.IsolatedAsyncioTestCase):

    async def test_upload_attachment_rejects_dangerous_executable_signatures(self):
        """Layer 0 & 1: Files with Windows PE, ELF, Shell script, or PHP headers are rejected immediately."""
        dangerous_payloads = [
            (b"MZ\x90\x00\x03\x00\x00\x00", "malicious.pdf", "application/pdf"),
            (b"\x7fELF\x02\x01\x01\x00", "exploit.png", "image/png"),
            (b"#!/bin/bash\nrm -rf /", "script.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
            (b"<?php system($_GET['cmd']); ?>", "webshell.pdf", "application/pdf"),
            (b"<script>alert(1)</script>", "xss.pdf", "application/pdf"),
        ]

        for payload, filename, content_type in dangerous_payloads:
            upload_file = UploadFile(
                filename=filename,
                file=BytesIO(payload),
                headers=Headers({"content-type": content_type})
            )

            with self.assertRaises(HTTPException) as ctx:
                await upload_campaign_attachment(
                    file=upload_file,
                    supabase=MagicMock(),
                    workspace_id="ws_1",
                    user_id="user_1"
                )
            self.assertEqual(ctx.exception.status_code, 400)
            self.assertIn("Malicious file signature detected", ctx.exception.detail)

    async def test_upload_attachment_validates_magic_bytes_for_allowed_formats(self):
        """Layer 0: Spoofed extensions with corrupt headers are rejected; valid magic bytes pass."""
        # Spoofed PDF (extension .pdf but missing %PDF-)
        fake_pdf = UploadFile(
            filename="document.pdf",
            file=BytesIO(b"Not a real PDF file content"),
            headers=Headers({"content-type": "application/pdf"})
        )
        with self.assertRaises(HTTPException) as ctx:
            await upload_campaign_attachment(
                file=fake_pdf,
                supabase=MagicMock(),
                workspace_id="ws_1",
                user_id="user_1"
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Magic header %PDF- missing", ctx.exception.detail)

        # Spoofed PNG
        fake_png = UploadFile(
            filename="image.png",
            file=BytesIO(b"Not a real PNG image content"),
            headers=Headers({"content-type": "image/png"})
        )
        with self.assertRaises(HTTPException) as ctx:
            await upload_campaign_attachment(
                file=fake_png,
                supabase=MagicMock(),
                workspace_id="ws_1",
                user_id="user_1"
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Invalid PNG image header", ctx.exception.detail)

    def test_upload_csv_rejects_binary_null_bytes(self):
        """Layer 1: CSV upload rejecting embedded null bytes to prevent binary smuggling."""
        binary_csv = UploadFile(
            filename="leads.csv",
            file=BytesIO(b"first_name,last_name,email\x00\xffbinarycontent"),
            headers=Headers({"content-type": "text/csv"})
        )
        with self.assertRaises(HTTPException) as ctx:
            upload_csv(
                file=binary_csv,
                list_name="Test Leads",
                workspace_id="ws_1",
                supabase=MagicMock(),
                user_id="user_1"
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Binary null bytes", ctx.exception.detail)


# ==============================================================================
# Vector 3: Mid-Sequence DNC & Suppression Guard
# ==============================================================================
class TestVector3MidSequenceDNCGuard(unittest.TestCase):

    def test_executor_execute_blocks_suppressed_prospect_mid_sequence(self):
        """Layer 0 & 1: execute performs real-time suppression check before dispatching action."""
        mock_supabase = MagicMock()
        executor = EleInNodeExecutor(
            worker=MagicMock(),
            supabase=mock_supabase,
            workspace_id="ws_tenant_1",
            campaign_id="camp_1"
        )

        # Mock suppression check to return suppressed=True
        with patch("leads.backend.services.suppression_service.check_lead_suppression") as mock_supp:
            mock_supp.return_value = {
                "suppressed": True,
                "reason": "prospect_unsubscribed",
                "matched_by": "email"
            }

            node_data = {
                "action": "send_email",
                "email": "optout@example.com",
                "_workspace_id": "ws_tenant_1",
                "subject": "Follow-up",
                "message": "Hello"
            }

            with patch.object(executor, "_release_limit") as mock_release:
                res = executor.execute(
                    action="send_email",
                    data=node_data,
                    linkedin_url=None
                )

                self.assertEqual(res["status"], "suppressed")
                self.assertEqual(res["branch"], Branch.FAILED.value)
                self.assertIn("workspace suppression list", res["error"])
                # Must release reserved limit
                mock_release.assert_called_once()

    def test_handle_if_replied_auto_enrolls_opt_out_into_suppression_list(self):
        """Layer 1 & 2: If prospect replies with unsubscribe or stop, automatically add to suppression_list."""
        mock_supabase = MagicMock()
        mock_table = MagicMock()
        mock_supabase.table.return_value = mock_table

        executor = EleInNodeExecutor(
            worker=MagicMock(),
            supabase=mock_supabase,
            workspace_id="ws_tenant_1",
            campaign_id="camp_1"
        )

        data = {
            "last_reply_sentiment": "negative",
            "last_reply_text": "Please unsubscribe me from this mailing list and stop contacting me.",
            "email": "lead_optout@acme.com",
            "_workspace_id": "ws_tenant_1"
        }

        res = executor.handle_if_replied(data, linkedin_url=None)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["branch"], Branch.NEGATIVE.value)

        # Verify auto-enrollment into suppression_list
        mock_supabase.table.assert_any_call("suppression_list")
        mock_table.upsert.assert_called_once()
        upsert_call = mock_table.upsert.call_args[0][0]
        self.assertEqual(upsert_call["workspace_id"], "ws_tenant_1")
        self.assertEqual(upsert_call["value"], "lead_optout@acme.com")
        self.assertEqual(upsert_call["reason"], "inbound_opt_out_reply")


# ==============================================================================
# Vector 4: Campaign Resume Thundering Herd & Burst Storm
# ==============================================================================
class TestVector4CampaignResumePacing(unittest.TestCase):

    def test_campaign_resume_staggers_lead_execution_intervals(self):
        """Layer 1: Resuming paused campaigns spaces out next_run_at timestamps rather than firing all at once."""
        mock_supabase = MagicMock()
        touchpoint_nodes = json.dumps([
            {"id": "n1", "type": "send_email", "data": {"subject": "Hi", "message": "Test"}}
        ])

        tables = {}
        def get_table(table_name):
            if table_name not in tables:
                t = MagicMock()
                if table_name == "campaigns":
                    t.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                        data=[{
                            "id": "camp_1",
                            "status": "PAUSED",
                            "title": "Outreach Campaign",
                            "nodes_json": touchpoint_nodes,
                            "metadata": {}
                        }]
                    )
                    t.select.return_value.eq.return_value.execute.return_value = MagicMock(count=0)
                elif table_name == "workspaces":
                    t.select.return_value.eq.return_value.execute.return_value = MagicMock(
                        data=[{"tier": "PRO"}]
                    )
                elif table_name == "campaign_nodes":
                    t.select.return_value.eq.return_value.execute.return_value = MagicMock(
                        data=[{"node_type": "send_email", "data": {}}]
                    )
                elif table_name == "campaign_accounts":
                    t.select.return_value.eq.return_value.execute.return_value = MagicMock(
                        data=[]
                    )
                elif table_name == "accounts":
                    t.select.return_value.eq.return_value.or_.return_value.execute.return_value = MagicMock(
                        data=[{"id": "acc_1", "status": "ACTIVE"}]
                    )
                elif table_name == "campaign_enrollments":
                    enrs = [{"id": f"enr_{i}", "lead_id": f"lead_{i}"} for i in range(10)]
                    t.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                        data=enrs
                    )
                tables[table_name] = t
            return tables[table_name]

        mock_supabase.table.side_effect = get_table
        mock_supabase.rpc.return_value.execute.return_value = MagicMock(
            data={"balance": 5000, "tier": "PRO"}
        )

        res = _activate_campaign_core("camp_1", "ws_1", mock_supabase)
        self.assertEqual(res["status"], "activated")

        # Verify that updates were called on execution states with staggered next_run_at
        state_updates = tables["campaign_execution_states"].update.call_args_list
        self.assertTrue(len(state_updates) > 0)
        updated_payload = state_updates[0][0][0]
        self.assertEqual(updated_payload["status"], "pending")
        self.assertIn("next_run_at", updated_payload)


# ==============================================================================
# Vector 5: Unified Inbox Realtime Sync & Concurrency Locks
# ==============================================================================
class TestVector5UnifiedInboxConcurrencyAndLock(unittest.TestCase):

    def test_send_inbox_reply_enforces_operator_lock_lease_collision_defense(self):
        """Layer 0 & 2: If another operator holds active lock lease, 409 Conflict is raised."""
        mock_supabase = MagicMock()
        # Acquire lease for operator_1
        acquired, owner, rem = acquire_thread_reply_lease(
            workspace_id="ws_lock_test",
            thread_key="lead_999",
            operator_id="operator_alpha",
            ttl_seconds=30
        )
        self.assertTrue(acquired)

        payload = SendReplyPayload(
            sender_name="Sales Rep",
            message_text="Hello prospective client!",
            lead_id="lead_999",
            client_draft_id="operator_beta"  # Different operator attempting concurrent reply
        )

        try:
            with self.assertRaises(HTTPException) as ctx:
                send_inbox_reply(
                    payload=payload,
                    supabase=mock_supabase,
                    workspace_id="ws_lock_test"
                )
            self.assertEqual(ctx.exception.status_code, 409)
            self.assertIn("Another reply is currently being dispatched for this thread", ctx.exception.detail)
        finally:
            # Clean up lease
            release_thread_reply_lease("ws_lock_test", "lead_999", "operator_alpha")

    def test_send_inbox_reply_enforces_60s_deduplication_window(self):
        """Layer 2: Duplicate replies within 60s window return existing message ID with deduplicated=True."""
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.gte.return_value.execute.return_value = MagicMock(
            data=[{"id": "msg_existing_uuid_123"}]
        )

        payload = SendReplyPayload(
            sender_name="John Agent",
            message_text="Looking forward to our chat tomorrow.",
            lead_id="lead_123",
            client_draft_id="op_unique_1"
        )

        res = send_inbox_reply(
            payload=payload,
            supabase=mock_supabase,
            workspace_id="ws_dedupe_test"
        )

        self.assertEqual(res["status"], "success")
        self.assertEqual(res["message_id"], "msg_existing_uuid_123")
        self.assertTrue(res.get("deduplicated"))


# ==============================================================================
# Vector 6: Chrome Extension Proxy Failsafe
# ==============================================================================
class TestVector6ChromeExtensionProxyFailsafe(unittest.TestCase):

    def test_extension_background_pac_script_contains_no_direct_fallback(self):
        """Layer 0 & 1: background.js PAC routing for LinkedIn must never contain '; DIRECT' fallback."""
        bg_path = os.path.join(os.getcwd(), "extension", "background.js")
        self.assertTrue(os.path.exists(bg_path), "extension/background.js must exist")

        with open(bg_path, "r", encoding="utf-8") as f:
            content = f.read()

        # The PAC script must route LinkedIn through proxy without DIRECT fallback
        self.assertNotIn("; DIRECT", content, "Critical Deanonymization Bug: '; DIRECT' fallback found in extension/background.js")
        # Must register onProxyError listener
        self.assertIn("chrome.proxy.onProxyError.addListener", content, "Missing onProxyError listener in extension/background.js")


# ==============================================================================
# Vector 7: Billing & Stripe Churn Lifecycle Sync
# ==============================================================================
class TestVector7BillingStripeChurnLifecycle(unittest.IsolatedAsyncioTestCase):

    def test_verify_stripe_signature_rejects_expired_timestamp_replay_attacks(self):
        """Layer 1: Stripe webhook signature timestamp older than 300 seconds is rejected."""
        secret = "whsec_test_secret_123"
        raw_body = b'{"type": "customer.subscription.updated"}'

        # Fresh timestamp within 300s
        fresh_time = int(time.time())
        signed_payload = f"{fresh_time}.".encode("utf-8") + raw_body
        valid_sig = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
        valid_header = f"t={fresh_time},v1={valid_sig}"

        self.assertTrue(verify_stripe_signature(raw_body, valid_header, secret))

        # Expired timestamp (400 seconds ago)
        expired_time = int(time.time()) - 400
        expired_payload = f"{expired_time}.".encode("utf-8") + raw_body
        expired_sig = hmac.new(secret.encode("utf-8"), expired_payload, hashlib.sha256).hexdigest()
        expired_header = f"t={expired_time},v1={expired_sig}"

        self.assertFalse(verify_stripe_signature(raw_body, expired_header, secret))

    async def test_cancel_subscription_graceful_churn_and_stripe_sync(self):
        """Layer 1 & 2: cancel_subscription updates local status to canceling and syncs cancel_at_period_end=True."""
        mock_supabase = MagicMock()
        mock_table = MagicMock()
        mock_supabase.table.return_value = mock_table

        # Active subscription in database
        mock_table.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "sub_row_1", "provider_subscription_id": "sub_stripe_123", "status": "active"}]
        )

        with patch("core.backend.api.routers.billing.os.getenv") as mock_env:
            mock_env.return_value = "sk_test_mock_stripe_key"
            with patch("core.backend.api.routers.billing.stripe", create=True) as mock_stripe:
                req = CancelSubscriptionRequest(reason="Moving to different tool")
                res = await cancel_subscription(
                    request=req,
                    workspace_id="ws_1",
                    supabase=mock_supabase
                )

                self.assertEqual(res["status"], "success")
                self.assertIn("scheduled to cancel at end of current billing cycle", res["message"])

                # Check DB subscription update
                mock_table.update.assert_any_call({"status": "canceling", "cancel_at_period_end": True})

    async def test_reactivate_subscription_revokes_cancellation_and_resumes(self):
        """Layer 1 & 2: reactivate_subscription restores active status and unsets cancel_at_period_end."""
        mock_supabase = MagicMock()
        mock_table = MagicMock()
        mock_supabase.table.return_value = mock_table

        # Canceling subscription in database
        mock_table.select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(
            data=[{"id": "sub_row_1", "provider_subscription_id": "sub_stripe_123", "status": "canceling"}]
        )

        with patch("core.backend.api.routers.billing.os.getenv") as mock_env:
            mock_env.return_value = "sk_test_mock_stripe_key"
            with patch("core.backend.api.routers.billing.stripe", create=True) as mock_stripe:
                res = await reactivate_subscription(
                    workspace_id="ws_1",
                    supabase=mock_supabase
                )

                self.assertEqual(res["status"], "success")
                self.assertIn("reactivated", res["message"].lower())

                # Check DB subscription update
                mock_table.update.assert_any_call({"status": "active", "cancel_at_period_end": False})
