# research log

Append-only. Newest last.

## 2026-07-05: harness bring-up

Vendored fx2-cmix at `src/` (subtree). Two vendored fixes were required to
build and run on this machine (NixOS, kernel 6.18, i9-13900H); both are
environment/kernel-compat only and do not change compression logic:

- `fix(env)`: the `clang++-17` devshell wrapper rewrites `-march=native` to
  `-march=raptorlake`. LLVM 17 misdetects 13th-gen Intel mobile CPUs and falls
  back to generic x86-64 (no AVX2), which fails to compile the vectorized
  model code.
- `fix(ppmd)`: `PPMD::ByteUpdate` remaps the disk-backed PPM heap with
  `MAP_FIXED_NOREPLACE` at the same base address. The PPM model holds absolute
  pointers into the heap; kernels >= ~6.x no longer reuse the freed hole for a
  NULL-hint mmap, so the original code left every pointer dangling and
  segfaulted after ~20k updates.

Tiering decision (see spec "Tiering reality"): the scored `-e` pipeline is
hardwired to full enwik9 structure and cannot roundtrip on prefixes, so
proxies (t0/t1) score via the raw `cmix_orig -c`/`-d` codec path (codec layer
only, directional) and t2 uses the real `-e` pipeline. Faithful `-e` proxies
(storing per-input split line counts in the archive header) are a deferred
enhancement.

Baseline codec roundtrip verified: `cmix_orig -c`/`-d` on a 1 MB enwik9 prefix
is byte-identical (1,000,000 -> 199,137 bytes). Full-enwik9 `-e` roundtrip and
the ~110.8 MB reproduction are pending the Phase 0 t2 run.

## 2026-07-06: Phase 0 t0 baseline

t0 (10 MB prefix, codec path): score 1,921,963 = archive 1,779,227 +
cmix_orig 142,736. Roundtrip ok, peak RSS 6.19 GB, deterministic across
rebuilds (identical bytes on two independent PGO builds).

Timing lesson: unpinned, the scheduler drifted the single-threaded run onto
E-cores (comp 4,231 s, decomp 1,887 s, wildly asymmetric). Pinned to P-core 4
(taskset inside the systemd-run scope; AllowedCPUs= silently no-ops without
cpuset delegation): comp 2,284 s, decomp 2,210 s, symmetric as expected.
config.toml's Geekbench T (1950, P-core number) is only consistent with
P-core-pinned runs, so pinning is part of the harness contract now.

Effective codec rate ~4.4 KB/s. Naive extrapolation to t2 (~934 MB
preprocessed stream) suggests ~59 h/stage vs the enforced 35.9 h limit, BUT
t0 carries fixed model-init overhead and the -e stream differs from raw text;
t1 will give the real slope. If t1 confirms the overshoot, the whole record
attempt hinges on speed work first (which is where fx2-cmix's own authors
focused too). Watch this number.

## 2026-07-07: Phase 0 t1 baseline, and a compliance lesson

t1 (enwik8, codec path): score 15,979,075 = archive 15,836,339 + cmix_orig
142,736. Roundtrip ok. comp 21,682 s, decomp 19,979 s, peak RSS 7.46 GB.
Rate is almost perfectly linear vs t0 (marginal ~216 s/MB), so t0 is a
trustworthy directional proxy for codec-layer changes at 10x less cost.

Feasibility finding: a t2 stage extrapolates to ~56 h at codec rate vs the
33.4 h the Geekbench ratio predicts from the fx2-cmix submission (64.8 h at
T=1026). Either way it straddles or exceeds this laptop's enforced 35.9 h
budget. Lesson: GB5 single-core overrates memory-latency-bound cmix
throughput on this laptop (LPDDR5), and prize compliance depends on the
machine's ratio (cmix_hours x T / 70,000), which was already 0.95 on the
authors' Xeon. Consequences:
- Do not run t2 on this laptop; it would likely hit the RLIMIT and waste
  ~1.5 days. t2 belongs on a machine with a favorable ratio (measure the
  homelab workers' GB5 AND their cmix t0 rate before committing).
- Speed experiments are not optional polish; they are the gate to running
  a compliant t2 anywhere, and every saved CPU-hour also buys model
  headroom. First experiment wave should be profiling + speed.
