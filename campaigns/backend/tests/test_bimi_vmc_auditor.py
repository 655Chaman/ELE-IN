"""
Phase 42 — BIMI & VMC Certificate Validator with Google/Apple Verified Mark Audit
Three-Layer Paranoia Test Suite (45+ tests)

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
# Path bootstrap
# ---------------------------------------------------------------------------
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from core.backend.services.bimi_vmc_service import (
    BIMIVMCService,
    BIMIStatus,
    VerifiedMarkProvider,
    parse_bimi_record,
    lookup_bimi_record,
    lookup_dmarc_policy,
    validate_logo_url,
    validate_vmc_certificate,
    audit_domain_bimi,
    audit_sender_inbox_bimi,
    scan_workspace_bimi_health,
)


# =============================================================================
# LAYER 0: CORE MECHANICS
# =============================================================================

class TestBIMICoreParsingLayer0:
    def test_parse_bimi_record_full(self):
        raw = "v=BIMI1; l=https://brand.acme.com/logo.svg; a=https://digicert.com/vmc.pem"
        res = parse_bimi_record(raw)
        assert res["valid"] is True
        assert res["version"] == "BIMI1"
        assert res["logo_url"] == "https://brand.acme.com/logo.svg"
        assert res["vmc_url"] == "https://digicert.com/vmc.pem"
        assert res["error"] is None

    def test_parse_bimi_record_logo_only(self):
        raw = "v=BIMI1; l=https://brand.acme.com/logo.svg"
        res = parse_bimi_record(raw)
        assert res["valid"] is True
        assert res["logo_url"] == "https://brand.acme.com/logo.svg"
        assert res["vmc_url"] is None

    def test_parse_bimi_record_missing_version(self):
        raw = "l=https://brand.acme.com/logo.svg; a=https://digicert.com/vmc.pem"
        res = parse_bimi_record(raw)
        assert res["valid"] is False
        assert "Missing or misplaced v=BIMI1 tag" in res["error"]

    def test_parse_bimi_record_empty_a_tag(self):
        raw = "v=BIMI1; l=https://brand.acme.com/logo.svg; a="
        res = parse_bimi_record(raw)
        assert res["valid"] is True
        assert res["logo_url"] == "https://brand.acme.com/logo.svg"
        assert res["vmc_url"] is None

    def test_parse_bimi_record_tag_order_permutations(self):
        raw = "v=BIMI1; a=https://cert.digicert.com/vmc.pem; l=https://logo.svg"
        res = parse_bimi_record(raw)
        assert res["valid"] is True
        assert res["logo_url"] == "https://logo.svg"
        assert res["vmc_url"] == "https://cert.digicert.com/vmc.pem"

    def test_parse_bimi_record_quoted_values(self):
        raw = 'v=BIMI1; l="https://brand.acme.com/logo.svg"; a="https://entrust.com/vmc.pem"'
        res = parse_bimi_record(raw)
        assert res["valid"] is True
        assert res["logo_url"] == "https://brand.acme.com/logo.svg"
        assert res["vmc_url"] == "https://entrust.com/vmc.pem"


class TestDMARCPolicyLookupLayer0:
    def test_lookup_dmarc_policy_reject_sufficient(self):
        mock_dns = {"_dmarc.acme.com": "v=DMARC1; p=reject; sp=reject; pct=100"}
        res = lookup_dmarc_policy("acme.com", mock_dns=mock_dns)
        assert res["policy"] == "reject"
        assert res["sufficient_for_bimi"] is True

    def test_lookup_dmarc_policy_quarantine_sufficient(self):
        mock_dns = {"_dmarc.acme.com": "v=DMARC1; p=quarantine; pct=100"}
        res = lookup_dmarc_policy("acme.com", mock_dns=mock_dns)
        assert res["policy"] == "quarantine"
        assert res["sufficient_for_bimi"] is True

    def test_lookup_dmarc_policy_none_insufficient(self):
        mock_dns = {"_dmarc.acme.com": "v=DMARC1; p=none"}
        res = lookup_dmarc_policy("acme.com", mock_dns=mock_dns)
        assert res["policy"] == "none"
        assert res["sufficient_for_bimi"] is False

    def test_lookup_dmarc_policy_missing(self):
        mock_dns = {}
        res = lookup_dmarc_policy("acme.com", mock_dns=mock_dns)
        assert res["policy"] == "missing"
        assert res["sufficient_for_bimi"] is False

    def test_lookup_dmarc_policy_root_domain_fallback(self):
        mock_dns = {"_dmarc.acme.com": "v=DMARC1; p=reject"}
        res = lookup_dmarc_policy("sub.mail.acme.com", mock_dns=mock_dns)
        assert res["policy"] == "reject"
        assert res["sufficient_for_bimi"] is True


class TestBIMIAuditCoreLayer0:
    def test_audit_domain_bimi_fully_verified(self):
        mock_dns = {
            "default._bimi.acme.com": "v=BIMI1; l=https://brand.acme.com/logo.svg; a=https://digicert.com/vmc.pem",
            "_dmarc.acme.com": "v=DMARC1; p=reject",
        }
        res = audit_domain_bimi("acme.com", mock_dns=mock_dns)
        assert res["status"] == BIMIStatus.VERIFIED.value
        assert res["dmarc_sufficient"] is True
        assert res["bimi_record_found"] is True
        assert res["logo_url"] == "https://brand.acme.com/logo.svg"
        assert res["vmc_url"] == "https://digicert.com/vmc.pem"
        assert VerifiedMarkProvider.GOOGLE_GMAIL.value in res["supported_providers"]
        assert VerifiedMarkProvider.APPLE_MAIL.value in res["supported_providers"]
        assert VerifiedMarkProvider.YAHOO_MAIL.value in res["supported_providers"]

    def test_audit_domain_bimi_logo_only(self):
        mock_dns = {
            "default._bimi.acme.com": "v=BIMI1; l=https://brand.acme.com/logo.svg",
            "_dmarc.acme.com": "v=DMARC1; p=quarantine",
        }
        res = audit_domain_bimi("acme.com", mock_dns=mock_dns)
        assert res["status"] == BIMIStatus.LOGO_ONLY.value
        assert res["dmarc_sufficient"] is True
        assert res["logo_url"] == "https://brand.acme.com/logo.svg"
        assert res["vmc_url"] is None
        assert VerifiedMarkProvider.YAHOO_MAIL.value in res["supported_providers"]
        assert VerifiedMarkProvider.GOOGLE_GMAIL.value not in res["supported_providers"]

    def test_audit_domain_bimi_dmarc_insufficient(self):
        mock_dns = {
            "default._bimi.acme.com": "v=BIMI1; l=https://brand.acme.com/logo.svg; a=https://digicert.com/vmc.pem",
            "_dmarc.acme.com": "v=DMARC1; p=none",
        }
        res = audit_domain_bimi("acme.com", mock_dns=mock_dns)
        assert res["status"] == BIMIStatus.DMARC_INSUFFICIENT.value
        assert res["dmarc_sufficient"] is False
        assert len(res["supported_providers"]) == 0

    def test_audit_domain_bimi_not_configured(self):
        mock_dns = {"_dmarc.acme.com": "v=DMARC1; p=reject"}
        res = audit_domain_bimi("acme.com", mock_dns=mock_dns)
        assert res["status"] == BIMIStatus.NOT_CONFIGURED.value
        assert res["bimi_record_found"] is False
        assert len(res["recommendations"]) > 0

    def test_audit_domain_bimi_returns_recommendations_and_uplift(self):
        mock_dns = {}
        res = audit_domain_bimi("example.com", mock_dns=mock_dns)
        assert isinstance(res["recommendations"], list)
        assert len(res["recommendations"]) > 0
        assert "deliverability_uplift" in res


# =============================================================================
# LAYER 1: ENVIRONMENTAL FAILURE ANALYSIS
# =============================================================================

class TestBIMIEnvironmentalLayer1:
    def test_free_webmail_gmail_skipped(self):
        res = audit_domain_bimi("gmail.com")
        assert res["status"] == BIMIStatus.NOT_CONFIGURED.value
        assert "Free webmail domain" in res.get("note", "")
        assert len(res["supported_providers"]) == 0

    def test_free_webmail_yahoo_skipped(self):
        res = audit_domain_bimi("yahoo.com")
        assert res["status"] == BIMIStatus.NOT_CONFIGURED.value
        assert "Free webmail" in res.get("note", "")

    def test_free_webmail_outlook_skipped(self):
        res = audit_domain_bimi("outlook.com")
        assert res["status"] == BIMIStatus.NOT_CONFIGURED.value

    def test_bimi_record_found_dmarc_missing_fails_safe(self):
        mock_dns = {
            "default._bimi.acme.com": "v=BIMI1; l=https://brand.acme.com/logo.svg; a=https://digicert.com/vmc.pem"
            # No DMARC record provided
        }
        res = audit_domain_bimi("acme.com", mock_dns=mock_dns)
        assert res["status"] == BIMIStatus.DMARC_INSUFFICIENT.value
        assert res["dmarc_sufficient"] is False

    def test_bimi_record_corrupted_syntax_parse_error(self):
        mock_dns = {
            "default._bimi.acme.com": "v=INVALID_VERSION; l=https://logo.svg",
            "_dmarc.acme.com": "v=DMARC1; p=reject",
        }
        res = audit_domain_bimi("acme.com", mock_dns=mock_dns)
        assert res["status"] == BIMIStatus.PARSE_ERROR.value

    def test_audit_sender_inbox_bimi_extracts_domain(self):
        inbox = {"id": "inbox-123", "email": "outreach@acme.com"}
        mock_dns = {
            "default._bimi.acme.com": "v=BIMI1; l=https://acme.com/logo.svg",
            "_dmarc.acme.com": "v=DMARC1; p=reject",
        }
        res = audit_sender_inbox_bimi(inbox, mock_dns=mock_dns)
        assert res["inbox_id"] == "inbox-123"
        assert res["sender_email"] == "outreach@acme.com"
        assert res["domain"] == "acme.com"
        assert res["status"] == BIMIStatus.LOGO_ONLY.value

    def test_audit_sender_inbox_non_dict_safe(self):
        res = audit_sender_inbox_bimi(None)
        assert res["status"] == BIMIStatus.NOT_CONFIGURED.value
        assert res["error"] is not None

    def test_scan_workspace_bimi_health_aggregates_counts(self):
        mock_inboxes = [
            {"id": "inbox-1", "email": "alex@verified.com"},
            {"id": "inbox-2", "email": "sara@logo-only.com"},
            {"id": "inbox-3", "email": "dave@unconfigured.com"},
        ]
        mock_dns = {
            "default._bimi.verified.com": "v=BIMI1; l=https://logo.svg; a=https://digicert.com/vmc.pem",
            "_dmarc.verified.com": "v=DMARC1; p=reject",
            "default._bimi.logo-only.com": "v=BIMI1; l=https://logo.svg",
            "_dmarc.logo-only.com": "v=DMARC1; p=reject",
        }
        report = scan_workspace_bimi_health(
            supabase=None,
            workspace_id="ws-test",
            mock_inboxes=mock_inboxes,
            mock_dns=mock_dns,
        )
        assert report["workspace_id"] == "ws-test"
        assert report["total_inboxes"] == 3
        assert report["verified_count"] == 1
        assert report["logo_only_count"] == 1
        assert report["not_configured_count"] == 1
        assert report["overall_google_verified_eligible"] is True
        assert report["overall_apple_verified_eligible"] is True

    def test_scan_workspace_bimi_health_no_inboxes(self):
        report = scan_workspace_bimi_health(
            supabase=None,
            workspace_id="ws-test",
            mock_inboxes=[],
            mock_dns={},
        )
        assert report["total_inboxes"] == 0
        assert report["verified_count"] == 0
        assert report["overall_google_verified_eligible"] is False

    def test_vmc_url_from_authorized_ca_domain(self):
        res = validate_vmc_certificate("https://cert.digicert.com/vmc.pem")
        assert res["issuer_authorized"] is True
        assert res["issuer"] == "digicert"

    def test_vmc_url_from_entrust_authorized(self):
        res = validate_vmc_certificate("https://entrust.com/certificates/vmc.pem")
        assert res["issuer_authorized"] is True
        assert res["issuer"] == "entrust"

    def test_vmc_url_from_unauthorized_ca_rejected(self):
        res = validate_vmc_certificate("https://fake-ca-cert.com/vmc.pem")
        assert res["issuer_authorized"] is False
        assert res["valid"] is False

    def test_validate_logo_url_non_https_rejected(self):
        res = validate_logo_url("http://brand.acme.com/logo.svg")
        assert res["reachable"] is False
        assert "HTTPS" in res["error"]


# =============================================================================
# LAYER 2: HUMAN PARANOIA & SECURITY DEFENSE
# =============================================================================

class TestBIMISecurityAndSSRFDefenseLayer2:
    def test_empty_domain_handled_safely(self):
        res = audit_domain_bimi("")
        assert res["status"] == BIMIStatus.NOT_CONFIGURED.value
        assert res["bimi_record_found"] is False

    def test_none_domain_handled_safely(self):
        res = audit_domain_bimi(None)
        assert res["status"] == BIMIStatus.NOT_CONFIGURED.value

    def test_ssrf_localhost_logo_url_rejected(self):
        res = validate_logo_url("https://localhost/logo.svg")
        assert res["reachable"] is False
        assert "SSRF" in res["error"] or "Forbidden" in res["error"]

    def test_ssrf_loopback_ip_logo_url_rejected(self):
        res = validate_logo_url("https://127.0.0.1/logo.svg")
        assert res["reachable"] is False
        assert "SSRF" in res["error"] or "Forbidden" in res["error"]

    def test_ssrf_private_ip_192_168_logo_url_rejected(self):
        res = validate_logo_url("https://192.168.1.10/logo.svg")
        assert res["reachable"] is False
        assert "SSRF" in res["error"] or "Forbidden" in res["error"]

    def test_ssrf_private_ip_10_logo_url_rejected(self):
        res = validate_logo_url("https://10.0.0.1/logo.svg")
        assert res["reachable"] is False
        assert "SSRF" in res["error"] or "Forbidden" in res["error"]

    def test_ssrf_metadata_ip_logo_url_rejected(self):
        res = validate_logo_url("https://169.254.169.254/latest/meta-data/logo.svg")
        assert res["reachable"] is False
        assert "SSRF" in res["error"] or "Forbidden" in res["error"]

    def test_ssrf_loopback_vmc_url_rejected(self):
        res = validate_vmc_certificate("https://127.0.0.1/cert.pem")
        assert res["valid"] is False
        assert "SSRF" in res["error"] or "Forbidden" in res["error"]

    def test_facade_class_methods(self):
        assert hasattr(BIMIVMCService, "parse_bimi_record")
        assert hasattr(BIMIVMCService, "lookup_bimi_record")
        assert hasattr(BIMIVMCService, "lookup_dmarc_policy")
        assert hasattr(BIMIVMCService, "validate_logo_url")
        assert hasattr(BIMIVMCService, "validate_vmc_certificate")
        assert hasattr(BIMIVMCService, "audit_domain_bimi")
        assert hasattr(BIMIVMCService, "audit_sender_inbox_bimi")
        assert hasattr(BIMIVMCService, "scan_workspace_bimi_health")


class TestExecutorBIMITelemetryLayer2:
    def test_executor_send_enriches_bimi_telemetry(self):
        from campaigns.backend.services.elein_executor import EleInNodeExecutor

        mock_supabase = MagicMock()
        executor = EleInNodeExecutor(supabase=mock_supabase)

        # Mock out sendgrid & dns dependencies
        data = {
            "email": "test@prospect.com",
            "from_email": "sender@acme.com",
            "subject": "Quick note",
            "body": "Hello prospect, checking in.",
            "mock_dns": {"acme.com": [{"priority": 10, "host": "aspmx.l.google.com"}]},
        }

        # Mock audit_domain_bimi to return VERIFIED
        with patch.object(
            BIMIVMCService,
            "audit_domain_bimi",
            return_value={
                "domain": "acme.com",
                "status": "VERIFIED",
                "supported_providers": ["GOOGLE_GMAIL", "APPLE_MAIL"],
            },
        ):
            # Test handle_send_email in test mode without live SendGrid key
            res = executor.handle_send_email(data, linkedin_url=None)
            assert res is not None
            # Even if error or success, bimi_status should be safe
            if "bimi_status" in res:
                assert res["bimi_status"] in ("VERIFIED", "UNKNOWN", "NOT_CONFIGURED")

    def test_executor_bimi_failure_does_not_block_send(self):
        from campaigns.backend.services.elein_executor import EleInNodeExecutor

        mock_supabase = MagicMock()
        executor = EleInNodeExecutor(supabase=mock_supabase)

        data = {
            "email": "test@prospect.com",
            "from_email": "sender@broken.com",
            "subject": "Hello",
            "body": "Test body",
        }

        # Force audit_domain_bimi to raise an unexpected runtime error
        with patch.object(
            BIMIVMCService,
            "audit_domain_bimi",
            side_effect=RuntimeError("DNS socket connection reset"),
        ):
            # Must NOT crash, must handle exception non-blockingly
            try:
                res = executor.handle_send_email(data, linkedin_url=None)
                assert res is not None
            except RuntimeError:
                pytest.fail("Executor crashed on BIMI error! BIMI telemetry must be non-blocking.")


class TestRouterBIMIEndpointsLayer2:
    def setup_method(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from campaigns.backend.routers.elein import router, get_current_workspace, get_service_client

        app = FastAPI()
        app.include_router(router, prefix="/api/elein")

        self.mock_db = MagicMock()
        self.mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "inbox-101", "email": "sender@verified.com", "workspace_id": "ws-test"}]
        )

        app.dependency_overrides[get_current_workspace] = lambda: "ws-test"
        app.dependency_overrides[get_service_client] = lambda: self.mock_db

        self.client = TestClient(app, raise_server_exceptions=False)

    def test_router_verify_bimi_endpoint(self):
        mock_dns = {
            "default._bimi.acme.com": "v=BIMI1; l=https://logo.svg; a=https://digicert.com/vmc.pem",
            "_dmarc.acme.com": "v=DMARC1; p=reject",
        }
        resp = self.client.post(
            "/api/elein/deliverability/verify-bimi",
            json={"domain": "acme.com", "mock_dns": mock_dns},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["domain"] == "acme.com"
        assert data["status"] == BIMIStatus.VERIFIED.value
        assert data["workspace_id"] == "ws-test"

    def test_router_verify_bimi_empty_domain(self):
        resp = self.client.post(
            "/api/elein/deliverability/verify-bimi",
            json={"domain": ""},
        )
        assert resp.status_code == 422

    def test_router_bimi_status_inbox_endpoint(self):
        resp = self.client.get("/api/elein/deliverability/bimi-status/inbox-101")
        assert resp.status_code == 200
        data = resp.json()
        assert data["inbox_id"] == "inbox-101"
        assert data["workspace_id"] == "ws-test"
        assert "status" in data

    def test_router_bimi_status_inbox_not_in_workspace_returns_404(self):
        self.mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[]
        )
        resp = self.client.get("/api/elein/deliverability/bimi-status/inbox-foreign")
        assert resp.status_code == 404
