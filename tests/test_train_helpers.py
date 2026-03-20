import importlib
import unittest


class TrainHelpersTest(unittest.TestCase):
    def test_compute_score_bytes(self):
        mod = importlib.import_module("train")
        self.assertEqual(mod.compute_score_bytes(110, 7), 117)

    def test_compute_score_bytes_type_contract(self):
        mod = importlib.import_module("train")
        with self.assertRaises(TypeError):
            mod.compute_score_bytes(5.5, 2)

        with self.assertRaises(TypeError):
            mod.compute_score_bytes(3, "7")

        with self.assertRaises(TypeError):
            mod.compute_score_bytes(True, 2)

        with self.assertRaises(TypeError):
            mod.compute_score_bytes(2, False)

        self.assertEqual(mod.compute_score_bytes(-10, -2), -12)

    def test_roundtrip_helper(self):
        mod = importlib.import_module("train")
        self.assertTrue(mod.is_roundtrip_equal(b"abc", b"abc"))
        self.assertFalse(mod.is_roundtrip_equal(b"abc", b"abd"))


if __name__ == "__main__":
    unittest.main()
