#!/usr/bin/env bash
# init.sh — one-time setup for the autocompress experiment loop.
#
# Run this once before starting experiments:
#   nix develop --command ./init.sh
#
# After init completes, run experiments with:
#   uv run benchmark.py
#   uv run benchmark.py --full
#
# benchmark.py auto-invokes nix develop for compilation when g++ is not on PATH,
# so subsequent uv run benchmark.py calls work from any shell.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO"

echo "=== autocompress init ==="
echo ""

# 1. Install Python dependencies
echo "[1/3] Installing Python dependencies..."
uv sync --quiet
echo "      OK"
echo ""

# 2. Download enwik9 and create proxy slices (skips if already done)
echo "[2/3] Preparing enwik9 dataset..."
echo "      (downloads ~200 MB zip, extracts 1 GB — skipped if already present)"
uv run prepare.py
echo ""

# 3. Verify compile + benchmark works end-to-end
echo "[3/3] Compiling compress.cpp and running baseline proxy benchmark..."
uv run benchmark.py > /tmp/autocompress_init.log 2>&1 || {
    echo "FAILED. Last 30 lines of output:"
    tail -n 30 /tmp/autocompress_init.log
    exit 1
}
grep "proxy_score_bytes:" /tmp/autocompress_init.log
grep "roundtrip_ok:" /tmp/autocompress_init.log
echo ""

echo "=== Init complete. Environment is ready. ==="
echo ""
echo "Start the experiment loop:"
echo "  Read program.md for instructions, then edit compress.cpp and run:"
echo "  uv run benchmark.py > run.log 2>&1"
