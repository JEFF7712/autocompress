# autoresearch

This is an experiment to have the LLM do its own research.

## Setup

To set up a new experiment, work with the user to:

1. **Agree on a run tag**: propose a tag based on today's date (e.g. `mar20`). The branch `autocompress/<tag>` must not already exist — this is a fresh run.
2. **Create the branch**: `git checkout -b autocompress/<tag>` from current main.
3. **Run init.sh** to prepare the environment in one step:
   ```bash
   nix develop --command ./init.sh
   ```
   This installs Python dependencies, downloads enwik9, creates proxy slices, and runs a baseline benchmark to confirm everything works. Wait for it to print "Init complete."
4. **Read the in-scope files**: Read these files for full context:
   - `README.md` — repository context.
   - `compress.cpp` — the file you modify. Compression algorithm. Starts with tunable LZMA.
   - `benchmark.py` — fixed harness (compiles compress.cpp, runs benchmark, reports score). Do not modify.
5. **Initialize results.tsv**: Create `results.tsv` with just the header row (see template). Record the baseline score from init.sh output as the first row.
6. **Confirm and go**: Confirm setup looks good.

Once you get confirmation, kick off the experimentation.

## Experimentation

Each experiment modifies `compress.cpp` and benchmarks it against the enwik9 proxy slices. The harness in `benchmark.py` compiles the C++ file, runs it, verifies roundtrip correctness, and reports the score.

**You can only edit `compress.cpp`.** The harness (`benchmark.py`), data prep (`prepare.py`), and dependencies are fixed.

**The goal is simple: minimize the score** — `archive_bytes + binary_bytes`: the total compressed size plus the size of the compiled `compress` binary (the decompressor). Lower is better. This mirrors the real Hutter Prize, which scores compressor + archive together.

Because the binary baseline (~25 KB) is negligible next to a ~200 MB archive, there is effectively no incentive to golf hand-written algorithm code. The binary term exists to forbid one specific cheat: embedding corpus-derived data — a dictionary primed on enwik9, a trained model, or the input itself — into `compress.cpp`. Such data lands in the binary and is counted byte-for-byte, so it only pays off if it saves more than it costs (which is exactly the legitimate economics of dictionary coding).

## What to explore

The starting point is LZMA2 with tunable parameters (level, dict size, lc/lp/pb). That's already much better than the previous Python bz2 approach. But there is a long road ahead:

**Near-term** (tune existing algorithm):
- Increase `DICT_SIZE` (try 128 MB, 256 MB — bigger = better compression, more memory). NOTE: the proxy is a single 128 MB slice, so a dictionary larger than the input it sees can't register a gain on proxy. Dict sizes ≥ 128 MB must be validated on the full run directly — do not discard them on a flat proxy score (see the keep/discard rule below).
- Enable `EXTREME` mode
- Tune `LC`/`LP`/`PB` — for text, `lc=4, lp=0, pb=2` or `lc=3, lp=0, pb=2` often works well
- Try adding a BCJ (Branch/Call/Jump) or delta filter before LZMA2 (not helpful for XML text, but try it)

**Medium-term** (better algorithms):
- Implement PPM (Prediction by Partial Matching): order 4-8 with escape mechanism
  — PPM typically reaches ~130-150 MB on enwik9
- Implement a context mixer blending multiple order-N predictions
- Try BWT + move-to-front + arithmetic coding (bzip2-style but tunable)
- Explore preprocessing: XML/wiki-aware transforms, dictionary coding

**Longer-term** (state of the art):
- Arithmetic coding + adaptive bitwise models (PAQ/cmix-style context mixing)
- Neural network predictor + arithmetic coder (requires significant C++ infrastructure)

## Output format

Each run prints exactly four lines:

```
proxy_score_bytes: 14525000
archive_bytes: 14500000
binary_bytes: 25000
roundtrip_ok: true
```

The score (`proxy_score_bytes` / `full_score_bytes`) is `archive_bytes + binary_bytes`. Proxy runs print `proxy_score_bytes`, full runs print `full_score_bytes`. Parse with:
```
grep "^proxy_score_bytes:\|^full_score_bytes:" run.log
```

If `roundtrip_ok: false` appears or the process exits non-zero, treat as a crash.

## Logging results

Log each experiment to `results.tsv` (tab-separated, untracked by git). Columns:

```
commit	proxy_score_bytes	full_score_bytes	binary_bytes	status	description
```

1. git commit hash (short, 7 chars)
2. proxy_score_bytes (archive + binary; 0 if crashed before scoring)
3. full_score_bytes (archive + binary; 0 if not run yet)
4. binary_bytes (size of the compiled decompressor — watch this if you embed data)
5. status: `keep`, `discard`, or `crash`
6. short description of what this experiment tried (no commas)

Logging `binary_bytes` alongside both scores lets you watch the proxy↔full correlation hold (or break) across experiments instead of assuming it.

## The experiment loop

The experiment runs on a dedicated branch (e.g. `autocompress/mar20`).

LOOP FOREVER:

1. Look at the git state: the current branch/commit
2. Modify `compress.cpp` with an experimental idea
3. `git commit -m "short description"`
4. Run: `uv run benchmark.py > run.log 2>&1` (redirect everything — do NOT use tee)
5. Parse score: `grep "^proxy_score_bytes:" run.log`
6. If empty (crash): run `tail -n 50 run.log` to read the error. Fix if trivial (typo, missing include); otherwise log as crash and revert.
7. If `roundtrip_ok: false`: immediate failure — the compressor is broken. Revert.
8. Log results in results.tsv
9. **Keep**: if proxy_score_bytes improved (lower), keep the commit and optionally run full benchmark
10. **Discard**: if score is equal or worse, `git reset --hard HEAD~1` to revert
11. **Exception — proxy-invisible changes**: the proxy is one 128 MB slice. Changes whose payoff only appears at full scale — dictionaries ≥ 128 MB, long-range / whole-corpus models — can show a flat or slightly worse proxy score yet still win on the full 1 GB. For these, run the full benchmark *before* discarding, and keep/discard on the full score.

When proxy improves, run the full benchmark to get a real score:
```
uv run benchmark.py --full > run.log 2>&1
grep "^full_score_bytes:" run.log
```
Update results.tsv with the full score.

**Timeout**: Proxy runs (single 128 MB slice) should finish in roughly 2-6 minutes with LZMA — longer with heavier algorithms. Full enwik9 runs may take 5-30 minutes depending on the algorithm. If a run exceeds 60 minutes, kill it and treat as a failed experiment.

**Crashes**: Fix obvious bugs (typo, missing include, wrong flag). If the idea is fundamentally broken, log crash and move on.

**NEVER STOP**: Once the loop has begun, do NOT pause to ask if you should continue. The human may be asleep. You are autonomous. If you run out of ideas, re-read the algorithm literature, try combinations of near-misses, try more radical changes. The loop runs until manually interrupted.
