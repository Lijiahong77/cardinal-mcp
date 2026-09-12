#!/usr/bin/env python3
"""Cardinal patch 文件读写 —— 同时支持两种格式。

Cardinal 的 patch 有两种磁盘形态:
  1. 明文 JSON（我们手写的、以及官方 resources 里的示例）
  2. Rack 归档：pax tar + zstd，里面一个 patch.json
     （Cardinal 自己保存时写的格式，见 Rack src/system.cpp 的
      archive_write_set_format_pax_restricted + archive_write_add_filter_zstd）

读的时候自动识别，写的时候默认写明文 JSON（Cardinal 两种都能读）。
"""
import io
import json
import os
import tarfile

import zstandard

ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"
PATCH_ENTRY = "patch.json"


def is_archive(raw):
    return raw[:4] == ZSTD_MAGIC


def read_patch(path):
    """读 .vcv，返回 patch 字典。两种格式通吃。"""
    with open(path, "rb") as f:
        raw = f.read()
    if not is_archive(raw):
        return json.loads(raw.decode("utf-8-sig"))
    data = zstandard.ZstdDecompressor().decompress(raw, max_output_size=50_000_000)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as tf:
        names = tf.getnames()
        entry = next((n for n in names if os.path.basename(n) == PATCH_ENTRY), None)
        if entry is None:
            raise ValueError(f"归档里没有 {PATCH_ENTRY}: {names}")
        return json.loads(tf.extractfile(entry).read().decode("utf-8-sig"))


def archive_bytes(raw):
    """把明文 JSON 字节打包成 Rack 归档（tar+zstd）。"""
    if is_archive(raw):
        return raw
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.PAX_FORMAT) as tf:
        info = tarfile.TarInfo(PATCH_ENTRY)
        info.size = len(raw)
        info.mtime = 0
        info.mode = 0o644
        tf.addfile(info, io.BytesIO(raw))
    return zstandard.ZstdCompressor(level=3).compress(buf.getvalue())


def write_patch(path, patch, as_archive=False):
    """写回 patch 文件。as_archive=True 时写成 Cardinal 的归档格式。"""
    raw = json.dumps(patch, ensure_ascii=False, indent=2).encode("utf-8")
    with open(path, "wb") as f:
        f.write(archive_bytes(raw) if as_archive else raw)
    return path


def describe(path):
    """返回文件的格式描述，用于排查。"""
    with open(path, "rb") as f:
        raw = f.read()
    if is_archive(raw):
        data = zstandard.ZstdDecompressor().decompress(raw, max_output_size=50_000_000)
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as tf:
            return {"format": "tar+zstd (Cardinal 归档)", "entries": tf.getnames(),
                    "bytes": len(raw)}
    return {"format": "plain JSON", "bytes": len(raw)}
