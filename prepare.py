"""
One-time data preparation for the autocompress experiment loop.
Downloads enwik9 and creates deterministic proxy slices for fast benchmarking.

Usage:
    uv run prepare.py

Data is cached in ~/.cache/autoresearch/. Safe to re-run — skips work already done.
"""

import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

from prepare_helpers import expected_enwik9_size_bytes, proxy_offsets

CACHE_DIR = Path.home() / ".cache" / "autoresearch"
ENWIK9_URL = "https://mattmahoney.net/dc/enwik9.zip"
PROXY_SLICE_SIZE = 32 * 1024 * 1024  # 32 MB per slice


def verify_enwik9_size(path: Path) -> bool:
    return path.exists() and path.stat().st_size == expected_enwik9_size_bytes()


def _download_enwik9_zip(zip_path: Path) -> None:
    print(f"Downloading enwik9 from {ENWIK9_URL} ...")
    tmp = zip_path.with_suffix(".tmp")
    with urllib.request.urlopen(ENWIK9_URL) as r, tmp.open("wb") as f:
        shutil.copyfileobj(r, f)
    tmp.replace(zip_path)


def _extract_enwik9(zip_path: Path, dest: Path) -> None:
    print(f"Extracting enwik9 ...")
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(dest)


def _ensure_enwik9(cache_dir: Path) -> Path:
    enwik9 = cache_dir / "enwik9"
    zip_path = cache_dir / "enwik9.zip"

    if verify_enwik9_size(enwik9):
        print(f"enwik9 already present at {enwik9}")
        return enwik9

    for attempt in range(1, 3):
        if not zip_path.exists():
            try:
                _download_enwik9_zip(zip_path)
            except Exception as e:
                zip_path.unlink(missing_ok=True)
                if attempt == 2:
                    raise RuntimeError("enwik9 download failed after 2 attempts") from e
                continue

        enwik9.unlink(missing_ok=True)
        try:
            _extract_enwik9(zip_path, cache_dir)
        except (zipfile.BadZipFile, OSError) as e:
            zip_path.unlink(missing_ok=True)
            enwik9.unlink(missing_ok=True)
            if attempt == 2:
                raise RuntimeError("enwik9 extraction failed after 2 attempts") from e
            continue

        if verify_enwik9_size(enwik9):
            return enwik9

        zip_path.unlink(missing_ok=True)
        enwik9.unlink(missing_ok=True)
        if attempt == 2:
            raise RuntimeError("enwik9 size verification failed after 2 attempts")

    raise RuntimeError("unreachable")


def create_proxy_slices(enwik9_path: Path, proxy_dir: Path, slice_size: int = PROXY_SLICE_SIZE) -> list[Path]:
    """Write head/mid/tail slices of enwik9 for fast proxy benchmarking."""
    proxy_dir.mkdir(parents=True, exist_ok=True)
    total = enwik9_path.stat().st_size
    starts = proxy_offsets(total_size=total, slice_size=slice_size)
    outputs = []
    with enwik9_path.open("rb") as src:
        for name, start in zip(["head", "mid", "tail"], starts):
            out = proxy_dir / f"{name}.bin"
            src.seek(start)
            out.write_bytes(src.read(slice_size))
            outputs.append(out)
    return outputs


def main() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    enwik9 = _ensure_enwik9(CACHE_DIR)

    if not verify_enwik9_size(enwik9):
        print(f"ERROR: enwik9 verification failed", file=sys.stderr)
        sys.exit(1)

    proxy_dir = CACHE_DIR / "proxy_slices"
    outputs = create_proxy_slices(enwik9, proxy_dir)
    print("Proxy slices ready:", ", ".join(str(p) for p in outputs))


if __name__ == "__main__":
    main()
