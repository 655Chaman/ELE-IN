import pytest
from starlette.testclient import TestClient

from core.backend.main import app
from core.backend.api.auth_dep import get_current_workspace, get_service_client
from campaigns.backend.services.warmup_service import (
    calculate_daily_ramp_limit,
    audit_domain_dns_health,
    generate_swarm_conversation,
    simulate_swarm_cycle,
    list_warmup_mailboxes,
    create_warmup_mailbox,
    toggle_warmup_status,
    get_warmup_telemetry,
    normalize_domain,
    sanitize_text
)


class FailingTableMock:
    """Simulates missing Supabase table (Zero-Migration resilience)."""
    def select(self, *args, **kwargs):
        raise RuntimeError("relation 'public.warmup_mailboxes' does not exist")
    def insert(self, *args, **kwargs):
        raise RuntimeError("relation 'public.warmup_mailboxes' does not exist")
    def update(self, *args, **kwargs):
        raise RuntimeError("relation 'public.warmup_mailboxes' does not exist")


class FailingSupabaseMock:
    def table(self, table_name: str):
        return FailingTableMock()


@pytest.fixture
def auth_client():
    app.dependency_overrides[get_current_workspace] = lambda: "ws-test-warmup"
    app.dependency_overrides[get_service_client] = lambda: FailingSupabaseMock()
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


class TestWarmupPacingAndCalculations:
    def test_daily_ramp_limits_capped_at_50(self):
        # Day 1 balanced -> 7
        assert calculate_daily_ramp_limit(1, "balanced", 40) == 7
        # Day 10 balanced -> 25
        assert calculate_daily_ramp_limit(10, "balanced", 40) == 25
        # Day 100 balanced -> strictly capped at 40 (or 50 absolute max)
        assert calculate_daily_ramp_limit(100, "balanced", 40) == 40
        assert calculate_daily_ramp_limit(100, "balanced", 60) == 50

    def test_ramp_strategies(self):
        # Gentle: starts at 3, +1 every 2 days
        assert calculate_daily_ramp_limit(1, "gentle", 30) == 3
        assert calculate_daily_ramp_limit(4, "gentle", 30) == 5
        # Aggressive: starts at 8, +3 every day
        assert calculate_daily_ramp_limit(1, "aggressive", 30) == 11
        assert calculate_daily_ramp_limit(5, "aggressive", 30) == 23


class TestDnsAuditorAndSwarmGenerator:
    def test_dns_health_audit_resolution(self):
        audit = audit_domain_dns_health("https://www.outbound-scale.com", workspace_id="ws-test-warmup", supabase=None)
        assert audit["domain"] == "outbound-scale.com"
        assert audit["spf_valid"] is True
        assert audit["dkim_valid"] is True
        assert audit["dmarc_valid"] is True
        assert audit["mx_valid"] is True
        assert audit["overall_dns_health_score"] == 100

    def test_swarm_conversation_generation_and_sanitization(self):
        conv = generate_swarm_conversation("=Alex Mercer", "@Dana Scully")
        assert "Alex" in conv["body"] or "Dana" in conv["body"]
        assert len(conv["subject"]) > 5
        assert len(conv["reply"]) > 5


class TestWarmupServiceFleetOperations:
    def test_create_and_toggle_mailbox_with_fallback(self):
        created = create_warmup_mailbox(
            workspace_id="ws-test-warmup",
            email_address="jordan@b2b-outbound.org",
            sender_name="Jordan Belfort",
            provider="google_workspace",
            ramp_strategy="balanced",
            max_daily_limit=35,
            supabase=None
        )
        assert created["email_address"] == "jordan@b2b-outbound.org"
        assert created["warmup_status"] == "warming"
        assert created["current_daily_limit"] == 7

        toggled = toggle_warmup_status(
            mailbox_id=created["id"],
            workspace_id="ws-test-warmup",
            new_status="paused",
            supabase=None
        )
        assert toggled["warmup_status"] == "paused"

    def test_simulate_swarm_cycle(self):
        result = simulate_swarm_cycle(workspace_id="ws-test-warmup", supabase=None)
        assert result["success"] is True
        assert result["exchanges_sent"] >= 1
        assert result["rescued_from_spam"] >= 1


class TestWarmupEndpoints:
    def test_get_mailboxes_endpoint(self, auth_client: TestClient):
        res = auth_client.get("/api/elein/warmup/mailboxes")
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert isinstance(data["data"], list)

    def test_create_mailbox_endpoint(self, auth_client: TestClient):
        res = auth_client.post(
            "/api/elein/warmup/mailboxes",
            json={
                "email_address": "test-ae@acme-corp.com",
                "sender_name": "Test AE",
                "provider": "google_workspace",
                "ramp_strategy": "gentle",
                "max_daily_limit": 30
            }
        )
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["data"]["email_address"] == "test-ae@acme-corp.com"

    def test_dns_audit_endpoint(self, auth_client: TestClient):
        res = auth_client.post(
            "/api/elein/warmup/dns-audit",
            json={"domain": "https://acme-corp.com/path"}
        )
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["data"]["domain"] == "acme-corp.com"
        assert data["data"]["overall_dns_health_score"] == 100

    def test_simulate_swarm_endpoint(self, auth_client: TestClient):
        res = auth_client.post("/api/elein/warmup/simulate-swarm")
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert "exchanges_sent" in data["data"]

    def test_telemetry_endpoint(self, auth_client: TestClient):
        res = auth_client.get("/api/elein/warmup/telemetry")
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert "average_health_score" in data["data"]
        assert "average_inbox_placement_pct" in data["data"]

    def test_deduplicate_and_delete_mailbox_endpoint(self, auth_client: TestClient):
        res1 = auth_client.post(
            "/api/elein/warmup/mailboxes",
            json={
                "email_address": "dedupe-box@acme-corp.com",
                "sender_name": "Dedupe V1",
                "provider": "google_workspace",
                "ramp_strategy": "balanced",
                "max_daily_limit": 35
            }
        )
        assert res1.status_code == 200
        mb_id = res1.json()["data"]["id"]

        res2 = auth_client.post(
            "/api/elein/warmup/mailboxes",
            json={
                "email_address": "DEDUPE-BOX@acme-corp.com",
                "sender_name": "Dedupe V2",
                "provider": "microsoft_365",
                "ramp_strategy": "aggressive",
                "max_daily_limit": 45
            }
        )
        assert res2.status_code == 200
        assert res2.json()["data"]["id"] == mb_id
        assert res2.json()["data"]["sender_name"] == "Dedupe V2"

        del_res = auth_client.delete(f"/api/elein/warmup/mailboxes/{mb_id}")
        assert del_res.status_code == 200
        assert del_res.json()["data"]["deleted"] is True
        assert del_res.json()["data"]["removed_in_memory"] is True

        del_res_again = auth_client.delete(f"/api/elein/warmup/mailboxes/{mb_id}")
        assert del_res_again.status_code == 200
        assert del_res_again.json()["data"]["removed_in_memory"] is False

    def test_export_warmup_csv_endpoint_and_formula_defense(self, auth_client: TestClient):
        from campaigns.backend.services.warmup_service import sanitize_csv_field
        assert sanitize_csv_field("=cmd|' /C calc'!A0") == '"\'=cmd|\' /C calc\'!A0"'
        assert sanitize_csv_field("+SUM(1,2)") == '"\'+SUM(1,2)"'

        res = auth_client.get("/api/elein/warmup/mailboxes/export-csv")
        assert res.status_code == 200
        assert "text/csv" in res.headers.get("content-type", "")
        assert "Mailbox ID,Email Address,Sender Name,Provider" in res.text

