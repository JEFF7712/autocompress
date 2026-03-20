import os
import unittest
from unittest import mock

import importlib


class BaselineHookTest(unittest.TestCase):
    def test_baseline_configuration_switch(self):
        mod = importlib.import_module("train")
        with mock.patch.dict(os.environ, {"FX2_CMIX_BIN": ""}, clear=False):
            os.environ.pop("FX2_CMIX_BIN", None)
            self.assertFalse(mod.baseline_is_configured())
        with mock.patch.dict(
            os.environ, {"FX2_CMIX_BIN": "/tmp/fx2-cmix"}, clear=False
        ):
            self.assertTrue(mod.baseline_is_configured())


if __name__ == "__main__":
    unittest.main()
