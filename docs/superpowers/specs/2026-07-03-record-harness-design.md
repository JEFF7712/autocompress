# autocompress: world-record harness design

Date: 2026-07-03
Status: approved

## Goal

Beat the Hutter Prize record: fx2-cmix's 110,793,128 bytes (Kaido Orav & Byron Knoll, awarded 2024-10). A prize claim requires >=1% improvement, so the target is:

**S <= 109,685,196 bytes on enwik9** (find ~1.1 MB of savings)

where S = `archive_bytes + binary_bytes` under the comp=decomp relaxation of the official rules, subject to the prize envelope:

- <= 10 GB RAM
- <= 100 GB temp disk
- single core, no GPU, no network/external input
- CPU-time budget: 70,000/T hours, T = local Geekbench5 single-core score
- Linux x86-64 executable

Timing uses CPU seconds (not wall time) so laptop suspends don't corrupt measurements. Prize-machine time is projected via the Geekbench ratio.

## Starting point

Vendor the reigning champion, [fx2-cmix](https://github.com/kaitz/fx2-cmix) (GPL-3.0), as a git subtree at `src/`. It becomes the mutable code, replacing `compress.cpp`. Prize rules explicitly allow building on prior winners; every recent winner did (STARLIT -> fx-cmix -> fx2-cmix). Known baseline characteristics: ~65 h symmetric on the prize test machine, ~9.5 GB RAM, ~21 GB temp disk, builds with clang-17 + upx-ucl.

## Compute model

Laptop only (i9-13900H, ~1.8x the prize test machine single-core). Estimated run times:

| Tier | Input | Size | Approx. run |
|------|-------|------|-------------|
| t0 | first 10 MB of enwik9 | 10 MB | ~20 min |
| t1 | enwik8 (first 100 MB) | 100 MB | ~3.5 h |
| t2 | full enwik9 | 1 GB | ~35 h |

All tiers are prefixes of enwik9.

### Tiering reality (revised 2026-07-05, supersedes the assumption below)

The original assumption that "plain prefixes are structurally faithful tier inputs, no boundary snapping needed" is **false**. The scored artifact `archive9` is produced only by fx2-cmix's `-e` pipeline, which is hardwired to full enwik9's exact structure: `split4Comp`/`split4Decomp` (`src/src/readalike_prepr/misc.h`) use hardcoded line numbers (main ends at line 13,146,906), and the article-order file references 243,425 specific articles. A shorter prefix cannot roundtrip through `-e` because the decompressor's hardcoded splits do not match the shorter stream.

Verified: the raw codec path (`cmix -c` / `cmix -d`, no wiki preprocessing) *does* roundtrip on prefixes, and it exercises the cmix model / mixer / coder / SSE / APM / LSTM / PPM layers, which is where the large majority of experiments live.

**Decision (Option 2, chosen for correctness and to avoid gambling on phda9 prefix-safety while unattended):**
- **t0 / t1 proxies score via `cmix -c` / `cmix -d`** on the raw enwik9 prefix. Score = `comp_output_bytes + binary_bytes`. Roundtrip-verifiable, fast, faithful to the codec layer.
- **t2 scores via the full `-e` pipeline** on full enwik9. Score = `len(archive9)` (self-extracting, so comp == decomp). This is the real Hutter Prize number.
- Experiments touching the **preprocessing / dictionary / article-order** layer get **no proxy signal** (proxies skip that layer) and must be flagged `Tier: t2` in their commit trailer. `program.md` must state this.

**Fidelity caveats to record in `program.md`:** a t0/t1 `-c` score compresses *raw* wiki bytes, not the preprocessed `.ready4cmix` stream the real pipeline compresses, so proxy scores are **directional for codec-layer changes** (relative deltas track), not absolute, and are blind to the preprocessing layer. t2 is ground truth.

**Deferred enhancement (Option 1, faithful `-e` proxies):** extend the archive `HeaderInfo` to store this input's intro/main/coda line counts at compress time and read them back in `split4Decomp` instead of the hardcoded constants, plus make `reorder`/`sort` prefix-safe (bounds guards + trailing-line passthrough) and verify phda9 preprocessing has no other enwik9 assumptions. This would make t0/t1 true miniatures of the scored pipeline. Not done now: it sits on the t2 money-run scoring path and needs careful roundtrip verification that a 20-min-per-cycle rebuild loop makes expensive; revisit once the harness is otherwise working.

## Architecture: git-native queue + runner daemon

Thinking (agent sessions) is decoupled from benchmarking (daemon). The queue *is* git: an experiment is a branch `exp/<id>` whose head commit message carries a `Tier:` trailer (default `t0`) and states the hypothesis.

### Components

**`benchmark.py --tier {t0,t1,t2}`** (rewrite): builds via the vendored makefile; compresses, decompresses, verifies roundtrip by sha256; emits one machine-parsable block: `score_bytes`, `archive_bytes`, `binary_bytes`, `cpu_seconds_comp`, `cpu_seconds_decomp`, `peak_rss_bytes`, `projected_prize_hours`, `roundtrip_ok`. Runs execute under `systemd-run --user --scope -p MemoryMax=10G` with per-tier CPU-time limits (t0: 1.5 h; t1: 10 h; t2: the actual prize budget scaled by the Geekbench ratio, roughly 31 h each way on this laptop). Exceeding RAM or time is a hard fail (`oom` / `timeout`), not a warning.

**`runner.py`** (new, systemd user service): loop over `refs/heads/exp/*`; any (head commit, tier) pair absent from the ledger is queued FIFO by commit date. For each: check out into a temp worktree, build, run the trailer's tier via `benchmark.py`, append the result to `ledger.tsv`, remove the worktree. Full logs land in `runs/<commit7>-<tier>/`. Escalation is git-native: to promote a t0 winner, the agent adds an empty commit with `Tier: t1` (new head = new ledger key, no side-channel state). The ledger is append-only and keyed by (commit, tier), so the runner is idempotent and crash/suspend-safe.

**`ledger.tsv`** (untracked, append-only): commit, branch, tier, score_bytes, archive_bytes, binary_bytes, cpu_seconds, peak_rss_bytes, projected_prize_hours, status (`ok`/`crash`/`timeout`/`oom`/`roundtrip_fail`), description.

**`report.py`** (new): per-branch deltas vs the baseline at each tier plus a t0->t1->t2 correlation table, so sessions can see when small proxies lie. Dictionary/preprocessing changes are expected proxy-liars (payoff scales with corpus size) and go straight to t1.

**`prepare.py`** (extend): downloads enwik9, derives t0/t1 prefixes, records sha256s.

**`config`**: stores the measured Geekbench5 single-core score; all time budgets derive from it.

**`flake.nix`**: grows clang-17, upx-ucl, make, pinned to fx2-cmix's build expectations.

Deleted: `compress.cpp`, the LZMA harness, old proxy-slice logic (history keeps them).

## Phase 0: baseline reproduction

Before any experiment branches exist:

1. Measure Geekbench5 single-core, store in config.
2. Build vendored fx2-cmix unmodified.
3. Run t0 and t1; then one t2 (~1.5 days) to confirm ~110.8 MB within the envelope.
4. Record all three as baseline ledger rows.

## Agent program (`program.md` rewrite)

Sessions are a review-and-refill cycle, not a blind hill-climbing loop:

1. Read the ledger (`report.py`).
2. Kill losers (delete branch), escalate winners (empty commit with higher `Tier:`).
3. Generate 3-6 new hypothesis branches, each with hypothesis and expected direction in the commit message.
4. Exit; the daemon grinds overnight.

Hypotheses come from a tracked `research/` directory seeded with known gain surfaces: fx2-cmix TODO/issues, the STARLIT article-reordering lineage, cmix changelogs, encode.su threads, dictionary/preprocessing improvements, mixer tweaks, and speed optimizations (freeing CPU budget buys room for bigger models, since fx2-cmix sits at the resource ceiling).

Keep/discard rules: compare deltas vs baseline at the same tier; only strong t1 winners get t2 slots (a t2 run costs ~1.5 days of laptop time).

## Risks

- 16 GB laptop RAM minus a 10 GB-capped run leaves ~4-5 GB desktop headroom; t2 runs are best left to nights.
- fx2-cmix already sits at ~9.5 GB / ~65 h: the harness will reject most "make the model bigger" experiments. That is the constraint doing its job; gains must be nearly compute-neutral or buy back budget elsewhere.
- t0 (10 MB) scores are partly dominated by fixed model/dictionary overheads; treat t0 as a smoke test + directional signal, with t1 as the real proxy.

## Out of scope

Cloud burst / parallel runners, submission logistics (30-day comment period, comp9 packaging), any from-scratch algorithm track.
