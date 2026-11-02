#!/usr/bin/env bash
# ==============================================================================
# rea-canary-voyager.sh
# Automated Reverse Engineering & Protocol Extraction Pipeline
# Powered by morluto/rea (Reverse Engineer Anything v6.8.0 / v6.7.0)
# ==============================================================================

set -euo pipefail

TARGET_DIR="${1:-extension}"
OUTPUT_FILE="${2:-/tmp/rea_canary_output.json}"

echo "[REA-CANARY] Starting automated analysis on: ${TARGET_DIR}"

# 1. Enforce isolated npm cache to prevent permission/cache lockups
export npm_config_cache="/tmp/npm-cache"

# 2. Fire REA against the target application
npx -y rea-agents analyze-javascript-application "${TARGET_DIR}" --format json > "${OUTPUT_FILE}"

echo "[REA-CANARY] Analysis complete. Raw output saved to: ${OUTPUT_FILE}"

# 3. Execute python extractor to validate evidence & report schema drift
python3 backend/scripts/rea_voyager_extractor.py "${OUTPUT_FILE}"

echo "[REA-CANARY] Automated extraction and verification successful."
