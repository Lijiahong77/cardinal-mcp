#!/usr/bin/env python3
"""Read and write Cardinal patch files (.vcv), supporting BOTH on-disk formats.

Why two formats?
----------------
Cardinal (a fork of VCV Rack) stores a "patch" (the whole rack: modules, cables,
view state) on disk in one of two shapes:

  1. Plain JSON  ......... what we hand-write and what the official `resources/`
                          example patches ship as.
  2. Rack archive ........ a pax tar wrapped in a zstd stream, with a single
                          member `patch.json` inside. This is what Cardinal
                          itself writes when you press Ctrl+S. See Rack's
                          `src/system.cpp` (`archive_write_set_format_pax_restricted`
                          + `archive_write_add_filter_zstd`).

`read_patch()` auto-detects which one it got and always returns a plain Python
dict. `write_patch()` defaults to plain JSON (Cardinal reads both just fine).

The OSC `/load` command, however, only accepts the *archive* form — so callers
that want to push a patch into a running Cardinal must run `archive_bytes()`
first. See `cardinal_mcp.load_patch()` for that usage.

No third-party deps except `zstandard` for the decompression/compression step.
"""

import io
import json
import os
import tarfile

import zstandard


# A zstd stream always starts with this 4-byte magic number. We use it to
# tell an archive from a plain JSON file without trying to parse anything.
ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"

# The single file name Rack puts inside the tar archive. Cardinal hard-codes
# this; if a tar does not contain it, the patch is malformed.
PATCH_ENTRY = "patch.json"


def is_archive(raw):
    """Return True if `raw` bytes look like a zstd-compressed Rack archive.

    We only check the 4-byte magic header — cheap and sufficient because the
    one-byte prefix of a JSON file (`{`) can never collide with the zstd magic.
    """
    return raw[:4] == ZSTD_MAGIC


def read_patch(path):
    """Load a .vcv file from disk and return it as a plain patch dict.

    Accepts both formats transparently:
      - plain JSON   -> json.loads
      - tar+zstd     -> decompress, open the tar, read `patch.json` member

    The returned dict has (at least) the keys: version, zoom, gridOffset,
    modules (list), cables (list). See `cardinal_mcp.patch_info()` / `read_live()`.
    """
    with open(path, "rb") as f:
        raw = f.read()
    if not is_archive(raw):
        # utf-8-sig tolerates a BOM that some editors prepend.
        return json.loads(raw.decode("utf-8-sig"))
    # `max_output_size` is a safety cap so a corrupted/lying header cannot make
    # zstandard allocate gigabytes. 50 MB is far above any real patch.
    data = zstandard.ZstdDecompressor().decompress(raw, max_output_size=50_000_000)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as tf:
        names = tf.getnames()
        # Match by base name in case the tar member has a directory prefix.
        entry = next((n for n in names if os.path.basename(n) == PATCH_ENTRY), None)
        if entry is None:
            raise ValueError(f"archive has no {PATCH_ENTRY}: {names}")
        return json.loads(tf.extractfile(entry).read().decode("utf-8-sig"))


def archive_bytes(raw):
    """Pack plain-JSON *bytes* into a Rack archive (pax tar + zstd).

    If `raw` is already an archive, it is returned unchanged (idempotent) so
    callers can pass anything through this function safely.

    The Python `tarfile` module produces pax format by default, which matches
    what Rack expects. We set fixed mtime=0 / mode 0o644 so the bytes are
    reproducible (same input -> same output), which keeps `git diff` clean.
    """
    if is_archive(raw):
        return raw
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.PAX_FORMAT) as tf:
        info = tarfile.TarInfo(PATCH_ENTRY)
        info.size = len(raw)
        info.mtime = 0
        info.mode = 0o644
        # Add the JSON as a file *object* (not a path) so we never touch disk.
        tf.addfile(info, io.BytesIO(raw))
    # level=3 is Rack's default zstd level; keeps the blob small and loadable.
    return zstandard.ZstdCompressor(level=3).compress(buf.getvalue())


def write_patch(path, patch, as_archive=False):
    """Write a patch dict back to disk.

    - as_archive=False (default) -> plain JSON. Easiest to `git diff` and hand-edit.
    - as_archive=True            -> the Cardinal-native tar+zstd blob. Use this only
                                    when you specifically need a byte-identical
                                    "saved by Cardinal" file.

    `indent=2` keeps the JSON human-readable; `ensure_ascii=False` preserves any
    non-ASCII (e.g. labels in the TextEditor module).
    """
    raw = json.dumps(patch, ensure_ascii=False, indent=2).encode("utf-8")
    with open(path, "wb") as f:
        f.write(archive_bytes(raw) if as_archive else raw)
    return path


def describe(path):
    """Return a small diagnostic dict about a file's format.

    Useful for the command line / debugging — tells you whether a patch is
    plain JSON or a tar+zstd archive and how many bytes it occupies.
    """
    with open(path, "rb") as f:
        raw = f.read()
    if is_archive(raw):
        data = zstandard.ZstdDecompressor().decompress(raw, max_output_size=50_000_000)
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as tf:
            return {"format": "tar+zstd (Cardinal archive)", "entries": tf.getnames(),
                    "bytes": len(raw)}
    return {"format": "plain JSON", "bytes": len(raw)}
