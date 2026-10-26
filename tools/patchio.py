#!/usr/bin/env python3
"""Read and write Cardinal patch files (.vcv), supporting BOTH on-disk formats.

Why two formats?
----------------
Cardinal (a fork of VCV Rack) stores a "patch" (the whole rack: modules, cables,
view state) on disk in one of two shapes:

  1. Plain JSON  ......... what we hand-write and what the official `resources/`
                          example patches ship as.
  2. Rack archive ........ a pax tar wrapped in a zstd stream, containing
                          `patch.json` and optionally module resource members.
                          This is what Cardinal writes when you press Ctrl+S.
                          See Rack's `src/system.cpp`
                          (`archive_write_set_format_pax_restricted`
                          + `archive_write_add_filter_zstd`).

`read_patch()` auto-detects the format and returns an ordinary dict.
`write_patch()` preserves an existing target's format and archive resources;
new targets default to JSON. Writes use verified, synced sibling temporaries
and os.replace, with an exclusive version backup before replacing a target.
This is failure-safe file replacement, not a read-modify-write transaction:
GUI saves and stale callers are not serialized or merged.

The OSC `/load` command, however, only accepts the *archive* form — so callers
that want to push a patch into a running Cardinal must run `archive_bytes()`
first. See `cardinal_mcp.load_patch()` for that usage.

No third-party deps except `zstandard` for the decompression/compression step.
"""

import copy
import io
import json
import os
import tarfile
import uuid
from pathlib import Path

import zstandard


# A zstd stream always starts with this 4-byte magic number. We use it to
# tell an archive from a plain JSON file without trying to parse anything.
ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"

# The single file name Rack puts inside the tar archive. Cardinal hard-codes
# this; if a tar does not contain it, the patch is malformed.
PATCH_ENTRY = "patch.json"

# Public constants allow deliberately small caps in offline tests. Byte limits
# retain the original 50 MB design, now enforced on actual streamed output.
MAX_RAW_BYTES = 50_000_000
MAX_ARCHIVE_BYTES = 50_000_000
MAX_JSON_BYTES = 50_000_000
# Includes physical PAX/GNU headers as well as visible members.
MAX_MEMBERS = 10_000
_WINDOWS_RESERVED = {"con", "prn", "aux", "nul", "conin$", "conout$"} | {
    f"{prefix}{n}" for prefix in ("com", "lpt") for n in range(1, 10)
}


def _read_limited(stream, limit, label):
    chunks = []
    total = 0
    while True:
        chunk = stream.read(min(65536, limit - total + 1))
        if not chunk:
            return b"".join(chunks)
        total += len(chunk)
        if total > limit:
            raise ValueError(f"{label} exceeds {limit} bytes")
        chunks.append(chunk)


def _read_raw(path):
    with open(path, "rb") as f:
        return _read_limited(f, MAX_RAW_BYTES, "patch file")


def _json_dict(raw):
    if len(raw) > MAX_JSON_BYTES:
        raise ValueError("patch JSON exceeds byte limit")
    result = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(result, dict):
        raise ValueError("patch JSON must be an object")
    return result


class _ArchiveBuffer(io.BytesIO):
    def write(self, data):
        if self.tell() + len(data) > MAX_ARCHIVE_BYTES:
            raise ValueError("archive exceeds decompressed byte limit")
        return super().write(data)


def is_archive(raw):
    """Return True if `raw` bytes look like a zstd-compressed Rack archive.

    We only check the 4-byte magic header — cheap and sufficient because the
    one-byte prefix of a JSON file (`{`) can never collide with the zstd magic.
    """
    return raw[:4] == ZSTD_MAGIC


class _BoundedTarInfo(tarfile.TarInfo):
    def _proc_member(self, tf):
        # Count PAX/GNU extension records before tarfile recursively hides them.
        count = getattr(tf, "_patchio_headers", 0) + 1
        tf._patchio_headers = count
        if count > MAX_MEMBERS:
            raise ValueError("archive exceeds physical tar header count limit")
        depth = getattr(tf, "_patchio_depth", 0) + 1
        if depth > 64:
            raise ValueError("excessive tar extension nesting")
        tf._patchio_depth = depth
        try:
            return super()._proc_member(tf)
        finally:
            tf._patchio_depth -= 1


def _archive_members(raw):
    if len(raw) > MAX_RAW_BYTES:
        raise ValueError("compressed patch exceeds byte limit")
    with zstandard.ZstdDecompressor().stream_reader(io.BytesIO(raw), read_across_frames=True) as stream:
        data = _read_limited(stream, MAX_ARCHIVE_BYTES, "decompressed archive")
    # stream_reader enforces the output cap but accepts incomplete final frames.
    # Only AFTER that bounded pass, verify EOF with a second incremental pass.
    # No input capable of producing > MAX_ARCHIVE_BYTES reaches this verifier.
    verifier = zstandard.ZstdDecompressor().decompressobj()
    for offset in range(0, len(raw), 16384):
        verifier.decompress(raw[offset:offset + 16384])
        if verifier.eof:
            if verifier.unused_data or offset + 16384 < len(raw):
                raise ValueError("trailing or concatenated zstd frames")
            break
    if not verifier.eof:
        raise ValueError("truncated zstd frame")
    members = []
    seen = {}
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:", tarinfo=_BoundedTarInfo) as tf:
        for info in tf:
            if len(members) >= MAX_MEMBERS:
                raise ValueError("archive exceeds member count limit")
            if info.size < 0 or info.size > MAX_ARCHIVE_BYTES:
                raise ValueError("archive member exceeds byte limit")
            name = info.name
            # Rack uses a root '.' directory and './' member prefixes. Use a
            # validation-only spelling; retain TarInfo.name for rearchiving.
            relative = name[2:] if name.startswith("./") else name
            parts = [] if name in (".", "./") and info.isdir() else relative.split("/")
            if (not name or "\\" in name or ":" in name or
                    any(ord(c) < 32 or c in '<>"|?*' for c in name) or
                    any(part in ("", ".", "..") or part.endswith((".", " "))
                        or part.split(".", 1)[0].casefold() in _WINDOWS_RESERVED for part in parts)):
                raise ValueError(f"unsafe archive member: {name!r}")
            if (info.type not in (tarfile.REGTYPE, tarfile.AREGTYPE, tarfile.DIRTYPE)
                    or info.sparse is not None or info.linkname
                    or any(k.startswith("GNU.sparse") for k in info.pax_headers)):
                raise ValueError(f"unsupported archive member: {name!r}")
            key = "/".join(parts).casefold()
            if key in seen:
                raise ValueError(f"duplicate archive member: {name!r}")
            if any(seen.get("/".join(parts[:i]).casefold()) is False for i in range(1, len(parts))):
                raise ValueError(f"file used as archive directory: {name!r}")
            if not info.isdir() and any(n.startswith(key + "/") for n in seen):
                raise ValueError(f"archive directory replaced by file: {name!r}")
            seen[key] = info.isdir()
            if parts and parts[-1].casefold() == PATCH_ENTRY and (parts[-1] != PATCH_ENTRY or not info.isfile()):
                raise ValueError("ambiguous or non-file patch.json")
            if parts and parts[-1] == PATCH_ENTRY and info.size > MAX_JSON_BYTES:
                raise ValueError("patch JSON member exceeds byte limit")
            payload = b""
            if info.isfile():
                stream = tf.extractfile(info)
                if stream is None:
                    raise ValueError("unreadable archive member")
                with stream:
                    payload = _read_limited(stream, MAX_ARCHIVE_BYTES, "archive member")
                    if len(payload) != info.size:
                        raise ValueError("truncated archive member")
            members.append((info, payload))
        tail = data[tf.offset:]
        if len(tail) < 1024 or len(tail) % 512 or any(tail):
            raise ValueError("missing tar terminator or nonzero trailing archive data")
    entries = [i for i, (info, _) in enumerate(members)
               if info.name.rsplit("/", 1)[-1] == PATCH_ENTRY]
    if len(entries) != 1:
        raise ValueError("archive requires exactly one patch.json")
    _json_dict(members[entries[0]][1])
    return members, entries[0]


def _rewrite_archive(members, entry, raw):
    buf = _ArchiveBuffer()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.PAX_FORMAT) as tf:
        for i, (info, payload) in enumerate(members):
            info = copy.deepcopy(info)
            if i == entry:
                payload = raw
                info.size = len(raw)
                if "size" in info.pax_headers:
                    info.pax_headers["size"] = str(info.size)
            tf.addfile(info, io.BytesIO(payload))
    return zstandard.ZstdCompressor(level=3).compress(buf.getvalue())


def read_patch(path):
    """Read JSON or an archive into a plain dict; a single nested entry is accepted.

    Keeping a nested name is compatibility with historical Python readers, not
    a claim that Cardinal's engine loads that name.
    """
    raw = _read_raw(path)
    return _decode_patch(raw)


def _decode_patch(raw):
    if len(raw) > MAX_RAW_BYTES:
        raise ValueError("patch file exceeds byte limit")
    if is_archive(raw):
        members, entry = _archive_members(raw)
        raw = members[entry][1]
    return _json_dict(raw)


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
    if len(raw) > MAX_RAW_BYTES:
        raise ValueError("plain input exceeds byte limit")
    _json_dict(raw)
    buf = _ArchiveBuffer()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.PAX_FORMAT) as tf:
        info = tarfile.TarInfo(PATCH_ENTRY)
        info.size = len(raw)
        info.mtime = 0
        info.mode = 0o644
        # Add the JSON as a file *object* (not a path) so we never touch disk.
        tf.addfile(info, io.BytesIO(raw))
    # level=3 is Rack's default zstd level; keeps the blob small and loadable.
    return zstandard.ZstdCompressor(level=3).compress(buf.getvalue())


def _write_checked(path, data):
    """Create exclusively, sync and compare all bytes before any commit."""
    # Opening is outside the cleanup block: an exclusive-name collision is
    # somebody else's file and must never be removed.
    f = open(path, "xb")
    try:
        with f:
            if f.write(data) != len(data):
                raise OSError("short patch write")
            f.flush()
            os.fsync(f.fileno())
        with open(path, "rb") as check:
            if check.read(len(data) + 1) != data:
                raise OSError("patch write verification failed")
    except BaseException:
        Path(path).unlink(missing_ok=True)
        raise


def _atomic_write(path, output):
    target = Path(path)
    temporary = target.with_name("." + target.name + "." + uuid.uuid4().hex + ".tmp")
    _write_checked(temporary, output)
    try:
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def write_patch(path, patch, as_archive=None):
    """Atomically write a dict, preserving an existing target's format by default.

    True retains existing archive resources; False refuses to discard any
    extra archive members. New targets default to JSON. Existing targets get
    exclusive, durable sibling versions: <name>.bak-patchio-<uuid>.
    Only this target supplies archive resources; a dict has no source context.
    """
    raw = json.dumps(patch, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8")
    _json_dict(raw)
    target = Path(path)
    previous = _read_raw(path) if target.exists() else None
    members = None
    entry = 0
    if previous is not None and is_archive(previous):
        members, entry = _archive_members(previous)
        if as_archive is False and len(members) != 1:
            raise ValueError("refusing JSON conversion: archive has extra resources")
    use_archive = as_archive is True or (as_archive is None and members is not None)
    if use_archive:
        output = _rewrite_archive(members, entry, raw) if members is not None else archive_bytes(raw)
    else:
        output = raw
    _decode_patch(output)
    if previous is not None:
        backup = target.with_name(target.name + ".bak-patchio-" + uuid.uuid4().hex)
        _write_checked(backup, previous)
    _atomic_write(path, output)
    return path


def describe(path):
    """Return a small diagnostic dict about a file's format.

    Useful for the command line / debugging — tells you whether a patch is
    plain JSON or a tar+zstd archive and how many bytes it occupies.
    """
    raw = _read_raw(path)
    if is_archive(raw):
        members, _ = _archive_members(raw)
        return {"format": "tar+zstd (Cardinal archive)",
                "entries": [m.name for m, _ in members], "bytes": len(raw)}
    _json_dict(raw)
    return {"format": "plain JSON", "bytes": len(raw)}
