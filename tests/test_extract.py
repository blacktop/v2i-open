import struct
import unittest

try:
    from v2i_open import extract, lzo1x
except Exception:  # liblzo2 missing
    lzo1x = extract = None


def u24(n):
    return n.to_bytes(3, "little")


def block(index, chunks, trailer):
    payload = b"".join(u24(len(c)) + u24(n) + c for c, n in chunks) + u24(trailer)
    blk = bytearray(extract.BLK)
    blk[:4] = b"$CAN"
    struct.pack_into("<I", blk, 0x30, index)
    struct.pack_into("<I", blk, 0x40, sum(n for _, n in chunks) + trailer)
    struct.pack_into("<I", blk, 0x48, len(payload) - 3)
    blk[extract.HDR : extract.HDR + len(payload)] = payload
    return bytes(blk)


@unittest.skipIf(lzo1x is None, "liblzo2 not available")
class BlockDecodeTests(unittest.TestCase):
    def test_sub_streams_and_sparse_trailer(self):
        a = b"\xeb\x52\x90NTFS    " * 4000
        b = bytes(range(256)) * 300
        blk = block(1, [(lzo1x.compress(a), len(a)), (lzo1x.compress(b), len(b))], 1522)
        out = bytearray()
        self.assertEqual(extract.decode_block(blk, 1, out.extend), 2)
        self.assertEqual(bytes(out), a + b + bytes(1522))

    def test_bad_index_and_bad_span_are_rejected(self):
        a = b"x" * 1000
        blk = block(2, [(lzo1x.compress(a), len(a))], 0)
        with self.assertRaises(ValueError):
            extract.decode_block(blk, 1, lambda _: None)
        bad = bytearray(blk)
        struct.pack_into("<I", bad, 0x40, 999)
        with self.assertRaises(ValueError):
            extract.decode_block(bytes(bad), 2, lambda _: None)


if __name__ == "__main__":
    unittest.main()
