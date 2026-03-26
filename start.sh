#!/bin/bash

set -e

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║          SAP O2C Graph Explorer — Startup                ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# Check .env
if [ ! -f ".env" ]; then
  echo "⚠️  .env file not found. Copying from .env.example..."
  cp .env.example .env
  echo "   Please edit .env and add your GEMINI_API_KEY, then re-run."
  exit 1
fi

source .env

if [ -z "$GEMINI_API_KEY" ] || [ "$GEMINI_API_KEY" = "your_gemini_api_key_here" ]; then
  echo "⚠️  WARNING: GEMINI_API_KEY is not set in .env"
  echo "   The graph will work, but the AI chat will be disabled."
  echo "   Get a free key at: https://ai.google.dev"
  echo ""
fi

# Check dataset
DATA_DIR="${DATA_ROOT:-./data/sap-o2c-data}"
if [ ! -d "$DATA_DIR" ]; then
  echo "❌ Dataset not found at: $DATA_DIR"
  echo ""
  echo "   Please place your SAP O2C dataset at: $DATA_DIR"
  echo "   Expected structure:"
  echo "     $DATA_DIR/sales_order_headers/part-*.jsonl"
  echo "     $DATA_DIR/billing_document_headers/part-*.jsonl"
  echo "     ... etc"
  echo ""
  echo "   Or update DATA_ROOT in .env to point to your dataset."
  exit 1
fi

echo "✅ Dataset found at: $DATA_DIR"

# ── Frontend Build ────────────────────────────────────────────────────────────
echo ""
echo "📦 Building frontend..."
cd frontend

if ! command -v node &>/dev/null; then
  echo "❌ Node.js is not installed. Please install Node.js 18+."
  exit 1
fi

if [ ! -d "node_modules" ]; then
  echo "   Installing npm packages..."
  npm install --silent
fi

npm run build
echo "✅ Frontend built."

cd ..

# ── Backend ───────────────────────────────────────────────────────────────────
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

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  🚀  Starting server at http://localhost:8000            ║"
echo "║      Press Ctrl+C to stop                               ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

cd backend
$PYTHON -m uvicorn main:app --host 0.0.0.0 --port 8000
