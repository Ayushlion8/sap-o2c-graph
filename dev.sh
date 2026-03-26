#!/bin/bash
# dev.sh — starts backend and frontend in parallel with hot-reload

source .env 2>/dev/null || true

echo ""
echo "🔧 Starting in DEV mode (hot-reload)"
echo ""

# Trap to kill both processes on Ctrl+C
trap 'echo ""; echo "Shutting down..."; kill 0' SIGINT SIGTERM

# Backend
(
  cd backend
  if [ -d "venv" ]; then
    source venv/bin/activate
  fi
  echo "🐍 Backend starting on http://localhost:8000"
  python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
) &

# Frontend
(
  cd frontend
  if [ ! -d "node_modules" ]; then
    npm install
  fi
  echo "⚛️  Frontend starting on http://localhost:5173"
  npm run dev -- --host
) &

wait
