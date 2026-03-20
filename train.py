"""Minimal train harness placeholder for autoresearch evaluation."""

import argparse
import os
import zlib
from pathlib import Path
from typing import Iterable, Optional, Tuple


def compute_score_bytes(archive_bytes: int, code_bytes: int) -> int:
    """Score is total bytes needed to reproduce the solution."""
    if isinstance(archive_bytes, bool) or isinstance(code_bytes, bool):
        raise TypeError("compute_score_bytes requires integers")

    if not isinstance(archive_bytes, int) or not isinstance(code_bytes, int):
        raise TypeError("compute_score_bytes requires integers")

    return archive_bytes + code_bytes


def is_roundtrip_equal(original: bytes, restored: bytes) -> bool:
    """Roundtrip helper; compares original and restored candidates."""
    return original == restored


def baseline_is_configured() -> bool:
    """Detect optional fx2-cmix baseline via FX2_CMIX_BIN."""
    return bool(os.environ.get("FX2_CMIX_BIN"))


def _get_cache_dir(cache_dir: Optional[str]) -> Path:
    base = cache_dir or os.path.join(os.path.expanduser("~"), ".cache", "autoresearch")
    return Path(base).expanduser()


_VALID_MODES = ("proxy", "full")


def _validate_mode(mode: str) -> str:
    if mode not in _VALID_MODES:
        raise ValueError(f"unsupported mode {mode!r}; expected one of {_VALID_MODES}")
    return mode


def _mode_inputs(mode: str, cache_dir: Path) -> Iterable[Path]:
    mode = _validate_mode(mode)
    if mode == "proxy":
        base = cache_dir / "proxy_slices"
        for suffix in ("head.bin", "mid.bin", "tail.bin"):
            yield base / suffix
    else:
        yield cache_dir / "enwik9"


def _read_file(path: Path) -> bytes:
    with path.open("rb") as fh:
        return fh.read()


def run_evaluation(mode: str, cache_dir: Optional[str]) -> Tuple[int, bool]:
    """Run the compression/decompression loop and tally archive bytes."""
    mode = _validate_mode(mode)
    cache_path = _get_cache_dir(cache_dir)
    archive_bytes = 0
    roundtrip_ok = True
    for path in _mode_inputs(mode, cache_path):
        data = _read_file(path)
        compressed = zlib.compress(data)
        decompressed = zlib.decompress(compressed)
        roundtrip_ok = roundtrip_ok and is_roundtrip_equal(data, decompressed)
        archive_bytes += len(compressed)
    return archive_bytes, roundtrip_ok


def get_code_bytes() -> int:
    return os.path.getsize(__file__)


def format_summary(
    mode: str, archive_bytes: int, code_bytes: int, score_bytes: int, roundtrip_ok: bool
) -> str:
    """Render a stable field summary for CLI reporting."""
    mode = _validate_mode(mode)
    score_key = "proxy_score_bytes" if mode == "proxy" else "full_score_bytes"
    roundtrip_flag = "true" if roundtrip_ok else "false"
    return "\n".join(
        [
            f"{score_key}: {score_bytes}",
            f"archive_bytes: {archive_bytes}",
            f"code_bytes: {code_bytes}",
            f"roundtrip_ok: {roundtrip_flag}",
        ]
    )


def main() -> None:
    """CLI entry point with a minimal compression evaluation."""
    parser = argparse.ArgumentParser(description="Autoresearch train harness")
    parser.add_argument(
        "--full",
        action="store_true",
        help="Emit the full score key instead of the proxy score key",
    )
    parser.add_argument(
        "--cache-dir",
        type=str,
        default=None,
        help="Override the cache directory for input slices",
    )
    args = parser.parse_args()
    mode = "full" if args.full else "proxy"
    archive_bytes, roundtrip_ok = run_evaluation(mode, args.cache_dir)
    code_bytes = get_code_bytes()
    score_bytes = compute_score_bytes(archive_bytes, code_bytes)

    print(
        format_summary(
            mode=mode,
            archive_bytes=archive_bytes,
            code_bytes=code_bytes,
            score_bytes=score_bytes,
            roundtrip_ok=roundtrip_ok,
        )
    )


if __name__ == "__main__":
    main()
