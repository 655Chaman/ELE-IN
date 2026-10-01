#!/bin/bash
cd "$(dirname "$0")"
cd ..
echo "Starting Ele-in Job Worker..."
PYTHONPATH=. backend/venv/bin/python -m core.backend.workers.job_processor
