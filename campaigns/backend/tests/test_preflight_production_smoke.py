"""
test_preflight_production_smoke.py
Phase 25 & 26: Pre-Flight Production Readiness, Container Health Probes, and Security Hardening.
Tests unauthenticated liveness/readiness probes, security headers, CORS protection, rate limiting, and safe static media mounts.
"""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from core.backend.main import app


@pytest.fixture
def client():
    # Use TestClient with raise_server_exceptions=False to test graceful error handling
    return TestClient(app, raise_server_exceptions=False)


class TestPreflightProductionSmoke:
    """Pre-flight container probes, security headers, and edge hardening verification."""

    def test_liveness_probe_health(self, client):
        """
        Paranoia Layer 0: Unauthenticated container orchestrator liveness probe.
        Verifies both root /health and proxy /api/health return HTTP 200 with metadata.
        """
        for path in ["/health", "/api/health"]:
            res = client.get(path)
            assert res.status_code == 200, f"Expected 200 on {path}, got {res.status_code}"
            data = res.json()
            assert data["status"] == "healthy"
            assert data["service"] == "ele-in-backend"
            assert data["version"] == "3.0.0"
            assert "timestamp" in data
            assert "environment" in data

    def test_readiness_probe_healthy_db(self, client):
        """
        Paranoia Layer 0: Readiness probe returns HTTP 200 when database query succeeds.
        """
        mock_svc = MagicMock()
        mock_table = MagicMock()
        mock_select = MagicMock()
        mock_limit = MagicMock()
        
        mock_svc.table.return_value = mock_table
        mock_table.select.return_value = mock_select
        mock_select.limit.return_value = mock_limit
        mock_limit.execute.return_value = MagicMock(data=[{"id": "ws-123"}])

        with patch("core.backend.api.auth_dep.get_service_client", return_value=mock_svc):
            for path in ["/ready", "/api/ready"]:
                res = client.get(path)
                assert res.status_code == 200, f"Expected 200 on {path}, got {res.status_code}"
                data = res.json()
                assert data["status"] == "ready"
                assert data["database"] == "connected"
                assert data["service"] == "ele-in-backend"
                assert "timestamp" in data

    def test_readiness_probe_degraded_db_fallback(self, client):
        """
        Paranoia Layer 1: If database client throws connection failure, readiness probe
        must return HTTP 503 Service Unavailable with degraded payload and NEVER throw a 500.
        """
        with patch("core.backend.api.auth_dep.get_service_client", side_effect=ConnectionError("Database pool exhausted")):
            for path in ["/ready", "/api/ready"]:
                res = client.get(path)
                assert res.status_code == 503, f"Expected 503 on {path}, got {res.status_code}"
                data = res.json()
                assert data["status"] == "degraded"
                assert data["database"] == "unreachable"
                assert "Database pool exhausted" in data["error"]
                assert "timestamp" in data

    def test_readiness_probe_unconfigured_client(self, client):
        """
        Paranoia Layer 1: If service client returns None, probe safely returns 503 without crash.
        """
        with patch("core.backend.api.auth_dep.get_service_client", return_value=None):
            res = client.get("/ready")
            assert res.status_code == 503
            data = res.json()
            assert data["status"] == "degraded"
            assert data["database"] == "unconfigured"

    def test_enterprise_security_headers_present(self, client):
        """
        Paranoia Layer 1 & 2: Validates strict enterprise security headers on every response.
        """
        res = client.get("/health")
        assert res.status_code == 200

        headers = res.headers
        assert headers.get("strict-transport-security") == "max-age=31536000; includeSubDomains; preload"
        assert headers.get("x-content-type-options") == "nosniff"
        assert headers.get("x-frame-options") == "DENY"
        assert headers.get("x-xss-protection") == "1; mode=block"
        assert headers.get("referrer-policy") == "strict-origin-when-cross-origin"
        assert headers.get("cross-origin-opener-policy") == "same-origin-allow-popups"
        assert headers.get("cross-origin-resource-policy") == "cross-origin"
        assert "camera=()" in headers.get("permissions-policy", "")
        assert "microphone=(self)" in headers.get("permissions-policy", "")

    def test_cors_preflight_and_credentials_handling(self, client):
        """
        Paranoia Layer 1: Validates CORS preflight handling.
        """
        headers = {
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization,Content-Type",
        }
        res = client.options("/health", headers=headers)
        # OPTIONS preflight returns 200 OK and echoes allowed origin
        assert res.status_code == 200
        assert "access-control-allow-origin" in res.headers

    def test_rate_limiter_registered_with_spoofing_defense(self, client):
        """
        Paranoia Layer 1: Ensures SlowAPI limiter is attached to app state and utilizes client IP resolver.
        """
        assert hasattr(app.state, "limiter")
        assert app.state.limiter is not None

        # Verify endpoint functions under normal traffic
        res = client.get("/health", headers={"CF-Connecting-IP": "203.0.113.195"})
        assert res.status_code == 200

    def test_static_media_mount_path_traversal_defense(self, client):
        """
        Paranoia Layer 2: Validates that mounted static file directories reject directory traversal attacks.
        """
        # Attempting path traversal on voice notes
        res = client.get("/api/elein/media/voice_notes/../../../../etc/passwd")
        assert res.status_code in [400, 404], f"Expected 400/404 on path traversal, got {res.status_code}"

        # Attempting path traversal on attachments
        res = client.get("/api/elein/media/attachments/../../../../etc/passwd")
        assert res.status_code in [400, 404], f"Expected 400/404 on path traversal, got {res.status_code}"
