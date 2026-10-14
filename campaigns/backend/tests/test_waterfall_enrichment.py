import pytest
from starlette.testclient import TestClient

from core.backend.main import app
from core.backend.api.auth_dep import get_current_workspace, get_service_client
from campaigns.backend.services.waterfall_enrichment_service import (
    normalize_domain,
    sanitize_text,
    execute_waterfall_enrichment,
    list_waterfall_runs,
    get_vendor_configs,
    get_waterfall_telemetry
)


class FailingTableMock:
    """Simulates missing Supabase table (Zero-Migration resilience)."""
    def select(self, *args, **kwargs):
        raise RuntimeError("relation 'public.waterfall_enrichment_runs' does not exist")
    def insert(self, *args, **kwargs):
        raise RuntimeError("relation 'public.waterfall_enrichment_runs' does not exist")
    def update(self, *args, **kwargs):
        raise RuntimeError("relation 'public.waterfall_enrichment_runs' does not exist")


class FailingSupabaseMock:
    def table(self, table_name: str):
        return FailingTableMock()


@pytest.fixture
def auth_client():
    app.dependency_overrides[get_current_workspace] = lambda: "ws-test-waterfall"
    app.dependency_overrides[get_service_client] = lambda: FailingSupabaseMock()
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


class TestDomainAndNameNormalization:
    def test_normalize_messy_domains(self):
        assert normalize_domain("https://www.stripe.com/enterprise?utm_source=li") == "stripe.com"
        assert normalize_domain("http://github.com/") == "github.com"
        assert normalize_domain("LINEAR.APP") == "linear.app"

    def test_sanitize_formula_injection(self):
        assert sanitize_text("=cmd|' /C calc'!A0") == "cmd|' /C calc'!A0"
        assert sanitize_text("+123456") == "123456"
        assert sanitize_text("@admin") == "admin"


class TestWaterfallCascadeExecution:
    def test_internal_cache_hit_zero_cost(self):
        run = execute_waterfall_enrichment(
            lead_name="Satya Nadella",
            company_domain="microsoft.com",
            workspace_id="ws-test-waterfall",
            supabase=None
        )
        assert run["resolved_email"] == "satyan@microsoft.com"
        assert run["resolved_vendor"] == "internal_cache"
        assert run["total_cost_credits"] == 0.0
        assert run["deliverability_status"] == "valid"
        assert len(run["vendors_queried"]) == 1

    def test_apollo_cascade_hit(self):
        run = execute_waterfall_enrichment(
            lead_name="Patrick Collison",
            company_domain="stripe.com",
            workspace_id="ws-test-waterfall",
            supabase=None
        )
        assert run["resolved_email"] == "patrick.collison@stripe.com"
        assert run["resolved_vendor"] == "apollo"
        assert run["total_cost_credits"] == 1.0  # internal_cache (0) + apollo (1.0)
        assert run["deliverability_status"] == "valid"
        assert len(run["vendors_queried"]) == 2

    def test_catchall_domain_classification(self):
        run = execute_waterfall_enrichment(
            lead_name="Sam Altman",
            company_domain="catchall-domain.com",
            workspace_id="ws-test-waterfall",
            custom_sequence=["smtp_handshake"],
            supabase=None
        )
        assert run["deliverability_status"] == "risky_catchall"
        assert run["confidence_score"] <= 75


class TestWaterfallEndpoints:
    def test_enrich_single_endpoint(self, auth_client: TestClient):
        res = auth_client.post(
            "/api/elein/waterfall/enrich-single",
            json={
                "lead_name": "Marc Benioff",
                "company_domain": "https://www.salesforce.com"
            }
        )
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["company_domain"] == "salesforce.com"
        assert data["deliverability_status"] == "valid"
        assert "@salesforce.com" in data["resolved_email"]

    def test_enrich_batch_endpoint(self, auth_client: TestClient):
        res = auth_client.post(
            "/api/elein/waterfall/enrich-batch",
            json={
                "leads": [
                    {"name": "Satya Nadella", "domain": "microsoft.com"},
                    {"name": "Marc Benioff", "domain": "salesforce.com"}
                ]
            }
        )
        assert res.status_code == 200
        body = res.json()
        assert body["total_processed"] == 2
        assert body["matched_count"] == 2

    def test_runs_and_configs_endpoints(self, auth_client: TestClient):
        # Runs
        runs_res = auth_client.get("/api/elein/waterfall/runs")
        assert runs_res.status_code == 200
        assert runs_res.json()["total"] >= 1

        # Configs
        cfgs_res = auth_client.get("/api/elein/waterfall/configs")
        assert cfgs_res.status_code == 200
        configs = cfgs_res.json()["configs"]
        assert len(configs) >= 4
        assert configs[0]["vendor_slug"] == "internal_cache"

    def test_telemetry_endpoint(self, auth_client: TestClient):
        tel_res = auth_client.get("/api/elein/waterfall/telemetry")
        assert tel_res.status_code == 200
        t = tel_res.json()["telemetry"]
        assert t["overall_match_rate_pct"] > 50.0
        assert t["waterfall_lift_pct"] >= 0.0


class TestWaterfallCreditSecurity:
    """Paranoia Layer 0, 1 & 2: Tests credit security, tier gates, and deduction mechanics."""

    def test_free_tier_blocked_from_single_enrichment(self):
        app.dependency_overrides[get_current_workspace] = lambda: "ws-test-free"
        app.dependency_overrides[get_service_client] = lambda: FailingSupabaseMock()
        with TestClient(app) as client:
            res = client.post(
                "/api/elein/waterfall/enrich-single",
                json={
                    "lead_name": "Satya Nadella",
                    "company_domain": "microsoft.com"
                }
            )
            assert res.status_code == 403
            err_msg = res.json().get("error", {}).get("message", "") or res.json().get("detail", "")
            assert "Pro or Enterprise plan" in err_msg
        app.dependency_overrides.clear()

    def test_free_tier_blocked_from_batch_enrichment(self):
        app.dependency_overrides[get_current_workspace] = lambda: "ws-test-free"
        app.dependency_overrides[get_service_client] = lambda: FailingSupabaseMock()
        with TestClient(app) as client:
            res = client.post(
                "/api/elein/waterfall/enrich-batch",
                json={
                    "leads": [{"name": "Satya Nadella", "domain": "microsoft.com"}]
                }
            )
            assert res.status_code == 403
            err_msg = res.json().get("error", {}).get("message", "") or res.json().get("detail", "")
            assert "Pro or Enterprise plan" in err_msg
        app.dependency_overrides.clear()

    def test_negative_credit_debt_blocked_from_single_enrichment(self):
        app.dependency_overrides[get_current_workspace] = lambda: "ws-test-debt"
        app.dependency_overrides[get_service_client] = lambda: FailingSupabaseMock()
        with TestClient(app) as client:
            res = client.post(
                "/api/elein/waterfall/enrich-single",
                json={
                    "lead_name": "Satya Nadella",
                    "company_domain": "microsoft.com"
                }
            )
            assert res.status_code == 402
            err_msg = res.json().get("error", {}).get("message", "") or res.json().get("detail", "")
            assert "Insufficient credit balance" in err_msg
        app.dependency_overrides.clear()

    def test_negative_credit_debt_blocked_from_batch_enrichment(self):
        app.dependency_overrides[get_current_workspace] = lambda: "ws-test-debt"
        app.dependency_overrides[get_service_client] = lambda: FailingSupabaseMock()
        with TestClient(app) as client:
            res = client.post(
                "/api/elein/waterfall/enrich-batch",
                json={
                    "leads": [{"name": "Satya Nadella", "domain": "microsoft.com"}]
                }
            )
            assert res.status_code == 402
            err_msg = res.json().get("error", {}).get("message", "") or res.json().get("detail", "")
            assert "Insufficient credit balance" in err_msg
        app.dependency_overrides.clear()

    def test_empty_batch_returns_clean_zero_result(self, auth_client: TestClient):
        res = auth_client.post(
            "/api/elein/waterfall/enrich-batch",
            json={"leads": []}
        )
        assert res.status_code == 200
        body = res.json()
        assert body["total_processed"] == 0
        assert body["matched_count"] == 0
        assert body["stopped_early"] is False

    def test_zero_cost_does_not_deduct_credits(self):
        run = execute_waterfall_enrichment(
            lead_name="Satya Nadella",
            company_domain="microsoft.com",
            workspace_id="ws-test-waterfall",
            supabase=None
        )
        assert run["total_cost_credits"] == 0.0
        assert run["credits_deducted"] == 0
        assert run["credit_deduction_status"] == "zero_cost"

    def test_apollo_hit_records_credit_deduction(self):
        run = execute_waterfall_enrichment(
            lead_name="Patrick Collison",
            company_domain="stripe.com",
            workspace_id="ws-test-waterfall",
            supabase=None
        )
        assert run["total_cost_credits"] == 1.0
        assert run["credits_deducted"] == 1
        assert run["credit_deduction_status"] == "success"
