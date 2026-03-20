# autoresearch

This is an experiment to have the LLM do its own research.

## Setup

To set up a new experiment, work with the user to:

1. **Agree on a run tag**: propose a tag based on today's date (e.g. `mar5`). The branch `autoresearch/<tag>` must not already exist — this is a fresh run.
2. **Create the branch**: `git checkout -b autoresearch/<tag>` from current master.
3. **Read the in-scope files**: The repo is small. Read these files for full context:
   - `README.md` — repository context.
   - `prepare.py` — fixed constants and data prep (downloads enwik9 + builds proxy slices). Do not modify.
   - `train.py` — the file you modify. Compression candidate logic, scoring, and experiment loop.
4. **Verify data exists**: Check that `~/.cache/autoresearch/` contains `enwik9` and the proxy slices under `proxy_slices/`. If not, run `uv run prepare.py`.
5. **Initialize results.tsv**: Create `results.tsv` with just the header row. The baseline will be recorded after the first run.
6. **Confirm and go**: Confirm setup looks good.

Once you get confirmation, kick off the experimentation.

## Experimentation

Each experiment now executes the minimal Hutter Prize-inspired compression loop over the deterministic enwik9 proxy slices. The harness in `train.py` prints a mode-specific score key (`proxy_score_bytes` or `full_score_bytes`) plus `archive_bytes`, `code_bytes`, and the `roundtrip_ok` flag. Run it with `uv run train.py` (or `uv run train.py --full`).

You can only edit `train.py`; data prep (`prepare.py`), dependencies, and the evaluation helpers are fixed. The optional fx2-cmix baseline remains read-only, controlled entirely via the `FX2_CMIX_BIN` environment variable. Do not add any automatic cloning, building, or mutation logic for the baseline binary.

**The goal is simple: minimize `score_bytes`.** That is the sum of `archive_bytes` and `code_bytes`, and every experiment should lower it in the proxy run (and ideally in the full loop). Keep the reporting stable so the key metric can be grepped from the logs.

**Resource guidance**: VRAM/memory pressure is still relevant, but the compression loop is lightweight. Treat any meaningful growth in resource usage as a cost unless it materially lowers `score_bytes`.

**Simplicity criterion** remains the same: all else being equal, simpler, clearer changes are preferable to fragile tricks that only shave a few bytes.

**The first run** should still be the unmodified script to establish a personal baseline before tuning.

## Output format

Each run finishes by emitting a concise summary with its mode-specific score key plus the helper fields:

```
proxy_score_bytes: 117
archive_bytes: 100
code_bytes: 17
roundtrip_ok: true
```

Proxy runs print `proxy_score_bytes`, while full runs report `full_score_bytes`; there is no leading `---` separator. You can extract the key metric by grepping for whichever score key appeared (or add `code_bytes` and `archive_bytes` if you prefer).

## Logging results

When an experiment is done, log it to `results.tsv` (tab-separated). Use the provided `results_template.tsv` header to ensure you capture both proxy and full score_bytes.

The TSV has a header row and 5 columns:

```
commit	proxy_score_bytes	full_score_bytes	status	description
```

1. git commit hash (short, 7 chars)
2. proxy score_bytes achieved (0 when a run crashes before scoring)
3. full score_bytes achieved (0 when a run crashes before scoring)
4. status: `keep`, `discard`, or `crash`
5. short text description of what this experiment tried (avoid commas in descriptions)

## The experiment loop

The experiment runs on a dedicated branch (e.g. `autocompress/mar5` or `autocompress/mar5-gpu0`).

LOOP FOREVER:

1. Look at the git state: the current branch/commit we're on
2. Tune `train.py` with an experimental idea by directly hacking the code.
3. git commit
4. Run the experiment: `uv run train.py > run.log 2>&1` (redirect everything — do NOT use tee or let output flood your context)
5. Read out the results: `grep "^proxy_score_bytes:\|^full_score_bytes:" run.log` to capture the new objective.
6. If the grep output is empty, the run crashed. Run `tail -n 50 run.log` to read the Python stack trace and attempt a fix. If you can't get things to work after more than a few attempts, give up.
7. Record the results in the tsv (NOTE: do not commit the results.tsv file, leave it untracked by git)
8. If the `score_bytes` values improved (lower), you "advance" the branch, keeping the git commit
9. If `score_bytes` stay equal or worsen, you git reset back to where you started

The idea is that you are a completely autonomous researcher trying things out. If they work, keep. If they don't, discard. And you're advancing the branch so that you can iterate. If you feel like you're getting stuck in some way, you can rewind but you should probably do this very very sparingly (if ever).

**Timeout**: Each experiment should take ~5 minutes total (+ a few seconds for startup and eval overhead). If a run exceeds 10 minutes, kill it and treat it as a failure (discard and revert).

**Crashes**: If a run crashes (OOM, or a bug, or etc.), use your judgment: If it's something dumb and easy to fix (e.g. a typo, a missing import), fix it and re-run. If the idea itself is fundamentally broken, just skip it, log "crash" as the status in the tsv, and move on.

**NEVER STOP**: Once the experiment loop has begun (after the initial setup), do NOT pause to ask the human if you should continue. Do NOT ask "should I keep going?" or "is this a good stopping point?". The human might be asleep, or gone from a computer and expects you to continue working *indefinitely* until you are manually stopped. You are autonomous. If you run out of ideas, think harder — read papers referenced in the code, re-read the in-scope files for new angles, try combining previous near-misses, try more radical architectural changes. The loop runs until the human interrupts you, period.

As an example use case, a user might leave you running while they sleep. If each experiment takes you ~5 minutes then you can run approx 12/hour, for a total of about 100 over the duration of the average human sleep. The user then wakes up to experimental results, all completed by you while they slept!
