"""
test_rea_ghidra_decompiler.py — Unit tests for Ghidra & Wasm Telemetry Analysis Engine.

Phase 01: Ghidra 12.2 & REA WebAssembly Binary Decompilation Engine.
Verifies Three-Layer Logic Architecture:
  - Layer 0: Magic byte validation, section decoding, telemetry pattern extraction.
  - Layer 1: Malformed binary rejection, timeout safety, fallback resilience.
  - Layer 2: Cryptographic SHA-256 fingerprinting and risk classification.
"""

import os
import struct
import tempfile
import pytest
from backend.scripts.rea_ghidra_decompiler import (
    REAGhidraDecompiler,
    InvalidWasmBinaryError,
    WASM_MAGIC
)


@pytest.fixture
def decompiler():
    return REAGhidraDecompiler()


def create_minimal_wasm(custom_strings: list = None) -> bytes:
    """Helper to synthesize a valid minimal WebAssembly module containing test strings."""
    # Header: Magic \x00asm + Version 1
    header = b"\x00asm\x01\x00\x00\x00"

    # Section 0: Custom Section containing embedded telemetry strings
    custom_data = b"".join(s.encode("utf-8") + b"\x00" for s in (custom_strings or []))
    section_name = b"telemetry_test"
    sec_payload = bytes([len(section_name)]) + section_name + custom_data

    # LEB128 length of payload
    payload_len = len(sec_payload)
    custom_section = b"\x00" + bytes([payload_len]) + sec_payload

    return header + custom_section


def test_validate_and_parse_valid_wasm(decompiler):
    wasm_bytes = create_minimal_wasm()
    result = decompiler.validate_and_parse_wasm_sections(wasm_bytes)

    assert result["magic"] == "wasm"
    assert result["version"] == 1
    assert len(result["sha256"]) == 64
    assert len(result["sections"]) == 1
    assert result["sections"][0]["name"] == "Custom"


def test_reject_invalid_magic_header(decompiler):
    bad_bytes = b"NOTAWASM\x01\x00\x00\x00"
    with pytest.raises(InvalidWasmBinaryError) as exc_info:
        decompiler.validate_and_parse_wasm_sections(bad_bytes)
    assert "Invalid WebAssembly magic" in str(exc_info.value)


def test_reject_too_short_payload(decompiler):
    with pytest.raises(InvalidWasmBinaryError):
        decompiler.validate_and_parse_wasm_sections(b"\x00as")


def test_reject_overflow_leb128_shift(decompiler):
    """Layer 1 Paranoia: Prevent infinite loop or unbound shift on malicious LEB128."""
    # Header \x00asm\x01\x00\x00\x00 + Section ID 0 + 6 bytes with 0x80 MSB set
    corrupt_bytes = b"\x00asm\x01\x00\x00\x00\x00" + (b"\x80" * 7)
    with pytest.raises(InvalidWasmBinaryError) as exc_info:
        decompiler.validate_and_parse_wasm_sections(corrupt_bytes)
    assert "LEB128 integer overflow" in str(exc_info.value)


def test_scan_telemetry_signatures(decompiler):
    test_strings = [
        "WEBGL_debug_renderer_info",
        "movementX",
        "jerk",
        "performance.now",
        "debugger"
    ]
    wasm_bytes = create_minimal_wasm(test_strings)
    telemetry = decompiler.scan_telemetry_signatures(wasm_bytes)

    assert telemetry["total_matches"] >= 4
    assert telemetry["risk_rating"] == "CRITICAL_BOT_DETECTION"
    assert "canvas_webgl_fingerprinting" in telemetry["detections_by_category"]
    assert "mouse_kinematics_and_jerk" in telemetry["detections_by_category"]
    assert "timing_and_micro_jitter" in telemetry["detections_by_category"]


def test_analyze_wasm_artifact_e2e(decompiler):
    with tempfile.NamedTemporaryFile(suffix=".wasm", delete=False) as f:
        wasm_bytes = create_minimal_wasm(["clientX", "clientY", "UNMASKED_RENDERER_WEBGL"])
        f.write(wasm_bytes)
        f.flush()
        temp_path = f.name

    try:
        report = decompiler.analyze_wasm_artifact(temp_path, run_ghidra=False)
        assert report["artifact_path"] == temp_path
        assert len(report["sha256"]) == 64
        assert report["section_summary"]["section_count"] == 1
        assert "canvas_webgl_fingerprinting" in report["telemetry_findings"]
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_detect_ghidra_path(decompiler):
    # Verify path detector returns /opt/homebrew/bin/analyzeHeadless if present
    path = decompiler._detect_ghidra_path()
    if os.path.exists("/opt/homebrew/bin/analyzeHeadless"):
        assert path == "/opt/homebrew/bin/analyzeHeadless"
