"""One-time data preparation: download enwik9, derive tier prefixes.

Usage:
    uv run prepare.py

Data is cached in ~/.cache/autoresearch/. Safe to re-run.
"""

import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

from tiers import ensure_tiers

CACHE_DIR = Path.home() / ".cache" / "autoresearch"
ENWIK9_URL = "https://mattmahoney.net/dc/enwik9.zip"
ENWIK9_SIZE = 1_000_000_000


def verify_enwik9_size(path: Path) -> bool:
    return path.exists() and path.stat().st_size == ENWIK9_SIZE


def _download_enwik9_zip(zip_path: Path) -> None:
    print(f"Downloading enwik9 from {ENWIK9_URL} ...")
    tmp = zip_path.with_suffix(".tmp")
    with urllib.request.urlopen(ENWIK9_URL) as r, tmp.open("wb") as f:
        shutil.copyfileobj(r, f)
    tmp.replace(zip_path)


def _extract_enwik9(zip_path: Path, dest: Path) -> None:
    print("Extracting enwik9 ...")
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


def main() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    enwik9 = _ensure_enwik9(CACHE_DIR)
    if not verify_enwik9_size(enwik9):
        print("ERROR: enwik9 verification failed", file=sys.stderr)
        sys.exit(1)
    paths = ensure_tiers(enwik9, CACHE_DIR / "tiers")
    for tier, p in sorted(paths.items()):
        print(f"{tier}: {p} ({p.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
