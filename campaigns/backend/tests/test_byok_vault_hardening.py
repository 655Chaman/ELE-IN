import unittest
from unittest.mock import MagicMock, patch
import os
from fastapi import HTTPException

from knowledge.backend.services.byok_vault import (
    encrypt_byok_key,
    decrypt_byok_key,
    is_encrypted_byok_key,
    validate_byok_key,
    VaultDecryptionError,
    InvalidKeyFormatError,
    CIPHER_PREFIX
)
from knowledge.backend.routers.ai_gateway import (
    update_ai_settings,
    test_byok_key as route_test_byok_key,
    get_decrypted_workspace_byok_key,
    AISettingsUpdateRequest,
    TestKeyRequest as SchemaTestKeyRequest,
    _FALLBACK_AI_SETTINGS
)


class TestBYOKVaultHardening(unittest.TestCase):
    """
    H-02 Hardening Test Suite:
    Ensures Bring-Your-Own-Key (BYOK) credentials are authenticated and encrypted
    with AES-256-GCM at rest, with robust validation, replay prevention, and
    graceful legacy backward compatibility.
    """

    def setUp(self):
        _FALLBACK_AI_SETTINGS.clear()

    # =========================================================================
    # Layer 0: Core Encryption & Decryption
    # =========================================================================
    def test_encrypt_and_decrypt_roundtrip(self):
        """Layer 0: Valid keys encrypt to v1:gcm: envelope and decrypt back losslessly."""
        raw_key = "sk-proj-1234567890abcdef1234567890"
        ciphertext = encrypt_byok_key(raw_key)

        self.assertTrue(ciphertext.startswith(CIPHER_PREFIX))
        self.assertTrue(is_encrypted_byok_key(ciphertext))
        self.assertNotIn(raw_key, ciphertext, "Plaintext API key must not appear in ciphertext")

        decrypted = decrypt_byok_key(ciphertext)
        self.assertEqual(decrypted, raw_key)

    def test_encryption_produces_unique_nonces(self):
        """Layer 1: Repeated encryptions of the same key must produce different ciphertexts (random IV)."""
        raw_key = "sk-ant-api03-abcdefghijklmnopqrstuvwxyz12345"
        ct1 = encrypt_byok_key(raw_key)
        ct2 = encrypt_byok_key(raw_key)

        self.assertNotEqual(ct1, ct2, "Every encryption must use a fresh cryptographic nonce")
        self.assertEqual(decrypt_byok_key(ct1), raw_key)
        self.assertEqual(decrypt_byok_key(ct2), raw_key)

    # =========================================================================
    # Layer 1: Environmental Failure & Corruption Handling
    # =========================================================================
    def test_decrypt_legacy_plaintext_backward_compatibility(self):
        """Layer 1: Legacy rows storing unencrypted keys pass through safely without crashing."""
        legacy_key = "sk-legacy-unencrypted-key-from-old-version"
        decrypted = decrypt_byok_key(legacy_key)
        self.assertEqual(decrypted, legacy_key)

    def test_tampered_ciphertext_fails_cleanly(self):
        """Layer 1: Tampered or truncated ciphertext raises VaultDecryptionError instead of unhandled crash."""
        raw_key = "sk-deepseek-1234567890abcdef"
        ciphertext = encrypt_byok_key(raw_key)

        # Corrupt the last 4 bytes of authentication tag
        tampered = ciphertext[:-4] + "AAAA"
        with self.assertRaises(VaultDecryptionError):
            decrypt_byok_key(tampered)

        # Truncated payload
        with self.assertRaises(VaultDecryptionError):
            decrypt_byok_key(f"{CIPHER_PREFIX}dG9vc2hvcnQ=")

    # =========================================================================
    # Layer 2: Human Paranoia & Mistake Prevention
    # =========================================================================
    def test_masked_key_submission_rejected(self):
        """Layer 2: Accidental submission of masked string (e.g. ••••••••••••1234) is blocked."""
        with self.assertRaises(InvalidKeyFormatError) as cm:
            validate_byok_key("openai", "••••••••••••1234")
        self.assertIn("masked key", str(cm.exception).lower())

        with self.assertRaises(InvalidKeyFormatError) as cm:
            validate_byok_key("openai", "****************1234")
        self.assertIn("masked key", str(cm.exception).lower())

    def test_provider_prefix_and_length_validation(self):
        """Layer 2: Rejects invalid formats across supported providers."""
        # Too short
        with self.assertRaises(InvalidKeyFormatError):
            validate_byok_key("openai", "sk-short")

        # Wrong prefix for OpenAI
        with self.assertRaises(InvalidKeyFormatError):
            validate_byok_key("openai", "not-an-openai-key-at-all-12345")

        # Wrong prefix for Anthropic
        with self.assertRaises(InvalidKeyFormatError):
            validate_byok_key("anthropic", "sk-wrong-anthropic-prefix-12345")

        # Wrong prefix for Groq
        with self.assertRaises(InvalidKeyFormatError):
            validate_byok_key("groq", "sk-wrong-groq-prefix-1234567890")

        # Valid Anthropic
        valid_ant = validate_byok_key("anthropic", "sk-ant-api03-validanthropickey12345678")
        self.assertEqual(valid_ant, "sk-ant-api03-validanthropickey12345678")

    # =========================================================================
    # Endpoint Integration Tests
    # =========================================================================
    @patch("knowledge.backend.routers.ai_gateway.check_tier_access", return_value=True)
    def test_update_ai_settings_stores_ciphertext_never_plaintext(self, mock_tier):
        """Integration: PUT /settings encrypts key at rest and never leaks ciphertext to client."""
        mock_supabase = MagicMock()
        mock_table = MagicMock()
        mock_table.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        mock_supabase.table.return_value = mock_table

        req = AISettingsUpdateRequest(
            byok_provider="openai",
            byok_key="  sk-proj-0987654321fedcba1234567890  "  # Surrounding whitespace stripped
        )

        res = update_ai_settings(
            payload=req,
            supabase=mock_supabase,
            workspace_id="ws_byok_test"
        )

        # 1. Client response check: must be masked
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["byok_key_masked"], "••••••••••••7890")
        self.assertTrue(res["has_byok"])

        # 2. Database insert check: stored column must be encrypted with v1:gcm:
        insert_calls = mock_table.insert.call_args_list
        self.assertEqual(len(insert_calls), 1)
        inserted_data = insert_calls[0][0][0]
        stored_cipher = inserted_data["byok_key_ciphertext"]

        self.assertTrue(stored_cipher.startswith(CIPHER_PREFIX))
        self.assertNotIn("sk-proj", stored_cipher, "Raw API key must NEVER be persisted in plaintext")

        # 3. Decryption check: helper can recover original key
        mock_table.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"byok_provider": "openai", "byok_key_ciphertext": stored_cipher}]
        )
        decrypted_tuple = get_decrypted_workspace_byok_key(mock_supabase, "ws_byok_test")
        self.assertIsNotNone(decrypted_tuple)
        self.assertEqual(decrypted_tuple[0], "openai")
        self.assertEqual(decrypted_tuple[1], "sk-proj-0987654321fedcba1234567890")

    @patch("knowledge.backend.routers.ai_gateway.check_tier_access", return_value=True)
    def test_remove_byok_clears_credentials(self, mock_tier):
        """Integration: remove_byok clears ciphertext and provider."""
        mock_supabase = MagicMock()
        mock_table = MagicMock()
        mock_table.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"workspace_id": "ws_1"}])
        mock_supabase.table.return_value = mock_table

        req = AISettingsUpdateRequest(remove_byok=True)
        res = update_ai_settings(
            payload=req,
            supabase=mock_supabase,
            workspace_id="ws_1"
        )

        self.assertIsNone(res["byok_key_masked"])
        self.assertFalse(res["has_byok"])

        update_calls = mock_table.update.call_args_list
        self.assertEqual(len(update_calls), 1)
        updated_data = update_calls[0][0][0]
        self.assertIsNone(updated_data["byok_key_ciphertext"])
        self.assertIsNone(updated_data["byok_provider"])

    @patch("knowledge.backend.routers.ai_gateway.check_tier_access", return_value=True)
    def test_route_test_byok_key_endpoint(self, mock_tier):
        """Integration: POST /test-key validates formatting without persistence."""
        mock_supabase = MagicMock()
        valid_req = SchemaTestKeyRequest(provider="openai", api_key="sk-proj-12345678901234567890")
        res = route_test_byok_key(valid_req, supabase=mock_supabase, workspace_id="ws_1")
        self.assertTrue(res["valid"])
        self.assertEqual(res["last_chars"], "7890")

        # Invalid key raises 400
        invalid_req = SchemaTestKeyRequest(provider="openai", api_key="sk-short")
        with self.assertRaises(HTTPException) as cm:
            route_test_byok_key(invalid_req, supabase=mock_supabase, workspace_id="ws_1")
        self.assertEqual(cm.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
