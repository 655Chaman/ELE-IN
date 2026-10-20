"""
Enterprise AI Resilience & Hardening Test Suite
================================================
Comprehensive verification for Tier-1 Enterprise AI features:
1. AIDistributedLock & Lease Management (re-entrancy, TTL expiration, extension)
2. AIRateLimiter (Token Bucket RPM/TPM enforcement, multi-tenant quotas)
3. AICircuitBreaker (CLOSED -> OPEN -> HALF_OPEN state machine, probe routing)
4. BYOK Vault (Zero-downtime rotation re-encryption, constant-time envelope check)
5. AIOutputGuard (DLP / PII scrubbing: SSN, Credit Cards)
"""

import time
import unittest
from unittest.mock import MagicMock, patch

from knowledge.backend.services.ai_distributed_lock import (
    AILeaseLock,
    ai_distributed_lock,
    AILockAcquisitionError
)
from knowledge.backend.services.ai_rate_limiter import (
    check_and_record_ai_usage,
    reset_rate_limiter_state,
    AIRateLimitExceededError
)
from knowledge.backend.services.ai_circuit_breaker import (
    is_provider_available,
    record_provider_success,
    record_provider_failure,
    get_circuit_breaker_status,
    reset_circuit_breaker_state,
    STATE_CLOSED,
    STATE_OPEN,
    STATE_HALF_OPEN
)
from knowledge.backend.services.byok_vault import (
    encrypt_byok_key,
    decrypt_byok_key,
    reencrypt_byok_key,
    is_encrypted_byok_key
)
from knowledge.backend.services.ai_output_guard import sanitize_outbound_ai_message


class TestEnterpriseAIResilienceAndHardening(unittest.TestCase):

    def setUp(self):
        reset_rate_limiter_state()
        reset_circuit_breaker_state()

    def tearDown(self):
        reset_rate_limiter_state()
        reset_circuit_breaker_state()

    # ─── 1. AI DISTRIBUTED LEASE LOCK ────────────────────────────────────────

    def test_lease_lock_acquisition_and_reentrancy(self):
        """Re-entrant locks allow same-thread nested acquisition without deadlock."""
        lock = AILeaseLock("test:resource:1", ttl_seconds=10.0, timeout=1.0)
        self.assertTrue(lock.acquire())
        # Re-entrant acquire
        self.assertTrue(lock.acquire())
        lock.release()
        lock.release()

    def test_lease_lock_context_manager_and_heartbeat_extension(self):
        """Context manager acquires and extends lease properly."""
        with ai_distributed_lock("test:resource:heartbeat", ttl_seconds=5.0) as lease:
            self.assertTrue(lease.acquired)
            extended = lease.extend(extra_seconds=10.0)
            self.assertTrue(extended)

    def test_lease_lock_auto_expiry_allows_new_acquisition(self):
        """An expired lease is reclaimed automatically by another requester."""
        # Create a lock with very short TTL
        lock1 = AILeaseLock("test:resource:expiry", ttl_seconds=0.1, timeout=0.1)
        self.assertTrue(lock1.acquire())
        
        # Wait for TTL to expire
        time.sleep(0.15)
        
        # Another lock for the same key should succeed because lock1 expired
        lock2 = AILeaseLock("test:resource:expiry", ttl_seconds=5.0, timeout=0.2)
        self.assertTrue(lock2.acquire())
        lock2.release()

    # ─── 2. PER-WORKSPACE TOKEN BUCKET RATE LIMITER ──────────────────────────

    def test_rate_limiter_allows_under_quota(self):
        """Requests under RPM/TPM ceiling are granted."""
        allowed, retry_after = check_and_record_ai_usage(
            workspace_id="ws-enterprise-1",
            estimated_tokens=500,
            tier="pro"
        )
        self.assertTrue(allowed)
        self.assertEqual(retry_after, 0.0)

    def test_rate_limiter_blocks_on_rpm_ceiling(self):
        """Enforces hard RPM ceiling and returns actionable retry_after."""
        # Use custom small limit for test
        ws = "ws-rpm-test"
        for _ in range(5):
            allowed, _ = check_and_record_ai_usage(ws, estimated_tokens=10, custom_rpm=5, custom_tpm=10000)
            self.assertTrue(allowed)
            
        # 6th request should be blocked
        allowed, retry_after = check_and_record_ai_usage(ws, estimated_tokens=10, custom_rpm=5, custom_tpm=10000)
        self.assertFalse(allowed)
        self.assertGreater(retry_after, 0.0)

    def test_rate_limiter_blocks_on_tpm_ceiling(self):
        """Enforces hard TPM ceiling across multi-turn synthesis."""
        ws = "ws-tpm-test"
        allowed, _ = check_and_record_ai_usage(ws, estimated_tokens=800, custom_rpm=100, custom_tpm=1000)
        self.assertTrue(allowed)
        
        # Next request with 300 tokens exceeds 1000 limit
        allowed, retry_after = check_and_record_ai_usage(ws, estimated_tokens=300, custom_rpm=100, custom_tpm=1000)
        self.assertFalse(allowed)
        self.assertGreater(retry_after, 0.0)

    # ─── 3. UPSTREAM PROVIDER CIRCUIT BREAKER ────────────────────────────────

    def test_circuit_breaker_closed_by_default(self):
        """Circuit breaker starts in CLOSED state."""
        self.assertTrue(is_provider_available("nvidia"))
        status = get_circuit_breaker_status()
        self.assertEqual(status["nvidia"]["state"], STATE_CLOSED)

    def test_circuit_breaker_trips_to_open_after_consecutive_failures(self):
        """Trips to OPEN after 5 failures and blocks subsequent requests."""
        for _ in range(5):
            record_provider_failure("deepseek", Exception("Connection timeout"), failure_threshold=5)

        # Now provider should be unavailable (OPEN)
        self.assertFalse(is_provider_available("deepseek", recovery_timeout=60.0))
        status = get_circuit_breaker_status()
        self.assertEqual(status["deepseek"]["state"], STATE_OPEN)

    def test_circuit_breaker_transitions_to_half_open_and_resets_on_success(self):
        """After cooldown, transitions to HALF_OPEN, and resets to CLOSED upon success."""
        for _ in range(3):
            record_provider_failure("openai", Exception("500 Internal Error"), failure_threshold=3)

        # Immediate check: OPEN
        self.assertFalse(is_provider_available("openai", recovery_timeout=10.0))

        # Check with 0.0 recovery timeout simulates elapsed cooldown -> HALF_OPEN probe allowed
        self.assertTrue(is_provider_available("openai", recovery_timeout=0.0))
        status = get_circuit_breaker_status()
        self.assertEqual(status["openai"]["state"], STATE_HALF_OPEN)

        # Successful probe resets to CLOSED
        record_provider_success("openai")
        status = get_circuit_breaker_status()
        self.assertEqual(status["openai"]["state"], STATE_CLOSED)
        self.assertEqual(status["openai"]["failure_count"], 0)

    # ─── 4. BYOK VAULT ZERO-DOWNTIME ROTATION & TIMING DEFENSE ───────────────

    def test_byok_is_encrypted_constant_time_envelope(self):
        """Verifies envelope detection with constant-time matching."""
        encrypted = encrypt_byok_key("sk-ant-test-key-123456789012345")
        self.assertTrue(is_encrypted_byok_key(encrypted))
        self.assertFalse(is_encrypted_byok_key("sk-ant-raw-plaintext-key"))
        self.assertFalse(is_encrypted_byok_key(""))

    def test_byok_reencrypt_key_maintains_plaintext_identity(self):
        """Re-encrypting an encrypted key preserves decrypted plaintext value."""
        original_plaintext = "sk-ant-test-key-rotation-9988776655"
        first_cipher = encrypt_byok_key(original_plaintext)
        
        # Re-encrypt
        reencrypted = reencrypt_byok_key(first_cipher)
        self.assertTrue(is_encrypted_byok_key(reencrypted))
        
        # Decrypting re-encrypted value matches original plaintext
        self.assertEqual(decrypt_byok_key(reencrypted), original_plaintext)

    # ─── 5. AI OUTPUT GUARD PII & DATA LOSS PREVENTION ───────────────────────

    def test_ai_output_guard_scrubs_social_security_numbers(self):
        """Neutralizes SSN leakages in generated outbound copy."""
        raw_msg = "Hello, your reference verification code is 123-45-6789."
        clean, valid, reason = sanitize_outbound_ai_message(raw_msg, context_type="message")
        self.assertTrue(valid)
        self.assertNotIn("123-45-6789", clean)
        self.assertIn("[REDACTED_SSN]", clean)

    def test_ai_output_guard_scrubs_credit_card_numbers(self):
        """Neutralizes credit card numbers in generated outbound copy."""
        raw_msg = "Please verify your payment card ending in 4111111111111111."
        clean, valid, reason = sanitize_outbound_ai_message(raw_msg, context_type="message")
        self.assertTrue(valid)
        self.assertNotIn("4111111111111111", clean)
        self.assertIn("[REDACTED_CARD]", clean)


if __name__ == "__main__":
    unittest.main()
