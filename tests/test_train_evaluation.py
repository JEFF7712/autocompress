import tempfile
import unittest
from pathlib import Path

import zlib

import train


class TrainEvaluationTest(unittest.TestCase):
    def _write_slice(self, base: Path, name: str, data: bytes) -> None:
        path = base / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def test_proxy_mode_sums_three_slices(self):
        data_chunks = [b"alpha", b"beta", b"gamma"]
        with tempfile.TemporaryDirectory() as tempdir:
            base = Path(tempdir)
            slices = base / "proxy_slices"
            for suffix, chunk in zip(("head.bin", "mid.bin", "tail.bin"), data_chunks):
                self._write_slice(slices, suffix, chunk)

            archive_bytes, roundtrip_ok = train.run_evaluation("proxy", tempdir)
        expected = sum(len(zlib.compress(chunk)) for chunk in data_chunks)
        self.assertEqual(archive_bytes, expected)
        self.assertTrue(roundtrip_ok)

    def test_full_mode_reads_enwik9(self):
        sample = b"enwik9 data"
        with tempfile.TemporaryDirectory() as tempdir:
            Path(tempdir, "enwik9").write_bytes(sample)
            archive_bytes, roundtrip_ok = train.run_evaluation("full", tempdir)
        self.assertEqual(archive_bytes, len(zlib.compress(sample)))
        self.assertTrue(roundtrip_ok)

    def test_missing_files_raise(self):
        with tempfile.TemporaryDirectory() as tempdir:
            with self.assertRaises(FileNotFoundError):
                train.run_evaluation("full", tempdir)

    def test_invalid_mode_rejected(self):
        with self.assertRaises(ValueError):
            train.run_evaluation("invalid", None)


if __name__ == "__main__":
    unittest.main()
