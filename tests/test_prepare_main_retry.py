import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import prepare


class PrepareMainRetryTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self._cache_patcher = patch.object(prepare, "CACHE_DIR", self._tmpdir.name)
        self._cache_patcher.start()
        self.addCleanup(self._cache_patcher.stop)

    @property
    def cache_path(self) -> Path:
        return Path(self._tmpdir.name)

    def _enwik9_path(self) -> Path:
        return self.cache_path / prepare.ENWIK9_FILENAME

    def _zip_path(self) -> Path:
        return self.cache_path / prepare.ENWIK9_ZIP_NAME

    def _write_zip(self, path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.unlink(missing_ok=True)
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(prepare.ENWIK9_FILENAME, data)

    def test_prepare_main_retries_after_extract_failure(self):
        data = b"0123456789"
        downloads = {"count": 0}

        def fake_download(zip_path: Path) -> None:
            downloads["count"] += 1
            self._write_zip(zip_path, data)

        orig_extract = prepare._extract_enwik9
        extract_calls = {"count": 0}

        def fake_extract(zip_path: Path, enwik9_path: Path) -> None:
            extract_calls["count"] += 1
            if extract_calls["count"] == 1:
                raise zipfile.BadZipFile("corrupt")
            orig_extract(zip_path, enwik9_path)

        with (
            patch.object(prepare, "_download_enwik9_zip", side_effect=fake_download),
            patch.object(prepare, "_extract_enwik9", side_effect=fake_extract),
            patch.object(prepare, "expected_enwik9_size_bytes", return_value=len(data)),
            patch.object(prepare, "create_proxy_slices", return_value=[]),
        ):
            prepare.prepare_main()

        self.assertEqual(downloads["count"], 2)
        self.assertTrue(self._enwik9_path().exists())
        self.assertEqual(self._enwik9_path().stat().st_size, len(data))

    def test_prepare_main_retries_when_verification_fails(self):
        data_sequence = [b"A", b"AB"]
        downloads = {"count": 0}

        def fake_download(zip_path: Path) -> None:
            data = data_sequence[min(downloads["count"], len(data_sequence) - 1)]
            downloads["count"] += 1
            self._write_zip(zip_path, data)

        with (
            patch.object(prepare, "_download_enwik9_zip", side_effect=fake_download),
            patch.object(prepare, "expected_enwik9_size_bytes", return_value=2),
            patch.object(prepare, "create_proxy_slices", return_value=[]),
        ):
            prepare.prepare_main()

        self.assertEqual(downloads["count"], 2)
        self.assertTrue(self._enwik9_path().exists())
        self.assertEqual(self._enwik9_path().stat().st_size, 2)

    def test_prepare_main_retries_on_download_failure(self):
        data = b"XYZ"
        downloads = {"count": 0}

        def fake_download(zip_path: Path) -> None:
            downloads["count"] += 1
            if downloads["count"] == 1:
                raise OSError("network error")
            self._write_zip(zip_path, data)

        with (
            patch.object(prepare, "_download_enwik9_zip", side_effect=fake_download),
            patch.object(prepare, "expected_enwik9_size_bytes", return_value=len(data)),
            patch.object(prepare, "create_proxy_slices", return_value=[]),
        ):
            prepare.prepare_main()

        self.assertEqual(downloads["count"], 2)
        self.assertTrue(self._enwik9_path().exists())
        self.assertEqual(self._enwik9_path().stat().st_size, len(data))


if __name__ == "__main__":
    unittest.main()
