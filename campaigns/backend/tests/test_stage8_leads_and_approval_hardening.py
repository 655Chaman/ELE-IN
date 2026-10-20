import pytest
from unittest.mock import MagicMock, patch

from leads.backend.services.lead_ingestion_service import (
    execute_bulk_import_leads,
    RESERVED_SYSTEM_LEAD_KEYS,
    STANDARD_LEAD_ATTRIBUTES,
)
from leads.backend.services.data_hygiene import DataHygieneService
from leads.backend.routers.leads import sanitize_csv_value
from campaigns.backend.services.elein_executor import EleInNodeExecutor, Branch
from campaigns.backend.services.elein_orchestrator import interpolate, EleInOrchestrator


# ============================================================================
# FLAW 27 & 28: Lead Ingestion Custom Variables, System Collision & DDE Injection
# ============================================================================

def test_flaw27_lead_ingestion_custom_variables_preserved_and_system_keys_isolated():
    """
    Paranoia Layer 0 & 2: Non-standard columns (technology, acv, funding_round)
    must be preserved in metadata['custom_variables'], while system reserved keys
    (status, workspace_id, id) must never overwrite system pipeline columns.
    """
    mock_supabase = MagicMock()
    # Mock RPC failure to test chunked direct table & in-memory paths
    mock_supabase.rpc.side_effect = Exception("RPC bulk_import_leads not found")
    
    # Mock table queries
    mock_table = MagicMock()
    mock_supabase.table.return_value = mock_table
    mock_table.select.return_value = mock_table
    mock_table.eq.return_value = mock_table
    mock_table.or_.return_value = mock_table
    mock_table.in_.return_value = mock_table
    mock_table.execute.return_value = MagicMock(data=[])
    mock_table.insert.return_value = mock_table
    mock_table.upsert.return_value = mock_table

    leads_payload = [
        {
            "first_name": "Alice",
            "last_name": "Smith",
            "email": "alice@cybercorp.com",
            "linkedin_url": "https://linkedin.com/in/alicesmith",
            "technology": "Kubernetes",
            "acv": "$120,000",
            "funding_round": "Series B",
            "pain_point": "Manual outreach scaling",
            # Adversarial: untrusted CSV attempts to overwrite pipeline status & workspace_id
            "status": "CONVERTED",
            "workspace_id": "malicious-workspace-override"
        }
    ]

    res = execute_bulk_import_leads(
        supabase=mock_supabase,
        list_id="list-test-123",
        workspace_id="ws-safe-100",
        leads=leads_payload,
        collision_policy="merge"
    )

    assert res["success"] is True

    # Verify that in mock_table.insert call for leads table, metadata was included and preserved
    assert mock_table.insert.called
    # The first insert call is to 'leads', the second is to 'list_members'
    inserted_rows = mock_table.insert.call_args_list[0][0][0]
    assert len(inserted_rows) == 1
    inserted_lead = inserted_rows[0]

    # Status must NOT be overwritten by the CSV "CONVERTED" value
    assert inserted_lead.get("status") != "CONVERTED"
    assert inserted_lead.get("workspace_id") == "ws-safe-100"

    # Custom variables must be isolated and safely stored in metadata['custom_variables']
    meta = inserted_lead.get("metadata", {})
    custom_vars = meta.get("custom_variables", {})
    assert custom_vars.get("technology") == "Kubernetes"
    assert custom_vars.get("acv") == "$120,000"
    assert custom_vars.get("funding_round") == "Series B"
    assert custom_vars.get("pain_point") == "Manual outreach scaling"

    # The CSV status must be safely redirected to custom_variables['csv_status']
    assert custom_vars.get("csv_status") == "CONVERTED"
    assert custom_vars.get("csv_workspace_id") == "malicious-workspace-override"


def test_flaw28_csv_dde_formula_injection_defense():
    """
    Paranoia Layer 0 & 1: Formula injection triggers (=, +, -, @, \t, \r)
    must be neutralized with leading single quote while legitimate signed numbers
    must be preserved intact.
    """
    # 1. Test Ingestion text sanitization
    malicious_formula = "=CMD|' /C calc'!A0"
    neutralized = DataHygieneService.sanitize_text(malicious_formula)
    assert neutralized.startswith("'=")

    at_formula = "@SUM(1+1)*cmd|' /C calc'!A0"
    assert DataHygieneService.sanitize_text(at_formula).startswith("'@")

    tab_trigger = "\t+cmd"
    assert DataHygieneService.sanitize_text(tab_trigger).startswith("'+cmd")

    # 2. Legitimate signed numbers must NOT be broken into strings
    assert DataHygieneService.sanitize_text("-42") == "-42"
    assert DataHygieneService.sanitize_text("+3.1415") == "+3.1415"
    assert DataHygieneService.sanitize_text("-0.05") == "-0.05"

    # 3. Test Export CSV sanitizer in leads router
    assert sanitize_csv_value("=1+1") == "'=1+1"
    assert sanitize_csv_value("-42") == "'-42"
    assert sanitize_csv_value("+99.9") == "'+99.9"
    assert sanitize_csv_value("@dangerous") == "'@dangerous"


# ============================================================================
# FLAW 29: AI Reply Approval Double-Dispatch Prevention
# ============================================================================

def test_flaw29_ai_reply_approval_double_dispatch_prevention():
    """
    Paranoia Layer 0 & 1: When an AI reply is approved, it is enqueued for
    delivery via LinkedInWorker job queue. When handle_ai_generate_reply runs
    subsequently for the execution state, it must detect approval_delivered_via_job: True
    and skip duplicate worker dispatch.
    """
    mock_supabase = MagicMock()
    executor = EleInNodeExecutor(mock_supabase, workspace_id="ws-stage8")
    executor.worker = MagicMock()

    node_data = {
        "_workspace_id": "ws-stage8",
        "_lead_id": "lead-999",
        "_enrollment_id": "enr-999",
        "_execution_state_id": "exec-999",
        "approved_ai_reply": "Thanks for your inquiry! Here is the pricing deck.",
        "approval_delivered_via_job": True
    }

    result = executor.handle_ai_generate_reply(node_data, "https://linkedin.com/in/prospect")

    assert result["status"] == "success"
    assert result["branch"] == Branch.THEN.value
    assert result["delivered_via"] == "approval_job_queue"

    # worker.send_message must NOT have been called, preventing double-messaging
    executor.worker.send_message.assert_not_called()


# ============================================================================
# FLAW 30: Custom Variables Template Interpolation in Sequences
# ============================================================================

def test_flaw30_custom_variables_template_interpolation_in_orchestrator():
    """
    Paranoia Layer 0 & 1: Template interpolation in orchestrator must resolve
    custom variables stored under opportunity['metadata']['custom_variables']
    without triggering unresolved variable safety aborts.
    """
    opportunity = {
        "id": "lead-custom-1",
        "first_name": "Marcus",
        "last_name": "Aurelius",
        "company_name": "Rome Inc",
        "metadata": {
            "custom_variables": {
                "technology": "Databricks",
                "funding_round": "Series C",
                "pain_point": "high compute costs"
            }
        }
    }

    template = "Hey {{first_name}}, saw {{company_name}} is scaling on {{technology}} after your {{funding_round}} round. Are you experiencing {{pain_point}}?"
    rendered = interpolate(template, opportunity)

    assert "Hey Marcus" in rendered
    assert "Rome Inc" in rendered
    assert "Databricks" in rendered
    assert "Series C" in rendered
    assert "high compute costs" in rendered
    assert "{{" not in rendered
    assert "}}" not in rendered


def test_flaw30_custom_variables_template_interpolation_in_executor():
    """
    Paranoia Layer 0 & 1: _interpolate_template in executor must unpack custom
    variables from lead metadata so that action steps render properly.
    """
    mock_supabase = MagicMock()
    mock_table = MagicMock()
    mock_supabase.table.return_value = mock_table
    mock_table.select.return_value = mock_table
    mock_table.eq.return_value = mock_table
    mock_table.limit.return_value = mock_table

    db_lead = {
        "first_name": "Elena",
        "last_name": "Rostova",
        "company_name": "Apex Cloud",
        "title": "VP Engineering",
        "metadata": {
            "custom_variables": {
                "cloud_provider": "AWS",
                "target_metric": "99.999% uptime"
            }
        }
    }
    mock_table.execute.return_value = MagicMock(data=[db_lead])

    executor = EleInNodeExecutor(supabase=mock_supabase, workspace_id="ws-stage8")
    data = {
        "_lead_id": "lead-elena",
        "body": "Hi {{first_name}}, noticed your team at {{company}} on {{cloud_provider}} aims for {{target_metric}}."
    }

    interpolated_body = executor._interpolate_template(data["body"], data)

    assert "Hi Elena" in interpolated_body
    assert "Apex Cloud" in interpolated_body
    assert "AWS" in interpolated_body
    assert "99.999% uptime" in interpolated_body


# ============================================================================
# FLAW 31: A/B Split Weighted Percentages & Edge Handle Normalization
# ============================================================================

def test_flaw31_ab_split_weighted_percentages_and_edge_handles():
    """
    Paranoia Layer 0 & 1: handle_ab_split must respect path_a_pct weights,
    and resolve_branch_edge must match diverse edge handles ('a', 'path_a', 'variant a').
    """
    mock_supabase = MagicMock()
    executor = EleInNodeExecutor(mock_supabase, workspace_id="ws-stage8")

    # 1. Test 100% Path A
    data_100_a = {
        "_lead_id": "lead-1",
        "_current_node_id": "ab-1",
        "path_a_pct": 100.0
    }
    res_a = executor.handle_ab_split(data_100_a, "https://linkedin.com/in/test")
    assert res_a["branch"] == "Path A"
    assert res_a["path_a_pct"] == 100.0

    # 2. Test 0% Path A (100% Path B)
    data_0_a = {
        "_lead_id": "lead-1",
        "_current_node_id": "ab-1",
        "path_a_pct": 0.0
    }
    res_b = executor.handle_ab_split(data_0_a, "https://linkedin.com/in/test")
    assert res_b["branch"] == "Path B"
    assert res_b["path_a_pct"] == 0.0

    # 3. Test resolve_branch_edge handle normalization in orchestrator
    orchestrator = EleInOrchestrator(mock_supabase)
    outgoing_edges = [
        {"id": "e1", "source_handle": "variant_a", "target_node_id": "node-variant-a"},
        {"id": "e2", "source_handle": "variant_b", "target_node_id": "node-variant-b"},
    ]

    edge_a, _ = orchestrator.resolve_branch_edge(outgoing_edges, "Path A")
    assert edge_a is not None
    assert edge_a["target_node_id"] == "node-variant-a"

    edge_b, _ = orchestrator.resolve_branch_edge(outgoing_edges, "Path B")
    assert edge_b is not None
    assert edge_b["target_node_id"] == "node-variant-b"
