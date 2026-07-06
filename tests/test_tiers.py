from pathlib import Path

from tiers import TIER_INPUT_BYTES, ensure_tiers


def test_tier_sizes():
    assert TIER_INPUT_BYTES == {
        "t0": 10_000_000,
        "t1": 100_000_000,
        "t2": 1_000_000_000,
    }


def test_ensure_tiers_writes_prefixes(tmp_path: Path):
    enwik9 = tmp_path / "enwik9"
    enwik9.write_bytes(bytes(range(256)) * 100)
    sizes = {"t0": 300, "t1": 5_000, "t2": enwik9.stat().st_size}
    paths = ensure_tiers(enwik9, tmp_path / "tiers", sizes)
    assert paths["t2"] == enwik9
    assert paths["t0"].read_bytes() == enwik9.read_bytes()[:300]
    assert paths["t1"].read_bytes() == enwik9.read_bytes()[:5_000]


def test_ensure_tiers_is_idempotent(tmp_path: Path):
    enwik9 = tmp_path / "enwik9"
    enwik9.write_bytes(b"x" * 1000)
    sizes = {"t0": 100, "t2": 1000}
    first = ensure_tiers(enwik9, tmp_path / "tiers", sizes)
    mtime = first["t0"].stat().st_mtime_ns
    second = ensure_tiers(enwik9, tmp_path / "tiers", sizes)
    assert second["t0"].stat().st_mtime_ns == mtime
