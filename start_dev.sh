#!/bin/bash
trap "kill 0" EXIT

echo "Starting Backend..."
cd backend
source .venv/bin/activate
uvicorn main:app --reload --host 0.0.0.0 --port 8009 &

echo "Starting Frontend..."
cd ../frontend
npm run dev -- -p 3000 &

wait
