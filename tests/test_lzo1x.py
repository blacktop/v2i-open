import os
import unittest

try:
    from v2i_open import lzo1x
except Exception:  # liblzo2 missing
    lzo1x = None


@unittest.skipIf(lzo1x is None, "liblzo2 not available")
class Lzo1xTests(unittest.TestCase):
    def test_round_trip(self):
        sample = (b"FILE0" + bytes(1019)) * 40 + os.urandom(3000) + b"NTFS    " * 64
        packed = lzo1x.compress(sample)
        self.assertLess(len(packed), len(sample))
        self.assertEqual(lzo1x.decompress(packed, len(sample)), sample)

    def test_truncated_input_is_rejected(self):
        packed = lzo1x.compress(bytes(range(256)) * 64)
        with self.assertRaises(lzo1x.LzoError):
            lzo1x.decompress(packed[: len(packed) // 2], 1 << 16)

    def test_output_bound_is_enforced(self):
        with self.assertRaises(lzo1x.LzoError):
            lzo1x.decompress(lzo1x.compress(bytes(65536)), 1024)


if __name__ == "__main__":
    unittest.main()
