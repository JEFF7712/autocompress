# autocompress

Goal: beat the Hutter Prize world record. The current record is fx2-cmix
(Kaido Orav & Byron Knoll, 2024) at S = 110,793,128 bytes; a prize claim
requires S <= 109,685,196 (>= 1% better) on enwik9 inside the prize envelope
(< 70,000/T CPU-hours per stage, <= 10 GB RAM, <= 100 GB temp disk, single
core, no GPU).

The reigning champion is vendored at `src/` (GPL-3.0) as the baseline. An
agent proposes patches as `exp/*` branches; a runner daemon benchmarks them
continuously; sessions review the ledger and refill the queue. See
`program.md` for the loop and `docs/superpowers/specs/` for the design.

## Layout

| Path | Role |
|------|------|
| `src/` | fx2-cmix (mutable: this is what experiments edit) |
| `benchmark.py` | fixed harness: build, compress, decompress, verify, score |
| `runner.py` | daemon: benchmarks unscored `exp/*` heads FIFO |
| `ledger.py` / `ledger.tsv` | append-only results, keyed (commit, tier) |
| `report.py` | deltas vs main baselines |
| `envelope.py` | prize resource math |
| `tiers.py` / `prepare.py` | enwik9 download + tier prefixes |
| `config.toml` | machine Geekbench5 score (copy from config.toml.example) |
| `program.md` | agent instructions |
| `research/` | hypothesis backlog and findings log |

## Tiers

Two scoring paths, because fx2-cmix's scored `-e` pipeline only works on full
enwik9 (its preprocessing is hardwired to enwik9's exact structure):

| Tier | Input | Path | Measures | Approx. cost/stage |
|------|-------|------|----------|--------------------|
| t0 | first 10 MB | `cmix_orig -c`/`-d` | codec layer only (directional) | ~20 min |
| t1 | enwik8 (100 MB) | `cmix_orig -c`/`-d` | codec layer only (directional) | ~3.5 h |
| t2 | enwik9 (1 GB) | `cmix -e` + `archive9` | real Hutter S (ground truth) | ~35 h |

t0/t1 are blind to the preprocessing/dictionary/article-order layer; those
experiments are scored directly at t2 (see `program.md`).

## Setup

```bash
nix develop --command ./init.sh   # deps, data, toolchain check
cp config.toml.example config.toml  # then fill in per-machine values
./systemd/install.sh                # generate + enable the runner service
```

Deployment to a Kubernetes cluster (container image via `nix build
.#runner-image`, `ram_enforcer = "external"`) is supported; manifests live
with the target cluster's GitOps config, not here.

## Commands

```bash
uv run benchmark.py --tier t0            # one-off benchmark of current HEAD
uv run report.py                          # ledger summary
uv run runner.py --once                   # drain queue without the service
journalctl --user -u autocompress-runner -f
```
