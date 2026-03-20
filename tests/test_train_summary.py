import io
import sys
import unittest
from contextlib import redirect_stdout
from unittest import mock

import train


class TrainSummaryTest(unittest.TestCase):
    def test_proxy_summary_fields(self):
        text = train.format_summary(
            mode="proxy",
            archive_bytes=100,
            code_bytes=20,
            score_bytes=120,
            roundtrip_ok=True,
        )
        self.assertIn("proxy_score_bytes: 120", text)
        self.assertIn("archive_bytes: 100", text)
        self.assertIn("code_bytes: 20", text)
        self.assertIn("roundtrip_ok: true", text)

    def test_full_summary_fields(self):
        text = train.format_summary(
            mode="full",
            archive_bytes=5,
            code_bytes=1,
            score_bytes=6,
            roundtrip_ok=False,
        )
        self.assertIn("full_score_bytes: 6", text)
        self.assertIn("roundtrip_ok: false", text)

    def test_invalid_mode_rejected(self):
        with self.assertRaises(ValueError):
            train.format_summary(
                mode="invalid",
                archive_bytes=0,
                code_bytes=0,
                score_bytes=0,
                roundtrip_ok=True,
            )


class TrainMainCLITest(unittest.TestCase):
    def _run_main_and_capture(self, args):
        buf = io.StringIO()
        original_args = sys.argv
        try:
            sys.argv = ["train.py"] + args
            with redirect_stdout(buf):
                train.main()
        finally:
            sys.argv = original_args
        return buf.getvalue()

    def test_main_defaults_to_proxy_mode(self):
        with mock.patch("train.run_evaluation", return_value=(12, False)):
            with mock.patch("train.get_code_bytes", return_value=3):
                output = self._run_main_and_capture([])
        self.assertIn("proxy_score_bytes: 15", output)
        self.assertIn("archive_bytes: 12", output)
        self.assertIn("code_bytes: 3", output)
        self.assertIn("roundtrip_ok: false", output)
        self.assertNotIn("full_score_bytes", output)

    def test_main_full_mode_prints_full_score(self):
        with mock.patch("train.run_evaluation", return_value=(7, True)):
            with mock.patch("train.get_code_bytes", return_value=5):
                output = self._run_main_and_capture(["--full"])
        self.assertIn("full_score_bytes: 12", output)
        self.assertIn("archive_bytes: 7", output)
        self.assertIn("code_bytes: 5", output)
        self.assertIn("roundtrip_ok: true", output)
        self.assertNotIn("proxy_score_bytes", output)


if __name__ == "__main__":
    unittest.main()
