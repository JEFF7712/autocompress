# World-Record Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the autocompress harness around a vendored fx2-cmix so an agent + runner-daemon loop can hunt for a >=1% Hutter Prize improvement (target S <= 109,685,196 bytes on enwik9) under enforced prize constraints.

**Architecture:** fx2-cmix vendored as a git subtree at `src/`. A tiered `benchmark.py` (t0 = 10 MB prefix, t1 = enwik8, t2 = enwik9) builds the compressor, runs compress/decompress under `systemd-run` memory caps and RLIMIT_CPU time caps, verifies roundtrip by sha256, and appends results to an append-only `ledger.tsv`. A `runner.py` systemd user service treats `exp/*` git branches as the work queue (tier chosen by a `Tier:` commit trailer), benchmarking unscored heads FIFO in throwaway worktrees. `report.py` renders deltas vs main-branch baselines.

**Tech Stack:** Python 3.11+ (stdlib only, pytest for tests, uv for env), nix flake devshell providing clang-17/upx/make, git worktrees, systemd user units.

**Spec:** `docs/superpowers/specs/2026-07-03-record-harness-design.md`

**Key upstream facts (verified 2026-07-03):**
- fx2-cmix: https://github.com/kaitz/fx2-cmix (GPL-3.0, branch `main`). Record S = 110,793,128 = compressor binary 441,463 + self-extracting archive 110,351,665.
- Build: `./build_and_construct_comp.sh` (PGO: `make prof_gen`, profile run on `prof_input/input`, `llvm-profdata-17 merge`, `make prof_use`, `upx-ucl -9 cmix`, then concatenates cmix + compressed dictionary + compressed article order + header into self-extracting `run/cmix`). Expects binaries named `clang++-17`, `llvm-profdata-17`, `upx-ucl`.
- Usage: `cd <dir with cmix>; ./cmix -e <input> enwik9.comp` writes self-extracting `archive9` to cwd. `./archive9` (no args) writes `enwik9_restored` to cwd.
- Prize envelope: per stage < 70,000/T CPU-hours (T = local Geekbench5 single-core), <= 10 GB RAM, <= 100 GB temp disk, single core, no GPU. fx2 submission machine T = 1026, 64.8 h compress.
- `src/models/ppmd.cpp` ships `mmap_to_disk = true` (the RAM-compliant setting). Leave it true.
- enwik8 is byte-identical to the first 10^8 bytes of enwik9, and enwik9 itself ends mid-article, so plain prefixes are structurally faithful tier inputs (no boundary snapping needed).

**Conventions:** repo commit style is `type(scope): summary` lowercase. No em dashes anywhere. No code comments unless the why is non-obvious. All temp/cache data under `~/.cache/autoresearch/`.

---

### Task 1: Toolchain flake + gitignore

fx2-cmix's build script hardcodes `clang++-17`, `llvm-profdata-17`, `upx-ucl`. Provide those names as wrapper binaries in the devshell so upstream scripts run unmodified.

**Files:**
- Modify: `flake.nix`
- Modify: `.gitignore`

- [ ] **Step 1: Rewrite flake.nix**

```nix
{
  description = "autocompress: Hutter Prize world-record harness";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" ];
      forAll = f: nixpkgs.lib.genAttrs systems (s: f nixpkgs.legacyPackages.${s});
    in {
      devShells = forAll (pkgs:
        let
          clang17 = pkgs.llvmPackages_17.clang;
          wrappers = [
            (pkgs.writeShellScriptBin "clang++-17" ''exec ${clang17}/bin/clang++ "$@"'')
            (pkgs.writeShellScriptBin "llvm-profdata-17" ''exec ${pkgs.llvmPackages_17.llvm}/bin/llvm-profdata "$@"'')
            (pkgs.writeShellScriptBin "upx-ucl" ''exec ${pkgs.upx}/bin/upx "$@"'')
          ];
        in {
          default = pkgs.mkShell {
            packages = wrappers ++ [
              clang17
              pkgs.llvmPackages_17.llvm
              pkgs.upx
              pkgs.gnumake
              pkgs.uv
            ];
          };
        });
    };
}
```

If `llvmPackages_17` has been dropped from nixos-unstable by now, pin `inputs.nixpkgs.url` to a release that still has it (e.g. `github:NixOS/nixpkgs/nixos-24.05`) rather than changing the clang major version; fx2-cmix's PGO flags are clang-17-validated.

- [ ] **Step 2: Verify the shell provides the exact binary names**

Run: `nix develop /home/rupan/projects/autocompress --command bash -c 'clang++-17 --version && llvm-profdata-17 --help >/dev/null && upx-ucl --version && make --version'`
Expected: clang version 17.x printed, upx version printed, no "command not found".

- [ ] **Step 3: Extend .gitignore**

Append to `.gitignore`:

```
ledger.tsv
runs/
config.toml
src/pgo_data/
src/run/
src/*.o
src/default.profdata
src/prof_output
src/prof_comp
src/cmix
src/remap
```

- [ ] **Step 4: Commit**

```bash
git add flake.nix .gitignore
git commit -m "chore(env): clang-17 toolchain wrappers for fx2-cmix build"
```

---

### Task 2: Vendor fx2-cmix as a subtree and smoke-build it

**Files:**
- Create: `src/` (entire fx2-cmix tree via git subtree)

- [ ] **Step 1: Add the subtree**

```bash
cd /home/rupan/projects/autocompress
git subtree add --prefix=src https://github.com/kaitz/fx2-cmix.git main --squash
```

Expected: two commits (squash + merge), `src/makefile`, `src/build_and_construct_comp.sh`, `src/src/runner.cpp`, `src/dictionary/english.dic`, `src/LICENSE` exist. Note the nested `src/src/` is upstream's layout; keep it.

- [ ] **Step 2: Confirm the RAM-compliant PPM setting**

Run: `rg -n "mmap_to_disk = " src/src/models/ppmd.cpp`
Expected: `bool mmap_to_disk = true;`. If false, do NOT change it silently; stop and report (it means upstream changed the default and the RAM envelope math needs rechecking).

- [ ] **Step 3: Smoke-build (takes ~15-30 min, PGO does two full compiles plus a profiling run)**

```bash
cd /home/rupan/projects/autocompress/src
nix develop .. --command bash build_and_construct_comp.sh
```

Expected: exits 0, `src/run/cmix` exists, is executable, and is roughly 440 KB (`ls -l run/cmix`). Run this in the background (`run_in_background`), it is slow.

- [ ] **Step 4: Verify a micro roundtrip by hand**

```bash
cd /home/rupan/projects/autocompress/src/run
head -c 1000000 ~/.cache/autoresearch/enwik9 > /tmp/claude-1000/-home-rupan-projects-autocompress/4eee89da-716f-41a6-9d75-50301a30818f/scratchpad/mini.bin
./cmix -e /tmp/claude-1000/-home-rupan-projects-autocompress/4eee89da-716f-41a6-9d75-50301a30818f/scratchpad/mini.bin mini.comp
./archive9
cmp enwik9_restored /tmp/claude-1000/-home-rupan-projects-autocompress/4eee89da-716f-41a6-9d75-50301a30818f/scratchpad/mini.bin && echo ROUNDTRIP_OK
rm -f mini.comp archive9 enwik9_restored
```

Expected: `ROUNDTRIP_OK`. (This also validates that `-e` handles truncated prefixes; enwik9 itself ends mid-article so truncation is in-distribution.) If `-e` crashes on the prefix, stop: the tier design needs revisiting, report to the user.

- [ ] **Step 5: Commit** (only if the build made no tracked changes; build artifacts are gitignored, so normally nothing to commit here beyond the subtree commits from Step 1)

```bash
git status --short
```

Expected: clean (subtree commits already exist).

---

### Task 3: Tiered data preparation

Replace the 128 MB middle-slice proxy with prefix tiers: t0 = first 10 MB, t1 = first 100 MB (enwik8), t2 = enwik9 itself.

**Files:**
- Modify: `prepare.py`
- Delete: `prepare_helpers.py`
- Create: `tiers.py`
- Test: `tests/test_tiers.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_tiers.py`:

```python
from pathlib import Path

from tiers import TIER_INPUT_BYTES, ensure_tiers


def test_tier_sizes():
    assert TIER_INPUT_BYTES == {
        "t0": 10_000_000,
        "t1": 100_000_000,
        "t2": 1_000_000_000,
    }


def test_ensure_tiers_writes_prefixes(tmp_path: Path):
    enwik9 = tmp_path / "enwik9"
    enwik9.write_bytes(bytes(range(256)) * 100)
    sizes = {"t0": 300, "t1": 5_000, "t2": enwik9.stat().st_size}
    paths = ensure_tiers(enwik9, tmp_path / "tiers", sizes)
    assert paths["t2"] == enwik9
    assert paths["t0"].read_bytes() == enwik9.read_bytes()[:300]
    assert paths["t1"].read_bytes() == enwik9.read_bytes()[:5_000]


def test_ensure_tiers_is_idempotent(tmp_path: Path):
    enwik9 = tmp_path / "enwik9"
    enwik9.write_bytes(b"x" * 1000)
    sizes = {"t0": 100, "t2": 1000}
    first = ensure_tiers(enwik9, tmp_path / "tiers", sizes)
    mtime = first["t0"].stat().st_mtime_ns
    second = ensure_tiers(enwik9, tmp_path / "tiers", sizes)
    assert second["t0"].stat().st_mtime_ns == mtime
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `uv run pytest tests/test_tiers.py -v`
Expected: FAIL (ModuleNotFoundError: tiers). If pytest itself is missing, first run `uv add --group dev pytest` and set `requires-python = ">=3.11"` in `pyproject.toml`.

- [ ] **Step 3: Implement `tiers.py`**

```python
"""Tier inputs are prefixes of enwik9. t1 equals enwik8 byte-for-byte;
enwik9 itself ends mid-article, so truncation is in-distribution for the
fx2-cmix transform."""

from pathlib import Path

TIER_INPUT_BYTES = {
    "t0": 10_000_000,
    "t1": 100_000_000,
    "t2": 1_000_000_000,
}

_CHUNK = 1 << 22


def _write_prefix(src: Path, dest: Path, size: int) -> None:
    tmp = dest.with_suffix(".tmp")
    remaining = size
    with src.open("rb") as fin, tmp.open("wb") as fout:
        while remaining > 0:
            chunk = fin.read(min(_CHUNK, remaining))
            if not chunk:
                raise ValueError(f"{src} shorter than requested prefix {size}")
            fout.write(chunk)
            remaining -= len(chunk)
    tmp.replace(dest)


def ensure_tiers(
    enwik9: Path, tier_dir: Path, sizes: dict[str, int] = TIER_INPUT_BYTES
) -> dict[str, Path]:
    tier_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for tier, size in sizes.items():
        if size == enwik9.stat().st_size:
            paths[tier] = enwik9
            continue
        dest = tier_dir / f"{tier}.bin"
        if not (dest.exists() and dest.stat().st_size == size):
            _write_prefix(enwik9, dest, size)
        paths[tier] = dest
    return paths
```

- [ ] **Step 4: Run tests, expect PASS**

Run: `uv run pytest tests/test_tiers.py -v`
Expected: 3 passed.

- [ ] **Step 5: Rewire `prepare.py`**

Keep the existing download/extract/verify logic (`_ensure_enwik9`, `verify_enwik9_size` but inline the size constant). Replace the proxy-slice code and `prepare_helpers` import:

```python
"""One-time data preparation: download enwik9, derive tier prefixes.

Usage:
    uv run prepare.py

Data is cached in ~/.cache/autoresearch/. Safe to re-run.
"""

import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

from tiers import ensure_tiers

CACHE_DIR = Path.home() / ".cache" / "autoresearch"
ENWIK9_URL = "https://mattmahoney.net/dc/enwik9.zip"
ENWIK9_SIZE = 1_000_000_000


def verify_enwik9_size(path: Path) -> bool:
    return path.exists() and path.stat().st_size == ENWIK9_SIZE


# _download_enwik9_zip, _extract_enwik9, _ensure_enwik9: unchanged from the
# current prepare.py except expected_enwik9_size_bytes() becomes ENWIK9_SIZE.


def main() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    enwik9 = _ensure_enwik9(CACHE_DIR)
    if not verify_enwik9_size(enwik9):
        print("ERROR: enwik9 verification failed", file=sys.stderr)
        sys.exit(1)
    paths = ensure_tiers(enwik9, CACHE_DIR / "tiers")
    for tier, p in sorted(paths.items()):
        print(f"{tier}: {p} ({p.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
```

Copy the three underscore-prefixed functions verbatim from the current file (they are correct), replacing the one call to `expected_enwik9_size_bytes()` inside `verify_enwik9_size`. Delete `prepare_helpers.py` (`git rm prepare_helpers.py`).

- [ ] **Step 6: Run prepare end-to-end** (enwik9 already cached from the old setup, so this only writes the two prefixes)

Run: `uv run prepare.py`
Expected: three lines, `t0 ... 10000000 bytes`, `t1 ... 100000000 bytes`, `t2 ... 1000000000 bytes`.

- [ ] **Step 7: Commit**

```bash
git add tiers.py prepare.py tests/test_tiers.py pyproject.toml uv.lock
git rm prepare_helpers.py
git commit -m "feat(data): tiered prefix inputs (t0 10MB, t1 enwik8, t2 enwik9)"
```

---

### Task 4: Prize envelope math

**Files:**
- Create: `envelope.py`
- Create: `config.toml.example`
- Test: `tests/test_envelope.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_envelope.py`:

```python
import pytest

from envelope import (
    RAM_LIMIT_BYTES,
    cpu_budget_seconds,
    load_geekbench_t,
    projected_prize_hours,
    tier_cpu_limit_seconds,
)


def test_ram_limit_is_decimal_10gb():
    assert RAM_LIMIT_BYTES == 10_000_000_000


def test_cpu_budget_scales_inversely_with_geekbench():
    assert cpu_budget_seconds(1026) == pytest.approx(70_000 / 1026 * 3600)
    assert cpu_budget_seconds(2052) == pytest.approx(cpu_budget_seconds(1026) / 2)


def test_tier_limits():
    assert tier_cpu_limit_seconds("t0", 1000) == 2 * 3600
    assert tier_cpu_limit_seconds("t1", 1000) == 12 * 3600
    assert tier_cpu_limit_seconds("t2", 1000) == pytest.approx(70_000 / 1000 * 3600)
    with pytest.raises(ValueError):
        tier_cpu_limit_seconds("t9", 1000)


def test_projected_prize_hours_matches_fx2_reference():
    assert projected_prize_hours(64.8 * 3600, 1026) == pytest.approx(64.8)
    assert projected_prize_hours(32.4 * 3600, 2052) == pytest.approx(64.8)


def test_load_geekbench_t(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text("geekbench5_single_core = 1800\n")
    assert load_geekbench_t(cfg) == 1800.0
    cfg.write_text("geekbench5_single_core = 0\n")
    with pytest.raises(ValueError):
        load_geekbench_t(cfg)
```

- [ ] **Step 2: Run it, expect FAIL** (ModuleNotFoundError: envelope)

Run: `uv run pytest tests/test_envelope.py -v`

- [ ] **Step 3: Implement `envelope.py`**

```python
"""Prize resource envelope (http://prize.hutter1.net/hrules.htm): each stage
must run in under 70'000/T CPU-hours with at most 10 GB RAM and 100 GB temp
disk, where T is the machine's Geekbench5 single-core score. Single core,
no GPU. CPU seconds (not wall time) so laptop suspends don't corrupt timing."""

import tomllib
from pathlib import Path

RAM_LIMIT_BYTES = 10_000_000_000
FX2_SUBMISSION_GEEKBENCH_T = 1026

_FIXED_TIER_CPU_LIMIT_S = {"t0": 2 * 3600, "t1": 12 * 3600}


def load_geekbench_t(config_path: Path) -> float:
    with config_path.open("rb") as f:
        t = tomllib.load(f)["geekbench5_single_core"]
    if t <= 0:
        raise ValueError(
            "geekbench5_single_core unset in config.toml: measure Geekbench 5 "
            "single-core on this machine and fill it in (see config.toml.example)"
        )
    return float(t)


def cpu_budget_seconds(geekbench_t: float) -> float:
    return 70_000 / geekbench_t * 3600


def tier_cpu_limit_seconds(tier: str, geekbench_t: float) -> float:
    if tier in _FIXED_TIER_CPU_LIMIT_S:
        return _FIXED_TIER_CPU_LIMIT_S[tier]
    if tier == "t2":
        return cpu_budget_seconds(geekbench_t)
    raise ValueError(f"unknown tier: {tier}")


def projected_prize_hours(cpu_seconds: float, geekbench_t: float) -> float:
    return cpu_seconds / 3600 * geekbench_t / FX2_SUBMISSION_GEEKBENCH_T
```

- [ ] **Step 4: Run tests, expect PASS**

Run: `uv run pytest tests/test_envelope.py -v`

- [ ] **Step 5: Create `config.toml.example`**

```toml
# Copy to config.toml (gitignored) and fill in the measured value.
# Geekbench 5 SINGLE-CORE score of this machine. All CPU-time budgets derive
# from it: prize budget per stage = 70000/T hours. Do not guess; measure, or
# use the browser.geekbench.com median for the exact CPU model.
geekbench5_single_core = 0
```

- [ ] **Step 6: Commit**

```bash
git add envelope.py config.toml.example tests/test_envelope.py
git commit -m "feat(harness): prize envelope math and machine config"
```

---

### Task 5: Ledger module

**Files:**
- Create: `ledger.py`
- Test: `tests/test_ledger.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_ledger.py`:

```python
from ledger import COLUMNS, append_row, read_rows, scored_keys


def _row(commit="a" * 40, tier="t0", **kw):
    base = {c: "" for c in COLUMNS}
    base.update(commit=commit, branch="exp/001", tier=tier, status="ok")
    base.update(kw)
    return base


def test_append_and_read_roundtrip(tmp_path):
    path = tmp_path / "ledger.tsv"
    append_row(path, _row(score_bytes="123"))
    append_row(path, _row(tier="t1", score_bytes="456"))
    rows = read_rows(path)
    assert len(rows) == 2
    assert rows[0]["score_bytes"] == "123"
    assert rows[1]["tier"] == "t1"


def test_header_written_once(tmp_path):
    path = tmp_path / "ledger.tsv"
    append_row(path, _row())
    append_row(path, _row(tier="t1"))
    assert path.read_text().count("commit\t") == 1


def test_scored_keys(tmp_path):
    path = tmp_path / "ledger.tsv"
    append_row(path, _row(commit="a" * 40, tier="t0"))
    append_row(path, _row(commit="a" * 40, tier="t1"))
    keys = scored_keys(read_rows(path))
    assert ("a" * 40, "t0") in keys
    assert ("a" * 40, "t1") in keys
    assert ("b" * 40, "t0") not in keys


def test_read_missing_file(tmp_path):
    assert read_rows(tmp_path / "nope.tsv") == []
```

- [ ] **Step 2: Run it, expect FAIL**

Run: `uv run pytest tests/test_ledger.py -v`

- [ ] **Step 3: Implement `ledger.py`**

```python
import csv
from pathlib import Path

COLUMNS = [
    "commit",
    "branch",
    "tier",
    "status",
    "score_bytes",
    "archive_bytes",
    "binary_bytes",
    "cpu_seconds_comp",
    "cpu_seconds_decomp",
    "peak_rss_bytes",
    "projected_prize_hours",
    "description",
]


def append_row(path: Path, row: dict[str, str]) -> None:
    write_header = not path.exists()
    with path.open("a", newline="") as f:
        w = csv.DictWriter(f, COLUMNS, delimiter="\t")
        if write_header:
            w.writeheader()
        w.writerow(row)


def read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def scored_keys(rows: list[dict[str, str]]) -> set[tuple[str, str]]:
    return {(r["commit"], r["tier"]) for r in rows}
```

- [ ] **Step 4: Run tests, expect PASS**

Run: `uv run pytest tests/test_ledger.py -v`

- [ ] **Step 5: Commit**

```bash
git add ledger.py tests/test_ledger.py
git commit -m "feat(harness): append-only tsv ledger keyed by (commit, tier)"
```

---

### Task 6: benchmark.py rewrite

The heart of the harness. Replaces the LZMA-era file wholesale and deletes `compress.cpp`.

**REVISED 2026-07-05 (see spec "Tiering reality"):** the benchmark has TWO scoring paths because fx2-cmix's scored `-e` pipeline only works on full enwik9:

- **t0, t1 (codec proxy path):** run `run/cmix_orig -c <tier_prefix> out.comp` then `run/cmix_orig -d out.comp restored`; verify `sha256(restored) == sha256(tier_prefix)`. `archive_bytes = len(out.comp)`, `binary_bytes = len(run/cmix_orig)`, `score = archive_bytes + binary_bytes`. This exercises the cmix codec/model layer only (no wiki preprocessing), so it is a **directional** proxy for codec-layer experiments and blind to preprocessing/dict/reorder changes.
- **t2 (real pipeline):** run `run/cmix -e <enwik9> enwik9.comp` (writes self-extracting `archive9` to cwd), then `./archive9` (writes `enwik9_restored` to cwd); verify `sha256(enwik9_restored) == sha256(enwik9)`. `archive_bytes = len(archive9)`, `binary_bytes = len(run/cmix)` (the self-extracting compressor, reported for tracking), `score = len(archive9)` (self-extracting, so comp == decomp; this is the official Hutter S). Emit both so the ledger keeps the composition.

Note `cmix` and `archive9` write `progress.log` and `ppm.temp` to their **current working directory**, so every stage must `cwd` into the per-run scratch dir. `run/cmix_orig` is the pure PGO'd compressor (produced by `build_and_construct_comp.sh` before the dict/order are concatenated into `run/cmix`); `run/cmix` is the self-extracting one. Copy whichever binary the tier needs into the scratch dir and run it there.

**Files:**
- Rewrite: `benchmark.py`
- Delete: `compress.cpp`
- Test: `tests/test_benchmark_helpers.py`

Design notes for the implementer:
- Stages run via `systemd-run --user --scope` for the RAM cap (`MemoryMax` kills on breach; `MemorySwapMax=0` prevents swap-cheating) and `resource.setrlimit(RLIMIT_CPU, ...)` in `preexec_fn` for the CPU cap (rlimits inherit through systemd-run's exec; the kernel SIGKILLs at the hard limit, immune to suspend).
- CPU seconds and peak RSS come from `os.wait4()`: the rusage of a reaped child includes its waited-for descendants; `ru_maxrss` is in KiB on Linux.
- All big artifacts live in a per-run scratch dir under the cache; only sizes and logs survive (logs in `runs/<commit7>-<tier>/` in the repo).
- The code block below is the ORIGINAL single-path `-e` skeleton; adapt it to dispatch on tier per the REVISED note above (a `run_codec_stage` for t0/t1 and the `-e`/`archive9` stages for t2). Keep `classify_failure` and `render_output` exactly as tested.

- [ ] **Step 1: Write the failing test for the pure helpers**

Create `tests/test_benchmark_helpers.py`:

```python
from benchmark import classify_failure, render_output


def test_classify_ok():
    assert classify_failure(0, cpu_seconds=10, cpu_limit=100, peak_rss=1_000, ram_limit=10_000) == "ok"


def test_classify_timeout():
    assert classify_failure(-9, cpu_seconds=101, cpu_limit=100, peak_rss=1_000, ram_limit=10_000) == "timeout"


def test_classify_oom():
    assert classify_failure(-9, cpu_seconds=5, cpu_limit=100, peak_rss=9_800, ram_limit=10_000) == "oom"


def test_classify_crash():
    assert classify_failure(1, cpu_seconds=5, cpu_limit=100, peak_rss=1_000, ram_limit=10_000) == "crash"


def test_render_output_is_grep_stable():
    text = render_output(
        tier="t1",
        status="ok",
        score_bytes=110_793_128,
        archive_bytes=110_351_665,
        binary_bytes=441_463,
        cpu_seconds_comp=100.0,
        cpu_seconds_decomp=200.0,
        peak_rss_bytes=9_000_000_000,
        projected_prize_hours=64.8,
        roundtrip_ok=True,
    )
    lines = text.splitlines()
    assert "score_bytes: 110793128" in lines
    assert "status: ok" in lines
    assert "roundtrip_ok: true" in lines
    assert "projected_prize_hours: 64.80" in lines
```

- [ ] **Step 2: Run it, expect FAIL** (cannot import names from benchmark)

Run: `uv run pytest tests/test_benchmark_helpers.py -v`

- [ ] **Step 3: Rewrite `benchmark.py`**

```python
"""Tiered Hutter Prize benchmark for the vendored fx2-cmix at src/.

Builds the self-extracting compressor, compresses the tier input, runs the
produced archive9 to decompress, verifies roundtrip by sha256, and reports
score = len(cmix) + len(archive9) under enforced prize constraints
(10 GB MemoryMax via systemd-run, per-tier RLIMIT_CPU).

DO NOT MODIFY during experiments; the agent edits src/ only.

Usage:
    uv run benchmark.py --tier t0
    uv run benchmark.py --tier t2 --append-ledger
"""

import argparse
import hashlib
import os
import resource
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from envelope import (
    RAM_LIMIT_BYTES,
    load_geekbench_t,
    projected_prize_hours,
    tier_cpu_limit_seconds,
)
from ledger import append_row
from tiers import TIER_INPUT_BYTES

REPO = Path(__file__).resolve().parent
CACHE = Path.home() / ".cache" / "autoresearch"


@dataclass
class Stage:
    returncode: int
    cpu_seconds: float
    peak_rss_bytes: int


def classify_failure(
    returncode: int,
    cpu_seconds: float,
    cpu_limit: float,
    peak_rss: int,
    ram_limit: int,
) -> str:
    if returncode == 0:
        return "ok"
    if cpu_seconds >= cpu_limit * 0.98:
        return "timeout"
    if peak_rss >= ram_limit * 0.95:
        return "oom"
    return "crash"


def render_output(
    *,
    tier: str,
    status: str,
    score_bytes: int,
    archive_bytes: int,
    binary_bytes: int,
    cpu_seconds_comp: float,
    cpu_seconds_decomp: float,
    peak_rss_bytes: int,
    projected_prize_hours: float,
    roundtrip_ok: bool,
) -> str:
    return "\n".join(
        [
            f"tier: {tier}",
            f"status: {status}",
            f"score_bytes: {score_bytes}",
            f"archive_bytes: {archive_bytes}",
            f"binary_bytes: {binary_bytes}",
            f"cpu_seconds_comp: {cpu_seconds_comp:.2f}",
            f"cpu_seconds_decomp: {cpu_seconds_decomp:.2f}",
            f"peak_rss_bytes: {peak_rss_bytes}",
            f"projected_prize_hours: {projected_prize_hours:.2f}",
            f"roundtrip_ok: {'true' if roundtrip_ok else 'false'}",
        ]
    )


def run_stage(cmd: list[str], cwd: Path, cpu_limit_s: float, log: Path) -> Stage:
    argv = [
        "systemd-run",
        "--user",
        "--scope",
        "--quiet",
        "-p",
        f"MemoryMax={RAM_LIMIT_BYTES}",
        "-p",
        "MemorySwapMax=0",
        "--",
        *cmd,
    ]

    def limits() -> None:
        lim = int(cpu_limit_s)
        resource.setrlimit(resource.RLIMIT_CPU, (lim, lim + 60))

    with log.open("ab") as lf:
        proc = subprocess.Popen(
            argv, cwd=cwd, stdout=lf, stderr=subprocess.STDOUT, preexec_fn=limits
        )
        _, status, ru = os.wait4(proc.pid, 0)
    rc = -os.WTERMSIG(status) if os.WIFSIGNALED(status) else os.WEXITSTATUS(status)
    proc.returncode = rc
    return Stage(
        returncode=rc,
        cpu_seconds=ru.ru_utime + ru.ru_stime,
        peak_rss_bytes=ru.ru_maxrss * 1024,
    )


def build(src_dir: Path, log: Path) -> Path:
    env_cmd = []
    if not shutil.which("clang++-17"):
        env_cmd = ["nix", "develop", str(REPO), "--command"]
    with log.open("ab") as lf:
        r = subprocess.run(
            [*env_cmd, "bash", "build_and_construct_comp.sh"],
            cwd=src_dir,
            stdout=lf,
            stderr=subprocess.STDOUT,
        )
    binary = src_dir / "run" / "cmix"
    if r.returncode != 0 or not binary.exists():
        raise RuntimeError(f"build failed, see {log}")
    return binary


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1 << 22):
            h.update(chunk)
    return h.hexdigest()


def git(args: list[str]) -> str:
    return subprocess.run(
        ["git", *args], cwd=Path.cwd(), capture_output=True, text=True, check=True
    ).stdout.strip()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--tier", choices=sorted(TIER_INPUT_BYTES), required=True)
    p.add_argument("--append-ledger", action="store_true")
    p.add_argument("--branch", default=None)
    p.add_argument("--ledger", default=str(REPO / "ledger.tsv"))
    p.add_argument("--config", default=str(REPO / "config.toml"))
    p.add_argument("--src-dir", default=None, help="fx2-cmix dir (defaults to <cwd>/src)")
    p.add_argument("--keep-artifacts", action="store_true")
    args = p.parse_args()

    src_dir = Path(args.src_dir) if args.src_dir else Path.cwd() / "src"
    geekbench_t = load_geekbench_t(Path(args.config))
    cpu_limit = tier_cpu_limit_seconds(args.tier, geekbench_t)
    tier_file = (
        CACHE / "enwik9"
        if args.tier == "t2"
        else CACHE / "tiers" / f"{args.tier}.bin"
    )
    if not tier_file.exists():
        sys.exit(f"{tier_file} missing: run prepare.py first")

    commit = git(["rev-parse", "HEAD"])
    branch = args.branch or git(["rev-parse", "--abbrev-ref", "HEAD"])
    description = git(["log", "-1", "--format=%s"])

    run_dir = Path(args.ledger).resolve().parent / "runs" / f"{commit[:7]}-{args.tier}"
    run_dir.mkdir(parents=True, exist_ok=True)
    log = run_dir / "run.log"

    scratch = CACHE / "scratch" / f"{commit[:7]}-{args.tier}"
    if scratch.exists():
        shutil.rmtree(scratch)
    scratch.mkdir(parents=True)

    status = "ok"
    archive_bytes = binary_bytes = peak_rss = 0
    cpu_comp = cpu_decomp = 0.0
    roundtrip_ok = False

    try:
        compressor = build(src_dir, log)
        binary_bytes = compressor.stat().st_size
        shutil.copy2(compressor, scratch / "cmix")

        comp = run_stage(
            ["./cmix", "-e", str(tier_file), "input.comp"], scratch, cpu_limit, log
        )
        cpu_comp, peak_rss = comp.cpu_seconds, comp.peak_rss_bytes
        archive = scratch / "archive9"
        if comp.returncode != 0 or not archive.exists():
            status = classify_failure(
                comp.returncode, cpu_comp, cpu_limit, peak_rss, RAM_LIMIT_BYTES
            )
            if status == "ok":
                status = "crash"
        else:
            archive_bytes = archive.stat().st_size
            decomp = run_stage(["./archive9"], scratch, cpu_limit, log)
            cpu_decomp = decomp.cpu_seconds
            peak_rss = max(peak_rss, decomp.peak_rss_bytes)
            restored = scratch / "enwik9_restored"
            if decomp.returncode != 0 or not restored.exists():
                status = classify_failure(
                    decomp.returncode, cpu_decomp, cpu_limit,
                    decomp.peak_rss_bytes, RAM_LIMIT_BYTES,
                )
                if status == "ok":
                    status = "crash"
            else:
                roundtrip_ok = sha256(restored) == sha256(tier_file)
                if not roundtrip_ok:
                    status = "roundtrip_fail"
    except RuntimeError as e:
        print(e, file=sys.stderr)
        status = "crash"
    finally:
        if not args.keep_artifacts:
            shutil.rmtree(scratch, ignore_errors=True)

    score = archive_bytes + binary_bytes if status == "ok" else 0
    prize_hours = projected_prize_hours(max(cpu_comp, cpu_decomp), geekbench_t)

    out = render_output(
        tier=args.tier,
        status=status,
        score_bytes=score,
        archive_bytes=archive_bytes,
        binary_bytes=binary_bytes,
        cpu_seconds_comp=cpu_comp,
        cpu_seconds_decomp=cpu_decomp,
        peak_rss_bytes=peak_rss,
        projected_prize_hours=prize_hours,
        roundtrip_ok=roundtrip_ok,
    )
    print(out)
    (run_dir / "result.txt").write_text(out + "\n")

    if args.append_ledger:
        append_row(
            Path(args.ledger),
            {
                "commit": commit,
                "branch": branch,
                "tier": args.tier,
                "status": status,
                "score_bytes": str(score),
                "archive_bytes": str(archive_bytes),
                "binary_bytes": str(binary_bytes),
                "cpu_seconds_comp": f"{cpu_comp:.2f}",
                "cpu_seconds_decomp": f"{cpu_decomp:.2f}",
                "peak_rss_bytes": str(peak_rss),
                "projected_prize_hours": f"{prize_hours:.2f}",
                "description": description,
            },
        )

    sys.exit(0 if status == "ok" else 1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run helper tests, expect PASS**

Run: `uv run pytest tests/test_benchmark_helpers.py -v`

- [ ] **Step 5: Delete the legacy compressor**

```bash
git rm compress.cpp
rm -f compress
```

- [ ] **Step 6: Run the full test suite**

Run: `uv run pytest -v`
Expected: all pass (tiers, envelope, ledger, benchmark helpers).

- [ ] **Step 7: Commit**

```bash
git add benchmark.py tests/test_benchmark_helpers.py
git commit -m "feat(harness): tiered fx2-cmix benchmark with enforced prize envelope"
```

(The `git rm compress.cpp` from Step 5 is already staged and lands in this commit. Run logs live beside the ledger, `runs/` in the main repo, so they survive worktree cleanup.)

(Integration validation of this file happens in Task 10 Phase 0; a t0 run costs ~40 min and needs the built binary plus a filled-in config.toml.)

---

### Task 7: Runner daemon

**Files:**
- Create: `runner.py`
- Create: `systemd/autocompress-runner.service`
- Test: `tests/test_runner.py`

- [ ] **Step 1: Write the failing test for queue logic**

Create `tests/test_runner.py`:

```python
from runner import Job, parse_tier, select_jobs


def test_parse_tier_valid():
    assert parse_tier("t1") == "t1"
    assert parse_tier("  t2\n") == "t2"


def test_parse_tier_defaults_to_t0():
    assert parse_tier("") == "t0"
    assert parse_tier("bogus") == "t0"


def test_select_jobs_filters_scored_and_sorts_fifo():
    heads = [
        Job(branch="exp/002", commit="b" * 40, tier="t0", committed_at=200),
        Job(branch="exp/001", commit="a" * 40, tier="t1", committed_at=100),
        Job(branch="exp/003", commit="c" * 40, tier="t0", committed_at=300),
    ]
    scored = {("b" * 40, "t0")}
    jobs = select_jobs(heads, scored)
    assert [j.branch for j in jobs] == ["exp/001", "exp/003"]


def test_select_jobs_rescores_same_commit_at_new_tier():
    heads = [Job(branch="exp/001", commit="a" * 40, tier="t1", committed_at=100)]
    scored = {("a" * 40, "t0")}
    assert len(select_jobs(heads, scored)) == 1
```

- [ ] **Step 2: Run it, expect FAIL**

Run: `uv run pytest tests/test_runner.py -v`

- [ ] **Step 3: Implement `runner.py`**

```python
"""Benchmark runner daemon: git-native queue over exp/* branches.

Any exp/* head whose (commit, tier) is not in the ledger gets benchmarked
FIFO by commit date in a throwaway worktree. Tier comes from the head
commit's "Tier:" trailer (default t0). Escalation = empty commit with a
higher Tier: trailer.

Run as a systemd user service (systemd/autocompress-runner.service) or
one-shot: uv run runner.py --once
"""

import argparse
import fcntl
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from ledger import read_rows, scored_keys
from tiers import TIER_INPUT_BYTES

REPO = Path(__file__).resolve().parent
LEDGER = REPO / "ledger.tsv"
LOCK = Path.home() / ".cache" / "autoresearch" / "runner.lock"


@dataclass(frozen=True)
class Job:
    branch: str
    commit: str
    tier: str
    committed_at: int


def parse_tier(raw: str) -> str:
    tier = raw.strip()
    return tier if tier in TIER_INPUT_BYTES else "t0"


def select_jobs(heads: list[Job], scored: set[tuple[str, str]]) -> list[Job]:
    pending = [j for j in heads if (j.commit, j.tier) not in scored]
    return sorted(pending, key=lambda j: j.committed_at)


def git(args: list[str], cwd: Path = REPO) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    ).stdout


def list_heads() -> list[Job]:
    out = git(
        [
            "for-each-ref",
            "--format=%(refname:short)\t%(objectname)\t%(committerdate:unix)",
            "refs/heads/exp/",
        ]
    )
    heads = []
    for line in out.splitlines():
        branch, sha, ts = line.split("\t")
        trailer = git(["log", "-1", "--format=%(trailers:key=Tier,valueonly)", sha])
        heads.append(
            Job(branch=branch, commit=sha, tier=parse_tier(trailer), committed_at=int(ts))
        )
    return heads


def run_job(job: Job) -> None:
    print(f"[runner] {job.branch} {job.commit[:7]} {job.tier}", flush=True)
    wt = Path(tempfile.mkdtemp(prefix="autocompress-wt-"))
    try:
        git(["worktree", "add", "--detach", str(wt), job.commit])
        subprocess.run(
            [
                "uv",
                "run",
                "benchmark.py",
                "--tier",
                job.tier,
                "--append-ledger",
                "--branch",
                job.branch,
                "--ledger",
                str(LEDGER),
                "--config",
                str(REPO / "config.toml"),
            ],
            cwd=wt,
        )
    finally:
        subprocess.run(["git", "worktree", "remove", "--force", str(wt)], cwd=REPO)
        shutil.rmtree(wt, ignore_errors=True)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--once", action="store_true", help="drain the queue and exit")
    p.add_argument("--poll-seconds", type=int, default=300)
    args = p.parse_args()

    LOCK.parent.mkdir(parents=True, exist_ok=True)
    lock_file = LOCK.open("w")
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        sys.exit("another runner instance holds the lock")

    while True:
        jobs = select_jobs(list_heads(), scored_keys(read_rows(LEDGER)))
        if jobs:
            run_job(jobs[0])
        elif args.once:
            return
        else:
            time.sleep(args.poll_seconds)


if __name__ == "__main__":
    main()
```

Note the deliberate absence of `check=True` on the benchmark subprocess: benchmark.py exits 1 for failed experiments while still appending the ledger row, which removes the job from the queue. The runner must not crash on a failed experiment.

- [ ] **Step 4: Run unit tests, expect PASS**

Run: `uv run pytest tests/test_runner.py -v`

- [ ] **Step 5: Integration-test the queue scan against a throwaway branch** (no benchmark run: just verify `list_heads` sees it)

```bash
cd /home/rupan/projects/autocompress
git branch exp/smoke
git commit --allow-empty -m "smoke: queue scan test" --only 2>/dev/null || true
uv run python -c "
from runner import list_heads
heads = list_heads()
print(heads)
assert any(h.branch == 'exp/smoke' and h.tier == 't0' for h in heads)
print('QUEUE_SCAN_OK')
"
git branch -D exp/smoke
```

Expected: `QUEUE_SCAN_OK`.

- [ ] **Step 6: Create `systemd/autocompress-runner.service`**

```ini
[Unit]
Description=autocompress benchmark runner

[Service]
Type=exec
WorkingDirectory=/home/rupan/projects/autocompress
ExecStart=/usr/bin/env uv run runner.py
Nice=10
Restart=on-failure
RestartSec=60

[Install]
WantedBy=default.target
```

Do not enable it yet (Phase 0 does that). Note for NixOS: if `/usr/bin/env uv` does not resolve under the user manager, replace ExecStart with the absolute uv path (`which uv`).

- [ ] **Step 7: Commit**

```bash
git add runner.py systemd/autocompress-runner.service tests/test_runner.py
git commit -m "feat(harness): git-native queue runner daemon"
```

---

### Task 8: report.py

**Files:**
- Create: `report.py`
- Test: `tests/test_report.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_report.py`:

```python
from report import baselines, deltas


def _row(branch, tier, score, status="ok", commit="c" * 40):
    return {
        "commit": commit,
        "branch": branch,
        "tier": tier,
        "status": status,
        "score_bytes": str(score),
        "cpu_seconds_comp": "100.0",
        "description": "test row",
    }


ROWS = [
    _row("main", "t0", 1_000_000),
    _row("main", "t1", 10_000_000),
    _row("exp/001", "t0", 990_000),
    _row("exp/001", "t1", 9_950_000),
    _row("exp/002", "t0", 1_010_000),
    _row("exp/003", "t0", 0, status="crash"),
]


def test_baselines_latest_ok_main_row_per_tier():
    b = baselines(ROWS)
    assert b["t0"]["score_bytes"] == "1000000"
    assert b["t1"]["score_bytes"] == "10000000"


def test_deltas_vs_baseline():
    d = deltas(ROWS)
    exp1_t0 = next(r for r in d if r["branch"] == "exp/001" and r["tier"] == "t0")
    assert exp1_t0["delta_bytes"] == -10_000
    exp2 = next(r for r in d if r["branch"] == "exp/002")
    assert exp2["delta_bytes"] == 10_000


def test_deltas_skips_failed_rows():
    d = deltas(ROWS)
    assert not any(r["branch"] == "exp/003" for r in d)
```

- [ ] **Step 2: Run it, expect FAIL**

Run: `uv run pytest tests/test_report.py -v`

- [ ] **Step 3: Implement `report.py`**

```python
"""Ledger analytics: deltas vs main baselines and tier correlation.

Usage: uv run report.py
"""

from pathlib import Path

from ledger import read_rows

LEDGER = Path(__file__).resolve().parent / "ledger.tsv"


def baselines(rows: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for r in rows:
        if r["branch"] == "main" and r["status"] == "ok":
            out[r["tier"]] = r
    return out


def deltas(rows: list[dict]) -> list[dict]:
    base = baselines(rows)
    out = []
    for r in rows:
        if r["branch"] == "main" or r["status"] != "ok":
            continue
        b = base.get(r["tier"])
        if b is None:
            continue
        out.append(
            {
                **r,
                "delta_bytes": int(r["score_bytes"]) - int(b["score_bytes"]),
            }
        )
    return out


def main() -> None:
    rows = read_rows(LEDGER)
    base = baselines(rows)
    print("== baselines (main) ==")
    for tier in sorted(base):
        b = base[tier]
        print(f"{tier}: {b['score_bytes']} bytes  cpu {b['cpu_seconds_comp']}s")
    print()
    print("== experiments ==")
    for r in sorted(deltas(rows), key=lambda r: (r["branch"], r["tier"])):
        sign = "+" if r["delta_bytes"] >= 0 else ""
        print(
            f"{r['branch']:<28} {r['tier']} {r['commit'][:7]} "
            f"{sign}{r['delta_bytes']} bytes  {r['description']}"
        )
    print()
    failed = [r for r in rows if r["status"] != "ok"]
    if failed:
        print("== failures ==")
        for r in failed:
            print(f"{r['branch']:<28} {r['tier']} {r['commit'][:7]} {r['status']}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests, expect PASS**

Run: `uv run pytest tests/test_report.py -v`

- [ ] **Step 5: Full suite**

Run: `uv run pytest -v`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add report.py tests/test_report.py
git commit -m "feat(harness): ledger report with baseline deltas"
```

---

### Task 9: Docs, research seeds, init.sh

**Files:**
- Rewrite: `program.md`
- Rewrite: `README.md`
- Modify: `init.sh`
- Create: `research/README.md`
- Delete: `results_template.tsv`, `results.tsv`, `run.log`, `run_full.log`, `prompt.txt` leftovers

- [ ] **Step 1: Rewrite `program.md`**

Full replacement content:

```markdown
# autocompress: record program

Mission: beat the Hutter Prize record. S = archive9 + compressor binary must
reach <= 109,685,196 bytes on enwik9 (>= 1% below fx2-cmix's 110,793,128)
inside the prize envelope: per stage < 70,000/T CPU-hours (T in config.toml),
<= 10 GB RAM, <= 100 GB temp disk, single core, no GPU.

You edit only `src/` (the vendored fx2-cmix). The harness (benchmark.py,
runner.py, ledger.py, report.py, envelope.py, tiers.py, prepare.py) is fixed.

## Session cycle (review-and-refill)

1. `uv run report.py`: read every new ledger row since last session.
2. For each finished experiment:
   - Worse or equal at its tier: delete the branch (`git branch -D exp/NNN-name`).
     Record one line about why it failed in research/log.md.
   - Better at t0: escalate to t1:
     `git switch exp/NNN-name && git commit --allow-empty -m "bench: escalate" -m "Tier: t1"`
   - Better at t1 (and CPU/RAM within envelope): consider t2. A t2 run costs
     ~1.5 days of laptop compute each way; only clearly promising or
     proxy-invisible changes earn one.
   - Better at t2: merge to main, append the new baseline, celebrate, then
     raise the bar: the new main score is the number to beat.
3. Refill the queue to 3-6 pending branches. Each experiment:
   - One idea per branch, branched from main: `git switch -c exp/NNN-slug main`
   - Commit message: subject = short description; body = hypothesis, expected
     direction and rough magnitude; final trailer line `Tier: t0`
     (or `Tier: t1` for changes whose payoff scales with corpus size:
     dictionary, article order, long-range models).
4. Update research/log.md with what was learned.
5. Exit. The runner daemon grinds the queue; results appear in ledger.tsv.

## Where gains plausibly live (seed list, extend via research/)

- Speed first: fx2-cmix sits at ~95% of the time budget. Every saved CPU-hour
  buys headroom for a bigger PPM order, more mixer contexts, or a larger LSTM.
  Profile before believing anything.
- Dictionary: english.dic inherited from phda9/STARLIT lineage; retrain or
  extend against enwik9 vocabulary. Payoff scales with input size (Tier: t1).
- Article order: the embedding+t-SNE+k-means order from fx2-cmix was produced
  with a 2024-era embedding model; better embeddings or better clustering may
  yield a better order (Tier: t1, likely t2-only visible).
- Mixer/model surgery: fx2-cmix removed models vs cmix for speed; check
  whether any removal hurt more than it saved, now that other parts changed.
- NLP stemmer word-types: upstream README lists word-stream heuristics; more
  categories or better boundaries are cheap experiments.
- Preprocessor: single-pass wiki transform has known TODOs; UTF-8 entity
  handling, template/link stream separation.
- Rebuild constants: SEED and UPDATE_LIMIT in build_and_construct_comp.sh are
  tunable (they were tuned for the 2024 machine).

## Rules

- Never edit benchmark.py, runner.py, ledger.py, report.py, envelope.py,
  tiers.py, prepare.py, or config.toml from an experiment branch.
- Never delete ledger.tsv. Append-only.
- `status != ok` rows are informative failures: read runs/<commit7>-<tier>/run.log.
- Keep mmap_to_disk = true in src/src/models/ppmd.cpp (RAM envelope).
- An experiment that beats t0 but blows the CPU or RAM envelope is a loss.
- Do not start a t2 without checking the runner queue is otherwise empty
  (a t2 blocks everything for ~3 days).
```

- [ ] **Step 2: Rewrite `README.md`**

```markdown
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

| Tier | Input | Approx. cost/stage (this laptop) |
|------|-------|-------------------------------|
| t0 | first 10 MB of enwik9 | ~20 min |
| t1 | enwik8 (first 100 MB) | ~3.5 h |
| t2 | enwik9 | ~35 h |

## Setup

```bash
nix develop --command ./init.sh   # deps, data, toolchain check
cp config.toml.example config.toml  # then fill in measured Geekbench5 score
systemctl --user link $PWD/systemd/autocompress-runner.service
systemctl --user start autocompress-runner
```

## Commands

```bash
uv run benchmark.py --tier t0            # one-off benchmark of current HEAD
uv run report.py                          # ledger summary
uv run runner.py --once                   # drain queue without the service
journalctl --user -u autocompress-runner -f
```
```

- [ ] **Step 3: Update `init.sh`**

Replace steps so init: (1) `uv sync`, (2) `uv run prepare.py`, (3) toolchain check (`nix develop --command bash -c 'clang++-17 --version && upx-ucl --version'`), (4) prints next steps (fill config.toml, build via `cd src && nix develop .. --command bash build_and_construct_comp.sh`, enable runner). Remove the old compile-and-proxy-benchmark step (a baseline t0 costs ~40 min and belongs to Phase 0, not init).

- [ ] **Step 4: Create `research/README.md`**

```markdown
# research

Hypothesis backlog and findings. `log.md` (append-only) records what each
experiment taught us. Seed reading:

- fx2-cmix submission notes: https://github.com/kaitz/fx2-cmix (README lists
  every change vs fx-cmix; each is a tunable surface)
- fx2-cmix action-plan timeline:
  https://docs.google.com/document/d/14nNIMAFC11lNFD-WrLQbGLIuRqqcKKBnUtrxy-tc0Rc/
- improvement graphs:
  https://docs.google.com/document/d/1DW0Lqr_y-yAIvPpGua56j1Y3gRaMS5yt2RuQy5xgGMk/
- fx-cmix discussion thread: https://encode.su/threads/4161-fx-cmix-(HP)
- STARLIT (article ordering origin): https://github.com/amargaritov/starlit
- cmix: https://github.com/byronknoll/cmix
- Hutter Prize rules: http://prize.hutter1.net/hrules.htm
- LTCB (context on all approaches): https://mattmahoney.net/dc/text.html
```

- [ ] **Step 5: Delete stale files**

```bash
git rm results_template.tsv
rm -f results.tsv run.log run_full.log
```

(`results.tsv`, `run.log`, `run_full.log` are untracked or already gitignored; verify with `git status` before removing anything unexpected.)

- [ ] **Step 6: Commit**

```bash
git add program.md README.md init.sh research/README.md
git rm results_template.tsv
git commit -m "docs: reorient program and README around the record attempt"
```

---

### Task 10: Phase 0 baseline runbook

No new code. This is the execution checklist that validates everything end-to-end and produces the baseline ledger rows. Long steps run in the background.

- [ ] **Step 1: Fill config.toml with a measured Geekbench5 single-core score**

Options, in order of preference: (a) run Geekbench 5 locally (unfree; `nix run nixpkgs#geekbench` if acceptable, use the GB5 variant), (b) look up the median GB5 single-core for the exact CPU (i9-13900H) on browser.geekbench.com and note the source in a comment. Do NOT leave 0; do not invent a number without a source.

```bash
cp config.toml.example config.toml
# edit geekbench5_single_core
```

- [ ] **Step 2: Verify the full test suite and a build**

```bash
uv run pytest -v
cd src && nix develop .. --command bash build_and_construct_comp.sh  # background, ~20 min
```

- [ ] **Step 3: t0 baseline on main** (~40 min both stages, background)

```bash
uv run benchmark.py --tier t0 --append-ledger > /dev/null 2>&1 &
```

Then `uv run report.py`: expect one `main t0` baseline row, status ok, roundtrip true. Sanity-check `peak_rss_bytes` < 10e9 and cpu seconds against the ~20 min/stage estimate.

- [ ] **Step 4: t1 baseline on main** (~7 h both stages, overnight, background)

```bash
uv run benchmark.py --tier t1 --append-ledger > /dev/null 2>&1 &
```

Sanity anchor: enwik8 results for cmix-class programs are ~14.8-15.2 MB; fx2-cmix's t1 archive should land in that neighborhood. If it is wildly off, investigate before burning a t2.

- [ ] **Step 5: Enable the runner service**

```bash
systemctl --user link /home/rupan/projects/autocompress/systemd/autocompress-runner.service
systemctl --user start autocompress-runner
systemctl --user status autocompress-runner
```

Expected: active (running), journal shows idle polling (empty queue).

- [ ] **Step 6: t2 baseline on main** (~3 days round trip; requires user awareness since the laptop must stay powered)

Confirm with the user before launching (this monopolizes the machine for days):

```bash
uv run benchmark.py --tier t2 --append-ledger > /dev/null 2>&1 &
```

Acceptance: status ok, roundtrip true, `score_bytes` within ~0.2% of 110,793,128 (PGO noise and -march=native make bit-identical reproduction unlikely; the shape must match: archive ~110.35 MB + binary ~441 KB), `projected_prize_hours` <= 68, `peak_rss_bytes` <= 10e9.

- [ ] **Step 7: Record baseline provenance**

Append a dated note to `research/log.md` with the three baseline scores, cpu seconds, RSS, and the config.toml Geekbench value used. Commit `research/log.md`.

```bash
git add research/log.md
git commit -m "docs(research): phase-0 baseline results"
```

Phase 0 exit criteria: three ok baseline rows in ledger.tsv (t0, t1, t2), runner service running, test suite green. The experiment loop (program.md) may then begin.

---

## Self-review notes

- Spec coverage: vendoring (Task 2), tiered benchmark + enforcement (Tasks 3, 4, 6), runner + git queue + escalation (Task 7), ledger + report + correlation visibility (Tasks 5, 8), program.md/research (Task 9), phase 0 (Task 10), flake/toolchain (Task 1). The spec's "correlation table" is covered by report.py's per-branch tier rows; a dedicated correlation matrix is YAGNI until enough multi-tier rows exist.
- The spec's score formula (archive + binary) maps to fx2-cmix reality as len(run/cmix self-extracting compressor) + len(archive9), matching the official S = comp9 + archive9 of the 2024 submission.
- Types check: Job dataclass fields match test usage; ledger COLUMNS match benchmark.py's append_row dict keys exactly; parse_tier/select_jobs signatures match tests.
```
