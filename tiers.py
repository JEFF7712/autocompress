"""Tier inputs are prefixes of enwik9. t1 equals enwik8 byte-for-byte;
enwik9 itself ends mid-article, so truncation is in-distribution for the
fx2-cmix transform."""

from pathlib import Path

TIER_INPUT_BYTES = {
    "t0": 10_000_000,
    "t1": 100_000_000,
    "t2": 1_000_000_000,
}

_CHUNK = 1 << 22


def _write_prefix(src: Path, dest: Path, size: int) -> None:
    tmp = dest.with_suffix(".tmp")
    remaining = size
    with src.open("rb") as fin, tmp.open("wb") as fout:
        while remaining > 0:
            chunk = fin.read(min(_CHUNK, remaining))
            if not chunk:
                raise ValueError(f"{src} shorter than requested prefix {size}")
            fout.write(chunk)
            remaining -= len(chunk)
    tmp.replace(dest)


def ensure_tiers(
    enwik9: Path, tier_dir: Path, sizes: dict[str, int] = TIER_INPUT_BYTES
) -> dict[str, Path]:
    tier_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for tier, size in sizes.items():
        if size == enwik9.stat().st_size:
            paths[tier] = enwik9
            continue
        dest = tier_dir / f"{tier}.bin"
        if not (dest.exists() and dest.stat().st_size == size):
            _write_prefix(enwik9, dest, size)
        paths[tier] = dest
    return paths
