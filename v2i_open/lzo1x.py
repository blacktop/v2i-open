"""LZO1X via the system liblzo2 (ctypes).

decompress(src, max_out) -> bytes. Raises LzoError on malformed input or on an output
that would exceed max_out. compress() exists only for the self-test.
"""

import ctypes
import ctypes.util

_LIB_CANDIDATES = ("/opt/homebrew/lib/liblzo2.2.dylib", "liblzo2.so.2", ctypes.util.find_library("lzo2"))


class LzoError(ValueError):
    pass


def _load():
    for cand in _LIB_CANDIDATES:
        if cand:
            try:
                lib = ctypes.CDLL(cand)
                break
            except OSError:
                continue
    else:
        raise LzoError("liblzo2 not found; install with: brew install lzo")
    lib.lzo_version.restype = ctypes.c_uint
    lib.__lzo_init_v2.restype = ctypes.c_int
    lib.__lzo_init_v2.argtypes = [ctypes.c_uint] + [ctypes.c_int] * 9
    rc = lib.__lzo_init_v2(lib.lzo_version(), -1, -1, -1, -1, -1, -1, -1, -1, -1)
    if rc != 0:
        raise LzoError(f"lzo_init failed: {rc}")
    lib.lzo1x_decompress_safe.restype = ctypes.c_int
    lib.lzo1x_decompress_safe.argtypes = [
        ctypes.c_char_p,
        ctypes.c_size_t,
        ctypes.c_char_p,
        ctypes.POINTER(ctypes.c_size_t),
        ctypes.c_void_p,
    ]
    lib.lzo1x_1_compress.restype = ctypes.c_int
    lib.lzo1x_1_compress.argtypes = [
        ctypes.c_char_p,
        ctypes.c_size_t,
        ctypes.c_char_p,
        ctypes.POINTER(ctypes.c_size_t),
        ctypes.c_void_p,
    ]
    return lib


_lib = _load()
_OK, _E_INPUT_OVERRUN, _E_OUTPUT_OVERRUN, _E_LOOKBEHIND, _E_EOF_NOT_FOUND, _E_INPUT_NOT_CONSUMED = 0, -4, -5, -6, -7, -8
_ERRORS = {
    -1: "error",
    -2: "out of memory",
    -3: "not compressible",
    -4: "input overrun",
    -5: "output overrun",
    -6: "lookbehind overrun",
    -7: "eof not found",
    -8: "input not consumed",
}


def decompress(src, max_out):
    """Decompress one LZO1X stream; max_out bounds the destination buffer."""
    dst = ctypes.create_string_buffer(max_out)
    dst_len = ctypes.c_size_t(max_out)
    rc = _lib.lzo1x_decompress_safe(bytes(src), len(src), dst, ctypes.byref(dst_len), None)
    if rc != _OK:
        raise LzoError(f"lzo1x_decompress_safe: {_ERRORS.get(rc, rc)} (produced {dst_len.value} bytes)")
    return dst.raw[: dst_len.value]


def compress(data):
    wrk = ctypes.create_string_buffer(16384 * 8)
    dst = ctypes.create_string_buffer(len(data) + len(data) // 16 + 64 + 3)
    dst_len = ctypes.c_size_t(len(dst))
    rc = _lib.lzo1x_1_compress(bytes(data), len(data), dst, ctypes.byref(dst_len), wrk)
    if rc != _OK:
        raise LzoError(f"lzo1x_1_compress: {_ERRORS.get(rc, rc)}")
    return dst.raw[: dst_len.value]


if __name__ == "__main__":
    import os

    sample = (b"FILE0" + bytes(1019)) * 40 + os.urandom(3000) + b"NTFS    " * 64
    packed = compress(sample)
    assert decompress(packed, len(sample)) == sample
    print(f"self-test OK: {len(sample)} -> {len(packed)} -> {len(sample)} bytes")
