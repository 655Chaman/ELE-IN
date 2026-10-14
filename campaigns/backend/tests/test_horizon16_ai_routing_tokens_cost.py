"""
test_horizon16_ai_routing_tokens_cost.py

Horizon 16: Advanced AI Multi-Model Routing, Token Usage Caching & Cost Accounting
Adheres strictly to the Three-Layer Logic Architecture (Paranoia Framework):
- Layer 0: Foundational Layer (Model routing, real cost math, client caching, failover waterfall)
- Layer 1: Environmental Failure Analysis (Token bounds, network/provider failures, key quarantine, event loop isolation)
- Layer 2: Human Paranoia (Jailbreak stripping, dirty token sanitization, credit double-spend prevention, 400 Bad Request innocence)
"""

import unittest
import time
import json
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch

from knowledge.backend.services.elein_ai_service import (
    _resolve_model,
    _calculate_real_cost,
    _normalize_api_key_and_config,
    _clean_token_string,
    _get_sync_client,
    _get_async_client,
    _mark_key_failed,
    _run_llm_with_failover,
    stream_reply_draft,
    classify_intent,
    UsageLimitExceededError,
    ROUTING_CONFIG,
    MODEL_COSTS_PER_MILLION,
    _rate_limited_env_keys,
    _sync_client_cache,
    _async_client_cache,
    _client_cache_lock,
)
from core.backend.services.credit_service import (
    refund_credits,
    add_credits,
    deduct_credits,
    check_and_notify_low_balance,
    check_tier_access,
    get_credit_balance,
)


class TestHorizon16ModelRoutingAndCost(unittest.TestCase):
    """Test model resolution waterfalls and mathematical token accounting."""

    def test_resolve_model_auto_route_and_defaults(self):
        """Layer 0: Verify auto-route falls back to task-specific defaults."""
        self.assertEqual(
            _resolve_model("", "scoring"),
            ROUTING_CONFIG["scoring"]
        )
        self.assertEqual(
            _resolve_model("Auto-Route (Recommended)", "intent"),
            ROUTING_CONFIG["intent"]
        )
        self.assertEqual(
            _resolve_model("Auto-Route (Recommended)", "drafting"),
            ROUTING_CONFIG["drafting"]
        )
        # Unknown task fallback
        self.assertEqual(
            _resolve_model(None, "non_existent_task"),
            ["meta/llama-3.2-11b-vision-instruct"]
        )

    def test_resolve_model_friendly_name_mapping(self):
        """Layer 0: Verify human-friendly model names resolve to provider URNs."""
        self.assertEqual(_resolve_model("DeepSeek V4 Pro", "any"), ["deepseek-ai/deepseek-r1"])
        self.assertEqual(_resolve_model("GPT-OS", "any"), ["openai/gpt-oss-20b"])
        self.assertEqual(_resolve_model("Kimi k3", "any"), ["moonshot-v1-32k"])
        self.assertEqual(_resolve_model("Llama-3.2 11B", "any"), ["meta/llama-3.2-11b-vision-instruct"])
        self.assertEqual(_resolve_model("Nemotron 120B", "any"), ["nvidia/nemotron-4-340b-instruct"])

    def test_resolve_model_explicit_urn_and_unrecognized_fallback(self):
        """Layer 2 Paranoia: Explicit model URNs are honored; unknown strings fallback to task default."""
        self.assertEqual(_resolve_model("meta/llama-3.1-8b-instruct", "scoring"), ["meta/llama-3.1-8b-instruct"])
        self.assertEqual(_resolve_model("gpt-4o-mini", "drafting"), ["gpt-4o-mini"])
        self.assertEqual(_resolve_model("custom-vendor/model-v1", "synthesis"), ["custom-vendor/model-v1"])
        # Unrecognized string without slash falls back to task default
        self.assertEqual(_resolve_model("nonexistent_model", "scoring"), ROUTING_CONFIG["scoring"])

    def test_calculate_real_cost_exact_math(self):
        """Layer 0: Verify exact cost per million calculation."""
        # nemotron-3-super-120b-a12b is (3.50, 3.50) per million
        cost = _calculate_real_cost("nvidia/nemotron-3-super-120b-a12b", 1000, 500)
        expected = (1000 * 3.50 + 500 * 3.50) / 1_000_000
        self.assertAlmostEqual(cost, expected, places=7)

        # deepseek-ai/deepseek-r1 is (0.55, 2.19)
        cost_ds = _calculate_real_cost("deepseek-ai/deepseek-r1", 10_000, 2_000)
        expected_ds = (10_000 * 0.55 + 2_000 * 2.19) / 1_000_000
        self.assertAlmostEqual(cost_ds, expected_ds, places=7)

    def test_calculate_real_cost_unlisted_model_fallback(self):
        """Layer 1: Verify unlisted model defaults to 0.60 / 0.60 per million."""
        cost = _calculate_real_cost("unknown-model", 1000, 1000)
        expected = (1000 * 0.60 + 1000 * 0.60) / 1_000_000
        self.assertAlmostEqual(cost, expected, places=7)

    def test_calculate_real_cost_edge_cases_and_paranoia(self):
        """Layer 1/2 Paranoia: Negative, None, string, float, and invalid tokens never break or cause negative costs."""
        self.assertEqual(_calculate_real_cost("meta/llama-3.1-8b-instruct", -100, -50), 0.0)
        self.assertEqual(_calculate_real_cost("meta/llama-3.1-8b-instruct", None, None), 0.0)
        self.assertEqual(_calculate_real_cost("meta/llama-3.1-8b-instruct", "invalid", "bad"), 0.0)
        
        # Numeric strings and floats convert safely
        cost_str = _calculate_real_cost("meta/llama-3.1-8b-instruct", "1000", "500.5")
        expected = (1000 * 0.10 + 500 * 0.10) / 1_000_000
        self.assertAlmostEqual(cost_str, expected, places=7)


class TestHorizon16TokenHygieneAndClientPooling(unittest.TestCase):
    """Test token cleaning, polymorphic normalization, and connection cache pooling."""

    def setUp(self):
        with _client_cache_lock:
            _sync_client_cache.clear()
            _async_client_cache.clear()

    def test_clean_token_string_hygiene(self):
        """Layer 2 Paranoia: Test aggressive stripping of quotes, backticks, and Bearer prefix."""
        self.assertEqual(_clean_token_string("  nvapi-test123  "), "nvapi-test123")
        self.assertEqual(_clean_token_string('"nvapi-quoted"'), "nvapi-quoted")
        self.assertEqual(_clean_token_string("'nvapi-single'"), "nvapi-single")
        self.assertEqual(_clean_token_string("`nvapi-backtick`"), "nvapi-backtick")
        self.assertEqual(_clean_token_string("Bearer nvapi-bearer"), "nvapi-bearer")
        self.assertEqual(_clean_token_string('Bearer "nvapi-both"'), "nvapi-both")
        self.assertEqual(_clean_token_string('"Bearer nvapi-inside"'), "nvapi-inside")

    def test_normalize_api_key_polymorphic(self):
        """Layer 0: Test normalization of str, dict, and custom object."""
        # Raw string with nvidia prefix
        k, p, url, to = _normalize_api_key_and_config("nvapi-12345")
        self.assertEqual(k, "nvapi-12345")
        self.assertEqual(p, "nvidia")
        self.assertEqual(url, "https://integrate.api.nvidia.com/v1")
        self.assertEqual(to, 120.0)

        # Raw string with openai prefix
        k, p, url, to = _normalize_api_key_and_config("sk-openai123")
        self.assertEqual(k, "sk-openai123")
        self.assertEqual(p, "openai")
        self.assertIsNone(url)

        # Dict with explicit config
        cfg = {"key": "  'sk-custom'  ", "provider": "openai", "url": "https://custom.api/v1", "timeout": 45}
        k, p, url, to = _normalize_api_key_and_config(cfg)
        self.assertEqual(k, "sk-custom")
        self.assertEqual(p, "openai")
        self.assertEqual(url, "https://custom.api/v1")
        self.assertEqual(to, 45.0)

        # Object with attributes
        class CustomKeyObj:
            key = "Bearer nvapi-objkey"
            provider = "nvidia"
            timeout = 30
        k, p, url, to = _normalize_api_key_and_config(CustomKeyObj())
        self.assertEqual(k, "nvapi-objkey")
        self.assertEqual(p, "nvidia")
        self.assertEqual(to, 30.0)

    def test_normalize_api_key_invalid_inputs(self):
        """Layer 2 Paranoia: None or empty keys raise ValueError."""
        with self.assertRaises(ValueError):
            _normalize_api_key_and_config(None)
        with self.assertRaises(ValueError):
            _normalize_api_key_and_config("")
        with self.assertRaises(ValueError):
            _normalize_api_key_and_config({"key": "   "})

    def test_sync_client_pooling(self):
        """Layer 1: Verify sync clients are connection-pooled and reused across identical configs."""
        calls = []
        class DummyOpenAI:
            def __init__(self, base_url=None, api_key=None, timeout=None):
                calls.append((base_url, api_key, timeout))
                self.base_url = base_url
                self.api_key = api_key
                self.timeout = timeout

        with patch("knowledge.backend.services.elein_ai_service.OpenAI", DummyOpenAI):
            client1 = _get_sync_client("nvapi-key1", timeout=60.0)
            client2 = _get_sync_client("nvapi-key1", timeout=60.0)
            self.assertIs(client1, client2)
            self.assertEqual(len(calls), 1)

            # Different timeout creates a distinct client
            client3 = _get_sync_client("nvapi-key1", timeout=30.0)
            self.assertIsNot(client1, client3)
            self.assertEqual(len(calls), 2)


class TestHorizon16KeyQuarantine(unittest.TestCase):
    """Test key failure marking, 400 Bad Request innocence, and quarantine mechanics."""

    def setUp(self):
        from knowledge.backend.services import elein_ai_service
        elein_ai_service._rate_limited_env_keys.clear()

    def test_bad_request_400_spares_key(self):
        """Layer 0 Paranoia: 400 Bad Request must NOT quarantine or kill the API key."""
        from knowledge.backend.services import elein_ai_service
        mock_supabase = MagicMock()
        with patch("knowledge.backend.services.elein_ai_service.get_service_client", return_value=mock_supabase):
            _mark_key_failed("env_generic", "Error code: 400 - {'error': {'message': 'Bad Request'}}", actual_api_key="nvapi-test")
            self.assertNotIn("nvapi-test", elein_ai_service._rate_limited_env_keys)
            mock_supabase.table.assert_not_called()

            # Test DB key
            _mark_key_failed("db-key-uuid-123", "400 Bad Request: model not found")
            mock_supabase.table.assert_not_called()

    def test_rate_limit_429_quarantines_env_key(self):
        """Layer 1: 429 Rate Limit quarantines env key in memory and updates system_api_keys."""
        from knowledge.backend.services import elein_ai_service
        mock_supabase = MagicMock()
        mock_table = MagicMock()
        mock_supabase.table.return_value = mock_table
        mock_table.upsert.return_value.execute.return_value = MagicMock()

        with patch("knowledge.backend.services.elein_ai_service.get_service_client", return_value=mock_supabase):
            _mark_key_failed("env_generic", "429 Rate Limit Exceeded", actual_api_key="nvapi-rl-key")
            self.assertIn("nvapi-rl-key", elein_ai_service._rate_limited_env_keys)
            self.assertGreater(elein_ai_service._rate_limited_env_keys["nvapi-rl-key"], time.time())
            mock_supabase.table.assert_called_with("system_api_keys")
            mock_table.upsert.assert_called_with({"api_key": "nvapi-rl-key", "status": "rate_limited"})

    def test_auth_failure_401_403_exhausts_env_key(self):
        """Layer 1: 401/403 auth failures update status to exhausted."""
        mock_supabase = MagicMock()
        mock_table = MagicMock()
        mock_supabase.table.return_value = mock_table
        mock_table.upsert.return_value.execute.return_value = MagicMock()

        with patch("knowledge.backend.services.elein_ai_service.get_service_client", return_value=mock_supabase):
            _mark_key_failed("env_generic", "401 Unauthorized: Invalid API key", actual_api_key="nvapi-dead-key")
            mock_supabase.table.assert_called_with("system_api_keys")
            mock_table.upsert.assert_called_with({"api_key": "nvapi-dead-key", "status": "exhausted"})

    def test_polymorphic_dict_key_failure(self):
        """Layer 2: Passing dict as key_id is safely decomposed into actual key and ID."""
        from knowledge.backend.services import elein_ai_service
        mock_supabase = MagicMock()
        mock_table = MagicMock()
        mock_supabase.table.return_value = mock_table
        mock_table.upsert.return_value.execute.return_value = MagicMock()

        with patch("knowledge.backend.services.elein_ai_service.get_service_client", return_value=mock_supabase):
            key_dict = {"id": "env_scoring", "key": "nvapi-dict-key"}
            _mark_key_failed(key_dict, "429 Too Many Requests")
            self.assertIn("nvapi-dict-key", elein_ai_service._rate_limited_env_keys)


class TestHorizon16RunLLMWithFailover(unittest.TestCase):
    """Test synchronous universal LLM failover, credit deduction, telemetry, and refund idempotency."""

    def test_run_llm_insufficient_credits_raises(self):
        """Layer 0: When credits cannot be deducted, raise UsageLimitExceededError."""
        mock_supabase = MagicMock()
        mock_rpc = MagicMock()
        mock_supabase.rpc.return_value = mock_rpc
        mock_rpc.execute.return_value = MagicMock(data={"success": False, "reason": "insufficient_credits"})

        with patch("core.backend.api.auth_dep.get_service_client", return_value=mock_supabase):
            with self.assertRaises(UsageLimitExceededError):
                _run_llm_with_failover(
                    system_prompt="sys",
                    user_prompt="user",
                    workspace_id="ws-123"
                )

    def test_run_llm_no_keys_refunds_credits(self):
        """Layer 1: When no API keys exist, refund deducted credit and return empty string."""
        mock_supabase = MagicMock()
        mock_rpc = MagicMock()
        mock_supabase.rpc.return_value = mock_rpc
        mock_rpc.execute.return_value = MagicMock(data={"success": True})

        with patch("core.backend.api.auth_dep.get_service_client", return_value=mock_supabase), \
             patch("knowledge.backend.services.elein_ai_service.get_active_nvidia_keys", return_value=[]):
            res = _run_llm_with_failover(
                system_prompt="sys",
                user_prompt="user",
                workspace_id="ws-123",
                idempotency_key="idem_no_keys"
            )
            self.assertEqual(res, "")
            # Check refund was called
            refund_called = any(
                call[0][0] == 'add_credits_safely' and call[0][1].get('p_event_id') == 'refund_idem_no_keys'
                for call in mock_supabase.rpc.call_args_list
            )
            self.assertTrue(refund_called, "add_credits_safely should be called to refund when no keys are available")

    def test_run_llm_success_and_telemetry_logging(self):
        """Layer 0: Successful generation inserts telemetry into ai_generations with exact cost."""
        mock_supabase = MagicMock()
        mock_rpc = MagicMock()
        mock_supabase.rpc.return_value = mock_rpc
        mock_rpc.execute.return_value = MagicMock(data={"success": True})

        mock_table = MagicMock()
        mock_supabase.table.return_value = mock_table
        mock_table.insert.return_value.execute.return_value = MagicMock()

        # Mock OpenAI completion
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "Excellent response"
        mock_resp.choices = [mock_choice]
        mock_resp.usage = MagicMock(total_tokens=150, prompt_tokens=100, completion_tokens=50)
        mock_client.chat.completions.create.return_value = mock_resp

        with patch("core.backend.api.auth_dep.get_service_client", return_value=mock_supabase), \
             patch("core.backend.services.credit_service.check_tier_access", return_value=True), \
             patch("knowledge.backend.services.elein_ai_service.get_active_nvidia_keys", return_value=[{"id": "k1", "key": "nvapi-k1"}]), \
             patch("knowledge.backend.services.elein_ai_service._get_sync_client", return_value=mock_client), \
             patch("knowledge.backend.services.elein_ai_service.check_ai_rate_limit_db", return_value=True):
            
            res = _run_llm_with_failover(
                system_prompt="sys prompt",
                user_prompt="user prompt",
                workspace_id="ws-123",
                ai_model="meta/llama-3.1-8b-instruct"
            )
            self.assertEqual(res, "Excellent response")
            # Verify telemetry logged
            mock_supabase.table.assert_called_with("ai_generations")
            insert_args = mock_table.insert.call_args[0][0]
            self.assertEqual(insert_args["workspace_id"], "ws-123")
            self.assertEqual(insert_args["model"], "meta/llama-3.1-8b-instruct")
            self.assertEqual(insert_args["tokens_used"], 150)
            self.assertGreater(insert_args["cost"], 0.0)

    def test_run_llm_bad_request_aborts_and_refunds(self):
        """Layer 0 Paranoia: 400 Bad Request aborts failover immediately and refunds credits."""
        mock_supabase = MagicMock()
        mock_rpc = MagicMock()
        mock_supabase.rpc.return_value = mock_rpc
        mock_rpc.execute.return_value = MagicMock(data={"success": True})

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("400 Bad Request: prompt contains invalid tokens")

        with patch("core.backend.api.auth_dep.get_service_client", return_value=mock_supabase), \
             patch("knowledge.backend.services.elein_ai_service.get_active_nvidia_keys", return_value=[{"id": "k1", "key": "nvapi-k1"}, {"id": "k2", "key": "nvapi-k2"}]), \
             patch("knowledge.backend.services.elein_ai_service._get_sync_client", return_value=mock_client), \
             patch("knowledge.backend.services.elein_ai_service.check_ai_rate_limit_db", return_value=True):

            res = _run_llm_with_failover(
                system_prompt="sys",
                user_prompt="user",
                workspace_id="ws-123",
                idempotency_key="idem_400_test"
            )
            self.assertEqual(res, "")
            # Verify it only called chat.completions.create ONCE (did not cascade across second key)
            self.assertEqual(mock_client.chat.completions.create.call_count, 1)
            # Verify credit refund was called
            refund_called = any(
                call[0][0] == 'add_credits_safely' and call[0][1].get('p_event_id') == 'refund_idem_400_test'
                for call in mock_supabase.rpc.call_args_list
            )
            self.assertTrue(refund_called, "Credits should be refunded on 400 Bad Request abort")


class TestHorizon16StreamAndIntentClassification(unittest.IsolatedAsyncioTestCase):
    """Test asynchronous streaming and intent classification error paths and credit idempotency."""

    async def test_stream_reply_draft_insufficient_credits(self):
        """Layer 0: stream_reply_draft yields error string when credits cannot be deducted."""
        mock_supabase = MagicMock()
        mock_rpc = MagicMock()
        mock_supabase.rpc.return_value = mock_rpc
        mock_rpc.execute.return_value = MagicMock(data={"success": False, "reason": "insufficient_credits"})

        with patch("core.backend.api.auth_dep.get_service_client", return_value=mock_supabase):
            gen = stream_reply_draft(
                sender_name="Alice",
                thread_messages=[{"message_text": "Interested"}],
                workspace_id="ws-123",
                is_simulation=False
            )
            chunks = [c async for c in gen]
            self.assertEqual(chunks, ["AI Error: insufficient_credits"])

    async def test_stream_reply_draft_no_keys_refunds(self):
        """Layer 1: stream_reply_draft refunds credits and yields message when no keys exist in non-simulation."""
        mock_supabase = MagicMock()
        mock_rpc = MagicMock()
        mock_supabase.rpc.return_value = mock_rpc
        mock_rpc.execute.return_value = MagicMock(data={"success": True})

        with patch("core.backend.api.auth_dep.get_service_client", return_value=mock_supabase), \
             patch("knowledge.backend.services.elein_ai_service.get_active_nvidia_keys", return_value=[]), \
             patch.dict("os.environ", {"ALLOW_MOCK_BILLING": "false"}):

            gen = stream_reply_draft(
                sender_name="Alice",
                thread_messages=[{"message_text": "Interested"}],
                workspace_id="ws-123",
                idempotency_key="idem_stream_nokeys",
                is_simulation=False
            )
            chunks = [c async for c in gen]
            self.assertEqual(chunks, ["No AI keys configured. Please add NVIDIA API keys to continue."])
            
            refund_called = any(
                call[0][0] == 'add_credits_safely' and call[0][1].get('p_event_id') in ('refund_idem_stream_nokeys', 'refund_ws-123_idem_stream_nokeys')
                for call in mock_supabase.rpc.call_args_list
            )
            self.assertTrue(refund_called, "stream_reply_draft should refund credits when no keys exist")

    async def test_classify_intent_insufficient_credits(self):
        """Layer 0: classify_intent returns unknown with error on insufficient credits."""
        mock_supabase = MagicMock()
        mock_rpc = MagicMock()
        mock_supabase.rpc.return_value = mock_rpc
        mock_rpc.execute.return_value = MagicMock(data={"success": False, "reason": "insufficient_credits"})

        with patch("core.backend.api.auth_dep.get_service_client", return_value=mock_supabase):
            res = await classify_intent("Sounds great!", workspace_id="ws-123")
            self.assertEqual(res.get("intent"), "unknown")
            self.assertEqual(res.get("error"), "insufficient_credits")

    async def test_classify_intent_success(self):
        """Layer 0: classify_intent parses JSON reply into structured label."""
        mock_supabase = MagicMock()
        mock_rpc = MagicMock()
        mock_supabase.rpc.return_value = mock_rpc
        mock_rpc.execute.return_value = MagicMock(data={"success": True})

        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = json.dumps({
            "intent": "positive",
            "confidence": 0.95,
            "reasoning": "Prospect agreed to meet",
            "confirmed_time": "2026-10-15T14:00:00Z"
        })
        mock_resp.choices = [mock_choice]
        mock_resp.usage = MagicMock(total_tokens=50)
        mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)

        with patch("core.backend.api.auth_dep.get_service_client", return_value=mock_supabase), \
             patch("knowledge.backend.services.elein_ai_service.get_active_nvidia_keys", return_value=[{"id": "k1", "key": "nvapi-k1"}]), \
             patch("knowledge.backend.services.elein_ai_service._get_async_client", return_value=mock_client):

            res = await classify_intent("Sounds great, let's talk next week", workspace_id="ws-123")
            self.assertEqual(res["intent"], "positive")
            self.assertEqual(res["confidence"], 0.95)
            self.assertEqual(res["confirmed_time"], "2026-10-15T14:00:00Z")
            self.assertEqual(res["label"], "Interested")


class TestHorizon16CreditService(unittest.TestCase):
    """Test credit_service.py refund, add, deduct, and tier evaluation."""

    def test_refund_credits_success(self):
        """Layer 0: refund_credits formats RPC call cleanly."""
        mock_supabase = MagicMock()
        mock_rpc = MagicMock()
        mock_supabase.rpc.return_value = mock_rpc
        mock_rpc.execute.return_value = MagicMock(data={"success": True, "balance": 105})

        with patch("core.backend.services.credit_service.get_service_client", return_value=mock_supabase):
            res = refund_credits("ws-123", 5, "idem_abc", reason="test_refund")
            self.assertTrue(res.get("success"))
            mock_supabase.rpc.assert_called_with('add_credits_safely', {
                'p_workspace_id': 'ws-123',
                'p_credits': 5,
                'p_event_id': 'refund_ws-123_idem_abc',
                'p_provider': 'test_refund'
            })

    def test_refund_credits_input_hygiene(self):
        """Layer 2 Paranoia: Missing workspace or negative/invalid amount handled safely."""
        self.assertFalse(refund_credits("", 5, "idem_abc")["success"])
        self.assertFalse(refund_credits("ws-123", 5, "")["success"])

        mock_supabase = MagicMock()
        mock_rpc = MagicMock()
        mock_supabase.rpc.return_value = mock_rpc
        mock_rpc.execute.return_value = MagicMock(data={"success": True})

        with patch("core.backend.services.credit_service.get_service_client", return_value=mock_supabase):
            # Non-integer / negative amount clamped to 1
            refund_credits("ws-123", -10, "refund_already_prefixed")
            mock_supabase.rpc.assert_called_with('add_credits_safely', {
                'p_workspace_id': 'ws-123',
                'p_credits': 1,
                'p_event_id': 'refund_ws-123_refund_already_prefixed',
                'p_provider': 'system_refund'
            })

    def test_add_credits_success(self):
        """Layer 0: add_credits formats RPC call cleanly."""
        mock_supabase = MagicMock()
        mock_rpc = MagicMock()
        mock_supabase.rpc.return_value = mock_rpc
        mock_rpc.execute.return_value = MagicMock(data={"success": True, "balance": 500})

        with patch("core.backend.services.credit_service.get_service_client", return_value=mock_supabase):
            res = add_credits("ws-123", 200, "evt_topup_123", provider="stripe")
            self.assertTrue(res.get("success"))
            mock_supabase.rpc.assert_called_with('add_credits_safely', {
                'p_workspace_id': 'ws-123',
                'p_credits': 200,
                'p_event_id': 'evt_topup_123',
                'p_provider': 'stripe'
            })

    def test_check_tier_access(self):
        """Layer 0: check_tier_access evaluates FREE, PRO, and ENTERPRISE tiers."""
        mock_supabase = MagicMock()
        mock_table = MagicMock()
        mock_supabase.table.return_value = mock_table
        mock_table.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"tier": "FREE"}]
        )

        with patch("core.backend.services.credit_service.get_service_client", return_value=mock_supabase):
            self.assertFalse(check_tier_access("ws-free", "enrichment"))
            self.assertFalse(check_tier_access("ws-free", "apify"))

        mock_table.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"tier": "PRO"}]
        )
        with patch("core.backend.services.credit_service.get_service_client", return_value=mock_supabase):
            self.assertTrue(check_tier_access("ws-pro", "enrichment"))
            self.assertTrue(check_tier_access("ws-pro", "apify"))


if __name__ == '__main__':
    unittest.main()
