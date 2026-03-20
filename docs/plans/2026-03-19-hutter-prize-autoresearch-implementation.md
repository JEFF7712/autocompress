# Hutter Prize Autoresearch Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the current GPU language-model experiment loop with a minimal proxy-first `enwik9` compression loop while keeping the original autoresearch workflow shape.

**Architecture:** Keep `prepare.py` and `train.py` as the only executable scripts. `prepare.py` becomes a fixed data-prep harness (download/extract/verify `enwik9`, then generate deterministic proxy slices). `train.py` becomes a fixed evaluation harness with a small mutable candidate compression block, roundtrip verification, and score reporting (`archive_bytes + code_bytes`). Add optional read-only `fx2-cmix` baseline comparison through an environment variable.

**Tech Stack:** Python 3.10+, `uv`, standard library modules (`argparse`, `pathlib`, `subprocess`, `zipfile`, `tempfile`, `hashlib`, `shutil`), external `fx2-cmix` binary (optional).

---

### Task 1: Add deterministic `prepare.py` helper functions

**Files:**
- Modify: `prepare.py`
- Create: `tests/__init__.py`
- Test: `tests/test_prepare_helpers.py`

**Step 1: Write the failing test**

```python
import unittest

from prepare import expected_enwik9_size_bytes, proxy_offsets


class PrepareHelpersTest(unittest.TestCase):
    def test_expected_size_constant(self):
        self.assertEqual(expected_enwik9_size_bytes(), 1_000_000_000)

    def test_proxy_offsets_are_deterministic(self):
        offsets = proxy_offsets(total_size=1_000_000_000, slice_size=32 * 1024 * 1024)
        self.assertEqual(offsets, [0, 483_222_784, 966_445_568])


if __name__ == "__main__":
    unittest.main()
```

**Step 2: Run test to verify it fails**

Run: `uv run python -m unittest tests.test_prepare_helpers -v`
Expected: FAIL with import or attribute errors for missing helper functions.

**Step 3: Write minimal implementation**

```python
def expected_enwik9_size_bytes() -> int:
    return 1_000_000_000


def proxy_offsets(total_size: int, slice_size: int) -> list[int]:
    middle = (total_size - slice_size) // 2
    tail = total_size - slice_size
    return [0, middle, tail]
```

**Step 4: Run test to verify it passes**

Run: `uv run python -m unittest tests.test_prepare_helpers -v`
Expected: PASS

**Step 5: Commit**

```bash
git add prepare.py tests/__init__.py tests/test_prepare_helpers.py
git commit -m "test: add deterministic enwik9 helper coverage"
```

### Task 2: Implement proxy-slice creation in `prepare.py`

**Files:**
- Modify: `prepare.py`
- Test: `tests/test_prepare_pipeline.py`

**Step 1: Write the failing test**

```python
import os
import tempfile
import unittest
from pathlib import Path

from prepare import create_proxy_slices


class PreparePipelineTest(unittest.TestCase):
    def test_create_proxy_slices_writes_three_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "enwik9"
            src.write_bytes(os.urandom(2 * 1024 * 1024))
            proxy_dir = Path(tmp) / "proxy"

            outputs = create_proxy_slices(src, proxy_dir, slice_size=256 * 1024)

            self.assertEqual(len(outputs), 3)
            self.assertTrue(all(p.exists() for p in outputs))
            self.assertTrue(all(p.stat().st_size == 256 * 1024 for p in outputs))


if __name__ == "__main__":
    unittest.main()
```

**Step 2: Run test to verify it fails**

Run: `uv run python -m unittest tests.test_prepare_pipeline -v`
Expected: FAIL because `create_proxy_slices` is not implemented.

**Step 3: Write minimal implementation**

```python
def create_proxy_slices(enwik9_path: Path, proxy_dir: Path, slice_size: int = 32 * 1024 * 1024) -> list[Path]:
    proxy_dir.mkdir(parents=True, exist_ok=True)
    total_size = enwik9_path.stat().st_size
    starts = proxy_offsets(total_size=total_size, slice_size=slice_size)
    outputs = []
    with enwik9_path.open("rb") as src:
        for name, start in zip(["head", "mid", "tail"], starts):
            out = proxy_dir / f"{name}.bin"
            src.seek(start)
            out.write_bytes(src.read(slice_size))
            outputs.append(out)
    return outputs
```

**Step 4: Run test to verify it passes**

Run: `uv run python -m unittest tests.test_prepare_pipeline -v`
Expected: PASS

**Step 5: Commit**

```bash
git add prepare.py tests/test_prepare_pipeline.py
git commit -m "feat: add deterministic enwik9 proxy slicing"
```

### Task 3: Implement `prepare.py` end-to-end enwik9 prep flow

**Files:**
- Modify: `prepare.py`
- Test: `tests/test_prepare_download_verify.py`

**Step 1: Write the failing test**

```python
import tempfile
import unittest
from pathlib import Path

from prepare import verify_enwik9_size


class PrepareVerifyTest(unittest.TestCase):
    def test_verify_enwik9_size_rejects_wrong_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "enwik9"
            bad.write_bytes(b"abc")
            self.assertFalse(verify_enwik9_size(bad))
```

**Step 2: Run test to verify it fails**

Run: `uv run python -m unittest tests.test_prepare_download_verify -v`
Expected: FAIL because `verify_enwik9_size` is missing.

**Step 3: Write minimal implementation**

```python
def verify_enwik9_size(path: Path) -> bool:
    return path.exists() and path.stat().st_size == expected_enwik9_size_bytes()


def prepare_main() -> None:
    # 1) ensure cache dir
    # 2) download enwik9.zip if missing
    # 3) extract enwik9 if missing
    # 4) verify size
    # 5) create proxy slices
    ...


if __name__ == "__main__":
    prepare_main()
```

**Step 4: Run test to verify it passes**

Run: `uv run python -m unittest tests.test_prepare_download_verify -v`
Expected: PASS

**Step 5: Commit**

```bash
git add prepare.py tests/test_prepare_download_verify.py
git commit -m "feat: switch prepare script to enwik9 download and verification"
```

### Task 4: Refactor `train.py` into import-safe evaluator helpers

**Files:**
- Modify: `train.py`
- Test: `tests/test_train_helpers.py`

**Step 1: Write the failing test**

```python
import importlib
import unittest


class TrainHelpersTest(unittest.TestCase):
    def test_compute_score_bytes(self):
        mod = importlib.import_module("train")
        self.assertEqual(mod.compute_score_bytes(110, 7), 117)

    def test_roundtrip_helper(self):
        mod = importlib.import_module("train")
        self.assertTrue(mod.is_roundtrip_equal(b"abc", b"abc"))
        self.assertFalse(mod.is_roundtrip_equal(b"abc", b"abd"))
```

**Step 2: Run test to verify it fails**

Run: `uv run python -m unittest tests.test_train_helpers -v`
Expected: FAIL due missing helper functions or import side effects.

**Step 3: Write minimal implementation**

```python
def compute_score_bytes(archive_bytes: int, code_bytes: int) -> int:
    return int(archive_bytes) + int(code_bytes)


def is_roundtrip_equal(original: bytes, restored: bytes) -> bool:
    return original == restored


def main() -> None:
    # CLI entry point and evaluation flow
    ...


if __name__ == "__main__":
    main()
```

**Step 4: Run test to verify it passes**

Run: `uv run python -m unittest tests.test_train_helpers -v`
Expected: PASS

**Step 5: Commit**

```bash
git add train.py tests/test_train_helpers.py
git commit -m "refactor: make train module import-safe with scoring helpers"
```

### Task 5: Add proxy/full output formatting and roundtrip status reporting

**Files:**
- Modify: `train.py`
- Test: `tests/test_train_summary.py`

**Step 1: Write the failing test**

```python
import unittest

from train import format_summary


class TrainSummaryTest(unittest.TestCase):
    def test_proxy_summary_fields(self):
        text = format_summary(mode="proxy", archive_bytes=100, code_bytes=20, score_bytes=120, roundtrip_ok=True)
        self.assertIn("proxy_score_bytes: 120", text)
        self.assertIn("archive_bytes: 100", text)
        self.assertIn("code_bytes: 20", text)
        self.assertIn("roundtrip_ok: true", text)
```

**Step 2: Run test to verify it fails**

Run: `uv run python -m unittest tests.test_train_summary -v`
Expected: FAIL because `format_summary` is missing.

**Step 3: Write minimal implementation**

```python
def format_summary(mode: str, archive_bytes: int, code_bytes: int, score_bytes: int, roundtrip_ok: bool) -> str:
    score_key = "proxy_score_bytes" if mode == "proxy" else "full_score_bytes"
    ok = "true" if roundtrip_ok else "false"
    return "\n".join([
        f"{score_key}: {score_bytes}",
        f"archive_bytes: {archive_bytes}",
        f"code_bytes: {code_bytes}",
        f"roundtrip_ok: {ok}",
    ])
```

**Step 4: Run test to verify it passes**

Run: `uv run python -m unittest tests.test_train_summary -v`
Expected: PASS

**Step 5: Commit**

```bash
git add train.py tests/test_train_summary.py
git commit -m "feat: add stable proxy/full summary output"
```

### Task 6: Add read-only `fx2-cmix` baseline hook and update loop docs

**Files:**
- Modify: `train.py`
- Modify: `program.md`
- Create: `results_template.tsv`
- Test: `tests/test_baseline_hook.py`

**Step 1: Write the failing test**

```python
import os
import unittest

from train import baseline_is_configured


class BaselineHookTest(unittest.TestCase):
    def test_baseline_configuration_switch(self):
        os.environ.pop("FX2_CMIX_BIN", None)
        self.assertFalse(baseline_is_configured())
        os.environ["FX2_CMIX_BIN"] = "/tmp/fx2-cmix"
        self.assertTrue(baseline_is_configured())
```

**Step 2: Run test to verify it fails**

Run: `uv run python -m unittest tests.test_baseline_hook -v`
Expected: FAIL because baseline hook helper is missing.

**Step 3: Write minimal implementation**

```python
def baseline_is_configured() -> bool:
    return bool(os.environ.get("FX2_CMIX_BIN"))
```

Also update `program.md` objective to `score_bytes` and add `results_template.tsv` header:

```tsv
commit	proxy_score	full_score	status	description
```

**Step 4: Run test and smoke checks**

Run: `uv run python -m unittest tests.test_baseline_hook -v`
Expected: PASS

Run: `uv run python -m unittest -v`
Expected: PASS

Run: `uv run prepare.py --help`
Expected: shows CLI usage without traceback

Run: `uv run train.py --help`
Expected: shows CLI usage without traceback

**Step 5: Commit**

```bash
git add train.py program.md results_template.tsv tests/test_baseline_hook.py
git commit -m "docs: wire fx2-cmix baseline hook and hutter loop instructions"
```

## Verification Checklist

- `prepare.py` creates/validates `enwik9` and deterministic proxy slices.
- `train.py` prints stable grep-friendly fields and fails hard on roundtrip mismatch.
- Proxy run and full run use the same score formula (`archive_bytes + code_bytes`).
- Baseline hook is optional and read-only in v1.
- `program.md` keeps autonomous loop shape with updated objective.

## If Something Fails

- Apply `@systematic-debugging` before changing implementation strategy.
- Keep changes minimal (YAGNI) and preserve stable output keys.
- Do not broaden scope to winner-code mutation in v1.
