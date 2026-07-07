"""Tiered Hutter Prize benchmark for the vendored fx2-cmix at src/.

Two scoring paths (see docs/superpowers/specs, "Tiering reality"):

  t0, t1  codec proxy: `cmix_orig -c <prefix>` then `-d`, sha256 roundtrip.
          Exercises the cmix codec/model layer only (no wiki preprocessing);
          a directional proxy for codec-layer experiments, blind to the
          preprocessing/dictionary/article-order layer.
  t2      real pipeline: `cmix -e enwik9` produces self-extracting archive9,
          `./archive9` reproduces enwik9. Score = len(archive9), the official
          Hutter S.

Stages run under `systemd-run --user --scope -p MemoryMax=10G` (RAM cap,
SIGKILL on breach) with an RLIMIT_CPU cap (CPU seconds, immune to suspend).

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
    MachineConfig,
    load_machine_config,
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


def stage_argv(cmd: list[str], machine: MachineConfig) -> list[str]:
    argv: list[str] = []
    if machine.ram_enforcer == "systemd-run":
        argv += [
            "systemd-run",
            "--user",
            "--scope",
            "--quiet",
            "-p",
            f"MemoryMax={RAM_LIMIT_BYTES}",
            "-p",
            "MemorySwapMax=0",
            "--",
        ]
    # ram_enforcer = "external": the environment caps RAM (e.g. k8s pod limits).
    if machine.pin_cpu is not None:
        # Pin to a fixed core: config.toml's Geekbench T is a best-core number,
        # and on hybrid CPUs the scheduler otherwise drifts this single-threaded
        # load onto E-cores, inflating CPU seconds ~3x and making envelope math
        # inconsistent. (taskset, not AllowedCPUs: user scopes lack cpuset
        # delegation here.)
        argv += ["taskset", "-c", str(machine.pin_cpu)]
    return argv + cmd


def run_stage(
    cmd: list[str], cwd: Path, cpu_limit_s: float, log: Path, machine: MachineConfig
) -> Stage:
    argv = stage_argv(cmd, machine)

    def limits() -> None:
        lim = int(cpu_limit_s)
        resource.setrlimit(resource.RLIMIT_CPU, (lim, lim + 60))

    with log.open("ab") as lf:
        lf.write(f"\n=== {' '.join(cmd)} (cwd={cwd}) ===\n".encode())
        lf.flush()
        proc = subprocess.Popen(
            argv, cwd=cwd, stdout=lf, stderr=subprocess.STDOUT, preexec_fn=limits
        )
        _, status, ru = os.wait4(proc.pid, 0)
    rc = -os.WTERMSIG(status) if os.WIFSIGNALED(status) else os.WEXITSTATUS(status)
    return Stage(
        returncode=rc,
        cpu_seconds=ru.ru_utime + ru.ru_stime,
        peak_rss_bytes=ru.ru_maxrss * 1024,
    )


def build(src_dir: Path, log: Path, machine: MachineConfig) -> None:
    env_cmd: list[str] = []
    if not shutil.which("clang++-17"):
        env_cmd = ["nix", "develop", str(REPO), "--command"]
    env = os.environ.copy()
    if machine.march_override:
        # The devshell's clang++-17 wrapper rewrites -march=native to this
        # target; needed where LLVM 17 misdetects the host CPU (see
        # config.toml.example).
        env["AUTOCOMPRESS_MARCH"] = machine.march_override
    with log.open("ab") as lf:
        r = subprocess.run(
            [*env_cmd, "bash", "build_and_construct_comp.sh"],
            cwd=src_dir,
            stdout=lf,
            stderr=subprocess.STDOUT,
            env=env,
        )
    if r.returncode != 0:
        raise RuntimeError(f"build failed, see {log}")
    if not (src_dir / "run" / "cmix").exists():
        raise RuntimeError(f"build produced no run/cmix, see {log}")


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


@dataclass
class Result:
    status: str
    archive_bytes: int
    binary_bytes: int
    cpu_comp: float
    cpu_decomp: float
    peak_rss: int
    roundtrip_ok: bool
    score: int


def _codec_result(
    src_dir: Path,
    scratch: Path,
    tier_file: Path,
    cpu_limit: float,
    log: Path,
    machine: MachineConfig,
) -> Result:
    """t0/t1: score cmix_orig -c/-d on the raw prefix."""
    compressor = src_dir / "run" / "cmix_orig"
    if not compressor.exists():
        raise RuntimeError("build produced no run/cmix_orig")
    binary_bytes = compressor.stat().st_size
    shutil.copy2(compressor, scratch / "cmix_orig")

    comp = run_stage(
        ["./cmix_orig", "-c", str(tier_file), "out.comp"],
        scratch,
        cpu_limit,
        log,
        machine,
    )
    out = scratch / "out.comp"
    if comp.returncode != 0 or not out.exists():
        st = classify_failure(
            comp.returncode,
            comp.cpu_seconds,
            cpu_limit,
            comp.peak_rss_bytes,
            RAM_LIMIT_BYTES,
        )
        return Result(
            st if st != "ok" else "crash",
            0,
            binary_bytes,
            comp.cpu_seconds,
            0.0,
            comp.peak_rss_bytes,
            False,
            0,
        )

    archive_bytes = out.stat().st_size
    dec = run_stage(
        ["./cmix_orig", "-d", "out.comp", "restored"], scratch, cpu_limit, log, machine
    )
    peak = max(comp.peak_rss_bytes, dec.peak_rss_bytes)
    restored = scratch / "restored"
    if dec.returncode != 0 or not restored.exists():
        st = classify_failure(
            dec.returncode,
            dec.cpu_seconds,
            cpu_limit,
            dec.peak_rss_bytes,
            RAM_LIMIT_BYTES,
        )
        return Result(
            st if st != "ok" else "crash",
            archive_bytes,
            binary_bytes,
            comp.cpu_seconds,
            dec.cpu_seconds,
            peak,
            False,
            0,
        )

    ok = sha256(restored) == sha256(tier_file)
    if not ok:
        return Result(
            "roundtrip_fail",
            archive_bytes,
            binary_bytes,
            comp.cpu_seconds,
            dec.cpu_seconds,
            peak,
            False,
            0,
        )
    return Result(
        "ok",
        archive_bytes,
        binary_bytes,
        comp.cpu_seconds,
        dec.cpu_seconds,
        peak,
        True,
        archive_bytes + binary_bytes,
    )


def _selfextract_result(
    src_dir: Path,
    scratch: Path,
    tier_file: Path,
    cpu_limit: float,
    log: Path,
    machine: MachineConfig,
) -> Result:
    """t2: real -e pipeline. cmix (self-extracting) must be named 'cmix' in cwd;
    it writes archive9 to cwd; ./archive9 writes enwik9_restored to cwd."""
    compressor = src_dir / "run" / "cmix"
    binary_bytes = compressor.stat().st_size
    shutil.copy2(compressor, scratch / "cmix")

    comp = run_stage(
        ["./cmix", "-e", str(tier_file), "enwik9.comp"],
        scratch,
        cpu_limit,
        log,
        machine,
    )
    archive = scratch / "archive9"
    if comp.returncode != 0 or not archive.exists():
        st = classify_failure(
            comp.returncode,
            comp.cpu_seconds,
            cpu_limit,
            comp.peak_rss_bytes,
            RAM_LIMIT_BYTES,
        )
        return Result(
            st if st != "ok" else "crash",
            0,
            binary_bytes,
            comp.cpu_seconds,
            0.0,
            comp.peak_rss_bytes,
            False,
            0,
        )

    archive_bytes = archive.stat().st_size
    dec = run_stage(["./archive9"], scratch, cpu_limit, log, machine)
    peak = max(comp.peak_rss_bytes, dec.peak_rss_bytes)
    restored = scratch / "enwik9_restored"
    if dec.returncode != 0 or not restored.exists():
        st = classify_failure(
            dec.returncode,
            dec.cpu_seconds,
            cpu_limit,
            dec.peak_rss_bytes,
            RAM_LIMIT_BYTES,
        )
        return Result(
            st if st != "ok" else "crash",
            archive_bytes,
            binary_bytes,
            comp.cpu_seconds,
            dec.cpu_seconds,
            peak,
            False,
            0,
        )

    ok = sha256(restored) == sha256(tier_file)
    if not ok:
        return Result(
            "roundtrip_fail",
            archive_bytes,
            binary_bytes,
            comp.cpu_seconds,
            dec.cpu_seconds,
            peak,
            False,
            0,
        )
    # Self-extracting archive: comp == decomp, so the official S is just len(archive9).
    return Result(
        "ok",
        archive_bytes,
        binary_bytes,
        comp.cpu_seconds,
        dec.cpu_seconds,
        peak,
        True,
        archive_bytes,
    )


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--tier", choices=sorted(TIER_INPUT_BYTES), required=True)
    p.add_argument("--append-ledger", action="store_true")
    p.add_argument("--branch", default=None)
    p.add_argument("--ledger", default=str(REPO / "ledger.tsv"))
    p.add_argument("--config", default=str(REPO / "config.toml"))
    p.add_argument(
        "--src-dir", default=None, help="fx2-cmix dir (defaults to <cwd>/src)"
    )
    p.add_argument("--keep-artifacts", action="store_true")
    args = p.parse_args()

    src_dir = Path(args.src_dir) if args.src_dir else Path.cwd() / "src"
    config_path = Path(args.config)
    if not config_path.exists():
        sys.exit(
            f"{config_path} missing: copy config.toml.example to config.toml and "
            "fill in the measured Geekbench5 single-core score"
        )
    machine = load_machine_config(config_path)
    geekbench_t = machine.geekbench_t
    cpu_limit = tier_cpu_limit_seconds(args.tier, geekbench_t)
    tier_file = (
        CACHE / "enwik9" if args.tier == "t2" else CACHE / "tiers" / f"{args.tier}.bin"
    )
    if not tier_file.exists():
        sys.exit(f"{tier_file} missing: run prepare.py first")

    commit = git(["rev-parse", "HEAD"])
    branch = args.branch or git(["rev-parse", "--abbrev-ref", "HEAD"])
    description = git(["log", "-1", "--format=%s"])

    ledger_path = Path(args.ledger).resolve()
    run_dir = ledger_path.parent / "runs" / f"{commit[:7]}-{args.tier}"
    run_dir.mkdir(parents=True, exist_ok=True)
    log = run_dir / "run.log"

    scratch = CACHE / "scratch" / f"{commit[:7]}-{args.tier}"
    if scratch.exists():
        shutil.rmtree(scratch)
    scratch.mkdir(parents=True)

    try:
        build(src_dir, log, machine)
        run = _selfextract_result if args.tier == "t2" else _codec_result
        res = run(src_dir, scratch, tier_file, cpu_limit, log, machine)
    except RuntimeError as e:
        print(e, file=sys.stderr)
        res = Result("crash", 0, 0, 0.0, 0.0, 0, False, 0)
    finally:
        if not args.keep_artifacts:
            shutil.rmtree(scratch, ignore_errors=True)

    prize_hours = projected_prize_hours(max(res.cpu_comp, res.cpu_decomp), geekbench_t)
    out = render_output(
        tier=args.tier,
        status=res.status,
        score_bytes=res.score,
        archive_bytes=res.archive_bytes,
        binary_bytes=res.binary_bytes,
        cpu_seconds_comp=res.cpu_comp,
        cpu_seconds_decomp=res.cpu_decomp,
        peak_rss_bytes=res.peak_rss,
        projected_prize_hours=prize_hours,
        roundtrip_ok=res.roundtrip_ok,
    )
    print(out)
    (run_dir / "result.txt").write_text(out + "\n")

    if args.append_ledger:
        append_row(
            ledger_path,
            {
                "commit": commit,
                "branch": branch,
                "tier": args.tier,
                "status": res.status,
                "score_bytes": str(res.score),
                "archive_bytes": str(res.archive_bytes),
                "binary_bytes": str(res.binary_bytes),
                "cpu_seconds_comp": f"{res.cpu_comp:.2f}",
                "cpu_seconds_decomp": f"{res.cpu_decomp:.2f}",
                "peak_rss_bytes": str(res.peak_rss),
                "projected_prize_hours": f"{prize_hours:.2f}",
                "description": description,
            },
        )

    sys.exit(0 if res.status == "ok" else 1)


if __name__ == "__main__":
    main()
