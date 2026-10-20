import os
import struct
import tempfile
import unittest

from v2i_open import container


def entry(eid, parent, tag, logical, size):
    return b"$CDE" + struct.pack("<IIIII", 0x28, eid, parent, tag, 0) + struct.pack("<QQ", logical, size)


def synthetic_image(blocks=2):
    """A minimal $CAN container: file header, directory header, chunk table, four entries, raw track 0."""
    can = bytearray(0x60)
    can[:4] = b"$CAN"
    struct.pack_into("<II", can, 4, 0x60, 0x60)
    struct.pack_into("<I", can, 0x14, 0x00080403)
    struct.pack_into("<II", can, 0x1C, 0x40000, 0x40000)
    cdh = bytearray(0x60)
    cdh[:4] = b"$CDH"
    struct.pack_into("<I", cdh, 0x0C, 0x60)
    struct.pack_into("<Q", cdh, 0x10, 0x30000)
    table = struct.pack("<QQ", 0x10000, 0x30000) + struct.pack("<Q", 0x30000) * 2
    entries = (
        entry(1, 0, 0, 0, 0)
        + entry(2, 1, 0x49515024, 0x1000, 0x86)
        + entry(3, 2, 0, 0x2000, 0x7E00)
        + entry(8, 2, 0, 0x10000, 0x20000)
    )
    body = bytearray(blocks * 0x40000)
    body[:0x60] = can
    body[0x60:0xC0] = cdh
    struct.pack_into("<I", body, 0x78, blocks)
    body[0xC0 : 0xC0 + len(table)] = table
    body[0xC0 + len(table) : 0xC0 + len(table) + len(entries)] = entries
    body[0x2000 + 0x60 + 0x1FE : 0x2000 + 0x60 + 0x200] = b"\x55\xaa"
    return bytes(body)


class ContainerTests(unittest.TestCase):
    def test_parse_synthetic_container(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "x.v2i")
            with open(path, "wb") as f:
                f.write(synthetic_image())
            info = container.parse(path)
        self.assertEqual(info["blocks"], 2)
        self.assertTrue(info["block_check"])
        self.assertEqual(info["total"], 0x30000)
        self.assertEqual(info["table"], [0x10000, 0x30000])
        self.assertEqual([e["id"] for e in info["entries"]], [1, 2, 3, 8])
        self.assertEqual(info["entries"][1]["type"], "$PQI")
        e3 = info["entries"][2]
        self.assertEqual((e3["logical"], e3["size"]), (0x2000, 0x7E00))
        fo = e3["logical"] + container.SHIFT
        self.assertEqual(info["head"][fo + 0x1FE : fo + 0x200], b"\x55\xaa")

    def test_rejects_other_files(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "not.v2i")
            with open(path, "wb") as f:
                f.write(bytes(1 << 20))
            with self.assertRaises(SystemExit):
                container.parse(path)


if __name__ == "__main__":
    unittest.main()
