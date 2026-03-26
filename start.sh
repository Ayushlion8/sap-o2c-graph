#!/bin/bash

set -e

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║          SAP O2C Graph Explorer — Startup                ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# ── ENV VARIABLES (Railway handles this) ───────────────────────────────
echo "🔐 Using environment variables from Railway..."

if [ -z "$GEMINI_API_KEY" ]; then
  echo "⚠️  WARNING: GEMINI_API_KEY is not set"
  echo "   AI features will be disabled"
  echo ""
fi

# ── DATASET CHECK ─────────────────────────────────────────────────────
DATA_DIR="${DATA_ROOT:-./data/sap-o2c-data}"

if [ ! -d "$DATA_DIR" ]; then
  echo "❌ Dataset not found at: $DATA_DIR"
  echo ""
  echo "👉 FIX:"
  echo "   - Ensure dataset is inside repo OR"
  echo "   - Set correct DATA_ROOT in Railway variables"
  echo ""
  exit 1
fi

echo "✅ Dataset found at: $DATA_DIR"

# ── FRONTEND BUILD ────────────────────────────────────────────────────
echo ""
echo "📦 Building frontend..."
cd frontend

if ! command -v node &>/dev/null; then
  echo "❌ Node.js is not installed."
  exit 1
fi

if [ ! -d "node_modules" ]; then
  echo "   Installing npm packages..."
  npm install --silent
fi

npm run build
echo "✅ Frontend built."

cd ..

# ── BACKEND SETUP ─────────────────────────────────────────────────────
echo ""
echo "🐍 Setting up Python backend..."
cd backend

if ! command -v python3 &>/dev/null; then
  echo "❌ Python 3 is not installed."
  exit 1
fi

PYTHON=python3

if [ -d "venv" ]; then
  source venv/bin/activate
  PYTHON=python
else
  echo "   Creating virtualenv..."
  python3 -m venv venv
  source venv/bin/activate
  PYTHON=python
fi

echo "   Installing Python packages..."
pip install -q -r requirements.txt

cd ..

# ── START SERVER ──────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  🚀  Starting server                                    ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

cd backend

# Railway provides PORT env variable
PORT=${PORT:-8000}

$PYTHON -m uvicorn main:app --host 0.0.0.0 --port $PORT