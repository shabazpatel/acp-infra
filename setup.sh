#!/usr/bin/env bash
set -euo pipefail

# ──────────────────────────────────────────────
# ACP Framework — Project Setup
# ──────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🚀 ACP Framework Setup"
echo "─────────────────────────────────────────"

# 1. Install uv if missing
if ! command -v uv &> /dev/null; then
    echo "📦 Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi
echo "✅ uv $(uv --version)"

# 2. Create virtual environment & install deps
echo ""
echo "📦 Creating virtual environment & installing dependencies..."
uv venv .venv
source .venv/bin/activate
uv pip install -e ".[dev]"
echo "✅ Python packages installed"

# 3. Copy .env if it doesn't exist
if [ ! -f .env ]; then
    cp .env.example .env
    echo "✅ Created .env from .env.example — edit it with your API keys"
else
    echo "✅ .env already exists"
fi

# 4. Start Docker services (Postgres + Temporal)
echo ""
echo "🐳 Starting Docker services (Postgres + Temporal)..."
if command -v docker &> /dev/null && docker info &> /dev/null; then
    docker compose up -d
    echo "✅ Docker services started"
    echo "   PostgreSQL: localhost:5432"
    echo "   Temporal:   localhost:7233 (gRPC) / localhost:8233 (Web UI)"
else
    echo "⚠️  Docker not available — skipping. Install Docker to use Postgres & Temporal."
    echo "   You can run 'docker compose up -d' later."
fi

# 5. Summary
echo ""
echo "─────────────────────────────────────────"
echo "✅ Setup complete! Next steps:"
echo ""
echo "   source .venv/bin/activate"
echo "   # Edit .env with your OPENAI_API_KEY"
echo ""
echo "   # Run services:"
echo "   uvicorn services.seller.main:app --port 8001"
echo "   uvicorn services.psp.main:app --port 8002"
echo "   uvicorn services.agent.main:app --port 8003"
echo ""
echo "   # Run UI:"
echo "   cd ui && npm install && npm run dev"
echo "─────────────────────────────────────────"
