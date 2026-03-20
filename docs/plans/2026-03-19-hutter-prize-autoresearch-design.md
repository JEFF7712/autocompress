# Hutter Prize Autoresearch (Minimal-Diff) Design

Date: 2026-03-19
Status: Approved

## Goal

Reuse the existing autoresearch workflow with minimal changes, but switch the research target from short GPU language-model training to Hutter Prize style lossless compression work on `enwik9`.

The loop stays autonomous and simple:

1. baseline first,
2. propose one change,
3. run benchmark,
4. keep or discard by metric.

## Scope and Constraints

- Keep architecture and workflow shape similar to the original project.
- Keep control surface small: fixed prep/eval harness + one mutable candidate file.
- Optimize for speed using proxy-first evaluation.
- Align score with contest intent: lower total size is better.
- Use winner code only as read-only baseline in v1.

## Recommended Approach

Use a two-stage benchmark loop:

- Stage A (default): deterministic proxy slices for fast iteration.
- Stage B (promotion): full `enwik9` run for candidates that improve proxy score.

This preserves the fast autonomous loop while still grounding decisions in full-task performance.

## Minimal File Changes

### `prepare.py` (fixed harness)

Replace tokenizer/data-shard preparation with dataset preparation for compression:

- ensure cache location exists (`~/.cache/autoresearch/`),
- fetch `enwik9.zip` if missing,
- extract `enwik9`,
- verify exact size is `1_000_000_000` bytes,
- generate deterministic proxy files in `~/.cache/autoresearch/proxy/` (head/middle/tail slices).

No model or tokenizer logic remains.

### `train.py` (mutable candidate + fixed evaluator)

Convert to single-run compression evaluation:

- candidate block at top: algorithm knobs/implementation the agent can change,
- fixed harness below:
  - compress,
  - decompress,
  - byte-equality roundtrip check,
  - score computation and reporting.

Metrics printed in grep-friendly format:

- `proxy_score_bytes:`
- `full_score_bytes:`
- `archive_bytes:`
- `code_bytes:`
- `roundtrip_ok:`

Primary metric is lower-is-better size score.

### `program.md`

Keep instructions in same style as current autoresearch loop, but replace optimization target:

- old target: `val_bpb`,
- new target: `score_bytes`.

Decision policy:

- baseline first,
- run proxy each experiment,
- run full when proxy improves,
- keep commit only on accepted improvement.

### `results.tsv`

Simple tab-separated tracking file (untracked):

`commit	proxy_score	full_score	status	description`

## Baseline Integration (v1)

Integrate `fx2-cmix` as a read-only external baseline:

- no autonomous edits to `fx2-cmix`,
- one wrapper command for compress and one for decompress,
- path configured by env var (for example `FX2_CMIX_BIN`),
- report baseline scores and candidate delta in logs.

This provides reality checks without adding codebase complexity.

## Keep/Discard and Reliability Rules

- Any roundtrip mismatch is an immediate failed run.
- Any timeout is a failed run.
- Proxy improvement is required to promote to full run.
- Full improvement is required for final keep (or marked provisional until full run completes).
- Output format stays stable and parseable to support autonomous looping.

## Commands (Shape Only)

- Setup once: `uv run prepare.py`
- Proxy experiment: `uv run train.py > run.log 2>&1`
- Parse summary: grep key metric lines from `run.log`
- Promotion/full: `uv run train.py --full > run.log 2>&1`

## Non-Goals for v1

- No scheduler, service, or database.
- No direct mutation of large winner codebases.
- No broad framework or language migration.

## Rollout Sequence

1. implement minimal-diff harness,
2. validate baseline/proxy/full reproducibility,
3. run autonomous loop,
4. only then consider phase-2 edits on a winner codebase.
