import argparse
import bz2
import os
import zlib
from pathlib import Path


_BZ2_THRESHOLD_BYTES = 1_000_000


def compress_payload(data):
    return (
        bz2.compress(data, compresslevel=9)
        if len(data) >= _BZ2_THRESHOLD_BYTES
        else zlib.compress(data, level=9)
    )


def restore_payload(data):
    return bz2.decompress(data) if data[:3] == b"BZh" else zlib.decompress(data)


def compute_score_bytes(archive_bytes, code_bytes):
    if isinstance(archive_bytes, bool) or isinstance(code_bytes, bool):
        raise TypeError("ints only")
    if not isinstance(archive_bytes, int) or not isinstance(code_bytes, int):
        raise TypeError("ints only")
    return archive_bytes + code_bytes


def is_roundtrip_equal(original, restored):
    return original == restored


def baseline_is_configured():
    return bool(os.environ.get("FX2_CMIX_BIN"))


def _get_cache_dir(cache_dir):
    base = cache_dir or os.path.join(os.path.expanduser("~"), ".cache", "autoresearch")
    return Path(base).expanduser()


def _validate_mode(mode):
    if mode not in {"proxy", "full"}:
        raise ValueError(mode)
    return mode


def _mode_inputs(mode, cache_dir):
    mode = _validate_mode(mode)
    if mode == "proxy":
        base = cache_dir / "proxy_slices"
        for suffix in ("head.bin", "mid.bin", "tail.bin"):
            yield base / suffix
    else:
        yield cache_dir / "enwik9"


def run_evaluation(mode, cache_dir):
    mode = _validate_mode(mode)
    cache_path = _get_cache_dir(cache_dir)
    archive_bytes = 0
    roundtrip_ok = True
    for path in _mode_inputs(mode, cache_path):
        data = path.read_bytes()
        compressed = compress_payload(data)
        decompressed = restore_payload(compressed)
        roundtrip_ok = roundtrip_ok and is_roundtrip_equal(data, decompressed)
        archive_bytes += len(compressed)
    return archive_bytes, roundtrip_ok


def get_code_bytes() -> int:
    return os.path.getsize(__file__)


def format_summary(mode, archive_bytes, code_bytes, score_bytes, roundtrip_ok):
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


def main():
    parser = argparse.ArgumentParser(description="train harness")
    parser.add_argument(
        "--full",
        action="store_true",
        help="use full data",
    )
    parser.add_argument(
        "--cache-dir",
        type=str,
        default=None,
        help="cache dir",
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
