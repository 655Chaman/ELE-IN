from datetime import datetime, timedelta
import os
import unittest
from unittest.mock import MagicMock

from fastapi import HTTPException

from campaigns.backend.routers.abm_router import (
    AddCommitteeMemberPayload,
    LaunchMultithreadPayload,
    ResolveAbmExecutionContextPayload,
    UpdateCommitteeStatusPayload,
    add_committee_member_endpoint,
    get_committee_members_endpoint,
    launch_multithread_endpoint,
    resolve_abm_execution_context_endpoint,
    update_committee_member_status_endpoint,
)
from campaigns.backend.services.abm_multithreading_service import (
    _ACCOUNT_TOUCH_LEDGER,
    _IN_MEMORY_ACCOUNTS,
    _IN_MEMORY_COMMITTEES,
    _SEED_ACCOUNTS,
    _SEED_COMMITTEES,
    add_committee_member,
    create_or_map_target_account,
    get_account_committee_members,
    launch_multithreaded_campaign,
    list_target_accounts,
    resolve_abm_context_for_execution,
    update_committee_member_status,
)
from campaigns.backend.services.elein_executor import EleInNodeExecutor


class TestHorizon34aAbmOrchestration(unittest.TestCase):
    """
    Horizon 34A: Account-Based Marketing (ABM) Multi-Threading & Buying-Committee Role Orchestration.
    Verifies Layer 0 (Foundational), Layer 1 (Environmental Failure Analysis),
    and Layer 2 (Human Paranoia / Cross-Tenant IDOR & Self-Reference Defense).
    """

    def setUp(self):
        _IN_MEMORY_ACCOUNTS.clear()
        _IN_MEMORY_ACCOUNTS.extend([dict(a) for a in _SEED_ACCOUNTS])
        _IN_MEMORY_COMMITTEES.clear()
        _IN_MEMORY_COMMITTEES.extend([dict(m) for m in _SEED_COMMITTEES])
        _ACCOUNT_TOUCH_LEDGER.clear()
        os.environ["TEST_MODE"] = "true"

    # -------------------------------------------------------------------------
    # LAYER 0: FOUNDATIONAL LAYER
    # -------------------------------------------------------------------------
    def test_layer0_resolve_abm_context_classifies_role_and_injects_peer_reference(self):
        res = resolve_abm_context_for_execution(
            workspace_id="ws-default",
            account_id="acc-stripe",
            company_name="Stripe, Inc.",
            lead_id="lead-stripe-cfo",
            prospect_name="Marcus Vance",
            title="Chief Financial Officer",
            staggered_interval_hours=4,
        )
        self.assertEqual(res["role_archetype"], "economic_buyer")
        self.assertEqual(res["abm_peer_reference"], "Elena Rostova (VP of Revenue Operations & Sales)")
        self.assertTrue(res["cross_thread_aware"])
        self.assertIn("ROI", res["subject"])
        self.assertIn("Elena Rostova (VP of Revenue Operations & Sales)", res["body"])
        self.assertFalse(res["collision_deferred"])

    def test_layer0_executor_handle_abm_multithread_populates_sequence_variables(self):
        executor = EleInNodeExecutor(worker=MagicMock(), supabase=None, workspace_id="ws-default")
        res = executor.handle_abm_multithread(
            {
                "account_id": "acc-stripe",
                "company_name": "Stripe, Inc.",
                "_lead_id": "lead-stripe-sec",
                "prospect_name": "Devon Miller",
                "title": "Head of Enterprise IT & Security",
                "staggered_interval_hours": 4,
            },
            "https://linkedin.com/in/devon-miller-security",
        )
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["branch"], "then")
        self.assertFalse(res["collision_deferred"])
        vars_dict = res["variables"]
        self.assertEqual(vars_dict["abm_role_archetype"], "technical_evaluator")
        self.assertEqual(vars_dict["abm_peer_reference"], "Elena Rostova (VP of Revenue Operations & Sales)")
        self.assertIn("SOC2", vars_dict["abm_subject"])
        self.assertIn("residential proxy", vars_dict["abm_body"].lower())

    def test_layer0_sequence_message_interpolates_abm_peer_reference_template_variable(self):
        mock_worker = MagicMock()
        mock_worker.send_message.return_value = {"status": "success"}
        executor = EleInNodeExecutor(worker=mock_worker, supabase=None, workspace_id="ws-default")

        msg_res = executor.handle_send_message(
            {
                "account_id": "acc-stripe",
                "_lead_id": "lead-stripe-cfo",
                "first_name": "Marcus",
                "last_name": "Vance",
                "job_title": "Chief Financial Officer",
                "company": "Stripe, Inc.",
                "body": "Hi {{first_name}}, following up after speaking with {{abm_peer_reference}} at {{company}}.",
            },
            "https://linkedin.com/in/marcus-vance-cfo",
        )
        self.assertEqual(msg_res["status"], "success")
        self.assertIn("Elena Rostova (VP of Revenue Operations & Sales)", msg_res["body_sent"])
        self.assertNotIn("{{abm_peer_reference}}", msg_res["body_sent"])

    def test_layer0_resolve_execution_context_router_endpoint_returns_differentiated_payload(self):
        payload = ResolveAbmExecutionContextPayload(
            account_id="acc-datadog",
            company_name="Datadog",
            lead_id="lead-datadog-cro",
            prospect_name="Liam Thorne",
            title="Chief Revenue Officer",
            staggered_interval_hours=4,
        )
        resp = resolve_abm_execution_context_endpoint(payload, workspace_id="ws-test", supabase=None)
        self.assertTrue(resp["success"])
        data = resp["data"]
        self.assertEqual(data["role_archetype"], "economic_buyer")
        self.assertEqual(data["abm_peer_reference"], "Maya Lin (Director of Business Development)")
        self.assertFalse(data["collision_deferred"])

    # -------------------------------------------------------------------------
    # LAYER 1: ENVIRONMENTAL FAILURE ANALYSIS
    # -------------------------------------------------------------------------
    def test_layer1_staggered_same_account_touch_collision_defers_second_stakeholder(self):
        t0 = datetime(2026, 10, 11, 9, 0, 0)
        first = resolve_abm_context_for_execution(
            workspace_id="ws-test-stagger",
            account_id="acc-stripe",
            company_name="Stripe, Inc.",
            lead_id="lead-stripe-cfo",
            prospect_name="Marcus Vance",
            title="Chief Financial Officer",
            staggered_interval_hours=4,
            now_dt=t0,
        )
        self.assertFalse(first["collision_deferred"])
        self.assertIsNone(first["next_available_slot_iso"])

        # 1 hour later (< 4h staggered interval), touching a different committee member on acc-stripe
        second = resolve_abm_context_for_execution(
            workspace_id="ws-test-stagger",
            account_id="acc-stripe",
            company_name="Stripe, Inc.",
            lead_id="lead-stripe-sec",
            prospect_name="Devon Miller",
            title="Head of Enterprise IT & Security",
            staggered_interval_hours=4,
            now_dt=t0 + timedelta(hours=1),
        )
        self.assertTrue(second["collision_deferred"])
        self.assertFalse(second["idempotent_retry"])
        self.assertEqual(second["next_available_slot_iso"], (t0 + timedelta(hours=4)).isoformat())

    def test_layer1_sticky_idempotent_retry_for_same_lead_does_not_self_collide(self):
        t0 = datetime(2026, 10, 11, 10, 0, 0)
        first = resolve_abm_context_for_execution(
            workspace_id="ws-test-idempotent",
            account_id="acc-stripe",
            lead_id="lead-stripe-cfo",
            prospect_name="Marcus Vance",
            title="Chief Financial Officer",
            staggered_interval_hours=4,
            now_dt=t0,
        )
        self.assertFalse(first["collision_deferred"])
        self.assertFalse(first["idempotent_retry"])

        retry = resolve_abm_context_for_execution(
            workspace_id="ws-test-idempotent",
            account_id="acc-stripe",
            lead_id="lead-stripe-cfo",
            prospect_name="Marcus Vance",
            title="Chief Financial Officer",
            staggered_interval_hours=4,
            now_dt=t0 + timedelta(minutes=25),
        )
        self.assertFalse(retry["collision_deferred"])
        self.assertTrue(retry["idempotent_retry"])
        self.assertIsNone(retry["next_available_slot_iso"])

    def test_layer1_different_stakeholder_allowed_after_staggered_window_elapses(self):
        t0 = datetime(2026, 10, 11, 8, 0, 0)
        resolve_abm_context_for_execution(
            workspace_id="ws-test-window",
            account_id="acc-stripe",
            lead_id="lead-stripe-cfo",
            prospect_name="Marcus Vance",
            title="Chief Financial Officer",
            staggered_interval_hours=4,
            now_dt=t0,
        )

        after_window = resolve_abm_context_for_execution(
            workspace_id="ws-test-window",
            account_id="acc-stripe",
            lead_id="lead-stripe-sec",
            prospect_name="Devon Miller",
            title="Head of Enterprise IT & Security",
            staggered_interval_hours=4,
            now_dt=t0 + timedelta(hours=5),
        )
        self.assertFalse(after_window["collision_deferred"])
        self.assertFalse(after_window["idempotent_retry"])
        self.assertIsNone(after_window["next_available_slot_iso"])

    # -------------------------------------------------------------------------
    # LAYER 2: HUMAN PARANOIA (THE HUMAN ERROR ELEMENT)
    # -------------------------------------------------------------------------
    def test_layer2_self_reference_guard_never_cites_prospect_as_own_peer(self):
        # Elena Rostova is the 'replied' champion on acc-stripe; she must not be cited to herself
        elena_ctx = resolve_abm_context_for_execution(
            workspace_id="ws-test-self-guard",
            account_id="acc-stripe",
            lead_id="lead-stripe-vps",
            prospect_name="Elena Rostova",
            title="VP of Revenue Operations & Sales",
        )
        self.assertNotIn("Elena Rostova", elena_ctx["abm_peer_reference"])
        self.assertEqual(elena_ctx["abm_peer_reference"], "Marcus Vance (Chief Financial Officer)")

        # On acc-datadog, Maya Lin is the ONLY engaged stakeholder; her peer reference must be empty
        maya_ctx = resolve_abm_context_for_execution(
            workspace_id="ws-test-self-guard",
            account_id="acc-datadog",
            lead_id="lead-datadog-dir",
            prospect_name="Maya Lin",
            title="Director of Business Development",
        )
        self.assertEqual(maya_ctx["abm_peer_reference"], "")
        self.assertFalse(maya_ctx["cross_thread_aware"])

    def test_layer2_cross_tenant_idor_blocked_across_service_and_list_filtering(self):
        created = create_or_map_target_account(
            workspace_id="ws-tenant-owner",
            company_name="VaultCore Enterprise",
            domain="vaultcore.io",
            leads=[{"name": "Hannah Abbott", "title": "CFO", "email": "hannah@vaultcore.io"}],
        )
        acc_id = created["account"]["id"]
        mem_id = created["committee_members"][0]["id"]

        # Attacker workspace listing accounts must not see VaultCore Enterprise
        attacker_accounts = list_target_accounts(workspace_id="ws-tenant-attacker")
        attacker_ids = [a["id"] for a in attacker_accounts]
        self.assertNotIn(acc_id, attacker_ids)

        with self.assertRaises(PermissionError):
            get_account_committee_members(workspace_id="ws-tenant-attacker", account_id=acc_id)

        with self.assertRaises(PermissionError):
            add_committee_member(
                workspace_id="ws-tenant-attacker",
                account_id=acc_id,
                prospect_name="Intruder",
                title="VP Sales",
            )

        with self.assertRaises(PermissionError):
            update_committee_member_status(
                workspace_id="ws-tenant-attacker",
                member_id=mem_id,
                status="meeting_booked",
            )

        with self.assertRaises(PermissionError):
            launch_multithreaded_campaign(
                workspace_id="ws-tenant-attacker",
                account_id=acc_id,
            )

        with self.assertRaises(PermissionError):
            resolve_abm_context_for_execution(
                workspace_id="ws-tenant-attacker",
                account_id=acc_id,
                prospect_name="Hannah Abbott",
                title="CFO",
            )

    def test_layer2_router_maps_cross_tenant_permission_error_to_http_403(self):
        created = create_or_map_target_account(
            workspace_id="ws-tenant-alpha",
            company_name="AlphaShield Corp",
            domain="alphashield.io",
            leads=[{"name": "grant@alphashield.io", "title": "CISO", "email": "grant@alphashield.io"}],
        )
        acc_id = created["account"]["id"]
        mem_id = created["committee_members"][0]["id"]

        with self.assertRaises(HTTPException) as ctx_get:
            get_committee_members_endpoint(acc_id, workspace_id="ws-test", supabase=None)
        self.assertEqual(ctx_get.exception.status_code, 403)

        with self.assertRaises(HTTPException) as ctx_add:
            add_committee_member_endpoint(
                acc_id,
                AddCommitteeMemberPayload(prospect_name="Eve", title="VP Sales"),
                workspace_id="ws-test",
                supabase=None,
            )
        self.assertEqual(ctx_add.exception.status_code, 403)

        with self.assertRaises(HTTPException) as ctx_upd:
            update_committee_member_status_endpoint(
                mem_id,
                UpdateCommitteeStatusPayload(status="replied"),
                workspace_id="ws-test",
                supabase=None,
            )
        self.assertEqual(ctx_upd.exception.status_code, 403)

        with self.assertRaises(HTTPException) as ctx_launch:
            launch_multithread_endpoint(
                LaunchMultithreadPayload(account_id=acc_id),
                workspace_id="ws-test",
                supabase=None,
            )
        self.assertEqual(ctx_launch.exception.status_code, 403)

        with self.assertRaises(HTTPException) as ctx_resolve:
            resolve_abm_execution_context_endpoint(
                ResolveAbmExecutionContextPayload(account_id=acc_id, prospect_name="Eve", title="CFO"),
                workspace_id="ws-test",
                supabase=None,
            )
        self.assertEqual(ctx_resolve.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
