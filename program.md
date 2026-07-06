# autocompress: record program

Mission: beat the Hutter Prize record. S = archive9 + compressor binary must
reach <= 109,685,196 bytes on enwik9 (>= 1% below fx2-cmix's 110,793,128)
inside the prize envelope: per stage < 70,000/T CPU-hours (T in config.toml),
<= 10 GB RAM, <= 100 GB temp disk, single core, no GPU.

You edit only `src/` (the vendored fx2-cmix). The harness (benchmark.py,
runner.py, ledger.py, report.py, envelope.py, tiers.py, prepare.py) is fixed.

## Tiers and what they actually measure

The scored `-e` pipeline is hardwired to full enwik9's structure, so it only
runs at t2. Proxies use the raw codec path instead:

- **t0 (10 MB) / t1 (enwik8):** `cmix_orig -c`/`-d` on the raw prefix.
  Score = comp_output + binary. This exercises the cmix codec / model /
  mixer / coder / SSE / APM / LSTM / PPM layers ONLY. It does NOT run the wiki
  preprocessing, dictionary, or article reordering. So a proxy score is a
  **directional** signal for codec-layer changes (relative deltas track) and
  is **blind** to preprocessing/dictionary/order changes.
- **t2 (enwik9):** the full `-e` pipeline. Score = len(archive9). This is the
  real Hutter number and the only ground truth.

Consequence for experiment routing (set in the commit `Tier:` trailer):
- Codec/model/mixer/coder experiments: `Tier: t0` (fast directional signal),
  escalate winners to t1, then t2.
- Preprocessing / dictionary / article-order / NLP-transform experiments:
  `Tier: t2` directly. Proxies cannot see them; do not waste a t0 slot.

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
   - Better at t2: merge to main, append the new baseline, then raise the bar:
     the new main score is the number to beat.
3. Refill the queue to 3-6 pending branches. Each experiment:
   - One idea per branch, branched from main: `git switch -c exp/NNN-slug main`
   - Commit message: subject = short description; body = hypothesis, expected
     direction and rough magnitude; final trailer line `Tier: t0`
     (or `Tier: t2` for the preprocessing/dict/order layer, per above).
4. Update research/log.md with what was learned.
5. Exit. The runner daemon grinds the queue; results appear in ledger.tsv.

## Where gains plausibly live (seed list, extend via research/)

- Speed first: fx2-cmix sits at ~95% of the time budget. Every saved CPU-hour
  buys headroom for a bigger PPM order, more mixer contexts, or a larger LSTM.
  Profile before believing anything. (Codec layer: proxy-visible.)
- Dictionary: english.dic inherited from the phda9/STARLIT lineage; retrain or
  extend against enwik9 vocabulary. (Preprocessing layer: `Tier: t2`.)
- Article order: the embedding+t-SNE+k-means order was produced with a
  2024-era embedding model; better embeddings or clustering may beat it.
  (Preprocessing layer: `Tier: t2`.)
- Mixer/model surgery: fx2-cmix removed models vs cmix for speed; check
  whether any removal hurt more than it saved. (Codec: proxy-visible.)
- NLP stemmer word-types: more categories or better boundaries are cheap.
  (Preprocessing layer, but affects codec input: `Tier: t2` to score.)
- Preprocessor: single-pass wiki transform has known TODOs. (`Tier: t2`.)
- Rebuild constants: SEED and UPDATE_LIMIT in build_and_construct_comp.sh are
  tunable (they were tuned for the 2024 machine). (Affects codec: proxy-visible.)

## Rules

- Never edit benchmark.py, runner.py, ledger.py, report.py, envelope.py,
  tiers.py, prepare.py, or config.toml from an experiment branch.
- Never delete ledger.tsv. Append-only.
- `status != ok` rows are informative failures: read runs/<commit7>-<tier>/run.log.
- Keep mmap_to_disk = true in src/src/models/ppmd.cpp (RAM envelope). Two
  vendored fixes already exist and must stay: the ppmd MAP_FIXED_NOREPLACE
  remap (this kernel relocates NULL-hint mmaps) and the -march=raptorlake
  wrapper in flake.nix (llvm17 misdetects this CPU).
- An experiment that beats a tier but blows the CPU or RAM envelope is a loss.
- Do not start a t2 without checking the runner queue is otherwise empty
  (a t2 blocks everything for ~3 days).
