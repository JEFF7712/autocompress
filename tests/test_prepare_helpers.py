import unittest

from prepare_helpers import expected_enwik9_size_bytes, proxy_offsets


class PrepareHelpersTest(unittest.TestCase):
    def test_expected_size_constant(self):
        self.assertEqual(expected_enwik9_size_bytes(), 1_000_000_000)

    def test_proxy_offsets_are_deterministic(self):
        offsets = proxy_offsets(total_size=1_000_000_000, slice_size=32 * 1024 * 1024)
        self.assertEqual(offsets, [0, 483_222_784, 966_445_568])

    def test_proxy_offsets_invalid_total_size(self):
        with self.assertRaises(ValueError):
            proxy_offsets(total_size=0, slice_size=1)

    def test_proxy_offsets_invalid_slice_size(self):
        with self.assertRaises(ValueError):
            proxy_offsets(total_size=100, slice_size=0)
        with self.assertRaises(ValueError):
            proxy_offsets(total_size=100, slice_size=101)


if __name__ == "__main__":
    unittest.main()
