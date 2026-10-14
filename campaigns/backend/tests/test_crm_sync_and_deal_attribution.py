"""
test_crm_sync_and_deal_attribution.py — Phase 20 CRM Sync & Deal Attribution Test Suite.
Rigorously constructed under the Three-Layer Logic Architecture (Paranoia Framework):
- Layer 0: Foundational Layer (Core math, models, domain normalization, and endpoints)
- Layer 1: Environmental Failure Analysis (Zero-Migration Supabase outages, echo loop debounce, campaign auto-halting)
- Layer 2: Human Paranoia (Formula injection sanitization, dirty input normalization, rapid double submissions)
"""

import copy
from typing import Dict, Any, List, Optional
from unittest.mock import MagicMock
import pytest
from starlette.testclient import TestClient

from core.backend.main import app
from core.backend.api.auth_dep import get_current_workspace, get_service_client
from campaigns.backend.services.crm_attribution_service import (
    sanitize_text,
    normalize_domain,
    calculate_payload_hash,
    is_echo_loop,
    calculate_deal_attribution,
    process_inbound_crm_event,
    list_synced_accounts,
    upsert_synced_account,
    list_deal_attributions,
    get_crm_sync_telemetry,
    _IN_MEMORY_CRM_ACCOUNTS,
    _IN_MEMORY_DEAL_ATTRIBUTIONS,
    _IN_MEMORY_SYNC_LOGS
)


# =============================================================================
# Paranoia Mocks & Fixtures
# =============================================================================

class FailingTableMock:
    """Simulates missing database relations or network partition (Zero-Migration resilience)."""
    def select(self, *args, **kwargs):
        raise RuntimeError("relation 'public.crm_account_sync_mappings' does not exist")

    def insert(self, *args, **kwargs):
        raise RuntimeError("relation 'public.crm_account_sync_mappings' does not exist")

    def update(self, *args, **kwargs):
        raise RuntimeError("relation 'public.crm_account_sync_mappings' does not exist")

    def eq(self, *args, **kwargs):
        return self

    def order(self, *args, **kwargs):
        return self

    def execute(self, *args, **kwargs):
        raise RuntimeError("database connection terminated unexpectedly")


class FailingSupabaseMock:
    """Supabase client simulator when database is completely down or unmigrated."""
    def table(self, table_name: str):
        return FailingTableMock()


class WorkingTableMock:
    """Simulates a healthy database table returning predetermined mock records."""
    def __init__(self, data: Optional[List[Dict[str, Any]]] = None):
        self._data = data if data is not None else []

    def select(self, *args, **kwargs):
        return self

    def eq(self, *args, **kwargs):
        return self

    def order(self, *args, **kwargs):
        return self

    def insert(self, record, *args, **kwargs):
        res = MagicMock()
        res.data = [record]
        return res

    def execute(self, *args, **kwargs):
        res = MagicMock()
        res.data = self._data
        return res


class WorkingSupabaseMock:
    """Healthy Supabase client simulator."""
    def __init__(self, data_by_table: Optional[Dict[str, List[Dict[str, Any]]]] = None):
        self.data_by_table = data_by_table or {}

    def table(self, table_name: str):
        return WorkingTableMock(self.data_by_table.get(table_name, []))


@pytest.fixture(autouse=True)
def reset_in_memory_stores():
    """Isolates state mutations across tests by capturing and restoring in-memory copies."""
    orig_accounts = copy.deepcopy(_IN_MEMORY_CRM_ACCOUNTS)
    orig_attributions = copy.deepcopy(_IN_MEMORY_DEAL_ATTRIBUTIONS)
    orig_logs = copy.deepcopy(_IN_MEMORY_SYNC_LOGS)
    yield
    _IN_MEMORY_CRM_ACCOUNTS.clear()
    _IN_MEMORY_CRM_ACCOUNTS.extend(orig_accounts)
    _IN_MEMORY_DEAL_ATTRIBUTIONS.clear()
    _IN_MEMORY_DEAL_ATTRIBUTIONS.extend(orig_attributions)
    _IN_MEMORY_SYNC_LOGS.clear()
    _IN_MEMORY_SYNC_LOGS.extend(orig_logs)


@pytest.fixture
def auth_client():
    """Client configured with FailingSupabaseMock to guarantee zero-migration resilience by default."""
    app.dependency_overrides[get_current_workspace] = lambda: "ws-test-crm"
    app.dependency_overrides[get_service_client] = lambda: FailingSupabaseMock()
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def healthy_client():
    """Client configured with WorkingSupabaseMock for operational DB verification."""
    mock_db = WorkingSupabaseMock({
        "crm_account_sync_mappings": [
            {
                "id": "acc-db-1",
                "workspace_id": "ws-test-crm",
                "domain": "operational-corp.com",
                "company_name": "Operational Corp",
                "crm_provider": "salesforce",
                "crm_company_id": "sfdc-999",
                "lifecycle_stage": "customer",
                "sync_status": "synced"
            }
        ],
        "deal_attributions": [
            {
                "id": "attr-db-1",
                "workspace_id": "ws-test-crm",
                "deal_id": "deal-db-001",
                "deal_name": "DB Enterprise Deal",
                "deal_amount": 120000.0,
                "pipeline_stage": "closed_won",
                "attribution_model": "w_shaped",
                "attributed_pipeline_arr": 120000.0
            }
        ]
    })
    app.dependency_overrides[get_current_workspace] = lambda: "ws-test-crm"
    app.dependency_overrides[get_service_client] = lambda: mock_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


# =============================================================================
# Layer 0: Foundational Layer Tests
# =============================================================================

class TestLayer0FoundationalDomainAndSanitization:
    """Verifies baseline text sanitization and domain parsing logic."""

    def test_normalize_domain_clean(self):
        assert normalize_domain("acmecorp.com") == "acmecorp.com"

    def test_normalize_domain_https_and_www(self):
        assert normalize_domain("https://www.salesforce.com/products/sales-cloud") == "salesforce.com"

    def test_normalize_domain_http_and_query_params(self):
        assert normalize_domain("http://sub.domain.co.uk/leads?utm_source=linkedin&ref=78") == "sub.domain.co.uk"

    def test_normalize_domain_uppercase_and_whitespace(self):
        assert normalize_domain("   STRIPE.COM/ENTERPRISE/  ") == "stripe.com"

    def test_normalize_domain_empty_and_none(self):
        assert normalize_domain("") == ""
        assert normalize_domain(None) == ""

    def test_sanitize_text_clean_value(self):
        assert sanitize_text("Acme Corporation") == "Acme Corporation"

    def test_sanitize_text_empty_and_none(self):
        assert sanitize_text("") == ""
        assert sanitize_text(None) == ""


class TestLayer0FoundationalAttributionModels:
    """Verifies mathematical accuracy of all four attribution models."""

    def test_first_touch_attribution(self):
        touchpoints = [
            {"channel": "linkedin_connection", "campaign": "Tech Execs", "step": 1},
            {"channel": "cold_email", "campaign": "Tech Execs", "step": 2},
            {"channel": "calendar_meeting", "campaign": "Closer", "step": 3}
        ]
        res = calculate_deal_attribution(
            deal_id="deal-101",
            deal_name="Enterprise Rollout",
            deal_amount=100000.0,
            touchpoints=touchpoints,
            model="first_touch",
            workspace_id="ws-test-crm",
            supabase=None
        )
        assert res["attribution_model"] == "first_touch"
        assert res["deal_amount"] == 100000.0
        assert res["touchpoints"][0]["weight"] == 1.0
        assert res["touchpoints"][0]["attributed_amount"] == 100000.0
        assert res["touchpoints"][1]["weight"] == 0.0
        assert res["touchpoints"][1]["attributed_amount"] == 0.0
        assert res["touchpoints"][2]["weight"] == 0.0
        assert res["touchpoints"][2]["attributed_amount"] == 0.0
        total_attributed = sum(tp["attributed_amount"] for tp in res["touchpoints"])
        assert total_attributed == 100000.0

    def test_last_touch_attribution(self):
        touchpoints = [
            {"channel": "linkedin_connection", "campaign": "Tech Execs", "step": 1},
            {"channel": "cold_email", "campaign": "Tech Execs", "step": 2},
            {"channel": "calendar_meeting", "campaign": "Closer", "step": 3}
        ]
        res = calculate_deal_attribution(
            deal_id="deal-102",
            deal_name="Expansion Tier",
            deal_amount=80000.0,
            touchpoints=touchpoints,
            model="last_touch",
            workspace_id="ws-test-crm",
            supabase=None
        )
        assert res["attribution_model"] == "last_touch"
        assert res["touchpoints"][0]["weight"] == 0.0
        assert res["touchpoints"][0]["attributed_amount"] == 0.0
        assert res["touchpoints"][1]["weight"] == 0.0
        assert res["touchpoints"][1]["attributed_amount"] == 0.0
        assert res["touchpoints"][2]["weight"] == 1.0
        assert res["touchpoints"][2]["attributed_amount"] == 80000.0
        total_attributed = sum(tp["attributed_amount"] for tp in res["touchpoints"])
        assert total_attributed == 80000.0

    def test_linear_attribution(self):
        touchpoints = [
            {"channel": "linkedin_inmail", "step": 1},
            {"channel": "email_sequence_1", "step": 2},
            {"channel": "voice_note", "step": 3},
            {"channel": "calendar_invite", "step": 4}
        ]
        res = calculate_deal_attribution(
            deal_id="deal-103",
            deal_name="Team Annual Plan",
            deal_amount=60000.0,
            touchpoints=touchpoints,
            model="linear",
            workspace_id="ws-test-crm",
            supabase=None
        )
        assert res["attribution_model"] == "linear"
        for tp in res["touchpoints"]:
            assert tp["weight"] == 0.25
            assert tp["attributed_amount"] == 15000.0
        total_attributed = sum(tp["attributed_amount"] for tp in res["touchpoints"])
        assert total_attributed == 60000.0

    def test_w_shaped_attribution_single_touch(self):
        touchpoints = [{"channel": "linkedin_direct", "step": 1}]
        res = calculate_deal_attribution(
            deal_id="deal-104",
            deal_name="Single Touch Win",
            deal_amount=40000.0,
            touchpoints=touchpoints,
            model="w_shaped",
            workspace_id="ws-test-crm",
            supabase=None
        )
        assert res["touchpoints"][0]["weight"] == 1.0
        assert res["touchpoints"][0]["attributed_amount"] == 40000.0

    def test_w_shaped_attribution_two_touches(self):
        touchpoints = [
            {"channel": "linkedin_intro", "step": 1},
            {"channel": "closing_call", "step": 2}
        ]
        res = calculate_deal_attribution(
            deal_id="deal-105",
            deal_name="Two Touch Deal",
            deal_amount=50000.0,
            touchpoints=touchpoints,
            model="w_shaped",
            workspace_id="ws-test-crm",
            supabase=None
        )
        assert res["touchpoints"][0]["weight"] == 0.5
        assert res["touchpoints"][0]["attributed_amount"] == 25000.0
        assert res["touchpoints"][1]["weight"] == 0.5
        assert res["touchpoints"][1]["attributed_amount"] == 25000.0

    def test_w_shaped_attribution_multi_touches(self):
        touchpoints = [
            {"channel": "linkedin_connection", "step": 1},
            {"channel": "personalized_email", "step": 2},
            {"channel": "phone_followup", "step": 3},
            {"channel": "calendar_concierge", "step": 4}
        ]
        res = calculate_deal_attribution(
            deal_id="deal-106",
            deal_name="Enterprise Platform Deal",
            deal_amount=100000.0,
            touchpoints=touchpoints,
            model="w_shaped",
            workspace_id="ws-test-crm",
            supabase=None
        )
        # First touch = 40% (40k), Middle touches = 20%/2 = 10% each (10k each), Last touch = 40% (40k)
        assert res["touchpoints"][0]["weight"] == 0.40
        assert res["touchpoints"][0]["attributed_amount"] == 40000.0
        assert res["touchpoints"][1]["weight"] == 0.10
        assert res["touchpoints"][1]["attributed_amount"] == 10000.0
        assert res["touchpoints"][2]["weight"] == 0.10
        assert res["touchpoints"][2]["attributed_amount"] == 10000.0
        assert res["touchpoints"][3]["weight"] == 0.40
        assert res["touchpoints"][3]["attributed_amount"] == 40000.0
        total_attributed = sum(tp["attributed_amount"] for tp in res["touchpoints"])
        assert total_attributed == 100000.0

    def test_attribution_empty_touchpoints_defaults(self):
        res = calculate_deal_attribution(
            deal_id="deal-107",
            deal_name="Inbound Deal",
            deal_amount=30000.0,
            touchpoints=[],
            model="w_shaped",
            workspace_id="ws-test-crm",
            supabase=None
        )
        assert len(res["touchpoints"]) == 1
        assert res["touchpoints"][0]["channel"] == "outbound_campaign"
        assert res["touchpoints"][0]["weight"] == 1.0
        assert res["touchpoints"][0]["attributed_amount"] == 30000.0

    def test_attribution_invalid_model_defaults_to_w_shaped(self):
        res = calculate_deal_attribution(
            deal_id="deal-108",
            deal_name="Custom Model Deal",
            deal_amount=20000.0,
            touchpoints=[{"channel": "email", "step": 1}, {"channel": "call", "step": 2}],
            model="unknown_unsupported_model",
            workspace_id="ws-test-crm",
            supabase=None
        )
        assert res["attribution_model"] == "w_shaped"
        assert res["touchpoints"][0]["weight"] == 0.5
        assert res["touchpoints"][1]["weight"] == 0.5

    def test_attribution_negative_amount_floored(self):
        res = calculate_deal_attribution(
            deal_id="deal-109",
            deal_name="Negative Value Deal",
            deal_amount=-5000.0,
            touchpoints=[{"channel": "email", "step": 1}],
            model="first_touch",
            workspace_id="ws-test-crm",
            supabase=None
        )
        assert res["deal_amount"] == 0.0
        assert res["touchpoints"][0]["attributed_amount"] == 0.0


class TestLayer0FoundationalCRMSyncService:
    """Verifies account sync operations and telemetry aggregation."""

    def test_upsert_synced_account_creates_record(self):
        acc = upsert_synced_account(
            workspace_id="ws-test-crm",
            domain="linear.app",
            company_name="Linear",
            crm_provider="hubspot",
            crm_company_id="hs-linear-01",
            lifecycle_stage="salesqualifiedlead",
            supabase=None
        )
        assert acc["domain"] == "linear.app"
        assert acc["company_name"] == "Linear"
        assert acc["crm_provider"] == "hubspot"
        assert acc["lifecycle_stage"] == "salesqualifiedlead"
        assert acc["sync_status"] == "synced"
        assert "id" in acc
        assert "last_synced_at" in acc

    def test_list_synced_accounts_returns_list(self):
        accounts = list_synced_accounts(workspace_id="ws-test-crm", supabase=None)
        assert isinstance(accounts, list)
        assert len(accounts) >= 1
        assert any(a["domain"] == "acmecorp.com" for a in accounts)

    def test_list_deal_attributions_returns_list(self):
        deals = list_deal_attributions(workspace_id="ws-test-crm", supabase=None)
        assert isinstance(deals, list)
        assert len(deals) >= 1
        assert "deal_id" in deals[0]

    def test_get_crm_sync_telemetry_schema(self):
        telemetry = get_crm_sync_telemetry(workspace_id="ws-test-crm", supabase=None)
        expected_keys = [
            "total_synced_accounts",
            "total_attributed_deals",
            "total_attributed_pipeline_arr",
            "echoes_prevented_count",
            "sync_health_score",
            "primary_crm_connected",
            "last_sync_timestamp"
        ]
        for key in expected_keys:
            assert key in telemetry
        assert telemetry["total_synced_accounts"] >= 1
        assert telemetry["total_attributed_deals"] >= 1
        assert telemetry["total_attributed_pipeline_arr"] > 0.0
        assert telemetry["sync_health_score"] >= 95.0


class TestLayer0FoundationalRouterEndpoints:
    """Verifies all six FastAPI router endpoints mounted at /api/elein/crm-sync/."""

    def test_get_accounts_endpoint(self, auth_client: TestClient):
        res = auth_client.get("/api/elein/crm-sync/accounts")
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert isinstance(data["data"], list)
        assert data["count"] == len(data["data"])

    def test_post_accounts_endpoint(self, auth_client: TestClient):
        res = auth_client.post(
            "/api/elein/crm-sync/accounts",
            json={
                "domain": "https://www.snowflake.com",
                "company_name": "Snowflake, Inc.",
                "crm_provider": "salesforce",
                "crm_company_id": "sfdc-snow-1",
                "lifecycle_stage": "opportunity"
            }
        )
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["data"]["domain"] == "snowflake.com"
        assert data["data"]["company_name"] == "Snowflake, Inc."
        assert "Successfully mapped" in data["message"]

    def test_webhook_inbound_endpoint(self, auth_client: TestClient):
        res = auth_client.post(
            "/api/elein/crm-sync/webhook-inbound",
            json={
                "event_type": "company.stage_change",
                "payload": {
                    "domain": "retune.io",
                    "company_name": "Retune",
                    "stage": "lead"
                }
            }
        )
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["data"]["status"] == "success"
        assert "Successfully processed" in data["data"]["message"]

    def test_calculate_attribution_endpoint(self, auth_client: TestClient):
        res = auth_client.post(
            "/api/elein/crm-sync/calculate-attribution",
            json={
                "deal_id": "deal-api-01",
                "deal_name": "API Enterprise Pilot",
                "deal_amount": 50000.0,
                "touchpoints": [
                    {"channel": "linkedin", "step": 1},
                    {"channel": "email", "step": 2}
                ],
                "model": "w_shaped"
            }
        )
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["data"]["deal_id"] == "deal-api-01"
        assert data["data"]["deal_amount"] == 50000.0
        assert data["data"]["attribution_model"] == "w_shaped"

    def test_get_attributions_endpoint(self, auth_client: TestClient):
        res = auth_client.get("/api/elein/crm-sync/attributions")
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert isinstance(data["data"], list)
        assert data["count"] == len(data["data"])

    def test_get_telemetry_endpoint(self, auth_client: TestClient):
        res = auth_client.get("/api/elein/crm-sync/telemetry")
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert "total_synced_accounts" in data["data"]
        assert "echoes_prevented_count" in data["data"]


# =============================================================================
# Layer 1: Environmental Failure Analysis Tests
# =============================================================================

class TestLayer1EnvironmentalFailureAndResilience:
    """
    Paranoia Layer 1: Simulates database outages, zero-migration states,
    echo loops, and auto-halting of campaigns when external systems ping back.
    """

    def test_failing_supabase_mock_list_accounts_fallback(self):
        """Zero-migration test: Missing table in Supabase must fall back cleanly to memory."""
        failing_mock = FailingSupabaseMock()
        accounts = list_synced_accounts(workspace_id="ws-test-crm", supabase=failing_mock)
        assert isinstance(accounts, list)
        assert len(accounts) >= 1

    def test_failing_supabase_mock_upsert_account_fallback(self):
        """Zero-migration test: Insert failure on unmigrated DB must save to in-memory fallback."""
        failing_mock = FailingSupabaseMock()
        acc = upsert_synced_account(
            workspace_id="ws-test-crm",
            domain="resilience-corp.com",
            company_name="Resilience Corp",
            crm_provider="hubspot",
            crm_company_id="hs-res-1",
            lifecycle_stage="lead",
            supabase=failing_mock
        )
        assert acc["domain"] == "resilience-corp.com"
        # Confirm it exists in the in-memory accounts list
        accounts = list_synced_accounts(workspace_id="ws-test-crm", supabase=failing_mock)
        assert any(a["domain"] == "resilience-corp.com" for a in accounts)

    def test_failing_supabase_mock_calculate_attribution_fallback(self):
        """Zero-migration test: Table failure during attribution insert must not crash."""
        failing_mock = FailingSupabaseMock()
        record = calculate_deal_attribution(
            deal_id="deal-fail-001",
            deal_name="Resilient Deal",
            deal_amount=45000.0,
            touchpoints=[{"channel": "email", "step": 1}],
            model="first_touch",
            workspace_id="ws-test-crm",
            supabase=failing_mock
        )
        assert record["deal_id"] == "deal-fail-001"
        assert record["deal_amount"] == 45000.0
        # Stored in memory
        deals = list_deal_attributions(workspace_id="ws-test-crm", supabase=failing_mock)
        assert any(d["deal_id"] == "deal-fail-001" for d in deals)

    def test_failing_supabase_mock_list_attributions_fallback(self):
        failing_mock = FailingSupabaseMock()
        deals = list_deal_attributions(workspace_id="ws-test-crm", supabase=failing_mock)
        assert isinstance(deals, list)
        assert len(deals) >= 1

    def test_working_supabase_mock_persists_records(self, healthy_client: TestClient):
        """Operational test: When DB is healthy, data is retrieved from Supabase."""
        res = healthy_client.get("/api/elein/crm-sync/accounts")
        assert res.status_code == 200
        data = res.json()
        assert any(a["domain"] == "operational-corp.com" for a in data["data"])

    def test_echo_loop_detection_direct(self):
        """Tests deterministic SHA256 payload hashing and echo detection."""
        payload_1 = {"domain": "acme.com", "stage": "lead", "id": 123}
        payload_2 = {"id": 123, "stage": "lead", "domain": "acme.com"}  # Different key order
        hash_1 = calculate_payload_hash(payload_1)
        hash_2 = calculate_payload_hash(payload_2)
        assert hash_1 == hash_2  # Canonical sorting ensures hash match

        assert is_echo_loop(payload_1, last_hash=hash_1) is True
        assert is_echo_loop(payload_1, last_hash="different_hash") is False
        assert is_echo_loop(payload_1, last_hash=None) is False

    def test_process_inbound_crm_event_echo_suppression(self):
        """Tests that duplicate webhook payloads within debounce window are suppressed."""
        payload = {
            "domain": "datadoghq.com",
            "company_name": "Datadog",
            "stage": "lead"
        }
        res_first = process_inbound_crm_event(
            event_type="lead.update",
            payload=payload,
            workspace_id="ws-test-crm",
            supabase=None
        )
        assert res_first["status"] == "success"

        # Fire the exact same event again
        res_second = process_inbound_crm_event(
            event_type="lead.update",
            payload=payload,
            workspace_id="ws-test-crm",
            supabase=None
        )
        assert res_second["status"] == "skipped_echo"
        assert "Echo loop suppressed" in res_second["message"]

    def test_echo_suppression_increments_telemetry(self):
        """Verifies telemetry counts echo-suppression events accurately."""
        initial_telemetry = get_crm_sync_telemetry(workspace_id="ws-test-crm", supabase=None)
        initial_echoes = initial_telemetry["echoes_prevented_count"]

        payload = {"domain": "echo-test.com", "val": "duplicate-burst"}
        process_inbound_crm_event("burst.test", payload)
        process_inbound_crm_event("burst.test", payload)  # Trigger echo suppression

        updated_telemetry = get_crm_sync_telemetry(workspace_id="ws-test-crm", supabase=None)
        assert updated_telemetry["echoes_prevented_count"] == initial_echoes + 1

    def test_campaign_auto_halting_on_closed_won(self):
        """When CRM signals closed_won, campaign must auto-halt and promote account to customer."""
        upsert_synced_account(
            workspace_id="ws-test-crm",
            domain="target-customer.com",
            company_name="Target Customer",
            lifecycle_stage="lead",
            supabase=None
        )

        inbound_event = {
            "domain": "target-customer.com",
            "deal_stage": "closed_won"
        }
        res = process_inbound_crm_event(
            event_type="deal.won",
            payload=inbound_event,
            workspace_id="ws-test-crm",
            supabase=None
        )
        assert res["status"] == "success"
        assert res["campaigns_halted"] == 1

        accounts = list_synced_accounts(workspace_id="ws-test-crm", supabase=None)
        matched = next(a for a in accounts if a["domain"] == "target-customer.com")
        assert matched["lifecycle_stage"] == "customer"

    def test_campaign_auto_halting_on_opportunity(self):
        """When CRM signals opportunity, campaign must auto-halt and promote account to opportunity."""
        upsert_synced_account(
            workspace_id="ws-test-crm",
            domain="active-prospect.com",
            company_name="Active Prospect",
            lifecycle_stage="lead",
            supabase=None
        )

        inbound_event = {
            "domain": "active-prospect.com",
            "stage": "opportunity"
        }
        res = process_inbound_crm_event(
            event_type="deal.created",
            payload=inbound_event,
            workspace_id="ws-test-crm",
            supabase=None
        )
        assert res["status"] == "success"
        assert res["campaigns_halted"] == 1

        accounts = list_synced_accounts(workspace_id="ws-test-crm", supabase=None)
        matched = next(a for a in accounts if a["domain"] == "active-prospect.com")
        assert matched["lifecycle_stage"] == "opportunity"

    def test_inbound_deal_event_triggers_instant_attribution(self):
        """Inbound event with deal_id and amount > 0 must trigger immediate attribution calculation."""
        inbound_deal = {
            "domain": "acmecorp.com",
            "company_name": "Acme Corporation",
            "deal_id": "deal-instant-01",
            "deal_amount": 95000.0,
            "stage": "closed_won",
            "touchpoints": [
                {"channel": "linkedin", "step": 1},
                {"channel": "email", "step": 2},
                {"channel": "demo_call", "step": 3}
            ]
        }
        res = process_inbound_crm_event(
            event_type="deal.won",
            payload=inbound_deal,
            workspace_id="ws-test-crm",
            supabase=None
        )
        assert res["status"] == "success"
        deals = list_deal_attributions(workspace_id="ws-test-crm", supabase=None)
        matched_deal = next((d for d in deals if d["deal_id"] == "deal-instant-01"), None)
        assert matched_deal is not None
        assert matched_deal["deal_amount"] == 95000.0
        assert matched_deal["attribution_model"] == "w_shaped"


# =============================================================================
# Layer 2: Human Paranoia & Security Hardening Tests
# =============================================================================

class TestLayer2HumanParanoiaAndSecurity:
    """
    Paranoia Layer 2: Prevents human errors, malicious inputs, spreadsheet formula
    injections, extreme domain formats, and rapid double-click bursts.
    """

    def test_formula_injection_sanitization_prefixes(self):
        """Neutralizes CSV/Excel formula injection vectors (=, +, -, @, \t, \r)."""
        assert sanitize_text("=cmd|' /C calc'!A0") == "cmd|' /C calc'!A0"
        assert sanitize_text("+HYPERLINK('http://malicious.ru')") == "HYPERLINK('http://malicious.ru')"
        assert sanitize_text("-SUM(A1:A10)") == "SUM(A1:A10)"
        assert sanitize_text("@admin_override") == "admin_override"
        assert sanitize_text("\tmalicious_tab\r") == "malicious_tab"
        assert sanitize_text("===+++@@@multiple_prefix") == "multiple_prefix"
        assert sanitize_text("Normal Account Name") == "Normal Account Name"

    def test_upsert_account_neutralizes_formula_injection(self):
        """Ensures formula injection in company name is stripped during account upsert."""
        acc = upsert_synced_account(
            workspace_id="ws-test-crm",
            domain="evilcorp.com",
            company_name="=2+5; DROP TABLE",
            crm_provider="hubspot",
            supabase=None
        )
        assert acc["company_name"] == "2+5; DROP TABLE"
        assert not acc["company_name"].startswith("=")

    def test_deal_attribution_neutralizes_formula_injection(self):
        """Ensures formula injection in deal name is stripped during attribution calculation."""
        res = calculate_deal_attribution(
            deal_id="deal-sec-01",
            deal_name="+123456 - Evil Deal",
            deal_amount=15000.0,
            touchpoints=[{"channel": "email", "step": 1}],
            supabase=None
        )
        assert not res["deal_name"].startswith("+")
        assert res["deal_name"] == "123456 - Evil Deal"

    def test_extreme_and_messy_domain_inputs(self):
        """Handles human formatting errors in domain names."""
        assert normalize_domain("   HTTPS://WWW.SubDomain.Enterprise-Tech.co.uk/path/to/page?utm_campaign=xyz#fragment   ") == "subdomain.enterprise-tech.co.uk"
        assert normalize_domain("HTTP://COMPANY.IO/") == "company.io"
        assert normalize_domain("www.notion.so?query=1") == "notion.so"
        assert normalize_domain("   ") == ""
        assert normalize_domain(None) == ""

    def test_provider_whitelist_sanitization(self):
        """Unrecognized CRM providers safely fall back to 'hubspot'."""
        acc = upsert_synced_account(
            workspace_id="ws-test-crm",
            domain="provider-test.com",
            company_name="Provider Test",
            crm_provider="malicious_or_unknown_provider",
            supabase=None
        )
        assert acc["crm_provider"] == "hubspot"

    def test_lifecycle_stage_whitelist_sanitization(self):
        """Unrecognized lifecycle stages safely fall back to 'lead'."""
        acc = upsert_synced_account(
            workspace_id="ws-test-crm",
            domain="stage-test.com",
            company_name="Stage Test",
            lifecycle_stage="super_admin_stage_override",
            supabase=None
        )
        assert acc["lifecycle_stage"] == "lead"

    def test_rapid_double_submission_via_api(self, auth_client: TestClient):
        """Simulates rapid human double-click on webhook trigger or CRM burst sync."""
        payload = {
            "event_type": "contact.created",
            "payload": {
                "domain": "doubleclick.com",
                "company_name": "Double Click",
                "stage": "lead"
            }
        }
        res_1 = auth_client.post("/api/elein/crm-sync/webhook-inbound", json=payload)
        assert res_1.status_code == 200
        assert res_1.json()["data"]["status"] == "success"

        # Immediate repeat click
        res_2 = auth_client.post("/api/elein/crm-sync/webhook-inbound", json=payload)
        assert res_2.status_code == 200
        assert res_2.json()["data"]["status"] == "skipped_echo"

    def test_router_validation_error_on_missing_fields(self, auth_client: TestClient):
        """Missing required payload fields returns HTTP 422 Unprocessable Entity, not 500."""
        # Missing domain & company_name
        res_acc = auth_client.post("/api/elein/crm-sync/accounts", json={})
        assert res_acc.status_code == 422

        # Missing deal_id & deal_name
        res_attr = auth_client.post("/api/elein/crm-sync/calculate-attribution", json={"deal_amount": 100})
        assert res_attr.status_code == 422

    def test_negative_deal_amount_sanitization_via_api(self, auth_client: TestClient):
        """Negative deal amounts submitted by human error are floored to zero."""
        res = auth_client.post(
            "/api/elein/crm-sync/calculate-attribution",
            json={
                "deal_id": "deal-neg-api",
                "deal_name": "Negative Deal",
                "deal_amount": -100000.0,
                "touchpoints": [{"channel": "email", "step": 1}]
            }
        )
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["deal_amount"] == 0.0
        assert data["attributed_pipeline_arr"] == 0.0

    def test_upsert_deduplication_and_delete_account_endpoint(self, auth_client: TestClient):
        """Layer 1 & 2: Upserting same domain deduplicates in-place, and DELETE endpoint removes mapping with tenant isolation."""
        res1 = auth_client.post(
            "/api/elein/crm-sync/accounts",
            json={
                "domain": "https://www.dedupe-corp.io",
                "company_name": "Dedupe Corp v1",
                "crm_provider": "hubspot",
                "crm_company_id": "hs-dedupe-1",
                "lifecycle_stage": "lead"
            }
        )
        assert res1.status_code == 200
        acc_id = res1.json()["data"]["id"]

        res2 = auth_client.post(
            "/api/elein/crm-sync/accounts",
            json={
                "domain": "dedupe-corp.io",
                "company_name": "Dedupe Corp v2",
                "crm_provider": "salesforce",
                "crm_company_id": "sfdc-dedupe-2",
                "lifecycle_stage": "opportunity"
            }
        )
        assert res2.status_code == 200
        assert res2.json()["data"]["id"] == acc_id
        assert res2.json()["data"]["company_name"] == "Dedupe Corp v2"

        # Delete the account
        del_res = auth_client.delete(f"/api/elein/crm-sync/accounts/{acc_id}")
        assert del_res.status_code == 200
        assert del_res.json()["data"]["deleted"] is True
        assert del_res.json()["data"]["removed_in_memory"] is True

        # Idempotent delete again reports removed_in_memory=False
        del_res_again = auth_client.delete(f"/api/elein/crm-sync/accounts/{acc_id}")
        assert del_res_again.status_code == 200
        assert del_res_again.json()["data"]["removed_in_memory"] is False

    def test_export_attributions_csv_endpoint_formula_defense(self, auth_client: TestClient):
        """Layer 0 & 2: Exports deal attributions as CSV with formula-injection protection."""
        from campaigns.backend.services.crm_attribution_service import sanitize_csv_field
        assert sanitize_csv_field("=SUM(A1:A10)") == '"\'=SUM(A1:A10)"'
        assert sanitize_csv_field("@malicious") == '"\'@malicious"'

        res = auth_client.get("/api/elein/crm-sync/attributions/export-csv")
        assert res.status_code == 200
        assert "text/csv" in res.headers.get("content-type", "")
        csv_text = res.text
        assert "Attribution ID,Deal ID,Deal Name,Deal Amount (USD)" in csv_text
        assert "w_shaped" in csv_text

