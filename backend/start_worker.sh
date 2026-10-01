#!/bin/bash
cd "$(dirname "$0")"
cd ..
echo "Starting Ele-in Background Orchestrator Worker..."
PYTHONPATH=. backend/venv/bin/python -m core.backend.workers.orchestrator_worker
