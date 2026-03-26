#!/bin/bash

set -e

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║          SAP O2C Graph Explorer — Startup                ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# ── ENV VARIABLES ─────────────────────────────────────────────────────
echo "🔐 Using environment variables from Railway..."

if [ -z "$GEMINI_API_KEY" ]; then
  echo "⚠️  WARNING: GEMINI_API_KEY is not set"
  echo "   AI features will be disabled"
else
  echo "✅ GEMINI_API_KEY detected"
fi

# ── DEBUG INFO (VERY USEFUL) ──────────────────────────────────────────
echo ""
echo "📁 Current working directory:"
pwd
echo ""
echo "📂 Project structure:"
ls

# ── DATASET CHECK ─────────────────────────────────────────────────────
if [ -z "$DATA_ROOT" ]; then
  echo ""
  echo "❌ ERROR: DATA_ROOT is not set"
  echo "👉 Set DATA_ROOT in Railway variables"
  exit 1
fi

DATA_DIR="$DATA_ROOT"

echo ""
echo "📂 Checking dataset at: $DATA_DIR"

if [ ! -d "$DATA_DIR" ]; then
  echo ""
  echo "❌ Dataset not found at: $DATA_DIR"
  echo ""
  echo "👉 FIX:"
  echo "   - Ensure dataset exists in repo"
  echo "   - Verify DATA_ROOT path"
  echo ""
  echo "📂 Available folders:"
  ls
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
  echo "   Using existing virtualenv"
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

PORT=${PORT:-8000}

echo "🌐 Running on port: $PORT"

$PYTHON -m uvicorn main:app --host 0.0.0.0 --port $PORT