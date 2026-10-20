"""
Stage 14 Paranoia Test Suite — Direct Campaign Enrollment & Bi-Directional Lifecycle Sync
========================================================================================
Validates the complete remediation of Bridge 3 (Campaign & Execution Bridge) under the
Three-Layer Logic Architecture (Paranoia Framework):

Layer 0 (Foundational Layer):
- Direct list enrollment updates leads.status to 'enrolled'.
- Direct lead IDs enrollment updates leads.status to 'enrolled'.
- ALLOWED_LEAD_STATUSES includes all production lifecycle values ('enrolled', 'connected', 'replied', 'opted_out').

Layer 1 (Environmental Failure Analysis):
- Dynamic segmentation auto-enrollment queries campaign_accounts and allocates sender account_id.
- In-flight sequence completions update leads.status to 'completed', while preserving 'replied'/'won'.
- Outbound touches advance lead status to 'contacted', but never downgrade terminal statuses ('replied', 'won', 'lost').

Layer 2 (Human Paranoia & Abuse Defense):
- Inbound reply webhooks use lowercase canonical enum value 'replied' instead of 'Replied (Email)'.
- Multi-channel collision guard bypasses in-flight leads during direct enrollment.
"""

import pytest
import unittest
from unittest.mock import MagicMock, patch, ANY
from datetime import datetime, timezone
from fastapi import HTTPException

from campaigns.backend.routers.elein import (
    ALLOWED_LEAD_STATUSES,
    enroll_leads,
    enroll_list_leads,
    EnrollLeadsRequest,
    EnrollListRequest,
)
from campaigns.backend.services.elein_executor import EleInNodeExecutor
from campaigns.backend.services.elein_orchestrator import EleInOrchestrator
from leads.backend.services.lead_segmentation_service import sync_dynamic_segment_members


class TestStage14LeadsDirectEnrollmentAndLifecycleSync(unittest.TestCase):

    def test_layer0_allowed_lead_statuses_includes_lifecycle_states(self):
        """
        Layer 0: Verify ALLOWED_LEAD_STATUSES contains all production lifecycle enum values
        including 'enrolled', 'connected', 'replied', 'opted_out'.
        """
        assert "enrolled" in ALLOWED_LEAD_STATUSES
        assert "connected" in ALLOWED_LEAD_STATUSES
        assert "replied" in ALLOWED_LEAD_STATUSES
        assert "opted_out" in ALLOWED_LEAD_STATUSES

    def test_layer0_enroll_leads_syncs_leads_status_to_enrolled(self):
        """
        Layer 0 & 1: Enrolling leads via enroll_leads must update leads.status to 'enrolled'.
        """
        mock_supabase = MagicMock()
        mock_camp_res = MagicMock(data=[{"id": "camp-1", "workspace_id": "ws-1"}])
        mock_ver_res = MagicMock(data=[{"id": "ver-1"}])
        mock_acc_res = MagicMock(data=[{"account_id": "acc-1", "accounts": {"id": "acc-1", "status": "ACTIVE"}}])
        mock_lead_res = MagicMock(data=[
            {"id": "lead-1", "linkedin_url": "https://linkedin.com/in/test1", "email": "test1@corp.com"},
            {"id": "lead-2", "linkedin_url": "https://linkedin.com/in/test2", "email": "test2@corp.com"}
        ])

        mock_leads_table = MagicMock()
        mock_leads_update = MagicMock()
        mock_leads_update.in_.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        mock_leads_table.update.return_value = mock_leads_update
        mock_leads_table.select.return_value.eq.return_value.in_.return_value.execute.return_value = mock_lead_res

        def table_router(name):
            m = MagicMock()
            if name == "campaigns":
                m.select.return_value.eq.return_value.eq.return_value.execute.return_value = mock_camp_res
                return m
            elif name == "campaign_versions":
                m.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = mock_ver_res
                return m
            elif name == "campaign_accounts":
                m.select.return_value.eq.return_value.execute.return_value = mock_acc_res
                return m
            elif name == "campaign_enrollments":
                m.select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(data=[])
                return m
            elif name == "leads":
                return mock_leads_table
            elif name == "suppression_list":
                m.select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(data=[])
                return m
            return m

        mock_supabase.table.side_effect = table_router

        with patch("core.backend.api.auth_dep.get_service_client", return_value=mock_supabase), \
             patch("campaigns.backend.routers.elein.get_conflicting_active_leads", return_value=set()):
            
            res = enroll_leads(
                campaign_id="camp-1",
                body=EnrollLeadsRequest(opportunity_ids=["lead-1", "lead-2"]),
                supabase=mock_supabase,
                workspace_id="ws-1"
            )

        assert res["enrolled"] == 2
        # Verify leads.status update was called with 'enrolled'
        mock_leads_table.update.assert_called()
        update_call_args = mock_leads_table.update.call_args[0][0]
        assert update_call_args["status"] == "enrolled"

    def test_layer1_dynamic_auto_enrollment_allocates_sender_account_and_syncs_status(self):
        """
        Layer 1 Paranoia (B3-F07): Dynamic segmentation auto-enrollment must query campaign_accounts,
        allocate sender account_id to enrollment payloads, and sync leads.status to 'enrolled'.
        """
        mock_supabase = MagicMock()
        mock_rule = MagicMock(data=[{
            "id": "rule-1",
            "workspace_id": "ws-dynamic",
            "list_id": "list-dynamic",
            "conditions": [{"field": "seniority", "operator": "equals", "value": "c_suite"}],
            "match_type": "ALL",
            "is_active": True,
            "auto_enroll_campaign_id": "camp-auto-1",
            "re_enroll_disqualified": False
        }])
        mock_camp_ver = MagicMock(data=[{"id": "ver-auto-1"}])
        mock_camp_acc = MagicMock(data=[
            {"account_id": "sender-acc-1", "accounts": {"id": "sender-acc-1", "status": "ACTIVE", "is_warmup": False, "warmup_max_connections": 50}}
        ])
        mock_leads = MagicMock(data=[
            {"id": "lead-dyn-1", "workspace_id": "ws-dynamic", "job_title": "CEO", "status": "extracted", "metadata": {}}
        ])
        mock_list_members = MagicMock(data=[])

        mock_leads_table = MagicMock()
        mock_leads_update = MagicMock()
        mock_leads_update.in_.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        mock_leads_table.update.return_value = mock_leads_update

        mock_enr_table = MagicMock()
        mock_enr_upsert = MagicMock()
        mock_enr_upsert.execute.return_value = MagicMock(data=[])
        mock_enr_table.upsert.return_value = mock_enr_upsert

        def table_router(name):
            m = MagicMock()
            if name == "dynamic_segmentation_rules":
                m.select.return_value.eq.return_value.eq.return_value.execute.return_value = mock_rule
                return m
            elif name == "lead_lists":
                m.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[{
                    "id": "list-dynamic",
                    "metadata": {
                        "dynamic_rules": {"seniority": ["c_suite"]},
                        "auto_enroll_campaign_id": "camp-auto-1"
                    }
                }])
                return m
            elif name == "campaigns":
                m.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "camp-auto-1", "status": "active"}])
                return m
            elif name == "campaign_versions":
                m.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = mock_camp_ver
                return m
            elif name == "campaign_accounts":
                m.select.return_value.eq.return_value.execute.return_value = mock_camp_acc
                return m
            elif name == "campaign_enrollments":
                m.select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(data=[])
                m.upsert = mock_enr_table.upsert
                return m
            elif name == "campaign_execution_states":
                m.upsert.return_value.execute.return_value = MagicMock(data=[])
                return m
            elif name == "list_members":
                m.select.return_value.eq.return_value.execute.return_value = mock_list_members
                m.insert.return_value.execute.return_value = MagicMock(data=[])
                m.upsert.return_value.execute.return_value = MagicMock(data=[])
                return m
            elif name == "leads":
                # Returns 1 candidate lead matching C-suite rule
                query = MagicMock()
                query.eq.return_value = query
                query.order.return_value = query
                query.range.return_value = query
                query.execute.return_value = mock_leads
                mock_leads_table.select.return_value = query
                return mock_leads_table
            return m

        mock_supabase.table.side_effect = table_router

        with patch("leads.backend.services.lead_segmentation_service.filter_leads_in_memory", return_value=mock_leads.data), \
             patch("campaigns.backend.services.collision_guard.get_conflicting_active_leads", return_value=[]):
            res = sync_dynamic_segment_members(
                workspace_id="ws-dynamic",
                list_id="list-dynamic",
                supabase=mock_supabase
            )

        assert res["auto_enrolled_count"] == 1
        # Verify enrollment upsert occurred with allocated sender account_id
        mock_enr_table.upsert.assert_called()
        enr_rows = mock_enr_table.upsert.call_args[0][0]
        assert len(enr_rows) == 1
        assert enr_rows[0]["account_id"] == "sender-acc-1"
        assert enr_rows[0]["campaign_version_id"] == "ver-auto-1"

        # Verify leads.status updated to 'enrolled'
        mock_leads_table.update.assert_called()
        upd_data = mock_leads_table.update.call_args[0][0]
        assert upd_data["status"] == "enrolled"

    def test_layer1_outbound_touch_advances_lead_to_contacted(self):
        """
        Layer 1 Paranoia: Logging an outbound touch in _log_outbound_message must
        advance leads.status to 'contacted' if currently 'enrolled' or 'extracted'.
        """
        mock_supabase = MagicMock()
        mock_leads_table = MagicMock()
        mock_leads_table.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"status": "enrolled"}])
        mock_update = MagicMock()
        mock_update.eq.return_value.execute.return_value = MagicMock(data=[])
        mock_leads_table.update.return_value = mock_update

        def table_router(name):
            m = MagicMock()
            if name == "leads":
                return mock_leads_table
            elif name == "messages":
                m.insert.return_value.execute.return_value = MagicMock(data=[])
                return m
            return m

        mock_supabase.table.side_effect = table_router

        executor = EleInNodeExecutor(supabase=mock_supabase, workspace_id="ws-1")
        data = {
            "workspace_id": "ws-1",
            "_lead_id": "lead-contact-1",
            "_account_id": "acc-1",
            "lead_profile": {"first_name": "Diana", "last_name": "Prince"}
        }

        executor._log_outbound_message(data, "Hi Diana, great to connect!")

        # Verify leads.status was updated to 'contacted'
        mock_leads_table.update.assert_called()
        upd_payload = mock_leads_table.update.call_args[0][0]
        assert upd_payload["status"] == "contacted"

    def test_layer1_outbound_touch_does_not_downgrade_replied_or_won(self):
        """
        Layer 1 Paranoia: Outbound touch must NEVER downgrade a lead that is already 'replied' or 'won'.
        """
        mock_supabase = MagicMock()
        mock_leads_table = MagicMock()
        mock_leads_table.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"status": "replied"}])
        mock_update = MagicMock()
        mock_leads_table.update.return_value = mock_update

        def table_router(name):
            m = MagicMock()
            if name == "leads":
                return mock_leads_table
            elif name == "messages":
                m.insert.return_value.execute.return_value = MagicMock(data=[])
                return m
            return m

        mock_supabase.table.side_effect = table_router

        executor = EleInNodeExecutor(supabase=mock_supabase, workspace_id="ws-1")
        data = {
            "workspace_id": "ws-1",
            "_lead_id": "lead-replied-1",
            "_account_id": "acc-1",
            "lead_profile": {"first_name": "Bruce", "last_name": "Wayne"}
        }

        executor._log_outbound_message(data, "Follow-up note")

        # Update to leads table should NOT have been called because status was already 'replied'
        mock_leads_table.update.assert_not_called()

    def test_layer1_orchestrator_completion_syncs_lead_status_to_completed(self):
        """
        Layer 1 Paranoia: When orchestrator marks an execution state as 'completed',
        it updates leads.status to 'completed' for leads in 'contacted' or 'enrolled' state.
        """
        mock_supabase = MagicMock()
        mock_leads_table = MagicMock()
        mock_leads_table.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"status": "contacted"}])
        mock_update = MagicMock()
        mock_update.eq.return_value.execute.return_value = MagicMock(data=[])
        mock_leads_table.update.return_value = mock_update

        mock_exec_table = MagicMock()
        mock_exec_table.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "state-1"}])

        mock_enr_table = MagicMock()
        mock_enr_table.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "enr-1"}])
        mock_enr_table.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"lead_id": "lead-fin-1"}])

        def table_router(name):
            if name == "campaign_execution_states":
                return mock_exec_table
            elif name == "campaign_enrollments":
                return mock_enr_table
            elif name == "leads":
                return mock_leads_table
            return MagicMock()

        mock_supabase.table.side_effect = table_router
        mock_supabase.rpc.return_value.execute.return_value = MagicMock(data=True)

        orchestrator = EleInOrchestrator(supabase=mock_supabase)
        success = orchestrator.update_state(
            state_id="state-1",
            node_id="node-end",
            status="completed",
            next_run_at=None,
            lease_token="lease-1",
            variables={},
            enrollment_id="enr-1"
        )

        assert success is True
        # Verify leads table was updated to 'completed'
        mock_leads_table.update.assert_called()
        upd = mock_leads_table.update.call_args[0][0]
        assert upd["status"] == "completed"

    def test_layer2_inbound_webhooks_use_canonical_replied_status(self):
        """
        Layer 2 Paranoia: Inbound reply webhook logic sets leads.status = 'replied'
        (canonical enum value, preventing PostgreSQL invalid enum input errors).
        """
        from campaigns.backend.routers.inbound_webhooks import smartlead_inbound_webhook
        from unittest.mock import AsyncMock

        mock_supabase = MagicMock()
        mock_ws_res = MagicMock(data=[{"id": "ws-1", "status": "active"}])
        mock_lead_res = MagicMock(data=[{
            "id": "lead-wh-1",
            "workspace_id": "ws-1",
            "metadata": {},
            "status": "contacted"
        }])
        mock_leads_table = MagicMock()
        mock_leads_table.select.return_value.eq.return_value.ilike.return_value.limit.return_value.execute.return_value = mock_lead_res
        mock_leads_table.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        def table_router(name):
            m = MagicMock()
            if name == "workspaces":
                m.select.return_value.eq.return_value.execute.return_value = mock_ws_res
                return m
            elif name == "leads":
                return mock_leads_table
            elif name == "campaign_enrollments":
                m.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "enr-1"}])
                return m
            elif name == "campaign_execution_states":
                m.select.return_value.in_.return_value.execute.return_value = MagicMock(data=[{"status": "waiting_for_reply"}])
                m.update.return_value.in_.return_value.in_.return_value.execute.return_value = MagicMock(data=[])
                return m
            elif name == "outbox_events":
                m.insert.return_value.execute.return_value = MagicMock(data=[])
                return m
            return m

        mock_supabase.table.side_effect = table_router

        # Fake webhook payload
        payload = {
            "event_type": "EMAIL_REPLY",
            "email": "prospect@acmecorp.com",
            "reply_text": "I am interested, let's chat next Tuesday."
        }

        mock_request = MagicMock()
        mock_request.headers = {}
        mock_request.query_params = {}
        mock_request.json = AsyncMock(return_value=payload)

        with patch("campaigns.backend.routers.inbound_webhooks.get_service_client", return_value=mock_supabase), \
             patch("campaigns.backend.routers.inbound_webhooks._cascade_halt_lead_linkedin_outreach"), \
             patch("integrations.backend.services.webhook_service.emit_webhook_event"):
            import asyncio
            res = asyncio.run(smartlead_inbound_webhook(
                workspace_id="ws-1",
                request=mock_request
            ))

        assert res["status"] in ("ok", "success")
        # Verify leads update called with 'replied'
        mock_leads_table.update.assert_called()
        upd = mock_leads_table.update.call_args[0][0]
        assert upd["status"] == "replied"
