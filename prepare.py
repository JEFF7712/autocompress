"""
One-time data preparation for autoresearch experiments.
Downloads the enwik9 archive and creates deterministic proxy slices.

Usage:
    python prepare.py  # download enwik9 and emit proxy slices

Data and proxy slices are stored in ~/.cache/autoresearch/.
"""

import os
import sys
import time
import math
import pickle
import shutil
import urllib.request
import zipfile
from multiprocessing import Pool
from pathlib import Path

try:
    import requests
except ImportError as exc:
    requests = None
    _requests_import_error = exc

try:
    import pyarrow.parquet as pq
except ImportError as exc:
    pq = None
    _pyarrow_import_error = exc
try:
    import rustbpe
except ImportError as exc:
    rustbpe = None
    _rustbpe_import_error = exc
try:
    import tiktoken
except ImportError as exc:
    tiktoken = None
    _tiktoken_import_error = exc

from prepare_helpers import expected_enwik9_size_bytes, proxy_offsets

try:
    import torch
except ImportError as exc:
    torch = None
    _torch_import_error = exc


def _require_pq_module():
    if pq is None:
        raise RuntimeError(
            "pyarrow.parquet is required but failed to import"
        ) from _pyarrow_import_error
    return pq


def _require_requests_module():
    if requests is None:
        raise RuntimeError(
            "requests is required for downloading data but is not installed"
        ) from _requests_import_error
    return requests


def _require_rustbpe_module():
    if rustbpe is None:
        raise RuntimeError(
            "rustbpe is required to train the tokenizer but is not installed"
        ) from _rustbpe_import_error
    return rustbpe


def _require_tiktoken_module():
    if tiktoken is None:
        raise RuntimeError(
            "tiktoken is required to build the tokenizer encoding but is not installed"
        ) from _tiktoken_import_error
    return tiktoken


def create_proxy_slices(
    enwik9_path: Path, proxy_dir: Path, slice_size: int = 32 * 1024 * 1024
) -> list[Path]:
    """Create deterministic proxy slices (head, mid, tail) from enwik9."""

    if not enwik9_path.exists():
        raise FileNotFoundError(f"enwik9 source not found: {enwik9_path}")
    if slice_size <= 0:
        raise ValueError("slice_size must be positive")

    total_size = enwik9_path.stat().st_size
    outputs: list[Path] = []
    names = ["head", "mid", "tail"]
    starts = proxy_offsets(total_size=total_size, slice_size=slice_size)

    if len(starts) != len(names):
        raise ValueError(
            "proxy_offsets must return exactly three start positions for head/mid/tail"
        )

    proxy_dir.mkdir(parents=True, exist_ok=True)
    with enwik9_path.open("rb") as source:
        for name, start in zip(names, starts):
            out_path = proxy_dir / f"{name}.bin"
            source.seek(start)
            chunk = source.read(slice_size)
            if len(chunk) != slice_size:
                raise ValueError(
                    f"requested slice_size {slice_size} unreadable at {name}"
                )
            out_path.write_bytes(chunk)
            outputs.append(out_path)
    return outputs


# ---------------------------------------------------------------------------
# Constants (fixed, do not modify)
# ---------------------------------------------------------------------------

MAX_SEQ_LEN = 2048  # context length
TIME_BUDGET = 300  # training time budget in seconds (5 minutes)
EVAL_TOKENS = 40 * 524288  # number of tokens for val eval

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CACHE_DIR = os.path.join(os.path.expanduser("~"), ".cache", "autoresearch")
DATA_DIR = os.path.join(CACHE_DIR, "data")
TOKENIZER_DIR = os.path.join(CACHE_DIR, "tokenizer")
BASE_URL = "https://huggingface.co/datasets/karpathy/climbmix-400b-shuffle/resolve/main"
MAX_SHARD = 6542  # the last datashard is shard_06542.parquet
VAL_SHARD = MAX_SHARD  # pinned validation shard (shard_06542)
VAL_FILENAME = f"shard_{VAL_SHARD:05d}.parquet"
VOCAB_SIZE = 8192
ENWIK9_URL = "https://mattmahoney.net/dc/enwik9.zip"
ENWIK9_ZIP_NAME = "enwik9.zip"
ENWIK9_FILENAME = "enwik9"
PROXY_DIR_NAME = "proxy_slices"
ENWIK9_DOWNLOAD_MAX_ATTEMPTS = 2

# BPE split pattern (GPT-4 style, with \p{N}{1,2} instead of {1,3})
SPLIT_PATTERN = r"""'(?i:[sdmt]|ll|ve|re)|[^\r\n\p{L}\p{N}]?+\p{L}+|\p{N}{1,2}| ?[^\s\p{L}\p{N}]++[\r\n]*|\s*[\r\n]|\s+(?!\S)|\s+"""

SPECIAL_TOKENS = [f"<|reserved_{i}|>" for i in range(4)]
BOS_TOKEN = "<|reserved_0|>"

# ---------------------------------------------------------------------------
# Data download
# ---------------------------------------------------------------------------


def download_single_shard(index):
    """Download one parquet shard with retries. Returns True on success."""
    filename = f"shard_{index:05d}.parquet"
    filepath = os.path.join(DATA_DIR, filename)
    if os.path.exists(filepath):
        return True

    url = f"{BASE_URL}/{filename}"
    max_attempts = 5
    for attempt in range(1, max_attempts + 1):
        try:
            requests_module = _require_requests_module()
            response = requests_module.get(url, stream=True, timeout=30)
            response.raise_for_status()
            temp_path = filepath + ".tmp"
            with open(temp_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        f.write(chunk)
            os.rename(temp_path, filepath)
            print(f"  Downloaded {filename}")
            return True
        except (_require_requests_module().RequestException, IOError) as e:
            print(f"  Attempt {attempt}/{max_attempts} failed for {filename}: {e}")
            for path in [filepath + ".tmp", filepath]:
                if os.path.exists(path):
                    try:
                        os.remove(path)
                    except OSError:
                        pass
            if attempt < max_attempts:
                time.sleep(2**attempt)
    return False


def download_data(num_shards, download_workers=8):
    """Download training shards + pinned validation shard."""
    os.makedirs(DATA_DIR, exist_ok=True)
    num_train = min(num_shards, MAX_SHARD)
    ids = list(range(num_train))
    if VAL_SHARD not in ids:
        ids.append(VAL_SHARD)

    # Count what's already downloaded
    existing = sum(
        1
        for i in ids
        if os.path.exists(os.path.join(DATA_DIR, f"shard_{i:05d}.parquet"))
    )
    if existing == len(ids):
        print(f"Data: all {len(ids)} shards already downloaded at {DATA_DIR}")
        return

    needed = len(ids) - existing
    print(f"Data: downloading {needed} shards ({existing} already exist)...")

    workers = max(1, min(download_workers, needed))
    with Pool(processes=workers) as pool:
        results = pool.map(download_single_shard, ids)

    ok = sum(1 for r in results if r)
    print(f"Data: {ok}/{len(ids)} shards ready at {DATA_DIR}")


# ---------------------------------------------------------------------------
# Tokenizer training
# ---------------------------------------------------------------------------


def list_parquet_files():
    """Return sorted list of parquet file paths in the data directory."""
    files = sorted(
        f
        for f in os.listdir(DATA_DIR)
        if f.endswith(".parquet") and not f.endswith(".tmp")
    )
    return [os.path.join(DATA_DIR, f) for f in files]


def text_iterator(max_chars=1_000_000_000, doc_cap=10_000):
    """Yield documents from training split (all shards except pinned val shard)."""
    parquet_paths = [p for p in list_parquet_files() if not p.endswith(VAL_FILENAME)]
    nchars = 0
    for filepath in parquet_paths:
        pf = _require_pq_module().ParquetFile(filepath)
        for rg_idx in range(pf.num_row_groups):
            rg = pf.read_row_group(rg_idx)
            for text in rg.column("text").to_pylist():
                doc = text[:doc_cap] if len(text) > doc_cap else text
                nchars += len(doc)
                yield doc
                if nchars >= max_chars:
                    return


def train_tokenizer():
    """Train BPE tokenizer using rustbpe, save as tiktoken pickle."""
    tokenizer_pkl = os.path.join(TOKENIZER_DIR, "tokenizer.pkl")
    token_bytes_path = os.path.join(TOKENIZER_DIR, "token_bytes.pt")

    if os.path.exists(tokenizer_pkl) and os.path.exists(token_bytes_path):
        print(f"Tokenizer: already trained at {TOKENIZER_DIR}")
        return

    os.makedirs(TOKENIZER_DIR, exist_ok=True)

    parquet_files = list_parquet_files()
    if len(parquet_files) < 2:
        print(
            "Tokenizer: need at least 2 data shards (1 train + 1 val). Download more data first."
        )
        sys.exit(1)

    # --- Train with rustbpe ---
    print("Tokenizer: training BPE tokenizer...")
    t0 = time.time()

    tokenizer = _require_rustbpe_module().Tokenizer()
    vocab_size_no_special = VOCAB_SIZE - len(SPECIAL_TOKENS)
    tokenizer.train_from_iterator(
        text_iterator(), vocab_size_no_special, pattern=SPLIT_PATTERN
    )

    # Build tiktoken encoding from trained merges
    pattern = tokenizer.get_pattern()
    mergeable_ranks = {bytes(k): v for k, v in tokenizer.get_mergeable_ranks()}
    tokens_offset = len(mergeable_ranks)
    special_tokens = {name: tokens_offset + i for i, name in enumerate(SPECIAL_TOKENS)}
    enc = _require_tiktoken_module().Encoding(
        name="rustbpe",
        pat_str=pattern,
        mergeable_ranks=mergeable_ranks,
        special_tokens=special_tokens,
    )

    # Save tokenizer
    with open(tokenizer_pkl, "wb") as f:
        pickle.dump(enc, f)

    t1 = time.time()
    print(f"Tokenizer: trained in {t1 - t0:.1f}s, saved to {tokenizer_pkl}")

    # --- Build token_bytes lookup for BPB evaluation ---
    print("Tokenizer: building token_bytes lookup...")
    special_set = set(SPECIAL_TOKENS)
    token_bytes_list = []
    for token_id in range(enc.n_vocab):
        token_str = enc.decode([token_id])
        if token_str in special_set:
            token_bytes_list.append(0)
        else:
            token_bytes_list.append(len(token_str.encode("utf-8")))
    token_bytes_tensor = torch.tensor(token_bytes_list, dtype=torch.int32)
    torch.save(token_bytes_tensor, token_bytes_path)
    print(f"Tokenizer: saved token_bytes to {token_bytes_path}")

    # Sanity check
    test = "Hello world! Numbers: 123. Unicode: 你好"
    encoded = enc.encode_ordinary(test)
    decoded = enc.decode(encoded)
    assert decoded == test, f"Tokenizer roundtrip failed: {test!r} -> {decoded!r}"
    print(f"Tokenizer: sanity check passed (vocab_size={enc.n_vocab})")


# ---------------------------------------------------------------------------
# Runtime utilities (imported by train.py)
# ---------------------------------------------------------------------------


class Tokenizer:
    """Minimal tokenizer wrapper. Training is handled above."""

    def __init__(self, enc):
        self.enc = enc
        self.bos_token_id = enc.encode_single_token(BOS_TOKEN)

    @classmethod
    def from_directory(cls, tokenizer_dir=TOKENIZER_DIR):
        with open(os.path.join(tokenizer_dir, "tokenizer.pkl"), "rb") as f:
            enc = pickle.load(f)
        return cls(enc)

    def get_vocab_size(self):
        return self.enc.n_vocab

    def get_bos_token_id(self):
        return self.bos_token_id

    def encode(self, text, prepend=None, num_threads=8):
        if prepend is not None:
            prepend_id = (
                prepend
                if isinstance(prepend, int)
                else self.enc.encode_single_token(prepend)
            )
        if isinstance(text, str):
            ids = self.enc.encode_ordinary(text)
            if prepend is not None:
                ids.insert(0, prepend_id)
        elif isinstance(text, list):
            ids = self.enc.encode_ordinary_batch(text, num_threads=num_threads)
            if prepend is not None:
                for row in ids:
                    row.insert(0, prepend_id)
        else:
            raise ValueError(f"Invalid input type: {type(text)}")
        return ids

    def decode(self, ids):
        return self.enc.decode(ids)


def get_token_bytes(device="cpu"):
    path = os.path.join(TOKENIZER_DIR, "token_bytes.pt")
    with open(path, "rb") as f:
        return torch.load(f, map_location=device)


def _document_batches(split, tokenizer_batch_size=128):
    """Infinite iterator over document batches from parquet files."""
    parquet_paths = list_parquet_files()
    assert len(parquet_paths) > 0, "No parquet files found. Run prepare.py first."
    val_path = os.path.join(DATA_DIR, VAL_FILENAME)
    if split == "train":
        parquet_paths = [p for p in parquet_paths if p != val_path]
        assert len(parquet_paths) > 0, "No training shards found."
    else:
        parquet_paths = [val_path]
    epoch = 1
    while True:
        for filepath in parquet_paths:
            pf = _require_pq_module().ParquetFile(filepath)
            for rg_idx in range(pf.num_row_groups):
                rg = pf.read_row_group(rg_idx)
                batch = rg.column("text").to_pylist()
                for i in range(0, len(batch), tokenizer_batch_size):
                    yield batch[i : i + tokenizer_batch_size], epoch
        epoch += 1


def make_dataloader(tokenizer, B, T, split, buffer_size=1000):
    """
    BOS-aligned dataloader with best-fit packing.
    Every row starts with BOS. Documents packed using best-fit to minimize cropping.
    When no document fits remaining space, crops shortest doc to fill exactly.
    100% utilization (no padding).
    """
    assert split in ["train", "val"]
    row_capacity = T + 1
    batches = _document_batches(split)
    bos_token = tokenizer.get_bos_token_id()
    doc_buffer = []
    epoch = 1

    def refill_buffer():
        nonlocal epoch
        doc_batch, epoch = next(batches)
        token_lists = tokenizer.encode(doc_batch, prepend=bos_token)
        doc_buffer.extend(token_lists)

    # Pre-allocate buffers: [inputs (B*T) | targets (B*T)]
    row_buffer = torch.empty((B, row_capacity), dtype=torch.long)
    cpu_buffer = torch.empty(2 * B * T, dtype=torch.long, pin_memory=True)
    gpu_buffer = torch.empty(2 * B * T, dtype=torch.long, device="cuda")
    cpu_inputs = cpu_buffer[: B * T].view(B, T)
    cpu_targets = cpu_buffer[B * T :].view(B, T)
    inputs = gpu_buffer[: B * T].view(B, T)
    targets = gpu_buffer[B * T :].view(B, T)

    while True:
        for row_idx in range(B):
            pos = 0
            while pos < row_capacity:
                while len(doc_buffer) < buffer_size:
                    refill_buffer()

                remaining = row_capacity - pos

                # Find largest doc that fits entirely
                best_idx = -1
                best_len = 0
                for i, doc in enumerate(doc_buffer):
                    doc_len = len(doc)
                    if doc_len <= remaining and doc_len > best_len:
                        best_idx = i
                        best_len = doc_len

                if best_idx >= 0:
                    doc = doc_buffer.pop(best_idx)
                    row_buffer[row_idx, pos : pos + len(doc)] = torch.tensor(
                        doc, dtype=torch.long
                    )
                    pos += len(doc)
                else:
                    # No doc fits — crop shortest to fill remaining
                    shortest_idx = min(
                        range(len(doc_buffer)), key=lambda i: len(doc_buffer[i])
                    )
                    doc = doc_buffer.pop(shortest_idx)
                    row_buffer[row_idx, pos : pos + remaining] = torch.tensor(
                        doc[:remaining], dtype=torch.long
                    )
                    pos += remaining

        cpu_inputs.copy_(row_buffer[:, :-1])
        cpu_targets.copy_(row_buffer[:, 1:])
        gpu_buffer.copy_(cpu_buffer, non_blocking=True)
        yield inputs, targets, epoch


# ---------------------------------------------------------------------------
# Evaluation (DO NOT CHANGE — this is the fixed metric)
# ---------------------------------------------------------------------------


def _maybe_no_grad(func):
    if torch is None:
        return func
    return torch.no_grad()(func)


@_maybe_no_grad
def evaluate_bpb(model, tokenizer, batch_size):
    """
    Bits per byte (BPB): vocab size-independent evaluation metric.
    Sums per-token cross-entropy (in nats), sums target byte lengths,
    then converts nats/byte to bits/byte. Special tokens (byte length 0)
    are excluded from both sums.
    Uses fixed MAX_SEQ_LEN so results are comparable across configs.
    """
    token_bytes = get_token_bytes(device="cuda")
    val_loader = make_dataloader(tokenizer, batch_size, MAX_SEQ_LEN, "val")
    steps = EVAL_TOKENS // (batch_size * MAX_SEQ_LEN)
    total_nats = 0.0
    total_bytes = 0
    for _ in range(steps):
        x, y, _ = next(val_loader)
        loss_flat = model(x, y, reduction="none").view(-1)
        y_flat = y.view(-1)
        nbytes = token_bytes[y_flat]
        mask = nbytes > 0
        total_nats += (loss_flat * mask).sum().item()
        total_bytes += nbytes.sum().item()
    return total_nats / (math.log(2) * total_bytes)


def verify_enwik9_size(path: Path) -> bool:
    """Return True when the enwik9 file matches the expected size."""

    return path.exists() and path.stat().st_size == expected_enwik9_size_bytes()


def _download_enwik9_zip(zip_path: Path) -> None:
    temp_path = zip_path.with_name(zip_path.name + ".tmp")
    with urllib.request.urlopen(ENWIK9_URL) as response, temp_path.open("wb") as out:
        shutil.copyfileobj(response, out)
    temp_path.replace(zip_path)


def _extract_enwik9(zip_path: Path, enwik9_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "r") as archive:
        archive.extractall(enwik9_path.parent)


def _ensure_verified_enwik9(
    zip_path: Path,
    enwik9_path: Path,
    *,
    max_attempts: int = ENWIK9_DOWNLOAD_MAX_ATTEMPTS,
) -> None:
    for attempt in range(1, max_attempts + 1):
        if not zip_path.exists():
            print(f"Downloading enwik9 from {ENWIK9_URL} to {zip_path}")
            try:
                _download_enwik9_zip(zip_path)
            except Exception as exc:
                zip_path.unlink(missing_ok=True)
                enwik9_path.unlink(missing_ok=True)
                if attempt == max_attempts:
                    raise RuntimeError(
                        f"enwik9 download failed after {max_attempts} attempts"
                    ) from exc
                continue

        enwik9_path.unlink(missing_ok=True)

        print(f"Extracting enwik9 into {enwik9_path.parent}")
        try:
            _extract_enwik9(zip_path, enwik9_path)
        except (zipfile.BadZipFile, OSError) as exc:
            zip_path.unlink(missing_ok=True)
            enwik9_path.unlink(missing_ok=True)
            if attempt == max_attempts:
                raise RuntimeError(
                    f"enwik9 extraction failed after {max_attempts} attempts"
                ) from exc
            continue

        if verify_enwik9_size(enwik9_path):
            return

        zip_path.unlink(missing_ok=True)
        enwik9_path.unlink(missing_ok=True)
        if attempt == max_attempts:
            raise RuntimeError(
                f"enwik9 verification failed after {max_attempts} attempts"
            )


def prepare_main() -> None:
    cache_dir = Path(CACHE_DIR)
    cache_dir.mkdir(parents=True, exist_ok=True)
    enwik9_path = cache_dir / ENWIK9_FILENAME
    zip_path = cache_dir / ENWIK9_ZIP_NAME
    proxy_dir = cache_dir / PROXY_DIR_NAME

    if not enwik9_path.exists() or not verify_enwik9_size(enwik9_path):
        _ensure_verified_enwik9(zip_path, enwik9_path)

    if not verify_enwik9_size(enwik9_path):
        raise RuntimeError(
            f"enwik9 verification failed: {enwik9_path.stat().st_size if enwik9_path.exists() else 'missing'} bytes"
        )

    outputs = create_proxy_slices(enwik9_path, proxy_dir)
    print("Proxy slices ready:", ", ".join(str(p) for p in outputs))


if __name__ == "__main__":
    prepare_main()
