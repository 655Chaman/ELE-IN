"""
test_pillar7_security_vault_and_encryption.py — Comprehensive Test Suite for Pillar 7
Security Vault, Envelope Encryption, RLS Audit, SSRF Defense, & Rate Limit Cooldown (Phases 7.1 – 7.4)
Rigorously verified under the Three-Layer Logic Architecture (Paranoia Framework).
"""

import pytest
import os
import time
import base64
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from core.backend.services.envelope_encryption import (
    encrypt_envelope,
    decrypt_envelope,
    get_or_provision_workspace_dek,
    clear_dek_cache_for_workspace,
    mask_secret,
    log_encryption_audit,
    VaultDecryptionError,
    _DEK_CACHE,
    _IN_MEMORY_WORKSPACE_DEKS,
    _IN_MEMORY_ENCRYPTION_AUDIT,
    _dek_lock,
)
from core.backend.services.tenant_guard import (
    enforce_tenant_boundary,
    audit_tenant_rls_integrity,
    TenantIDORViolationError,
)
from core.backend.services.ssrf_guard import (
    validate_outbound_url,
    parse_and_normalize_ip,
    is_ip_blocked,
    SSRFValidationError,
)
from core.backend.services.account_rate_limiter import (
    check_and_increment_account_action,
    trigger_account_security_cooldown,
    is_account_in_cooldown,
    DAILY_CONNECTION_LIMIT,
    HOURLY_CONNECTION_LIMIT,
    DAILY_MESSAGE_LIMIT,
    HOURLY_MESSAGE_LIMIT,
    _IN_MEMORY_ACCOUNT_COOLDOWNS,
    _IN_MEMORY_ACCOUNT_COUNTERS,
    _rate_limit_lock,
)


# =============================================================================
# PHASE 7.1: ENVELOPE ENCRYPTION WITH DEK MANAGEMENT TESTS
# =============================================================================

class TestPhase71EnvelopeEncryption:
    @pytest.fixture(autouse=True)
    def clean_stores(self):
        with _dek_lock:
            _DEK_CACHE.clear()
            _IN_MEMORY_WORKSPACE_DEKS.clear()
            _IN_MEMORY_ENCRYPTION_AUDIT.clear()
        yield
        with _dek_lock:
            _DEK_CACHE.clear()
            _IN_MEMORY_WORKSPACE_DEKS.clear()
            _IN_MEMORY_ENCRYPTION_AUDIT.clear()

    def test_envelope_encryption_and_decryption_roundtrip(self):
        ws_id = "ws-tenant-alpha"
        secret_token = "ghp_secure_github_pat_token_987654321_secret"

        # Encrypt
        envelope = encrypt_envelope(secret_token, workspace_id=ws_id)
        assert envelope.startswith("v2:env:1:")
        assert secret_token not in envelope

        # Decrypt with matching workspace ID
        decrypted = decrypt_envelope(envelope, workspace_id=ws_id)
        assert decrypted == secret_token

    def test_cross_tenant_tampering_denied_via_aad(self):
        """
        Layer 2 Paranoia: If Tenant A's ciphertext is copied into Tenant B's record,
        decryption must fail due to AAD (Additional Authenticated Data) mismatch!
        """
        ws_a = "ws-tenant-alpha"
        ws_b = "ws-tenant-beta"
        secret_cookie = "li_at=AQEDASecureLinkedInSessionCookieForTenantA"

        # Encrypted under Tenant A
        envelope_a = encrypt_envelope(secret_cookie, workspace_id=ws_a)

        # Attacker attempts to decrypt Tenant A's envelope within Tenant B's context
        with pytest.raises(VaultDecryptionError) as exc_info:
            decrypt_envelope(envelope_a, workspace_id=ws_b)

        assert "Authentication tag verification failed" in str(exc_info.value) or "tampering" in str(exc_info.value)

    def test_ephemeral_dek_caching_and_ttl_expiration(self):
        """
        Layer 1 Paranoia: DEK is cached in memory for high-throughput (TTL = 300s).
        When TTL expires, memory zeroing is executed and DEK is un-wrapped fresh.
        """
        ws_id = "ws-cache-test"
        dek1 = get_or_provision_workspace_dek(ws_id)

        # Should retrieve from in-memory cache without unwrapping
        with _dek_lock:
            assert ws_id in _DEK_CACHE
            cached_dek, expire_at = _DEK_CACHE[ws_id]
            assert cached_dek == dek1
            # Artificially expire the cache
            _DEK_CACHE[ws_id] = (cached_dek, time.time() - 10)

        # Next call should detect expired TTL, zero memory, and re-unwrap cleanly
        dek2 = get_or_provision_workspace_dek(ws_id)
        assert dek2 == dek1  # Same key un-wrapped from storage

    def test_master_kek_rotation_waterfall(self):
        """
        Layer 1 Paranoia: If Master KEK is rotated, data encrypted under earlier KEKs
        is still decrypted successfully through candidate key waterfall.
        """
        ws_id = "ws-rotation-test"
        original_secret = "api_key_openai_secret_v1"

        # 1. Encrypt with current default KEK
        envelope = encrypt_envelope(original_secret, workspace_id=ws_id)

        # 2. Simulate rotation: set a brand new MASTER_KEK and push previous into MASTER_PREVIOUS_KEKS
        with patch.dict(os.environ, {
            "MASTER_KEK": "new_rotated_kek_secret_key_2026_xyz",
            "MASTER_PREVIOUS_KEKS": "elein_master_envelope_kek_seed_2026_dev_only",
        }):
            # Clear DEK cache to force re-unwrapping with candidate KEKs
            clear_dek_cache_for_workspace(ws_id)

            # Decryption must succeed via waterfall
            decrypted = decrypt_envelope(envelope, workspace_id=ws_id)
            assert decrypted == original_secret

    def test_zero_secret_leakage_in_audit_log(self):
        """
        Layer 2 Paranoia: Audit logs record cryptographic operations with zero secret leakage.
        """
        ws_id = "ws-audit-test"
        sensitive_key = "sk-live-super-secret-stripe-token-12345"

        encrypt_envelope(sensitive_key, workspace_id=ws_id)
        envelope = encrypt_envelope(sensitive_key, workspace_id=ws_id)
        decrypt_envelope(envelope, workspace_id=ws_id)

        with _dek_lock:
            assert len(_IN_MEMORY_ENCRYPTION_AUDIT) >= 2
            for entry in _IN_MEMORY_ENCRYPTION_AUDIT:
                assert sensitive_key not in str(entry)
                assert "key_version" in entry
                assert "operation" in entry
                assert entry["status"] == "success"

    def test_mask_secret_utility(self):
        assert mask_secret("sk_live_123456789abcdef") == "sk_••••••••def"
        assert mask_secret("short") == "••••••"
        assert mask_secret("") == ""


# =============================================================================
# PHASE 7.2: MULTI-TENANT RLS LEAK AUDIT TESTS
# =============================================================================

class TestPhase72MultiTenantRLSAndIDOR:
    def test_enforce_tenant_boundary_valid(self):
        assert enforce_tenant_boundary("ws-user-123", "ws-user-123", actor_id="user-1") is True

    def test_enforce_tenant_boundary_blocks_idor_attack(self):
        with pytest.raises(TenantIDORViolationError) as exc_info:
            enforce_tenant_boundary(
                current_workspace_id="ws-victim-org",
                requested_workspace_id="ws-attacker-org",
                actor_id="user-evil",
                resource_type="campaign"
            )
        assert exc_info.value.status_code == 403
        assert "Forbidden" in exc_info.value.detail

    def test_audit_tenant_rls_integrity_100_percent_compliance(self):
        audit = audit_tenant_rls_integrity()
        assert audit["status"] == "SUCCESS"
        assert audit["compliance_score"] == 100.0
        assert audit["service_role_leak_detected"] is False
        assert audit["total_tables_checked"] >= 15
        assert "leads" in audit["table_reports"]
        assert "campaigns" in audit["table_reports"]
        assert "workspace_deks" in audit["table_reports"]
        assert "account_rate_limits" in audit["table_reports"]


# =============================================================================
# PHASE 7.3: SSRF & PRIVATE NETWORK DEFENSE TESTS
# =============================================================================

class TestPhase73SSRFDefense:
    @pytest.mark.parametrize("bad_url", [
        # Loopback
        "http://127.0.0.1/status",
        "http://127.0.1.1:80/admin",
        "http://localhost:80/debug",
        "http://api.localhost/internal",
        "http://[::1]/status",
        # Cloud Metadata (AWS/GCP/Azure)
        "http://169.254.169.254/latest/meta-data/",
        "http://metadata.google.internal/computeMetadata/v1/",
        "http://instance-data/latest/meta-data/",
        # RFC 1918 Private Ranges
        "http://10.0.0.1/api",
        "http://172.16.0.5/api",
        "http://192.168.1.1/router",
        # Carrier-Grade NAT (CGNAT)
        "http://100.64.0.1/telemetry",
        # Wildcard DNS Services
        "http://127.0.0.1.nip.io/exploit",
        "http://169.254.169.254.sslip.io/",
        "http://evil.vcap.me/test",
    ])
    def test_ssrf_blocks_private_and_metadata_targets(self, bad_url):
        with pytest.raises(SSRFValidationError):
            validate_outbound_url(bad_url)

    @pytest.mark.parametrize("obfuscated_url", [
        # Decimal IP format for 169.254.169.254: 2852039166
        "http://2852039166/latest/meta-data/",
        # Decimal IP format for 127.0.0.1: 2130706433
        "http://2130706433/admin",
        # Hexadecimal IP format for 169.254.169.254: 0xa9fea9fe
        "http://0xa9fea9fe/",
        # Octal IP format for 169.254.169.254: 0251.0376.0251.0376
        "http://0251.0376.0251.0376/",
        # IPv4-mapped IPv6 for 169.254.169.254
        "http://[::ffff:169.254.169.254]/",
        # IPv4-mapped IPv6 for 127.0.0.1
        "http://[::ffff:127.0.0.1]/",
    ])
    def test_ssrf_blocks_obfuscated_ip_representations(self, obfuscated_url):
        with pytest.raises(SSRFValidationError):
            validate_outbound_url(obfuscated_url)

    @pytest.mark.parametrize("forbidden_port_url", [
        "http://185.199.108.153:5432/db",    # PostgreSQL port
        "http://185.199.108.153:6379/redis", # Redis port
        "http://185.199.108.153:22/ssh",     # SSH port
        "http://185.199.108.153:8000/api",   # Internal worker port
    ])
    def test_ssrf_blocks_non_standard_ports(self, forbidden_port_url):
        with pytest.raises(SSRFValidationError) as exc_info:
            validate_outbound_url(forbidden_port_url)
        assert "forbidden" in str(exc_info.value.detail).lower()

    def test_ssrf_allows_legitimate_public_urls(self):
        # Public domains with standard ports 80/443
        clean = validate_outbound_url("https://api.hubspot.com/crm/v3/objects/contacts")
        assert clean == "https://api.hubspot.com/crm/v3/objects/contacts"

        clean2 = validate_outbound_url("https://hooks.slack.com/services/T00/B00/X00")
        assert clean2 == "https://hooks.slack.com/services/T00/B00/X00"


# =============================================================================
# PHASE 7.4: STRICT RATE LIMITING & ACCOUNT COOLDOWN MATRIX TESTS
# =============================================================================

class TestPhase74AccountRateLimitingAndCooldown:
    @pytest.fixture(autouse=True)
    def clean_limits(self):
        with _rate_limit_lock:
            _IN_MEMORY_ACCOUNT_COOLDOWNS.clear()
            _IN_MEMORY_ACCOUNT_COUNTERS.clear()
        yield
        with _rate_limit_lock:
            _IN_MEMORY_ACCOUNT_COOLDOWNS.clear()
            _IN_MEMORY_ACCOUNT_COUNTERS.clear()

    def test_account_rate_limiting_hourly_and_daily_ceilings(self):
        acc_id = "acc-linkedin-01"
        ws_id = "ws-enterprise-01"

        # 1. Fire up to HOURLY_CONNECTION_LIMIT (10)
        for i in range(HOURLY_CONNECTION_LIMIT):
            res = check_and_increment_account_action(acc_id, ws_id, "connection_request")
            assert res["allowed"] is True
            assert res["status"] == "dispatched"

        # 2. Attempt 11 within the hour must be cleanly paced/deferred
        res_deferred = check_and_increment_account_action(acc_id, ws_id, "connection_request")
        assert res_deferred["allowed"] is False
        assert res_deferred["status"] == "deferred_hourly_limit"
        assert "Hourly connection rate limit reached" in res_deferred["reason"]

    def test_account_rate_limiting_attempt_51_daily_deferral(self):
        acc_id = "acc-linkedin-02"
        ws_id = "ws-enterprise-01"

        # Artificially pre-set daily counter to 50 across past hours today
        today_str = datetime.now(timezone.utc).date().isoformat()
        with _rate_limit_lock:
            _IN_MEMORY_ACCOUNT_COUNTERS[(acc_id, today_str, 0)] = {
                "conn_daily": DAILY_CONNECTION_LIMIT,
                "msg_daily": 0,
                "conn_hourly": 0,
                "msg_hourly": 0
            }

        # Attempt 51 must be cleanly deferred without contacting LinkedIn
        res = check_and_increment_account_action(acc_id, ws_id, "connection_request")
        assert res["allowed"] is False
        assert res["status"] == "deferred_daily_limit"
        assert f"Daily connection limit reached ({DAILY_CONNECTION_LIMIT}/day)" in res["reason"]

    def test_trigger_account_security_cooldown_48h(self):
        acc_id = "acc-linkedin-checkpoint"
        ws_id = "ws-enterprise-01"
        mock_sb = MagicMock()

        # Trigger cooldown upon LinkedIn 429 / checkpoint detection
        cd_info = trigger_account_security_cooldown(
            account_id=acc_id,
            workspace_id=ws_id,
            trigger_reason="HTTP 429: LinkedIn Automated Traffic Checkpoint",
            cooldown_hours=48,
            supabase=mock_sb
        )

        assert cd_info["status"] == "cooling_challenge"
        assert cd_info["cooldown_hours"] == 48

        # Verify account is in active cooldown
        is_cooling, reason, cd_until = is_account_in_cooldown(acc_id)
        assert is_cooling is True
        assert "Checkpoint" in reason
        assert cd_until > datetime.now(timezone.utc)

        # Preflight check must immediately reject dispatch for cooling account
        res = check_and_increment_account_action(acc_id, ws_id, "message")
        assert res["allowed"] is False
        assert res["status"] == "deferred_cooldown"
        assert "Account is cooling" in res["message"]

        # Verify DB updates cascaded: rescheduled active execution states by 48h
        mock_sb.table.assert_any_call("campaign_execution_states")
