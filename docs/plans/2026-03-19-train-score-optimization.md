# Train Score Optimization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Execute the autonomous `program.md` workflow end-to-end, keeping `prepare.py` fixed and improving `train.py` against lower `score_bytes`.

**Architecture:** Start from a clean initial repository commit so experiment rows can record real short hashes and keep/discard decisions can use git safely. Use the fixed harness in `prepare.py` plus the stable CLI output from `train.py`, then iterate only on `train.py` with a proxy-first loop that promotes improvements to `--full` runs and logs every outcome in untracked `results.tsv`.

**Tech Stack:** Python 3.10+, `uv`, git, existing unit tests under `tests/`, standard library compression code in `train.py`.

---

### Task 1: Establish a git baseline for the run

**Files:**
- Modify: `docs/plans/2026-03-19-train-score-optimization.md`
- Commit: repository root initial snapshot

**Step 1: Verify current git state**

Run: `git status --short --branch`
Expected: no commits yet on `main`, files untracked.

**Step 2: Create the initial repository commit**

Run: `git add . && git commit -m "chore: initialize autoresearch baseline"`
Expected: first commit created successfully.

**Step 3: Create the experiment branch**

Run: `git checkout -b autoresearch/mar19`
Expected: switched to dedicated autoresearch branch.

### Task 2: Complete setup and record the baseline result

**Files:**
- Create: `results.tsv` (untracked from template)
- Read: `run.log`

**Step 1: Ensure cached data exists**

Run: `uv run prepare.py`
Expected: only if `~/.cache/autoresearch/enwik9` or `~/.cache/autoresearch/proxy_slices/` is missing.

**Step 2: Initialize results tracking**

Run: copy `results_template.tsv` to `results.tsv` if missing.
Expected: header-only TSV exists and remains untracked.

**Step 3: Run baseline proxy evaluation**

Run: `uv run train.py > run.log 2>&1`
Expected: `run.log` contains `proxy_score_bytes`, `archive_bytes`, `code_bytes`, and `roundtrip_ok`.

**Step 4: Parse and record the baseline row**

Run: extract `proxy_score_bytes` from `run.log`, use `0` for full score, and append a `keep` row to `results.tsv` with the current short commit hash and description `baseline`.

### Task 3: TDD each train.py experiment

**Files:**
- Modify: `train.py`
- Test: `tests/test_train_helpers.py`
- Test: `tests/test_train_summary.py`
- Test: `tests/test_train_evaluation.py`

**Step 1: Write or extend one failing test for the next behavior change**

Examples:
- coverage for a new helper that chooses a better compression strategy
- coverage for preserving summary output while reducing code size
- coverage for roundtrip correctness across the modified path

**Step 2: Run the focused test to verify RED**

Run: `uv run pytest <targeted-test> -q`
Expected: fail for the intended missing behavior, not an unrelated error.

**Step 3: Implement the minimal `train.py` change**

Allowed scope: `train.py` only.

**Step 4: Run the focused test to verify GREEN**

Run: `uv run pytest <targeted-test> -q`
Expected: pass.

**Step 5: Run the broader train test set**

Run: `uv run pytest tests/test_train_helpers.py tests/test_train_summary.py tests/test_train_evaluation.py -q`
Expected: pass before any experiment run.

### Task 4: Evaluate, log, and keep/discard each experiment

**Files:**
- Modify: `train.py`
- Read: `run.log`
- Read: `run_full.log`
- Modify: `results.tsv` (leave untracked)

**Step 1: Commit the candidate experiment**

Run: `git add train.py tests/test_train_helpers.py tests/test_train_summary.py tests/test_train_evaluation.py && git commit -m "<experiment message>"`
Expected: short hash available for the TSV row.

**Step 2: Run the proxy evaluation**

Run: `uv run train.py > run.log 2>&1`
Expected: score lines present within the timeout budget.

**Step 3: Parse proxy score and decide promotion**

If proxy improves versus the current kept best, run `uv run train.py --full > run_full.log 2>&1`.
If proxy does not improve, append a `discard` row and reset to the previous kept commit.

**Step 4: Parse full score and make keep/discard decision**

Keep when the promoted candidate lowers `score_bytes` on the chosen acceptance metric, otherwise discard and reset to the previous kept commit.

**Step 5: Handle crashes**

If score output is missing, inspect the log, fix only trivial issues, and rerun. If the idea is bad, append a `crash` row with zeroed missing scores and reset to the last kept commit.

### Task 5: Continue the autonomous loop safely

**Files:**
- Modify: `train.py`
- Modify: `results.tsv` (untracked)

**Step 1: Re-read `train.py` and prior results for the next idea**

Focus on simpler changes first: lower code size, better `zlib` settings, compact helper structure, or alternate compression wiring that keeps roundtrip correctness.

**Step 2: Repeat Task 3 and Task 4 indefinitely**

Stop only if the user interrupts or the environment prevents further progress.
