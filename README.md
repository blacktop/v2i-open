# v2i-open

Open **Norton Ghost / PowerQuest `.v2i` disk images** without Norton Ghost: parse the container, extract
the volume, decode the used-sector map, and mount the result as a read-only NTFS volume on Linux.
Pure Python 3 over the system LZO library. Read-only on the images.

Ghost 9 through 15 (2004–2013) wrote sector-based backups in this format, and Symantec discontinued the
product and its *Recovery Point Browser* years ago. The format was never documented. `docs/FORMAT.md` is
the result of reverse-engineering it from the Ghost 15 engine library and verifying every structure
against real images.

## Install

```sh
brew install lzo            # macOS;  Debian/Ubuntu: apt install liblzo2-2
uv sync                     # or just run the modules with python3 >= 3.10
```

## Usage

```sh
# 1. What is in the image? (container layout, entries, chunk index; prints no contents)
python3 -m v2i_open.container image.v2i

# 2. Extract: track0.bin (raw MBR track), entry7_map.bin (used-sector map), volume.packed (used sectors)
python3 -m v2i_open.extract image.v2i out/

# 3. Check the map against the packed stream
python3 -m v2i_open.bitmap out/entry7_map.bin --packed-size "$(stat -c %s out/volume.packed)"

# 4. Linux: expose the volume as a read-only block device and mount it
sudo python3 -m v2i_open.mount out/ ghostvol --mount /mnt/ghost
sudo python3 -m v2i_open.mount out/ ghostvol --umount
```

Step 4 builds a device-mapper table of `linear` targets over a read-only loop device for every used run
and `zero` targets for the gaps, so the full-size volume appears without writing a full-size file.
Everything is mounted read-only; the images and the extracted files are never written to.

Throughput is the LZO decoder's: roughly 50 MB/s of output per core in Python, so a 30 GB image takes
about fifteen minutes.

## Status

Verified on four Ghost 10-era images (27–93 GB, header version 3.4.8): every sub-stream decodes to its
declared length, every map walks to its last byte, and the map's run total equals the packed stream's
size exactly. Not yet handled: incremental images (`.iv2i`), encrypted images, and the `.fbf`
file-and-folder backups. The same engine library contains readers for all three.

## Tests

```sh
python3 -m unittest discover -s tests -v
```

The tests use synthetic containers, maps and LZO blocks, so they need no sample image.

## License

MIT.
