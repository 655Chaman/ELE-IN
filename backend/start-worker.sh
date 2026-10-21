#!/bin/bash
cd "$(dirname "$0")"
cd ..

PY_BIN="python"
if [ -f "backend/venv/bin/python" ]; then
    PY_BIN="backend/venv/bin/python"
fi

echo "Starting Ele-in Background Workers via Supervisor ($PY_BIN -m core.backend.workers.runner)..."
exec env PYTHONPATH=. "$PY_BIN" -m core.backend.workers.runner
