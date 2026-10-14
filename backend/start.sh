#!/bin/bash
cd "$(dirname "$0")"
cd ..

echo "Cleaning up ghost processes..."
lsof -ti :8000 | xargs kill -9 2>/dev/null
pkill -f "core.backend.workers.job_processor" 2>/dev/null
pkill -f "core.backend.workers.orchestrator_worker" 2>/dev/null

echo "Starting Background Workers in background..."
./backend/start-worker.sh &
WORKER_PID=$!

echo "Verifying database migrations..."
if [ -n "$DATABASE_URL" ]; then
    backend/venv/bin/python backend/scripts/apply_migrations.py || echo "Warning: Migrations script finished with warnings, continuing startup..."
fi

echo "Starting Uvicorn web server..."
backend/venv/bin/python -m uvicorn core.backend.main:app --host 0.0.0.0 --port 8000 --env-file backend/.env

# When uvicorn stops, kill the workers
kill $WORKER_PID 2>/dev/null
pkill -f "core.backend.workers.job_processor" 2>/dev/null
pkill -f "core.backend.workers.orchestrator_worker" 2>/dev/null
