import struct
import unittest

from v2i_open import bitmap


def tree(span, children, child_span):
    return b"\x02" + struct.pack("<H", 0x12) + struct.pack("<QHQ", span, len(children), child_span) + b"".join(children)


def const(kind, span, width=4):
    fmt = {2: "<H", 4: "<I", 8: "<Q"}[width]
    return bytes([kind]) + struct.pack("<H", width) + struct.pack(fmt, span)


def runlist(span, runs, width=4):
    one, pair = {2: ("<H", "<HH"), 4: ("<I", "<II"), 8: ("<Q", "<QQ")}[width]
    kind = {2: 0x10, 4: 0x20, 8: 0x40}[width]
    body = bytes([3]) + struct.pack("<H", len(runs)) + b"".join(struct.pack(pair, o, n) for o, n in runs)
    return bytes([kind]) + struct.pack("<H", width) + struct.pack(one, span) + body


def raw_bitmap(span, used_sectors):
    bits = 0
    for s in used_sectors:
        bits |= 1 << s
    return b"\x03" + struct.pack("<H", 2) + struct.pack("<H", span) + bits.to_bytes((span + 7) // 8, "little")


HEADER = b"\x14\x83" + bytes(30)


class BitmapTreeTests(unittest.TestCase):
    def test_every_node_type_round_trips(self):
        z = 0x80000
        leaves = [
            runlist(z, [(0, 8), (16, 24), (0x7FFF0, 16)]),
            const(0x00, z),
            const(0x01, z),
            runlist(0x8000, [(8, 8)], width=2),
            runlist(z, [(0x40000, 0x40000)], width=8),
            raw_bitmap(0x8000, [0, 1, 2, 9, 0x7FFF]),
        ]
        runs, total = bitmap.parse_runs(HEADER + tree(6 * z, leaves, z))
        self.assertEqual(total, 6 * z)
        self.assertEqual(
            runs,
            [
                (0, 8),
                (16, 24),
                (0x7FFF0, 16),
                (2 * z, z),
                (3 * z + 8, 8),
                (4 * z + 0x40000, 0x40000),
                (5 * z, 3),
                (5 * z + 9, 1),
                (5 * z + 0x7FFF, 1),
            ],
        )

    def test_nested_trees_advance_the_base(self):
        z = 0x80000
        inner = tree(2 * z, [const(0x01, z), runlist(z, [(4, 4)])], z)
        runs, total = bitmap.parse_runs(HEADER + tree(4 * z, [const(0x00, 2 * z, width=8), inner], 2 * z))
        self.assertEqual(total, 4 * z)
        self.assertEqual(runs, [(2 * z, z), (3 * z + 4, 4)])

    def test_trailing_garbage_is_rejected(self):
        z = 0x80000
        with self.assertRaises(ValueError):
            bitmap.parse_runs(HEADER + tree(z, [const(0x00, z)], z) + b"\x00")


if __name__ == "__main__":
    unittest.main()
