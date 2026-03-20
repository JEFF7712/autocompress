import os
import tempfile
import unittest
from pathlib import Path

from prepare import create_proxy_slices
from prepare_helpers import proxy_offsets


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

    def test_create_proxy_slices_validates_slice_size_and_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            proxy_dir = Path(tmp) / "proxy"
            missing = Path(tmp) / "missing.bin"
            with self.assertRaises(FileNotFoundError):
                create_proxy_slices(missing, proxy_dir, slice_size=64)

            src = Path(tmp) / "enwik9"
            data = bytes(range(100)) * 10
            src.write_bytes(data)

            with self.assertRaises(ValueError):
                create_proxy_slices(src, proxy_dir, slice_size=0)
            with self.assertRaises(ValueError):
                create_proxy_slices(src, proxy_dir, slice_size=len(data) + 1)

    def test_create_proxy_slices_outputs_content_at_expected_offsets(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "enwik9"
            content = bytes(range(256)) * 4
            src.write_bytes(content)
            slice_size = 128
            proxy_dir = Path(tmp) / "proxy"

            outputs = create_proxy_slices(src, proxy_dir, slice_size=slice_size)
            starts = proxy_offsets(total_size=len(content), slice_size=slice_size)

            slices = [p.read_bytes() for p in outputs]
            expected = [content[start : start + slice_size] for start in starts]
            self.assertEqual(slices, expected)


if __name__ == "__main__":
    unittest.main()
