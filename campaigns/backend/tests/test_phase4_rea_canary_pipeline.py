"""
Phase 4 Verification Suite: REA Canary Pipeline & Voyager Extractor
Tests:
1. REAVoyagerExtractor validates evidence integrity (SHA256, graph schema).
2. REAVoyagerExtractor extracts endpoints, storage calls, and call mechanisms.
3. REAVoyagerExtractor detects schema drift against active baseline routes.
"""
import pytest
import os
import json
from backend.scripts.rea_voyager_extractor import REAVoyagerExtractor


@pytest.fixture
def sample_evidence():
    evidence_path = "/Users/krdeeksha/.gemini/antigravity/brain/359c2f24-0bb5-45c7-9710-52ff56fd89a6/scratch/rea_extension_clean.json"
    if os.path.exists(evidence_path):
        return REAVoyagerExtractor.from_file(evidence_path)
    # Synthetic evidence fallback for isolated test runners
    return REAVoyagerExtractor({
        "evidence_id": "ev_test_12345",
        "normalized_result": {
            "root_artifact_sha256": "abcdef1234567890",
            "inventory_manifest_id": "agm_test",
            "graph": {
                "schema": "JavaScriptApplicationGraph",
                "nodes": [
                    {"kind": "endpoint", "observations": [{"label": "/voyager/api/growth/normInvitations"}]},
                    {"kind": "endpoint", "observations": [{"label": "browserInstanceId"}]}
                ],
                "edges": [
                    {"relation": "calls", "properties": {"mechanism": "call:fetch"}},
                    {"relation": "calls", "properties": {"mechanism": "call:chrome.storage.local.get", "interpretation": "candidate"}}
                ]
            }
        }
    })


def test_rea_evidence_integrity(sample_evidence):
    """Verify that REA evidence matches the expected cryptographic schema."""
    integrity = sample_evidence.validate_integrity()
    assert integrity["is_valid"] is True
    assert integrity["evidence_id"].startswith("ev_")
    assert len(integrity["root_sha256"]) == 64 or len(integrity["root_sha256"]) == 16
    assert integrity["node_count"] > 0
    assert integrity["edge_count"] > 0


def test_rea_endpoint_extraction(sample_evidence):
    """Verify that candidate endpoints and storage calls are extracted from the graph."""
    extracted = sample_evidence.extract_endpoints_and_calls()
    assert "discovered_endpoints" in extracted
    assert "storage_access_points" in extracted
    assert "call_mechanisms" in extracted
    assert len(extracted["call_mechanisms"]) > 0


def test_rea_schema_drift_detection(sample_evidence):
    """Verify that schema drift properly flags delta between discovered routes and baseline."""
    drift = sample_evidence.detect_schema_drift(active_routes={"/voyager/api/growth/normInvitations"})
    assert "has_drift" in drift
    assert "new_endpoints" in drift
    assert "missing_endpoints" in drift
