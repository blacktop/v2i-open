#!/usr/bin/env python3
"""Extract the logical stream of a Norton Ghost .v2i (PowerQuest $CAN container, LZO1X FSF blocks).

Writes <out>/track0.bin (raw MBR track), <out>/entry7_map.bin (extent map), and
<out>/volume.packed (the packed used-cluster stream of the imaged volume). Read-only on the input.
Framing established from VProImaging.dll (Ghost 15) and verified on sample images (docs/FORMAT.md):
  block 0: 0x60 header + raw payload; blocks N>0: 0x60 header, then sub-streams of
  {u24 clen, u24 ulen, LZO1X[clen]} up to header.clen; a u24 trailer gives the number of
  trailing zero bytes of the block's span that were not stored (sparse zeros), emitted here.
"""

import argparse
import ctypes
import os
import struct
import time

from v2i_open import lzo1x
from v2i_open.container import parse

lib = lzo1x._lib
BLK, HDR = 0x40000, 0x60
ZEROS = bytes(1 << 24)


def u24(b, o):
    return b[o] | b[o + 1] << 8 | b[o + 2] << 16


def decode_block(blk, index, sink):
    """Decode one 256 KiB physical block (index >= 1) and pass its logical bytes to sink.

    Returns the number of LZO sub-streams decoded. Raises ValueError on any framing or codec error.
    """
    if blk[:4] != b"$CAN" or struct.unpack_from("<I", blk, 0x30)[0] != index:
        raise ValueError(f"block {index}: bad header")
    span, clen_hdr = struct.unpack_from("<I", blk, 0x40)[0], struct.unpack_from("<I", blk, 0x48)[0]
    dst = ctypes.create_string_buffer(BLK)
    pos, produced, subs = HDR, 0, 0
    while pos < HDR + clen_hdr:
        clen, ulen = u24(blk, pos), u24(blk, pos + 3)
        n = ctypes.c_size_t(BLK)
        rc = lib.lzo1x_decompress_safe(blk[pos + 6 : pos + 6 + clen], clen, dst, ctypes.byref(n), None)
        if rc != 0 or n.value != ulen:
            raise ValueError(f"block {index} sub-stream at +{pos:#x}: lzo rc={rc} out={n.value} expected {ulen}")
        sink(dst.raw[:ulen])
        subs += 1
        pos += 6 + clen
        produced += ulen
    trailer = u24(blk, pos) if pos + 3 <= BLK else 0
    if produced + trailer != span:
        raise ValueError(f"block {index}: produced {produced} + trailer {trailer} != span {span}")
    if trailer:
        sink(ZEROS[:trailer])
    return subs


class LogicalWriter:
    """Receives the logical stream sequentially and routes byte ranges to output files."""

    def __init__(self, ranges):
        self.ranges = sorted(ranges, key=lambda r: r[0])  # (start, size, fileobj)
        self.pos = 0

    def feed(self, chunk):
        start, end = self.pos, self.pos + len(chunk)
        for rs, rsize, fh in self.ranges:
            re_ = rs + rsize
            lo, hi = max(start, rs), min(end, re_)
            if lo < hi:
                fh.write(chunk[lo - start : hi - start])
        self.pos = end


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image")
    ap.add_argument("out")
    ap.add_argument("--max-blocks", type=int, default=0, help="stop after this many physical blocks (test runs)")
    a = ap.parse_args()
    info = parse(a.image)
    ents = {e["id"]: e for e in info["entries"]}
    os.makedirs(a.out, exist_ok=True)
    files = {
        k: open(os.path.join(a.out, name), "wb")
        for k, name in ((3, "track0.bin"), (7, "entry7_map.bin"), (8, "volume.packed"))
    }
    writer = LogicalWriter([(ents[k]["logical"], ents[k]["size"], fh) for k, fh in files.items()])
    nblocks = info["blocks"] if not a.max_blocks else min(a.max_blocks, info["blocks"])
    t0 = time.time()
    subs = 0
    with open(a.image, "rb") as f:
        blk = f.read(BLK)
        writer.feed(blk[HDR:])
        for b in range(1, nblocks):
            blk = f.read(BLK)
            if len(blk) < BLK:
                raise SystemExit(f"short read at block {b}")
            try:
                subs += decode_block(blk, b, writer.feed)
            except ValueError as exc:
                raise SystemExit(str(exc)) from exc
            if b % 2000 == 0:
                dt = time.time() - t0
                print(
                    f"  block {b}/{nblocks} logical={writer.pos / 1e9:.2f} GB  "
                    f"{b * BLK / 1e6 / dt:.1f} MB/s in, {writer.pos / 1e6 / dt:.1f} MB/s out",
                    flush=True,
                )
    for fh in files.values():
        fh.close()
    print(f"done: {nblocks} blocks, {subs} sub-streams, logical {writer.pos} bytes in {time.time() - t0:.0f}s")
    for k, name in ((3, "track0.bin"), (7, "entry7_map.bin"), (8, "volume.packed")):
        print(f"  {name}: {os.path.getsize(os.path.join(a.out, name))} bytes (entry size {ents[k]['size']})")


if __name__ == "__main__":
    main()
