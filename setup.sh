#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
# thesis-engine setup script
# Run once after cloning: chmod +x setup.sh && ./setup.sh
# ──────────────────────────────────────────────────────────────
set -e

echo "=== thesis-engine setup ==="
echo ""

# ── Check Python version ─────────────────────────────────────
PYTHON=""
for cmd in python3.11 python3 python; do
    if command -v "$cmd" &>/dev/null; then
        version=$("$cmd" --version 2>&1 | grep -oE '[0-9]+\.[0-9]+')
        major=$(echo "$version" | cut -d. -f1)
        minor=$(echo "$version" | cut -d. -f2)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
            PYTHON="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo "ERROR: Python 3.10+ is required but not found."
    echo "Install Python from https://python.org and try again."
    exit 1
fi

echo "Found $($PYTHON --version)"

# ── Create virtual environment ───────────────────────────────
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    $PYTHON -m venv .venv
    echo "Virtual environment created at .venv/"
else
    echo "Virtual environment already exists at .venv/"
fi

# ── Install dependencies ─────────────────────────────────────
echo "Installing dependencies..."
.venv/bin/pip install --upgrade pip --quiet
.venv/bin/pip install -r requirements.txt --quiet
echo "Dependencies installed."

# ── Create .env from template ────────────────────────────────
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "Created .env from .env.example — edit it with your API keys."
else
    echo ".env already exists — skipping."
fi

# ── Create stocks.yaml from template ─────────────────────────
if [ ! -f "stocks.yaml" ]; then
    cp stocks.yaml.example stocks.yaml
    echo "Created stocks.yaml from stocks.yaml.example — edit it with your portfolio."
else
    echo "stocks.yaml already exists — skipping."
fi

# ── Create working directories ───────────────────────────────
mkdir -p logs context
echo "Created logs/ and context/ directories."

# ── Done ─────────────────────────────────────────────────────
echo ""
echo "=== Setup complete ==="
echo ""
echo "Next steps:"
echo "  1. Edit .env with your API keys (at minimum: ANTHROPIC_API_KEY, FINNHUB_API_KEY)"
echo "  2. Edit stocks.yaml with your portfolio"
echo "  3. Activate the environment:  source .venv/bin/activate"
echo "  4. Run a test:                python analyzer.py --test"
echo "  5. Deploy via GitHub Actions or cron (see README.md)"
echo ""
