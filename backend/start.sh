#!/bin/bash
cd "$(dirname "$0")"
cd ..

echo "Cleaning up ghost processes..."
lsof -ti :8000 | xargs kill -9 2>/dev/null
pkill -f "core.backend.workers.job_processor" 2>/dev/null

echo "Starting Orchestrator Worker in background..."
./backend/start-worker.sh &
WORKER_PID=$!

echo "Starting Uvicorn web server..."
backend/venv/bin/python -m uvicorn core.backend.main:app --host 0.0.0.0 --port 8000 --env-file backend/.env

# When uvicorn stops, kill the worker
kill $WORKER_PID
