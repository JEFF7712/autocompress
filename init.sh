#!/usr/bin/env bash
# init.sh: one-time setup for the autocompress record harness.
#
# Run once inside the dev shell:
#   nix develop --command ./init.sh

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO"

echo "=== autocompress init ==="
echo ""

echo "[1/3] Installing Python dependencies..."
uv sync --quiet
echo "      OK"
echo ""

echo "[2/3] Preparing enwik9 dataset and tier prefixes..."
echo "      (downloads ~300 MB zip, extracts 1 GB, writes t0/t1 prefixes; skipped if present)"
uv run prepare.py
echo ""

echo "[3/3] Verifying the clang-17 toolchain (fx2-cmix build deps)..."
clang++-17 --version | head -n 1
upx-ucl --version | head -n 1
make --version | head -n 1
echo "      OK"
echo ""

echo "=== Init complete. ==="
echo ""
echo "Next:"
echo "  1. cp config.toml.example config.toml   # fill in measured Geekbench5 single-core"
echo "  2. Build the baseline compressor (~20 min, PGO):"
echo "       cd src && nix develop .. --command bash build_and_construct_comp.sh && cd .."
echo "  3. Baseline benchmarks (see docs plan, Phase 0):"
echo "       uv run benchmark.py --tier t0 --append-ledger"
echo "  4. Enable the runner service:"
echo "       ./systemd/install.sh"
echo ""
echo "Read program.md for the experiment loop."
