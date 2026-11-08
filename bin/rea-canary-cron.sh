#!/usr/bin/env bash
# ==============================================================================
# rea-canary-cron.sh
# Scheduled Local Canary & Sentinel Cron Runner
# Powered by morluto/rea + Ghidra 12.2 Headless Decompiler
# Standard: Engineering Paranoia Framework (EPF Layers 0, 1 & 2)
# ==============================================================================

set -euo pipefail

# Ensure working directory is project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

STATE_DIR="${PROJECT_ROOT}/state"
mkdir -p "${STATE_DIR}"

TIMESTAMP="$(date -u +"%Y%m%d_%H%M%S")"
LOG_FILE="${STATE_DIR}/rea-canary.log"
LATEST_JSON="${STATE_DIR}/rea-canary-latest.json"
LATEST_MD="${STATE_DIR}/rea-canary-latest.md"
ALERT_FILE="${STATE_DIR}/rea-drift-alert.txt"
LOCK_FILE="/tmp/elein_rea_canary.lock"

# Layer 1: Environmental Failure Analysis — Prevent overlapping execution via flock / lockfile
if [ -e "${LOCK_FILE}" ]; then
    PID="$(cat "${LOCK_FILE}" 2>/dev/null || echo "")"
    if [ -n "${PID}" ] && kill -0 "${PID}" 2>/dev/null; then
        echo "[REA-CRON] An existing REA Canary pass is currently running (PID: ${PID}). Skipping duplicate run."
        exit 0
    fi
fi
echo "$$" > "${LOCK_FILE}"
trap 'rm -f "${LOCK_FILE}"' EXIT INT TERM

echo "------------------------------------------------------------------" >> "${LOG_FILE}"
echo "[REA-CRON] Starting Scheduled Voyager Canary Pass at $(date -u)" >> "${LOG_FILE}"

RAW_EVIDENCE="/tmp/rea_evidence_${TIMESTAMP}.json"

# Execute the canary pipeline
if ./bin/rea-canary-voyager.sh "extension" "${RAW_EVIDENCE}" "${LATEST_JSON}" "${LATEST_MD}" >> "${LOG_FILE}" 2>&1; then
    echo "[REA-CRON] Canary completed successfully." >> "${LOG_FILE}"
    
    # Layer 2: Inspect severity from generated JSON
    SEVERITY="$(python3 -c "import json; d = json.load(open('${LATEST_JSON}')); print(d.get('schema_drift', {}).get('severity', 'UNKNOWN'))" 2>/dev/null || echo "UNKNOWN")"
    echo "[REA-CRON] Detected Drift Severity: ${SEVERITY}" >> "${LOG_FILE}"
    
    if [ "${SEVERITY}" = "CRITICAL" ] || [ "${SEVERITY}" = "HIGH" ]; then
        echo "🚨 [ALERT] Schema Drift Detected! Severity: ${SEVERITY} at $(date -u)" > "${ALERT_FILE}"
        echo "Inspect report: ${LATEST_MD}" >> "${ALERT_FILE}"
        
        # On macOS, display native desktop notification
        if command -v osascript >/dev/null 2>&1; then
            osascript -e "display notification \"LinkedIn Voyager ${SEVERITY} drift detected! Inspect state/rea-canary-latest.md\" with title \"Ele-in REA Sentinel\" subtitle \"Security Alert\"" || true
        fi
        echo "[REA-CRON] Raised local desktop and alert file alarm." >> "${LOG_FILE}"
    else
        # Clear previous alert if clean
        rm -f "${ALERT_FILE}"
        echo "[REA-CRON] Baseline clean. No alert active." >> "${LOG_FILE}"
    fi
else
    echo "❌ [REA-CRON] Canary pass failed with error code $?. Inspect ${LOG_FILE}" >> "${LOG_FILE}"
    exit 1
fi

rm -f "${RAW_EVIDENCE}"
echo "[REA-CRON] Finished pass at $(date -u)" >> "${LOG_FILE}"
