"""
Fixed evaluation harness for the autoresearch compression loop.
Compiles compress.cpp, runs it on benchmark files, verifies roundtrip, reports score.

DO NOT MODIFY — agent edits compress.cpp only.

Usage:
    uv run train.py              # proxy run (3x32MB slices, fast)
    uv run train.py --full       # full enwik9 run (1 GB, slow)
    uv run train.py --cache-dir /path/to/cache
"""

import argparse
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

SRC = pathlib.Path(__file__).parent / "compress.cpp"
BIN = pathlib.Path(__file__).parent / "compress"
FLAKE = pathlib.Path(__file__).parent / "flake.nix"


def compile_compressor() -> None:
    """Compile compress.cpp. Uses nix develop transparently if g++ is not on PATH."""
    cxx = os.environ.get("CXX", "g++")

    if shutil.which(cxx):
        # g++ is on PATH (inside nix develop, or on a non-NixOS system)
        _compile_direct(cxx)
    elif FLAKE.exists() and shutil.which("nix"):
        # Not in nix dev env but flake.nix is here — compile via nix develop.
        # The shell sets NIX_LDFLAGS with -rpath so the binary works outside the shell too.
        _compile_via_nix()
    else:
        sys.stderr.write(
            "g++ not found. Enter the dev environment first:\n"
            "  nix develop      (NixOS/nix)\n"
            "  nix-shell        (legacy)\n"
            "Or set CXX=/path/to/g++ and ensure liblzma is available.\n"
        )
        sys.exit(1)


def _compile_direct(cxx: str) -> None:
    flags: list[str] = []
    try:
        r = subprocess.run(["pkg-config", "--cflags", "--libs", "liblzma"],
                           capture_output=True, text=True)
        if r.returncode == 0:
            flags = r.stdout.split()
    except FileNotFoundError:
        flags = ["-llzma"]

    cmd = [cxx, "-O3", "-std=c++17", "-march=native", "-o", str(BIN), str(SRC)] + flags
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(f"compile error:\n{r.stderr}\n")
        sys.exit(1)


def _compile_via_nix() -> None:
    # Use bash -c inside nix develop so pkg-config resolves the right lzma flags.
    # nix sets NIX_LDFLAGS (rpath) so the compiled binary runs outside the shell.
    compile_cmd = (
        f'g++ -O3 -std=c++17 -march=native -o "{BIN}" "{SRC}" '
        f'$(pkg-config --cflags --libs liblzma)'
    )
    r = subprocess.run(
        ["nix", "develop", str(FLAKE.parent), "--command", "bash", "-c", compile_cmd],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        sys.stderr.write(f"nix develop compile error:\n{r.stderr}\n")
        sys.exit(1)


def compress_file(src: pathlib.Path, tmp: str) -> pathlib.Path:
    out = pathlib.Path(tmp) / (src.name + ".c")
    r = subprocess.run([str(BIN), "c", str(src), str(out)], capture_output=True)
    if r.returncode != 0:
        sys.stderr.write(r.stderr.decode(errors="replace"))
        raise RuntimeError(f"compress failed: {src}")
    return out


def decompress_file(src: pathlib.Path, tmp: str) -> pathlib.Path:
    out = pathlib.Path(tmp) / (src.name + ".d")
    r = subprocess.run([str(BIN), "d", str(src), str(out)], capture_output=True)
    if r.returncode != 0:
        sys.stderr.write(r.stderr.decode(errors="replace"))
        raise RuntimeError(f"decompress failed: {src}")
    return out


def evaluate(files: list[pathlib.Path]) -> tuple[int, bool]:
    """Compress each file, decompress, verify. Returns (total_archive_bytes, all_ok)."""
    total = 0
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        for src in files:
            compressed = compress_file(src, tmp)
            total += compressed.stat().st_size
            restored = decompress_file(compressed, tmp)
            if restored.read_bytes() != src.read_bytes():
                ok = False
    return total, ok


def main() -> None:
    p = argparse.ArgumentParser(description="Run compression benchmark")
    p.add_argument("--full", action="store_true", help="run on full enwik9 (1 GB)")
    p.add_argument("--cache-dir", default=None)
    args = p.parse_args()

    cache = pathlib.Path(args.cache_dir) if args.cache_dir else pathlib.Path.home() / ".cache" / "autoresearch"

    if args.full:
        enwik9 = cache / "enwik9"
        if not enwik9.exists():
            sys.stderr.write(f"enwik9 not found at {enwik9} — run prepare.py first\n")
            sys.exit(1)
        files = [enwik9]
        mode = "full"
    else:
        slices = [cache / "proxy_slices" / s for s in ("head.bin", "mid.bin", "tail.bin")]
        missing = [s for s in slices if not s.exists()]
        if missing:
            sys.stderr.write(f"proxy slices missing: {missing} — run prepare.py first\n")
            sys.exit(1)
        files = slices
        mode = "proxy"

    compile_compressor()

    archive_bytes, roundtrip_ok = evaluate(files)

    if not roundtrip_ok:
        sys.stderr.write("ROUNDTRIP MISMATCH — decompressed output does not match input!\n")
        sys.exit(1)

    score_key = "proxy_score_bytes" if mode == "proxy" else "full_score_bytes"
    print(f"{score_key}: {archive_bytes}")
    print(f"archive_bytes: {archive_bytes}")
    print(f"roundtrip_ok: true")


if __name__ == "__main__":
    main()
