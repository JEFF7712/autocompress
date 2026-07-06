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
