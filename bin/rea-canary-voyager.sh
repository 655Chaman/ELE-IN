#!/usr/bin/env bash
# ==============================================================================
# rea-canary-voyager.sh
# Automated Reverse Engineering & Protocol Extraction Pipeline
# Powered by morluto/rea (Reverse Engineer Anything v6.8.0 / v6.7.0)
# Standard: Engineering Paranoia Framework (EPF Layers 0, 1 & 2)
# ==============================================================================

set -euo pipefail

TARGET_DIR="${1:-extension}"
OUTPUT_FILE="${2:-/tmp/rea_canary_output.json}"
DRIFT_REPORT="${3:-/tmp/rea_canary_drift.json}"
SUMMARY_FILE="${4:-/tmp/rea_canary_summary.md}"

echo "=================================================================="
echo "🛰️ ELE-IN REA CANARY SENTINEL: REVERSE ENGINEERING PIPELINE"
echo "🔬 ENGINE: REA v6.7.0 + Ghidra 12.2 analyzeHeadless"
echo "🛡️ STANDARD: Engineering Paranoia Framework (EPF)"
echo "=================================================================="
echo "[REA-CANARY] Target Directory: ${TARGET_DIR}"
echo "[REA-CANARY] Raw Evidence Output: ${OUTPUT_FILE}"
echo "[REA-CANARY] Schema Drift Report: ${DRIFT_REPORT}"
echo "[REA-CANARY] Markdown Summary: ${SUMMARY_FILE}"

# EPF Layer 1: Validate environmental prerequisites
if [ ! -d "${TARGET_DIR}" ]; then
    echo "❌ [REA-CANARY] Error: Target directory '${TARGET_DIR}' does not exist!"
    exit 1
fi

command -v node >/dev/null 2>&1 || { echo "❌ [REA-CANARY] Error: node is required on PATH."; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "❌ [REA-CANARY] Error: python3 is required on PATH."; exit 1; }

# 1. Enforce isolated npm cache to prevent permission/cache lockups
export npm_config_cache="/tmp/npm-cache"
mkdir -p "${npm_config_cache}"

# 2. Fire REA against the target application
echo "[REA-CANARY] Step 1: Executing REA JavaScript graph reconstruction..."
npx -y rea-agents analyze-javascript-application "${TARGET_DIR}" --format json > "${OUTPUT_FILE}"
echo "[REA-CANARY] Analysis complete. Raw evidence saved to: ${OUTPUT_FILE}"

# 3. Execute python extractor to validate evidence & report schema drift
echo "[REA-CANARY] Step 2: Extracting API endpoints, storage keys, and detecting schema drift..."
python3 backend/scripts/rea_voyager_extractor.py "${OUTPUT_FILE}" \
    --summary-file "${SUMMARY_FILE}" \
    --drift-json "${DRIFT_REPORT}"

# 4. Scan for WebAssembly (.wasm) anti-bot challenge binaries & run Ghidra decompiler
echo "[REA-CANARY] Step 3: Scanning for WebAssembly challenge binaries..."
WASM_FILES=$(find "${TARGET_DIR}" -name "*.wasm" 2>/dev/null || true)
if [ -n "$WASM_FILES" ]; then
    echo "[REA-CANARY] Discovered WebAssembly binaries. Running Ghidra 12.2 / Wasm decompilation analysis..."
    for wasm in $WASM_FILES; do
        python3 backend/scripts/rea_ghidra_decompiler.py "$wasm"
    done
else
    echo "[REA-CANARY] No WebAssembly binaries discovered in target directory. Skipping Wasm pass."
fi

echo "=================================================================="
echo "🎯 [REA-CANARY] Automated extraction and verification successful."
echo "=================================================================="
