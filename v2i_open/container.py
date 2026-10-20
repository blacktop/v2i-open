#!/usr/bin/env python3
"""Container parser for Norton Ghost / PowerQuest .v2i images (read-only).

Established from samples (Ghost 10-12 era, header version 3.4.8):
  0x00  '$CAN' container header, 0x60 bytes; u32 @0x78 = file size in 256 KiB blocks.
  0x60  '$CDH' directory header; u32 len @+0x0c; u64 logical total @+0x10.
  0xc0  table of increasing u64 logical positions (chunk boundaries), padded with the total.
  then  '$CDE' directory entries: u32 len, u32 id, u32 parent, u32 type tag, u32 pad,
        u64 logical offset, u64 size, ...  Logical offset -> file offset = +0x60.
Entries seen: '$PQI' product/computer record, 0x7e00-byte track 0 (raw MBR), 'PHDR',
two 12-byte records, a ~300 KB compressed metadata stream, and the compressed volume stream.
Compressed streams are decoded by v2i_open.extract. Nothing from inside the image is printed
except structure, sizes, and signature checks.
"""

import argparse
import hashlib
import re
import struct
import sys

SHIFT = 0x60
MBR_SIG = b"\x55\xaa"
TAG_RE = re.compile(rb"\$[A-Z]{3}")


def u32(b, o):
    return struct.unpack_from("<I", b, o)[0]


def u64(b, o):
    return struct.unpack_from("<Q", b, o)[0]


def tag_name(v):
    raw = struct.pack("<I", v)
    return raw.decode("ascii") if TAG_RE.fullmatch(raw) or raw.isalpha() else f"{v:#x}"


def parse(path):
    with open(path, "rb") as f:
        head = f.read(1 << 20)
        f.seek(0, 2)
        size = f.tell()
    if head[:4] != b"$CAN" or head[0x60:0x64] != b"$CDH":
        raise SystemExit("not a $CAN/$CDH v2i container")
    blocks = u32(head, 0x78)
    cdh_len = u32(head, 0x6C)
    total = u64(head, 0x70)
    table, off = [], 0xC0
    while off + 8 <= len(head):
        v = u64(head, off)
        if table and v <= table[-1]:
            break
        table.append(v)
        off += 8
    pad_end = off
    while u64(head, pad_end) == total:
        pad_end += 8
    off = pad_end
    while head[off] == 0:
        off += 1
    entries = []
    while off + 8 <= len(head) and head[off : off + 4] == b"$CDE":
        ln = u32(head, off + 4)
        entries.append(
            {
                "id": u32(head, off + 8),
                "parent": u32(head, off + 12),
                "type": tag_name(u32(head, off + 16)),
                "logical": u64(head, off + 24),
                "size": u64(head, off + 32),
                "len": ln,
            }
        )
        off += ln
    return {
        "size": size,
        "blocks": blocks,
        "block_check": blocks * 262144 == size,
        "cdh_len": cdh_len,
        "total": total,
        "table": table,
        "entries": entries,
        "head": head,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image", nargs="+")
    ap.add_argument("--extract-track0", metavar="OUT", help="write the raw 0x7e00-byte track-0 entry to OUT")
    args = ap.parse_args()
    for n, path in enumerate(args.image, 1):
        info = parse(path)
        print(
            f"== image {n}: size={info['size']} ({info['size'] / 1e9:.2f} GB) "
            f"blocks256K={info['blocks']} exact={info['block_check']} logical_total={info['total'] / 1e9:.2f} GB"
        )
        t = info["table"]
        d = [b - a for a, b in zip(t, t[1:], strict=False)]
        print(
            f"   chunk table: {len(t)} entries, mean span {sum(d) // len(d) / 1e6:.1f} MB, "
            f"min {min(d) / 1e6:.2f} MB, max {max(d) / 1e6:.1f} MB"
        )
        for e in info["entries"]:
            fo = e["logical"] + SHIFT
            note = ""
            if e["size"] == 0x7E00:
                sig = info["head"][fo + 0x1FE : fo + 0x200]
                note = f"track0 raw, MBR signature {'OK' if sig == MBR_SIG else 'MISSING'}"
                if args.extract_track0:
                    with open(args.extract_track0, "wb") as out:
                        out.write(info["head"][fo : fo + 0x7E00])
                    digest = hashlib.sha256(info["head"][fo : fo + 0x7E00]).hexdigest()[:16]
                    note += f", written to {args.extract_track0} sha256={digest}"
            elif e["size"] > 1 << 30:
                note = "packed volume stream (see v2i_open.extract)"
            elif e["size"] > 1 << 16:
                note = "used-sector map (see v2i_open.bitmap)"
            print(
                f"   entry {e['id']:2d} parent={e['parent']} type={e['type']:>10} logical=0x{e['logical']:x} "
                f"file=0x{fo:x} size={e['size']} {note}"
            )


if __name__ == "__main__":
    sys.exit(main())
