"""Prize resource envelope (http://prize.hutter1.net/hrules.htm): each stage
must run in under 70'000/T CPU-hours with at most 10 GB RAM and 100 GB temp
disk, where T is the machine's Geekbench5 single-core score. Single core,
no GPU. CPU seconds (not wall time) so laptop suspends don't corrupt timing."""

import tomllib
from pathlib import Path

RAM_LIMIT_BYTES = 10_000_000_000
FX2_SUBMISSION_GEEKBENCH_T = 1026

_FIXED_TIER_CPU_LIMIT_S = {"t0": 2 * 3600, "t1": 12 * 3600}


def load_geekbench_t(config_path: Path) -> float:
    with config_path.open("rb") as f:
        t = tomllib.load(f)["geekbench5_single_core"]
    if t <= 0:
        raise ValueError(
            "geekbench5_single_core unset in config.toml: measure Geekbench 5 "
            "single-core on this machine and fill it in (see config.toml.example)"
        )
    return float(t)


def cpu_budget_seconds(geekbench_t: float) -> float:
    return 70_000 / geekbench_t * 3600


def tier_cpu_limit_seconds(tier: str, geekbench_t: float) -> float:
    if tier in _FIXED_TIER_CPU_LIMIT_S:
        return _FIXED_TIER_CPU_LIMIT_S[tier]
    if tier == "t2":
        return cpu_budget_seconds(geekbench_t)
    raise ValueError(f"unknown tier: {tier}")


def projected_prize_hours(cpu_seconds: float, geekbench_t: float) -> float:
    return cpu_seconds / 3600 * geekbench_t / FX2_SUBMISSION_GEEKBENCH_T
