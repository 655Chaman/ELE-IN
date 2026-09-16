#!/bin/bash
cd "$(dirname "$0")"
echo "Starting Ele-in Job Worker..."
exec venv/bin/python -m app.workers.job_processor
