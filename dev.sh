#!/usr/bin/env bash

# Kill any existing processes on the ports to prevent EADDRINUSE or proxy failures
echo "Cleaning up old processes..."
lsof -ti:5173 | xargs kill -9 2>/dev/null
lsof -ti:5174 | xargs kill -9 2>/dev/null
lsof -ti:8000 | xargs kill -9 2>/dev/null

echo "Starting Backend..."
# Run from root so module paths resolve correctly (e.g., campaigns.backend)
backend/venv/bin/python -m uvicorn core.backend.main:app --host 127.0.0.1 --port 8000 --reload --env-file backend/.env &
BACKEND_PID=$!

echo "Starting Frontend..."
# npm run dev runs Vite from the root now
npm run dev &
FRONTEND_PID=$!

echo "------------------------------------------------------"
echo "Ele-in Development Servers are running!"
echo "Frontend: http://localhost:5173"
echo "Backend:  http://localhost:8000"
echo ""
echo "Press Ctrl+C to stop both servers gracefully."
echo "------------------------------------------------------"

# Trap SIGINT (Ctrl+C) to kill both background processes
trap "echo 'Shutting down...'; kill $BACKEND_PID $FRONTEND_PID; exit" INT

# Wait indefinitely (until trap catches SIGINT)
wait
