#!/bin/bash
cd "$(dirname "$0")"
cd ..

echo "Starting Ele-in Background Workers (Job Processor + Campaign Orchestrator)..."

cleanup() {
    echo "Stopping Ele-in background workers..."
    kill -TERM "$PID_JOBS" "$PID_ORCH" 2>/dev/null
    wait "$PID_JOBS" "$PID_ORCH" 2>/dev/null
    exit 0
}
trap cleanup SIGINT SIGTERM EXIT

PYTHONPATH=. backend/venv/bin/python -m core.backend.workers.job_processor &
PID_JOBS=$!

PYTHONPATH=. backend/venv/bin/python -m core.backend.workers.orchestrator_worker &
PID_ORCH=$!

echo "Workers started (Job Processor PID: $PID_JOBS, Orchestrator PID: $PID_ORCH)"
wait -n "$PID_JOBS" "$PID_ORCH"
cleanup
