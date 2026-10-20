"""Parser for the used-sector map (directory entry 7) of a .v2i image: a serialized bitmap tree.

Every node is {u8 type, u16 header_len, header...} followed by its body (see docs/FORMAT.md):
  0x02 tree    : header {u64 span, u16 nchildren, u64 child_span}; the children follow.
  0x00 / 0x01  : const-free / const-used leaf, header {uN span}, N = header_len bytes.
  0x10/0x20/0x40: run-list leaf, header {uN span}; body {u8 cluster_shift, u16 count, (off, len) x count}.
  0x03 bitmap  : header {uN span}; body ceil(span/8) bytes, one bit per sector, LSB first.
Spans and runs are in 512-byte sectors; runs are relative to the node's start and ascend overall.
"""

import struct

WIDTH = {2: ("<H", "<HH"), 4: ("<I", "<II"), 8: ("<Q", "<QQ")}


def parse_runs(m, bit_unit=1):
    runs = []

    def walk(pos, base):
        t = m[pos]
        hl = struct.unpack_from("<H", m, pos + 1)[0]
        h = pos + 3
        p = h + hl
        if t == 0x02:
            span = struct.unpack_from("<Q", m, h)[0]
            n = struct.unpack_from("<H", m, h + 8)[0]
            cspan = struct.unpack_from("<Q", m, h + 10)[0]
            cb = base
            for _ in range(n):
                p, _cs = walk(p, cb)
                cb += cspan
            return p, span
        one, pair = WIDTH[hl]
        span = struct.unpack_from(one, m, h)[0]
        if t == 0x00:
            return p, span
        if t == 0x01:
            runs.append((base, span))
            return p, span
        if t in (0x10, 0x20, 0x40):
            count = struct.unpack_from("<H", m, p + 1)[0]
            p += 3
            for j in range(count):
                offset, length = struct.unpack_from(pair, m, p + 2 * hl * j)
                runs.append((base + offset, length))
            return p + 2 * hl * count, span
        if t == 0x03:
            nbits = (span + bit_unit - 1) // bit_unit
            nbytes = (nbits + 7) // 8
            bits = int.from_bytes(m[p : p + nbytes], "little")
            i = 0
            while i < nbits:
                if bits >> i & 1:
                    j = i
                    while j < nbits and bits >> j & 1:
                        j += 1
                    runs.append((base + i * bit_unit, (j - i) * bit_unit))
                    i = j
                else:
                    i += 1
            return p + nbytes, span
        raise ValueError(f"unknown node type {t:#x} at {pos:#x}")

    start = m.find(b"\x02\x12\x00")
    end, total = walk(start, 0)
    if end != len(m):
        raise ValueError(f"map walk ended at {end} of {len(m)}")
    return runs, total


def main(argv=None):
    """Check a map file: walk it to the end and compare its run total with a packed stream size."""
    import argparse

    ap = argparse.ArgumentParser(description=main.__doc__)
    ap.add_argument("map_file")
    ap.add_argument("--packed-size", type=int, help="size of volume.packed in bytes")
    a = ap.parse_args(argv)
    with open(a.map_file, "rb") as f:
        runs, total = parse_runs(f.read())
    used = sum(length for _, length in runs)
    asc = all(runs[i][0] + runs[i][1] <= runs[i + 1][0] for i in range(len(runs) - 1))
    print(
        f"volume: {total} sectors ({total * 512 / 1e9:.2f} GB); runs: {len(runs)}, ascending: {asc}; "
        f"used: {used} sectors ({used * 512 / 1e9:.2f} GB)"
    )
    if a.packed_size is None:
        return 0
    ok = used * 512 == a.packed_size
    print("packed stream matches" if ok else f"packed stream differs by {a.packed_size - used * 512} bytes")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
