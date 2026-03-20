# autocompress

An autonomous research loop for [Hutter Prize](http://prize.hutter1.net/index.htm)-style lossless compression on `enwik9`. Inspired by [Karpathy's autoresearch](https://github.com/karpathy/autoresearch).

An LLM agent iterates on `compress.cpp`, runs compression benchmarks, keeps improvements, and discards regressions — autonomously, indefinitely.

## How it works

The loop is simple:

1. Propose a change to the compression algorithm in `compress.cpp`
2. Run proxy benchmark (3 × 32 MB slices of enwik9 — fast)
3. If proxy improves, run full benchmark on all 1 GB of enwik9
4. Keep commit if score improves, `git reset` otherwise

**Score = `archive_bytes`** (lower is better — total compressed size across benchmark files).

## Setup

```bash
# One-time setup: enters nix dev environment, installs deps, downloads enwik9,
# creates proxy slices, and runs a baseline benchmark to verify everything works.
nix develop --command ./init.sh
```

On non-NixOS Linux: `apt install gcc liblzma-dev` (Debian/Ubuntu) or `dnf install gcc xz-devel` (Fedora), then `uv sync && uv run prepare.py`.

After init, `uv run benchmark.py` works from any shell — `benchmark.py` auto-invokes `nix develop` for compilation when `g++` is not on PATH.

## Running experiments

```bash
# Proxy run (fast, 3×32 MB slices)
uv run benchmark.py > run.log 2>&1
grep "proxy_score_bytes:" run.log

# Full run (entire 1 GB enwik9)
uv run benchmark.py --full > run.log 2>&1
grep "full_score_bytes:" run.log
```

Output format:
```
proxy_score_bytes: 20445396
archive_bytes: 20445396
roundtrip_ok: true
```

## Files

| File | Purpose |
|------|---------|
| `compress.cpp` | **Mutable.** Compression algorithm — agent edits this |
| `benchmark.py` | **Fixed.** Compiles compress.cpp, runs benchmark, verifies roundtrip |
| `prepare.py` | **Fixed.** Downloads enwik9, generates proxy slices |
| `prepare_helpers.py` | **Fixed.** Shared constants (enwik9 size, proxy offsets) |
| `flake.nix` | Reproducible dev environment (gcc + liblzma) |
| `init.sh` | One-time setup script |
| `program.md` | Agent instructions for the autonomous loop |
| `results_template.tsv` | TSV header template for experiment runs |

## Autonomous loop

See `program.md` for full agent instructions. The agent runs on a dedicated branch (e.g. `autocompress/mar5`), loops forever, and logs results to `results.tsv`.

Optional: set `FX2_CMIX_BIN=/path/to/fx2-cmix` to compare against an external baseline (read-only).
