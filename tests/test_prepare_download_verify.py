import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from prepare import verify_enwik9_size


class PrepareVerifyTest(unittest.TestCase):
    @patch("prepare.expected_enwik9_size_bytes", return_value=10)
    def test_verify_enwik9_size_rejects_wrong_size(self, _):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "enwik9"
            bad.write_bytes(b"abc")
            self.assertFalse(verify_enwik9_size(bad))

    @patch("prepare.expected_enwik9_size_bytes", return_value=10)
    def test_verify_enwik9_size_accepts_correct_size(self, _):
        with tempfile.TemporaryDirectory() as tmp:
            good = Path(tmp) / "enwik9"
            good.write_bytes(b"0123456789")
            self.assertTrue(verify_enwik9_size(good))

    def test_verify_enwik9_size_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "enwik9"
            self.assertFalse(verify_enwik9_size(missing))


if __name__ == "__main__":
    unittest.main()
