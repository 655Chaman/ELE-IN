"""
Unit & Integration Tests for Stage 12 Elite Architecture Hardening:
  1. Omnichannel Fallback Cascade Webhook Emission & Suppression Filtering
  2. Multi-Tenant Credential Vault AI / LLM Resolution & Transparent BYOK Decryption
  3. Anti-Fingerprint Template Entropy Guard & Auto-Spintax Upgrading
  4. Lead Ingestion Suppression Pre-Flight Quarantine
Rigorously architected under the Three-Layer Logic Architecture (Paranoia Framework).
"""

import unittest
from unittest.mock import MagicMock, patch
import os

from integrations.backend.services.credential_vault import vault, CredentialVault
from knowledge.backend.services.byok_vault import encrypt_byok_key
from knowledge.backend.services.copywriting_service import get_llm_client
from campaigns.backend.services.omnichannel_fallback_service import (
    evaluate_stuck_linkedin_invitations,
    generate_bridge_message,
    execute_channel_fallback,
)
from campaigns.backend.services.template_spintax_guard import (
    calculate_spintax_combinations,
    ensure_minimum_entropy,
    resolve_spintax,
)
from leads.backend.services.lead_ingestion_service import execute_bulk_import_leads


class TestStage12EliteArchitecture(unittest.TestCase):

    def setUp(self):
        vault._cache.clear()
        vault._quarantine.clear()

    def test_omnichannel_fallback_webhook_emission_and_suppression_filter(self):
        """
        Layer 0 & 1: Verifies that omnichannel fallback ignores connected/booked leads,
        flags suppressed leads as 'suppressed' channel, and emits webhook events cleanly.
        """
        mock_supabase = MagicMock()
        mock_supabase.table().select().eq().eq().lte().limit().execute.return_value.data = [
            {
                "id": "act-1",
                "executed_at": "2026-10-01T00:00:00Z",
                "lead_id": "lead-connected",
                "leads": {
                    "id": "lead-connected",
                    "status": "connected",
                    "email": "connected@example.com",
                    "linkedin_url": "https://linkedin.com/in/connected"
                }
            },
            {
                "id": "act-2",
                "executed_at": "2026-10-01T00:00:00Z",
                "lead_id": "lead-suppressed",
                "leads": {
                    "id": "lead-suppressed",
                    "status": "open",
                    "email": "suppressed@competitor.com",
                    "linkedin_url": "https://linkedin.com/in/suppressed"
                }
            },
            {
                "id": "act-3",
                "executed_at": "2026-10-01T00:00:00Z",
                "lead_id": "lead-active",
                "leads": {
                    "id": "lead-active",
                    "status": "open",
                    "email": "valid@prospect.com",
                    "linkedin_url": "https://linkedin.com/in/active"
                }
            }
        ]

        with patch("leads.backend.services.suppression_service.check_lead_suppression") as mock_supp:
            def side_effect_supp(supabase, workspace_id, linkedin_url=None, email=None, domain=None):
                if email == "suppressed@competitor.com":
                    return {"suppressed": True, "matched_by": "email", "matched_value": email, "reason": "DNC"}
                return {"suppressed": False, "matched_by": None, "matched_value": None, "reason": None}

            mock_supp.side_effect = side_effect_supp

            res = evaluate_stuck_linkedin_invitations(mock_supabase, "ws-stage12", days_threshold=7)
            self.assertEqual(res["status"], "success")
            # lead-connected is skipped because status is 'connected'
            stuck_ids = [l["lead_id"] for l in res["stuck_leads"]]
            self.assertNotIn("lead-connected", stuck_ids)
            self.assertIn("lead-suppressed", stuck_ids)
            self.assertIn("lead-active", stuck_ids)

            # Suppressed lead must recommend 'suppressed' channel
            supp_lead = next(l for l in res["stuck_leads"] if l["lead_id"] == "lead-suppressed")
            self.assertEqual(supp_lead["recommended_channel"], "suppressed")
            self.assertTrue(supp_lead["is_suppressed"])

            # Valid lead recommends 'email'
            act_lead = next(l for l in res["stuck_leads"] if l["lead_id"] == "lead-active")
            self.assertEqual(act_lead["recommended_channel"], "email")
            self.assertFalse(act_lead["is_suppressed"])

        # Test webhook emission during execute_channel_fallback
        with patch("integrations.backend.services.webhook_service.emit_webhook_event") as mock_emit:
            fb_res = execute_channel_fallback(
                supabase=mock_supabase,
                workspace_id="ws-stage12",
                lead_id="lead-active",
                target_channel="email",
                lead_name="Alexander Hamilton",
                company="Treasury Ops"
            )
            self.assertEqual(fb_res["status"], "success")
            mock_emit.assert_called_once()
            call_kwargs = mock_emit.call_args[1]
            self.assertEqual(call_kwargs["event_type"], "lead.channel_cascaded")
            self.assertEqual(call_kwargs["payload"]["lead_id"], "lead-active")

    def test_vault_ai_provider_resolution_and_byok_decryption(self):
        """
        Layer 0 & 1: Verifies that CredentialVault securely resolves and decrypts
        AES-256-GCM encrypted BYOK keys for AI providers (OpenAI, Anthropic, DeepSeek, Groq).
        """
        raw_key = "sk-test-live-openai-key-secret-999"
        encrypted_envelope = encrypt_byok_key(raw_key)
        self.assertTrue(encrypted_envelope.startswith("v1:gcm:"))

        mock_supabase = MagicMock()
        mock_supabase.table().select().eq().limit().execute.return_value.data = [
            {
                "workspace_id": "ws-byok-ai",
                "api_key_openai": encrypted_envelope,
                "settings": {}
            }
        ]

        # 1. Test vault resolution
        resolved = vault.resolve_credential("ws-byok-ai", "openai", supabase_client=mock_supabase)
        self.assertEqual(resolved, raw_key)

        # 2. Test get_llm_client in copywriting service
        client, model = get_llm_client(workspace_id="ws-byok-ai", supabase_client=mock_supabase)
        self.assertIsNotNone(client)
        self.assertEqual(client.api_key, raw_key)

        # 3. Test quarantine on 401
        vault.quarantine_credential("ws-byok-ai", "openai", reason="HTTP 401 Unauthorized")
        is_quar, reason = vault.is_quarantined("ws-byok-ai", "openai")
        self.assertTrue(is_quar)
        self.assertIn("401", reason)

        # Subsequent resolution should return None due to quarantine
        quarantined_res = vault.resolve_credential("ws-byok-ai", "openai", supabase_client=mock_supabase)
        self.assertIsNone(quarantined_res)

    def test_template_anti_fingerprint_entropy_guard(self):
        """
        Layer 0 & 2: Verifies that ensure_minimum_entropy detects low-variation templates
        and auto-upgrades them with semantic spintax without breaking {{variable}} tags.
        """
        # Static template with 1 combination
        static_template = "Hi {{first_name}}, saw your profile and loved what you are building at {{company}}. Best, Alex"
        combinations = calculate_spintax_combinations(static_template)
        self.assertEqual(combinations, 1)

        # Check entropy verification with auto_upgrade=True
        entropy_res = ensure_minimum_entropy(static_template, required_variants=6, auto_upgrade=True)
        self.assertTrue(entropy_res["compliant"])
        self.assertTrue(entropy_res["upgraded"])
        self.assertGreaterEqual(entropy_res["variants"], 6)

        upgraded_text = entropy_res["template"]
        # Double-brace variables must be intact
        self.assertIn("{{first_name}}", upgraded_text)
        self.assertIn("{{company}}", upgraded_text)
        # Injected spintax must be present
        self.assertIn("{Hi|Hello|Hey}", upgraded_text)

        # Render variations and ensure they generate distinct outputs
        v1 = resolve_spintax(upgraded_text, seed="seed_1")
        v2 = resolve_spintax(upgraded_text, seed="seed_2")
        self.assertIn("{{first_name}}", v1)
        self.assertIn("{{first_name}}", v2)

    def test_lead_ingestion_suppression_quarantine(self):
        """
        Layer 1 & 2: Verifies that bulk import immediately quarantines re-imported leads
        whose email, linkedin_url, or domain matches the workspace suppression list.
        """
        mock_supabase = MagicMock()
        mock_supabase.rpc().execute.return_value.data = {"success": True, "inserted_count": 2}

        leads_to_import = [
            {
                "first_name": "Valid",
                "last_name": "Lead",
                "email": "valid@acmecorp.com",
                "linkedin_url": "https://linkedin.com/in/valid-lead"
            },
            {
                "first_name": "Competitor",
                "last_name": "Spy",
                "email": "spy@competitor.com",
                "linkedin_url": "https://linkedin.com/in/competitor-spy"
            }
        ]

        with patch("leads.backend.services.suppression_service.check_lead_suppression") as mock_supp:
            def side_effect(supabase, workspace_id, linkedin_url=None, email=None, domain=None):
                if email == "spy@competitor.com" or "competitor-spy" in str(linkedin_url):
                    return {"suppressed": True, "matched_by": "email", "matched_value": email, "reason": "Competitor Domain"}
                return {"suppressed": False, "matched_by": None, "matched_value": None, "reason": None}

            mock_supp.side_effect = side_effect

            res = execute_bulk_import_leads(
                supabase=mock_supabase,
                list_id="list-stage12",
                workspace_id="ws-stage12",
                leads=leads_to_import
            )
            self.assertTrue(res["success"])

            # Inspect payload sent to RPC
            rpc_call = mock_supabase.rpc.call_args
            self.assertEqual(rpc_call[0][0], "bulk_import_leads")
            payload = rpc_call[0][1]
            imported_leads = payload["p_leads"]

            valid_lead = next(l for l in imported_leads if l["email"] == "valid@acmecorp.com")
            self.assertNotEqual(valid_lead.get("status"), "QUARANTINED")

            spy_lead = next(l for l in imported_leads if l["email"] == "spy@competitor.com")
            self.assertEqual(spy_lead.get("status"), "QUARANTINED")
            self.assertIn("SUPPRESSION_LIST_MATCH", spy_lead.get("quarantine_reason", ""))
