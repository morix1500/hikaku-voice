#!/bin/bash
trap "kill 0" EXIT

# Default to port 8009 if not set
PORT="${PORT:-8009}"

echo "Starting Backend on port $PORT..."
# cd backend  <-- Removed
# source .venv/bin/activate # No longer needed with uv
uv run uvicorn main:app --reload --host 0.0.0.0 --port "$PORT" &

wait
