#!/usr/bin/env python3
"""Expose an extracted .v2i volume as a read-only block device (Linux) and mount it.

Inputs: entry7_map.bin (bitmap tree) and volume.packed (used sectors in run order), as written
by v2i_open.extract. Builds a device-mapper table: 'linear' targets onto a read-only loop device
over volume.packed for every run, 'zero' targets for the gaps. Nothing is written to the inputs.
Usage: sudo python3 -m v2i_open.mount <dir> <name> [--mount /mnt/point] [--umount]
"""

import argparse
import os
import subprocess

from v2i_open import bitmap as bm


def run(cmd, **kw):
    r = subprocess.run(cmd, text=True, capture_output=True, **kw)
    if r.returncode:
        raise SystemExit(f"{' '.join(cmd)} failed: {r.stderr.strip() or r.stdout.strip()}")
    return r.stdout.strip()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dir")
    ap.add_argument("name")
    ap.add_argument("--mount", metavar="DIR")
    ap.add_argument("--umount", action="store_true")
    a = ap.parse_args()
    dev = f"/dev/mapper/{a.name}"
    if a.umount:
        subprocess.run(["umount", dev])
        subprocess.run(["dmsetup", "remove", a.name])
        for line in run(["losetup", "-j", os.path.join(a.dir, "volume.packed")]).splitlines():
            subprocess.run(["losetup", "-d", line.split(":")[0]])
        print("released")
        return
    m = open(os.path.join(a.dir, "entry7_map.bin"), "rb").read()
    runs, total_sectors = bm.parse_runs(m)
    packed = os.path.join(a.dir, "volume.packed")
    need = sum(length for _, length in runs) * 512
    have = os.path.getsize(packed)
    if have != need:
        raise SystemExit(f"volume.packed is {have} bytes, map needs {need}")
    loop = run(["losetup", "-r", "-f", "--show", packed])
    table = []
    pos = 0
    cur = 0
    for start, length in runs:
        if start > cur:
            table.append(f"{cur} {start - cur} zero")
        table.append(f"{start} {length} linear {loop} {pos}")
        pos += length
        cur = start + length
    if cur < total_sectors:
        table.append(f"{cur} {total_sectors - cur} zero")
    run(["dmsetup", "create", a.name, "--readonly"], input="\n".join(table) + "\n")
    print(
        f"{dev}: {total_sectors} sectors ({total_sectors * 512 / 1e9:.2f} GB), "
        f"{len(runs)} runs mapped from {loop}, {len(table)} table lines"
    )
    if a.mount:
        os.makedirs(a.mount, exist_ok=True)
        run(["mount", "-t", "ntfs3", "-o", "ro,noatime", dev, a.mount])
        print(f"mounted read-only at {a.mount}")
        print(run(["df", "-h", a.mount]))


if __name__ == "__main__":
    main()
