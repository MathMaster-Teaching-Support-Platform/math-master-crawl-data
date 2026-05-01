#!/usr/bin/env bash
# scripts/setup.sh — Quick setup script for SGK Toán PDF → API
# Usage: bash scripts/setup.sh

set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo ""
echo "========================================"
echo "  SGK Toán PDF → API — Setup Script"
echo "========================================"
echo ""

# ---------------------------------------------------------------------------
# 1. Create .env from .env.example
# ---------------------------------------------------------------------------
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "✅ Created .env from .env.example"
        echo "   ⚠️  IMPORTANT: Open .env and fill in GEMINI_API_KEY before running the app."
    else
        echo "❌ .env.example not found. Please create .env manually."
        exit 1
    fi
else
    echo "ℹ️  .env already exists — skipping."
fi

# ---------------------------------------------------------------------------
# 2. Create required directories
# ---------------------------------------------------------------------------
mkdir -p storage/images
mkdir -p data/books
echo "✅ Created directories: storage/images, data/books"

# ---------------------------------------------------------------------------
# 3. Create virtual environment (if not exists)
# ---------------------------------------------------------------------------
if [ ! -d "venv" ]; then
    echo ""
    echo "Creating Python virtual environment..."
    python3 -m venv venv
    echo "✅ Virtual environment created at ./venv"
else
    echo "ℹ️  Virtual environment already exists — skipping."
fi

# ---------------------------------------------------------------------------
# 4. Install Python dependencies
# ---------------------------------------------------------------------------
echo ""
echo "Installing Python dependencies..."
if [ -f "venv/bin/pip" ]; then
    venv/bin/pip install --upgrade pip -q
    venv/bin/pip install -r requirements.txt -q
elif [ -f "venv/Scripts/pip" ]; then
    venv/Scripts/pip install --upgrade pip -q
    venv/Scripts/pip install -r requirements.txt -q
else
    pip install --upgrade pip -q
    pip install -r requirements.txt -q
fi
echo "✅ Python dependencies installed"

# ---------------------------------------------------------------------------
# 5. Start MongoDB with Docker Compose (if docker is available)
# ---------------------------------------------------------------------------
echo ""
if command -v docker &>/dev/null && command -v docker-compose &>/dev/null; then
    echo "Starting MongoDB with Docker Compose..."
    docker-compose up -d mongo
    echo "✅ MongoDB started (port 27017)"
elif command -v docker &>/dev/null; then
    echo "Starting MongoDB with Docker..."
    docker-compose up -d mongo 2>/dev/null || \
    docker run -d --name sgk-mongo -p 27017:27017 \
        -e MONGO_INITDB_DATABASE=sgk_toan \
        -v sgk_mongo_data:/data/db \
        mongo:7 2>/dev/null || \
    echo "ℹ️  MongoDB container may already be running."
    echo "✅ MongoDB started (port 27017)"
else
    echo "ℹ️  Docker not found — make sure MongoDB is running on localhost:27017"
fi

# ---------------------------------------------------------------------------
# 6. Final instructions
# ---------------------------------------------------------------------------
echo ""
echo "========================================"
echo "  Setup Complete!"
echo "========================================"
echo ""
echo "Next steps:"
echo "  1. Open .env and set GEMINI_API_KEY=<your-key>"
echo "     (Get free key at: https://aistudio.google.com/app/apikey)"
echo ""
echo "  2. Activate virtual environment:"
echo "     source venv/bin/activate    # Linux/macOS"
echo "     .\\venv\\Scripts\\activate   # Windows"
echo ""
echo "  3. Start the server:"
echo "     python run.py"
echo "     # or: uvicorn app.main:app --reload --port 8000"
echo ""
echo "  4. Open Swagger UI: http://localhost:8000/docs"
echo ""
echo "  5. Run tests:"
echo "     pytest tests/ -v"
echo ""
