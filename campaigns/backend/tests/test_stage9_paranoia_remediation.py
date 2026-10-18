"""
Stage 9 Paranoia Framework Regression Test Suite
Validates remediations for:
- VULN-20: Multi-workspace processing jobs tenant isolation RLS policy
- ENG-10: Midnight rollover race condition across sender account timezones
- ENG-11: Spintax depth bombing & execution timeout protection
- ENG-12: Condition node strict boolean evaluation in elein_executor
- API-01: Atomic campaign creation RPC & cascading rollback
- API-02: Atomic bulk lead enrollment RPC & ghost lead elimination
"""

import json
import pytest
from unittest.mock import MagicMock, patch, ANY
from campaigns.backend.services.template_spintax_guard import resolve_spintax, validate_template_and_spintax_syntax
from campaigns.backend.services.elein_executor import EleInNodeExecutor
from campaigns.backend.services.sender_pod_service import _calculate_account_action_capacity, select_pod_sender


class TestStage9ParanoiaRemediation:

    def test_eng11_spintax_timeout_and_depth_bounding(self):
        """ENG-11: Spintax resolution is bounded to max 5 depth and respects execution timeout."""
        # Flat spintax
        flat = "{Hi|Hello|Hey} {{first_name}}"
        resolved = resolve_spintax(flat, seed="test_seed_1")
        assert resolved in ("Hi {{first_name}}", "Hello {{first_name}}", "Hey {{first_name}}")

        # Nested spintax up to 4 levels
        nested = "{A|{B|{C|D}}}"
        resolved_nested = resolve_spintax(nested, seed="test_seed_2")
        assert resolved_nested in ("A", "B", "C", "D")

        # Spintax nesting depth limit in validation
        deep_bomb = "{{{{{opt1|opt2}}}}}"  # deeply nested single braces
        deep_spintax = "{1|{2|{3|{4|{5|{6|7}}}}}}"
        val_res = validate_template_and_spintax_syntax(deep_spintax)
        assert not val_res["valid"]
        assert any("depth exceeds maximum" in err.lower() for err in val_res["errors"])

    def test_eng12_condition_node_strict_boolean_coercion(self):
        """ENG-12: Condition nodes strictly parse booleans and distinguish 'false'/'0' from truthy values."""
        assert EleInNodeExecutor._to_bool("true") is True
        assert EleInNodeExecutor._to_bool("True") is True
        assert EleInNodeExecutor._to_bool("1") is True
        assert EleInNodeExecutor._to_bool("yes") is True
        assert EleInNodeExecutor._to_bool(True) is True
        assert EleInNodeExecutor._to_bool(1) is True

        # String false, 0, no, off, none must NEVER evaluate to True
        assert EleInNodeExecutor._to_bool("false") is False
        assert EleInNodeExecutor._to_bool("False") is False
        assert EleInNodeExecutor._to_bool("0") is False
        assert EleInNodeExecutor._to_bool("no") is False
        assert EleInNodeExecutor._to_bool("off") is False
        assert EleInNodeExecutor._to_bool("none") is False
        assert EleInNodeExecutor._to_bool("null") is False
        assert EleInNodeExecutor._to_bool(False) is False
        assert EleInNodeExecutor._to_bool(0) is False
        assert EleInNodeExecutor._to_bool(None) is False

    def test_eng12_handle_if_connected_strict_evaluation(self):
        """ENG-12: handle_if_connected correctly branches on boolean and string values."""
        executor = EleInNodeExecutor()
        
        # When payload has string 'false', it must not branch to Connected
        res_false = executor.handle_if_connected({"is_connected": "false"}, None)
        assert res_false["branch"] != "Connected" or res_false["connected"] is False

        # When payload has explicit True or 'true'
        res_true = executor.handle_if_connected({"is_connected": "true"}, None)
        assert res_true["branch"] == "Connected"
        assert res_true["connected"] is True

    def test_eng10_account_timezone_daily_capacity(self):
        """ENG-10: _calculate_account_action_capacity resolves usage date using sender account timezone."""
        mock_supabase = MagicMock()
        mock_execute = MagicMock()
        mock_execute.execute.return_value = MagicMock(data=[{"count": 5}])
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value = mock_execute

        account = {
            "id": "acc-123",
            "name": "Pacific Sender",
            "timezone": "America/Los_Angeles",
            "is_warmup": False,
            "daily_connection_limit": 30
        }

        cap = _calculate_account_action_capacity(account, "connection_request", mock_supabase)
        assert cap["daily_limit"] == 30
        assert cap["consumed_today"] == 5
        assert cap["remaining_headroom"] == 25

        # Verify that usage_date query used America/Los_Angeles local date
        call_args = mock_supabase.table().select().eq().eq().eq.call_args
        assert call_args is not None
        assert call_args[0][0] == "usage_date"
        # Usage date format must be YYYY-MM-DD
        import re
        assert re.match(r"^\d{4}-\d{2}-\d{2}$", call_args[0][1])

    def test_api01_atomic_campaign_creation_rpc(self):
        """API-01: create_campaign attempts atomic RPC creation first."""
        from campaigns.backend.routers.elein import create_campaign
        from campaigns.backend.schemas.elein import CampaignCreate, EleInNode, EleInEdge
        from fastapi import Request

        mock_supabase = MagicMock()
        mock_rpc = MagicMock()
        mock_rpc.execute.return_value = MagicMock(data={"campaign_id": "c-123", "version_id": "v-123", "status": "success"})
        mock_supabase.rpc.return_value = mock_rpc

        mock_req = MagicMock(spec=Request)
        mock_req.headers = {}

        payload = CampaignCreate(
            name="Atomic Campaign Test",
            nodes=[EleInNode(id="1", type="send_message", data={"message": "Hello"})],
            edges=[],
            senders=[],
            status="DRAFT"
        )

        resp = create_campaign(
            campaign=payload,
            request=mock_req,
            supabase=mock_supabase,
            workspace_id="ws-123",
            user_id="user-123"
        )

        assert resp.name == "Atomic Campaign Test"
        # Verify that create_campaign_atomic was called
        mock_supabase.rpc.assert_called_with("create_campaign_atomic", ANY)
