"""
Phase 4 Verification Suite: REA Canary Pipeline & Voyager Extractor
Governed under the Engineering Paranoia Framework (EPF Layers 0, 1 & 2):

Tests:
1. REAVoyagerExtractor validates evidence integrity (SHA256, graph schema).
2. REAVoyagerExtractor extracts endpoints, storage calls, and call mechanisms.
3. REAVoyagerExtractor detects schema drift against active baseline routes.
4. Layer 2: Classify drift severity (CRITICAL, HIGH, MEDIUM, CLEAN).
5. Layer 2: Generate rich GitHub Flavored Markdown summary card.
6. Layer 0 & 1: Export full structured JSON drift report.
7. Layer 1: Resilience against corrupted or truncated JSON files (InvalidEvidenceFileError).
8. Layer 1: Resilience against missing files (FileNotFoundError).
"""

import pytest
import os
import json
import tempfile
from backend.scripts.rea_voyager_extractor import (
    REAVoyagerExtractor,
    InvalidEvidenceFileError
)


@pytest.fixture
def sample_evidence():
    evidence_path = "/Users/krdeeksha/.gemini/antigravity/brain/359c2f24-0bb5-45c7-9710-52ff56fd89a6/scratch/rea_extension_clean.json"
    if os.path.exists(evidence_path):
        return REAVoyagerExtractor.from_file(evidence_path)
    # Synthetic evidence fallback for isolated test runners
    return REAVoyagerExtractor({
        "evidence_id": "ev_test_12345",
        "normalized_result": {
            "root_artifact_sha256": "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
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
    assert "severity" in drift


def test_classify_drift_severity_matrix():
    """Layer 2: Test threat classification matrix across critical, high, and clean states."""
    # Critical: Bot checkpoint/challenge keyword
    sev_crit, _ = REAVoyagerExtractor.classify_drift_severity(
        ["/voyager/api/identity/threatChallengeV2"],
        []
    )
    assert sev_crit == "CRITICAL"

    # Critical: Captcha / verification keyword
    sev_recaptcha, _ = REAVoyagerExtractor.classify_drift_severity(
        ["/api/security/recaptcha_enterprise"],
        []
    )
    assert sev_recaptcha == "CRITICAL"

    # High: General new Voyager API endpoint
    sev_high, _ = REAVoyagerExtractor.classify_drift_severity(
        ["/voyager/api/growth/superLeadsV3"],
        []
    )
    assert sev_high == "HIGH"

    # Medium: Non-voyager endpoint
    sev_med, _ = REAVoyagerExtractor.classify_drift_severity(
        ["staticAssetBundleId"],
        []
    )
    assert sev_med == "MEDIUM"

    # Clean: Empty delta
    sev_clean, _ = REAVoyagerExtractor.classify_drift_severity([], [])
    assert sev_clean == "CLEAN"


def test_generate_markdown_summary(sample_evidence):
    """Layer 2: Verify markdown summary formatting for GitHub Step Summary and notifications."""
    drift = sample_evidence.detect_schema_drift()
    md = sample_evidence.generate_markdown_summary(drift)
    assert "# 🛰️ REA Voyager Canary & Schema Drift Sentinel" in md
    assert "Cryptographic Evidence Integrity" in md
    assert "Voyager Endpoint Drift Analysis" in md
    assert sample_evidence.evidence_id in md


def test_export_full_report_roundtrip(sample_evidence):
    """Layer 0 & 1: Verify full report JSON persistence and deserialization."""
    with tempfile.NamedTemporaryFile(suffix="_drift_report.json", delete=False) as tf:
        out_path = tf.name

    try:
        report = sample_evidence.export_full_report(out_path)
        assert os.path.exists(out_path)
        with open(out_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert "timestamp" in data
        assert "evidence_integrity" in data
        assert "schema_drift" in data
        assert data["evidence_integrity"]["evidence_id"] == sample_evidence.evidence_id
    finally:
        if os.path.exists(out_path):
            os.remove(out_path)


def test_corrupted_evidence_json_handling():
    """Layer 1: Verify rejection of truncated or malformed evidence JSON."""
    with tempfile.NamedTemporaryFile(suffix="_corrupt.json", mode="w", delete=False) as tf:
        tf.write('{"evidence_id": "ev_123", "normalized_result": {TRUNCATED')
        corrupt_path = tf.name

    try:
        with pytest.raises(InvalidEvidenceFileError) as exc_info:
            REAVoyagerExtractor.from_file(corrupt_path)
        assert "Corrupted or invalid REA evidence JSON" in str(exc_info.value)
    finally:
        if os.path.exists(corrupt_path):
            os.remove(corrupt_path)


def test_missing_evidence_file_handling():
    """Layer 1: Verify proper FileNotFoundError when evidence file does not exist."""
    with pytest.raises(FileNotFoundError):
        REAVoyagerExtractor.from_file("/tmp/non_existent_rea_path_12345.json")
