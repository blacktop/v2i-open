# The Norton Ghost `.v2i` format

Established from `VProImaging.dll` (Norton Ghost 15, the engine shared with Symantec System Recovery)
and verified byte-for-byte on Ghost 10-era images. All integers are little-endian. Sizes in bytes unless
noted. Sectors are 512 bytes.

## 1. Physical layout: 256 KiB `$CAN` blocks

An image file is an exact multiple of 0x40000 bytes. Every block begins with a 0x60-byte header:

| Offset | Size | Meaning |
| --- | --- | --- |
| 0x00 | 4 | `$CAN` |
| 0x04 | 4 | header length (0x60) |
| 0x08 | 4 | header length (0x60) |
| 0x0C | 4 | 0x02020000 |
| 0x10 | 4 | image/creation identifier (constant across the file) |
| 0x14 | 4 | format version, 0x00080403 = 3.4.8 (TestDisk carves on the newer 0x00080413) |
| 0x1C | 4 | block size, 0x40000 |
| 0x20 | 4 | block size, 0x40000 |
| 0x30 | 4 | block index |
| 0x34 | 4 | block kind: 2 for block 0, 1 for data blocks |
| 0x38 | 8 | logical offset of this block's span |
| 0x40 | 4 | span: logical bytes covered by this block (block 0: raw payload length 0x3FFA0) |
| 0x48 | 4 | compressed payload length (data blocks) |
| 0x54 | 4 | previous block's span (back-link) |
| 0x58 | 4 | CRC32 of header bytes 0x00..0x57 |
| 0x5C | 4 | CRC32 of the payload |

The first block's header (file offset 0) is the file header; its payload is stored **raw** and starts the
logical stream, so logical offset *L* of anything inside block 0 is at file offset *L* + 0x60.

### Data blocks (index ≥ 1)

The payload is a sequence of LZO sub-streams followed by a 3-byte trailer:

```
repeat while consumed < header.compressed_length:
    u24 clen      compressed length
    u24 ulen      uncompressed length (≤ 0x3FF9D)
    byte[clen]    LZO1X stream (standard lzo1x_decompress_safe; no dictionary carried between streams)
u24 trailer       number of trailing zero bytes of the span that were NOT stored
```

The block's logical content is the concatenation of the decoded sub-streams followed by `trailer` zero
bytes; `sum(ulen) + trailer == span` always. The trailer is a sparse-zero optimisation and routinely
accounts for a third of the span on real images, so a decoder that ignores it produces a short stream.
The 3 bytes are reserved out of the payload capacity, which is why the maximum sub-stream `ulen` is
0x3FFA0 − 3. The engine names these classes `LzoDecompressorFSF` (fixed-size frame); the `VSF`
variant and a zlib codec exist in the engine but were not seen in the images.

## 2. Logical stream: directory

Block 0's payload holds, at logical offsets:

| Logical | Content |
| --- | --- |
| 0x00 | `$CDH` directory header: u32 length at +0x0C; u64 logical total at +0x10 |
| 0x60 | chunk index: increasing u64 logical offsets, one per 16 physical blocks (4 MiB of file), padded with the total up to 0x10000 |
| 0x10064 | `$CDE` entries: `u32 len, u32 id, u32 parent, u32 type tag, u32 0, u64 logical offset, u64 size, ...` |

Entries seen (ids 1–8): a root; a `$PQI` record (product name, computer name, UTF-16); **track 0**, 0x7E00
bytes raw (the MBR and the rest of the first track); a `PHDR` record with the exclusion pattern; two 12-byte
records; the **used-sector map** (entry 7, ~100–350 KB); and the **packed volume** (entry 8, size = used
bytes of the volume). Entry sizes are logical bytes; entries 2–6 lie in block 0 and can be read raw.

## 3. Entry 7: the used-sector map (serialized bitmap tree)

A 0x20-byte header (`0x8314` signature at +0 and +0x12, header length 0x20 at +0x02 and +0x10) then a
tree. Every node is `u8 type, u16 header_length, header[header_length]` followed by its body:

| Type | Header | Body |
| --- | --- | --- |
| 0x02 tree | `u64 span, u16 nchildren, u64 child_span` (header_length 0x12) | the children, in order; child *i* starts at `base + i * child_span` |
| 0x00 const-free | `uN span` | none |
| 0x01 const-used | `uN span` | none |
| 0x10 / 0x20 / 0x40 run list | `uN span` | `u8 cluster_shift, u16 count, (uN offset, uN length) x count` |
| 0x03 bitmap | `uN span` | `ceil(span / 8)` bytes, one bit per sector, LSB first |

`N` is the header length (2, 4 or 8 bytes) and also the width of the run-list integers. All spans, offsets
and lengths are in **sectors**; run offsets are relative to the node's own start. `cluster_shift` is the
file system's log2(sectors per cluster) and is informational. Observed trees: root = whole volume with
64 GiB children; then 4 GiB nodes with 256 MiB children; dense regions subdivide 256 MiB into 16 MiB
leaves. The runs, taken in tree order, ascend over the whole volume.

## 4. Entry 8: the packed volume

The volume's used sectors, concatenated in map order: packed byte `512*i` is the *i*-th used sector.
`sum(run lengths) * 512 == entry 8 size` exactly. Reconstruction is a sparse copy: for each run, copy
`length` sectors from the packed stream to volume sector `offset`. The map's root span is the volume's
sector count plus one. Free sectors are not stored and read as zero.

## 5. Companion files

`.sv2i`: a small UTF-16 XML catalogue (`SDO` root) listing the volumes of a backup set with image file
names, sizes, labels and drive letters. `.iv2i`: incremental images (not handled here). `.fbf`
(`SymBakUp 1.0`): Ghost's file-and-folder backup containers, LZO/zlib compressed, read by the same engine's
`FileBackup.dll` (not handled here).
