"""Prize resource envelope (http://prize.hutter1.net/hrules.htm): each stage
must run in under 70'000/T CPU-hours with at most 10 GB RAM and 100 GB temp
disk, where T is the machine's Geekbench5 single-core score. Single core,
no GPU. CPU seconds (not wall time) so laptop suspends don't corrupt timing."""

import tomllib
from dataclasses import dataclass
from pathlib import Path

RAM_LIMIT_BYTES = 10_000_000_000
FX2_SUBMISSION_GEEKBENCH_T = 1026

_FIXED_TIER_CPU_LIMIT_S = {"t0": 2 * 3600, "t1": 12 * 3600}

_RAM_ENFORCERS = ("systemd-run", "external")


@dataclass(frozen=True)
class MachineConfig:
    geekbench_t: float
    pin_cpu: int | None
    ram_enforcer: str
    march_override: str | None


def load_machine_config(config_path: Path) -> MachineConfig:
    with config_path.open("rb") as f:
        raw = tomllib.load(f)
    t = raw["geekbench5_single_core"]
    if t <= 0:
        raise ValueError(
            "geekbench5_single_core unset in config.toml: measure Geekbench 5 "
            "single-core on this machine and fill it in (see config.toml.example)"
        )
    enforcer = raw.get("ram_enforcer", "systemd-run")
    if enforcer not in _RAM_ENFORCERS:
        raise ValueError(f"ram_enforcer must be one of {_RAM_ENFORCERS}: {enforcer}")
    pin = raw.get("pin_cpu")
    return MachineConfig(
        geekbench_t=float(t),
        pin_cpu=int(pin) if pin is not None else None,
        ram_enforcer=enforcer,
        march_override=raw.get("march_override"),
    )


def load_geekbench_t(config_path: Path) -> float:
    return load_machine_config(config_path).geekbench_t


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
