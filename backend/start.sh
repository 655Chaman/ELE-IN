#!/bin/bash
cd "$(dirname "$0")"
cd ..
echo "Cleaning up port 8000..."
lsof -ti :8000 | xargs kill -9 2>/dev/null
echo "Starting uvicorn server..."
backend/venv/bin/python -m uvicorn core.backend.main:app --host 0.0.0.0 --port 8000 --env-file backend/.env
