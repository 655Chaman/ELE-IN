#!/bin/bash
# start.sh - Launch the Ele-in MCP Server as a standalone process

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"

# MCP SDK requires Python 3.10+. We use uv to seamlessly fetch it and isolate dependencies.
if command -v uv &> /dev/null || [ -f "$HOME/.local/bin/uv" ]; then
    UV_BIN="$(command -v uv || echo "$HOME/.local/bin/uv")"
    exec "$UV_BIN" run --python 3.11 \
        --with "mcp<2" \
        --with "supabase" \
        --with "python-dotenv" \
        --with "requests" \
        "$SCRIPT_DIR/server.py" "$@"
else
    echo "uv is not installed. Falling back to system python3 (requires 3.10+)."
    exec python3 "$SCRIPT_DIR/server.py" "$@"
fi

