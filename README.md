# autocompress

An autonomous research loop for [Hutter Prize](http://prize.hutter1.net/index.htm)-style lossless compression on `enwik9`. Inspired by [Karpathy's autoresearch](https://github.com/karpathy/autoresearch).

An LLM agent iterates on `train.py`, runs compression benchmarks, keeps improvements, and discards regressions — autonomously, indefinitely.

## How it works

The loop is simple:

1. Propose a change to the compression algorithm in `train.py`
2. Run proxy benchmark (3 × 32 MB slices of enwik9 — fast)
3. If proxy improves, run full benchmark on all 1 GB of enwik9
4. Keep commit if score improves, `git reset` otherwise

**Score = `archive_bytes + code_bytes`** (lower is better — code size counts, per Hutter Prize rules).

## Setup

```bash
# Install dependencies
uv sync

# Download enwik9 and generate proxy slices (~1 GB download)
uv run prepare.py
```

## Running experiments

```bash
# Proxy run (fast, ~seconds)
uv run train.py > run.log 2>&1
grep "proxy_score_bytes:" run.log

# Full run (slow, entire enwik9)
uv run train.py --full > run.log 2>&1
grep "full_score_bytes:" run.log
```

Output format:
```
proxy_score_bytes: 117
archive_bytes: 100
code_bytes: 17
roundtrip_ok: true
```

## Files

| File | Purpose |
|------|---------|
| `train.py` | **Mutable.** Compression candidate + fixed evaluation harness |
| `prepare.py` | **Fixed.** Downloads enwik9, generates proxy slices |
| `prepare_helpers.py` | **Fixed.** Shared constants (enwik9 size, proxy offsets) |
| `program.md` | Agent instructions for the autonomous loop |
| `results.tsv` | Experiment log (untracked) |
| `analysis.ipynb` | Notebook for visualizing experiment history |

## Autonomous loop

See `program.md` for full agent instructions. The agent runs on a dedicated branch (e.g. `autocompress/mar5`), loops forever, and logs results to `results.tsv`.

Optional: set `FX2_CMIX_BIN=/path/to/fx2-cmix` to compare against an external baseline (read-only).
