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
            Job(
                branch=branch,
                commit=sha,
                tier=parse_tier(trailer),
                committed_at=int(ts),
            )
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
