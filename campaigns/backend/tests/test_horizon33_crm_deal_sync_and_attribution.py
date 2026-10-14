import unittest
from typing import Dict, Any, List
from fastapi.testclient import TestClient

from core.backend.main import app
from core.backend.api.auth_dep import get_current_workspace, get_supabase_client
from campaigns.backend.services.elein_executor import EleInNodeExecutor
from campaigns.backend.services.bandit_service import (
    _IN_MEMORY_EXPERIMENTS,
    _IN_MEMORY_VARIANTS,
    _LEAD_ARM_LOCKS,
    resolve_bandit_arm_for_execution,
)
from integrations.backend.services.elein_crm_service import (
    _PROCESSED_DEAL_EVENTS,
    _DEAL_STATE_LEDGER,
    _DEAL_WORKSPACE_OWNER,
    normalize_crm_deal_stage,
    sync_crm_deal_stage_event,
    get_campaign_revenue_attribution,
)


class FakeQuery:
    def __init__(self, rows: List[Dict[str, Any]], updates_log: List[Dict[str, Any]]):
        self._rows = list(rows)
        self._updates_log = updates_log
        self._filters = {}
        self._pending_update = None

    def select(self, *args, **kwargs):
        return self

    def eq(self, key: str, val: Any):
        self._filters[key] = val
        return self

    def limit(self, n: int):
        return self

    def update(self, payload: Dict[str, Any]):
        self._pending_update = dict(payload)
        return self

    def upsert(self, payload: Dict[str, Any], **kwargs):
        self._updates_log.append({"op": "upsert", "payload": payload})
        return self

    def execute(self):
        matched = []
        for r in self._rows:
            ok = True
            for k, v in self._filters.items():
                if str(r.get(k)) != str(v):
                    ok = False
                    break
            if ok:
                if self._pending_update is not None:
                    r.update(self._pending_update)
                    self._updates_log.append({"op": "update", "row": dict(r), "patch": dict(self._pending_update)})
                matched.append(r)

        class Res:
            data = matched

        return Res()


class FakeSupabase:
    def __init__(self, tier: str = "PRO"):
        self.tier = tier
        self.updates_log: List[Dict[str, Any]] = []
        self.tables: Dict[str, List[Dict[str, Any]]] = {
            "leads": [],
            "campaigns": [],
            "campaign_enrollments": [],
            "campaign_execution_states": [],
            "crm_deals": [],
        }

    def rpc(self, fn_name: str, params: Dict[str, Any]):
        tier = self.tier

        class RpcExec:
            def execute(self_inner):
                class Res:
                    data = {"tier": tier, "balance": 5000}

                return Res()

        return RpcExec()

    def table(self, name: str):
        return FakeQuery(self.tables.setdefault(name, []), self.updates_log)


class TestHorizon33CrmDealSyncAndAttribution(unittest.TestCase):
    def setUp(self):
        _PROCESSED_DEAL_EVENTS.clear()
        _DEAL_STATE_LEDGER.clear()
        _DEAL_WORKSPACE_OWNER.clear()
        _IN_MEMORY_EXPERIMENTS.clear()
        _IN_MEMORY_VARIANTS.clear()
        _LEAD_ARM_LOCKS.clear()

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_01_layer0_normalize_crm_deal_stages_across_providers(self):
        """Layer 0: Normalizes HubSpot, Salesforce, and Pipedrive stage names into canonical pipeline stages."""
        self.assertEqual(normalize_crm_deal_stage("appointmentscheduled", "hubspot"), "discovery")
        self.assertEqual(normalize_crm_deal_stage("presentationscheduled", "hubspot"), "demo_completed")
        self.assertEqual(normalize_crm_deal_stage("decisionmakerboughtin", "hubspot"), "proposal_sent")
        self.assertEqual(normalize_crm_deal_stage("closedwon", "hubspot"), "closed_won")
        self.assertEqual(normalize_crm_deal_stage("Closed Lost", "salesforce"), "closed_lost")
        self.assertEqual(normalize_crm_deal_stage("Negotiation/Review", "salesforce"), "proposal_sent")

    def test_02_layer0_closed_won_halts_active_sequences_and_marks_lead_converted(self):
        """Layer 0: Transitioning a deal to Closed Won halts active campaign enrollments & execution states."""
        db = FakeSupabase()
        db.tables["leads"].append({"id": "lead-101", "workspace_id": "ws-alpha", "email": "ceo@acme.io", "status": "active"})
        db.tables["campaign_enrollments"].append({
            "id": "enr-101",
            "workspace_id": "ws-alpha",
            "campaign_id": "camp-alpha",
            "lead_id": "lead-101",
            "status": "active",
        })
        db.tables["campaign_execution_states"].append({
            "id": "exec-101",
            "workspace_id": "ws-alpha",
            "enrollment_id": "enr-101",
            "status": "running",
        })

        res = sync_crm_deal_stage_event(
            workspace_id="ws-alpha",
            deal_id="deal-101",
            raw_stage="closedwon",
            lead_id="lead-101",
            campaign_id="camp-alpha",
            deal_amount=48000.0,
            currency="USD",
            supabase=db,
        )
        self.assertEqual(res["status"], "synced")
        self.assertEqual(res["normalized_stage"], "closed_won")
        self.assertTrue(res["is_terminal"])
        self.assertEqual(res["sequences_halted"], 1)
        self.assertEqual(db.tables["campaign_enrollments"][0]["status"], "converted")
        self.assertEqual(db.tables["campaign_enrollments"][0]["exit_reason"], "crm_closed_won")
        self.assertEqual(db.tables["campaign_execution_states"][0]["status"], "completed")
        self.assertEqual(db.tables["leads"][0]["status"], "converted")

    def test_03_layer0_closed_lost_halts_active_sequences_with_completed_status(self):
        """Layer 0: Transitioning a deal to Closed Lost halts active sequences with crm_closed_lost reason."""
        db = FakeSupabase()
        db.tables["leads"].append({"id": "lead-102", "workspace_id": "ws-alpha", "status": "active"})
        db.tables["campaign_enrollments"].append({
            "id": "enr-102",
            "workspace_id": "ws-alpha",
            "campaign_id": "camp-alpha",
            "lead_id": "lead-102",
            "status": "running",
        })

        res = sync_crm_deal_stage_event(
            workspace_id="ws-alpha",
            deal_id="deal-102",
            raw_stage="closed_lost",
            lead_id="lead-102",
            campaign_id="camp-alpha",
            deal_amount=15000.0,
            close_reason="Budget frozen until Q4",
            supabase=db,
        )
        self.assertEqual(res["normalized_stage"], "closed_lost")
        self.assertEqual(res["sequences_halted"], 1)
        self.assertEqual(db.tables["campaign_enrollments"][0]["status"], "completed")
        self.assertEqual(db.tables["campaign_enrollments"][0]["exit_reason"], "crm_closed_lost")

    def test_04_layer0_closed_won_rewards_thompson_sampling_bandit_arm(self):
        """Layer 0: Closed Won deal automatically attributes high-weight alpha reward to the lead's bandit arm."""
        arm_sel = resolve_bandit_arm_for_execution(
            workspace_id="ws-bandit",
            campaign_id="camp-b1",
            node_id="node-msg-1",
            lead_id="lead-b1",
        )
        chosen_id = arm_sel["selected_variant_id"]
        exp_id = arm_sel["experiment_id"]
        before_alpha = next(v["alpha_param"] for v in _IN_MEMORY_VARIANTS[exp_id] if v["id"] == chosen_id)

        sync_res = sync_crm_deal_stage_event(
            workspace_id="ws-bandit",
            deal_id="deal-b1",
            raw_stage="closed_won",
            lead_id="lead-b1",
            deal_amount=32000.0,
        )
        self.assertTrue(sync_res["bandit_feedback_recorded"])
        self.assertEqual(sync_res["bandit_variant_id"], chosen_id)
        after_alpha = next(v["alpha_param"] for v in _IN_MEMORY_VARIANTS[exp_id] if v["id"] == chosen_id)
        self.assertGreaterEqual(after_alpha, before_alpha + 3.0)

    def test_05_layer0_revenue_attribution_aggregation_by_campaign_and_variant(self):
        """Layer 0: Aggregates open pipeline, closed-won revenue, win rate, and per-campaign/per-variant breakdown."""
        sync_crm_deal_stage_event(
            workspace_id="ws-rev",
            deal_id="d-1",
            raw_stage="proposal_sent",
            campaign_id="camp-1",
            bandit_variant_id="var-a",
            deal_amount=25000.0,
        )
        sync_crm_deal_stage_event(
            workspace_id="ws-rev",
            deal_id="d-2",
            raw_stage="closed_won",
            campaign_id="camp-1",
            bandit_variant_id="var-a",
            deal_amount=60000.0,
        )
        sync_crm_deal_stage_event(
            workspace_id="ws-rev",
            deal_id="d-3",
            raw_stage="closed_lost",
            campaign_id="camp-1",
            bandit_variant_id="var-b",
            deal_amount=20000.0,
        )

        attr = get_campaign_revenue_attribution(workspace_id="ws-rev", campaign_id="camp-1")
        self.assertEqual(attr["total_deals"], 3)
        self.assertEqual(attr["open_pipeline_value"], 25000.0)
        self.assertEqual(attr["closed_won_revenue"], 60000.0)
        self.assertEqual(attr["closed_lost_value"], 20000.0)
        self.assertEqual(attr["win_rate_pct"], 50.0)
        self.assertEqual(len(attr["by_campaign"]), 1)
        self.assertEqual(attr["by_campaign"][0]["closed_won_revenue"], 60000.0)

    def test_06_layer1_idempotent_webhook_replay_guard(self):
        """Layer 1: Duplicate CRM deal stage webhooks are ignored idempotently without double-counting."""
        first = sync_crm_deal_stage_event(
            workspace_id="ws-idem",
            deal_id="deal-idem-1",
            raw_stage="closed_won",
            campaign_id="camp-idem",
            deal_amount=50000.0,
            event_id="evt-hubspot-999",
        )
        self.assertEqual(first["status"], "synced")
        self.assertFalse(first["idempotent_replay"])

        replay = sync_crm_deal_stage_event(
            workspace_id="ws-idem",
            deal_id="deal-idem-1",
            raw_stage="closed_won",
            campaign_id="camp-idem",
            deal_amount=50000.0,
            event_id="evt-hubspot-999",
        )
        self.assertEqual(replay["status"], "duplicate_ignored")
        self.assertTrue(replay["idempotent_replay"])

        attr = get_campaign_revenue_attribution(workspace_id="ws-idem")
        self.assertEqual(attr["closed_won_revenue"], 50000.0)

    def test_07_layer1_out_of_order_stale_webhook_timestamp_guard(self):
        """Layer 1: Out-of-order older webhook timestamps do not regress deal stage from Closed Won back to Discovery."""
        newer = sync_crm_deal_stage_event(
            workspace_id="ws-order",
            deal_id="deal-ord-1",
            raw_stage="closed_won",
            deal_amount=75000.0,
            updated_at="2026-10-11T12:00:00Z",
        )
        self.assertEqual(newer["normalized_stage"], "closed_won")

        older_delayed = sync_crm_deal_stage_event(
            workspace_id="ws-order",
            deal_id="deal-ord-1",
            raw_stage="discovery",
            deal_amount=10000.0,
            updated_at="2026-10-10T08:00:00Z",
        )
        self.assertEqual(older_delayed["status"], "ignored_stale_event")
        self.assertTrue(older_delayed["stale_event"])
        self.assertEqual(older_delayed["normalized_stage"], "closed_won")
        self.assertEqual(older_delayed["deal_amount"], 75000.0)

    def test_08_layer2_cross_tenant_idor_blocked_on_deal_and_lead(self):
        """Layer 2: Blocks cross-workspace deal stage hijacking and cross-workspace lead sequence halting."""
        sync_crm_deal_stage_event(
            workspace_id="ws-owner",
            deal_id="deal-secret-1",
            raw_stage="discovery",
            campaign_id="camp-secret-1",
            deal_amount=40000.0,
        )

        with self.assertRaises(PermissionError):
            sync_crm_deal_stage_event(
                workspace_id="ws-attacker",
                deal_id="deal-secret-1",
                raw_stage="closed_lost",
                deal_amount=0.0,
            )

        with self.assertRaises(PermissionError):
            get_campaign_revenue_attribution(
                workspace_id="ws-attacker",
                campaign_id="camp-secret-1",
            )

    def test_09_layer2_deal_amount_hygiene_and_formula_injection_stripping(self):
        """Layer 2: Sanitizes formatted/negative/NaN amounts and strips spreadsheet formula prefixes."""
        res_formatted = sync_crm_deal_stage_event(
            workspace_id="ws-hygiene",
            deal_id="deal-h1",
            raw_stage="proposal_sent",
            deal_amount="$125,500.50",
            currency="eur",
            deal_name="=cmd|' /C calc'!A0 Enterprise License",
            close_reason="+Competitor underbid",
        )
        self.assertEqual(res_formatted["deal_amount"], 125500.50)
        self.assertEqual(res_formatted["currency"], "EUR")
        self.assertFalse(res_formatted["deal_name"].startswith("="))
        self.assertFalse(res_formatted["close_reason"].startswith("+"))

        res_negative = sync_crm_deal_stage_event(
            workspace_id="ws-hygiene",
            deal_id="deal-h2",
            raw_stage="discovery",
            deal_amount=-99999.0,
        )
        self.assertEqual(res_negative["deal_amount"], 0.0)

    def test_10_executor_handle_sync_crm_deal_stage_node(self):
        """Layer 0 & 2: EleInNodeExecutor executes sync_crm_deal_stage node and exposes CRM variables."""
        executor = EleInNodeExecutor(worker=None, supabase=None, workspace_id="ws-exec")
        node_res = executor.execute(
            "sync_crm_deal_stage",
            {
                "_workspace_id": "ws-exec",
                "_campaign_id": "camp-exec-1",
                "_lead_id": "lead-exec-1",
                "deal_id": "deal-exec-1",
                "deal_stage": "closed_won",
                "deal_amount": 36000,
                "currency": "USD",
            },
            "https://linkedin.com/in/exec-prospect",
        )
        self.assertEqual(node_res["status"], "success")
        self.assertTrue(node_res["terminal"])
        self.assertEqual(node_res["variables"]["crm_deal_stage"], "closed_won")
        self.assertEqual(node_res["variables"]["crm_deal_amount"], 36000.0)

    def test_11_router_crm_deal_sync_and_attribution_endpoints(self):
        """Router: POST /api/elein/crm/deals/sync-stage and GET /api/elein/crm/deals/attribution succeed for PRO workspace."""
        fake_db = FakeSupabase(tier="PRO")
        app.dependency_overrides[get_current_workspace] = lambda: "ws-router-pro"
        app.dependency_overrides[get_supabase_client] = lambda: fake_db
        client = TestClient(app)

        post_res = client.post(
            "/api/elein/crm/deals/sync-stage",
            json={
                "deal_id": "deal-r-1",
                "stage": "closed_won",
                "campaign_id": "camp-r-1",
                "deal_amount": 84000,
                "currency": "USD",
            },
        )
        self.assertEqual(post_res.status_code, 200)
        self.assertEqual(post_res.json()["normalized_stage"], "closed_won")

        get_res = client.get("/api/elein/crm/deals/attribution?campaign_id=camp-r-1")
        self.assertEqual(get_res.status_code, 200)
        body = get_res.json()
        self.assertEqual(body["closed_won_revenue"], 84000.0)
        self.assertEqual(body["win_rate_pct"], 100.0)

    def test_12_router_free_tier_402_and_cross_tenant_403_guards(self):
        """Router Layer 2: Blocks FREE tier with 402 and blocks cross-tenant deal access with 403."""
        # Seed a deal owned by ws-tenant-a
        sync_crm_deal_stage_event(
            workspace_id="ws-tenant-a",
            deal_id="deal-tenant-a",
            raw_stage="discovery",
            deal_amount=20000.0,
        )

        # Cross-tenant attempt by ws-tenant-b (PRO) -> 403
        pro_db = FakeSupabase(tier="PRO")
        app.dependency_overrides[get_current_workspace] = lambda: "ws-tenant-b"
        app.dependency_overrides[get_supabase_client] = lambda: pro_db
        client = TestClient(app)

        forbidden_res = client.post(
            "/api/elein/crm/deals/sync-stage",
            json={"deal_id": "deal-tenant-a", "stage": "closed_lost"},
        )
        self.assertEqual(forbidden_res.status_code, 403)

        # FREE tier attempt -> 402
        free_db = FakeSupabase(tier="FREE")
        app.dependency_overrides[get_current_workspace] = lambda: "prod-free-tenant-1"
        app.dependency_overrides[get_supabase_client] = lambda: free_db

        free_res = client.get("/api/elein/crm/deals/attribution")
        self.assertEqual(free_res.status_code, 402)


if __name__ == "__main__":
    unittest.main()
