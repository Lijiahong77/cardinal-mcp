"""Offline patchio contracts; every fixture stays under profile scratch."""
import io
import json
import os
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import zstandard
import patchio as p

SCRATCH = os.environ['TMPDIR']


class Safety(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=SCRATCH, prefix="patchio_safety_")
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "rack.vcv"
        self.old = b'{"version":"old","modules":[],"cables":[]}'
        self.path.write_bytes(self.old)

    def assert_original(self):
        self.assertEqual(self.path.read_bytes(), self.old)
        self.assertEqual(list(self.path.parent.glob("*.tmp")), [])

    def test_atomic_failures_leave_original_and_remove_temp(self):
        real_open = open
        for fault in ("write", "short", "flush", "fsync", "verify", "replace"):
            self.path.write_bytes(self.old)
            with self.subTest(fault=fault):
                class Broken:
                    def __init__(self, f): self.f = f
                    def __enter__(self): return self
                    def __exit__(self, *a): self.f.close()
                    def __getattr__(self, name): return getattr(self.f, name)
                    def write(self, data):
                        if fault == "write":
                            self.f.write(data[:2])
                            raise OSError("write failed")
                        if fault == "short":
                            self.f.write(data[:2])
                            return 2
                        if fault == "verify":
                            self.f.write(b"x" * len(data))
                            return len(data)
                        return self.f.write(data)
                    def flush(self):
                        if fault == "flush": raise OSError("flush failed")
                        return self.f.flush()
                def opening(name, mode="r", *a, **kw):
                    f = real_open(name, mode, *a, **kw)
                    return Broken(f) if str(name).endswith(".tmp") and ("w" in mode or "x" in mode) else f
                sync_calls = 0
                real_sync = os.fsync
                def syncing(fd):
                    nonlocal sync_calls
                    sync_calls += 1
                    if fault == "fsync" and sync_calls == 2:
                        raise OSError("temporary fsync")
                    return real_sync(fd)
                with patch.object(p, "open", side_effect=opening, create=True), \
                     patch.object(p.os, "fsync", side_effect=syncing), \
                     patch.object(p.os, "replace", side_effect=OSError("replace")) if fault == "replace" else patch.object(p.os, "replace", wraps=os.replace):
                    with self.assertRaises((OSError, ValueError)):
                        p.write_patch(self.path, {"version": "new"})
                self.assert_original()

    def test_success_uses_same_directory_replace(self):
        real_replace = os.replace
        def replacing(source, target):
            self.assertEqual(Path(source).parent, self.path.parent)
            self.assertEqual(self.path.read_bytes(), self.old)
            return real_replace(source, target)
        with patch.object(p.os, "replace", side_effect=replacing) as replace:
            self.assertIs(p.write_patch(self.path, {"version": "new"}), self.path)
        replace.assert_called_once()
        self.assertEqual(p.read_patch(self.path), {"version": "new"})

    def make_archive(self, names=("patch.json", "modules/", "modules/1/asset.bin")):
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w", format=tarfile.PAX_FORMAT) as tf:
            for i, name in enumerate(names):
                info = tarfile.TarInfo(name)
                info.mode = 0o750 if name.endswith("/") else 0o640
                info.uid, info.gid, info.uname, info.gname = 123, 456, "owner", "group"
                info.mtime = 123456789 + i
                info.pax_headers = {"comment": "resource metadata"}
                data = self.old if name.split("/")[-1] == "patch.json" else b"asset\\0payload\\xff"
                if name.endswith("/") or name == ".":
                    info.type, data = tarfile.DIRTYPE, b""
                info.size = len(data)
                tf.addfile(info, io.BytesIO(data))
        return zstandard.ZstdCompressor().compress(buf.getvalue())

    def members(self, raw):
        data = zstandard.ZstdDecompressor().decompress(raw)
        with tarfile.open(fileobj=io.BytesIO(data)) as tf:
            return [(m.name, m.mode, m.uid, m.gid, m.uname, m.gname,
                     m.mtime, m.type, m.pax_headers,
                     tf.extractfile(m).read() if m.isfile() else b"") for m in tf]

    def test_default_and_explicit_archive_preserve_all_resources(self):
        for explicit in (None, True):
            with self.subTest(as_archive=explicit):
                raw = self.make_archive()
                self.path.write_bytes(raw)
                before = self.members(raw)
                p.write_patch(self.path, {"version": "new"}, as_archive=explicit)
                after = self.members(self.path.read_bytes())
                self.assertEqual(after[1:], before[1:])
                self.assertEqual(after[0][:-1], before[0][:-1])
                self.assertEqual(json.loads(after[0][-1]), {"version": "new"})
                self.assertEqual(type(p.read_patch(self.path)), dict)

    def test_rack_root_and_leading_dot_names_roundtrip_without_metadata_loss(self):
        for root in (None, ".", "./"):
            for prefix in ("", "./"):
                with self.subTest(root=root, prefix=prefix):
                    names = ((root,) if root is not None else ()) + (
                        prefix + "modules/", prefix + "modules/1/asset.bin",
                        prefix + "patch.json", prefix + "tail.bin")
                    raw = self.make_archive(names)
                    self.path.write_bytes(raw)
                    before = self.members(raw)
                    self.assertEqual(p.read_patch(self.path), json.loads(self.old))
                    self.assertEqual(p.describe(self.path)["entries"], [m[0] for m in before])
                    self.assertIs(p.write_patch(self.path, {"version": "new"}), self.path)
                    after = self.members(self.path.read_bytes())
                    self.assertEqual(len(after), len(before))
                    for old, new in zip(before, after):
                        self.assertEqual(new[:-1], old[:-1])
                        if old[0].rsplit("/", 1)[-1] == "patch.json":
                            self.assertEqual(json.loads(new[-1]), {"version": "new"})
                        else:
                            self.assertEqual(new[-1], old[-1])
                    self.assertEqual(p.read_patch(self.path), {"version": "new"})
                    self.assertEqual(p.describe(self.path)["entries"], [m[0] for m in before])
                    self.assertIn(raw, [b.read_bytes() for b in self.path.parent.glob("*.bak-patchio-*")])

    def assert_archive_refused(self, raw):
        self.path.write_bytes(raw)
        before_files = set(self.path.parent.iterdir())
        for api in (p.read_patch, p.describe, lambda path: p.write_patch(path, {"version": "new"})):
            with self.assertRaises((ValueError, tarfile.TarError)):
                api(self.path)
            self.assertEqual(self.path.read_bytes(), raw)
            self.assertEqual(set(self.path.parent.iterdir()), before_files)

    def test_leading_dot_alias_collisions_and_ancestors_fail_closed(self):
        cases = [
            ("patch.json", "./patch.json"),
            ("patch.json", "./PATCH.JSON"),
            ("asset", "./asset"),
            ("asset", "./ASSET"),
            ("asset/", "./ASSET/"),
            ("asset", "./asset/child"),
            ("./ASSET", "asset/child"),
            ("./asset/child", "asset"),
            ("asset/child", "./ASSET"),
            (".", "./"),
        ]
        for names in cases:
            for ordered in (names, names[::-1]):
                with self.subTest(names=ordered):
                    if "patch.json" not in ordered:
                        ordered = ("./patch.json",) + ordered
                    self.assert_archive_refused(self.make_archive(ordered))

    def test_leading_dot_does_not_hide_traversal_or_unsafe_components(self):
        for name in ("../escape", "./../escape", "a/../escape", "./a/../escape",
                     "a/./escape", "./a/./escape", "./a//escape", ".//escape",
                     "./C:/drive", r"./a\escape", "./CON.bin", "./asset. "):
            with self.subTest(name=name):
                self.assert_archive_refused(self.make_archive(("./patch.json", name)))

    def test_root_dot_regular_files_fail_closed(self):
        for name in (".", "./"):
            with self.subTest(name=name):
                buf = io.BytesIO()
                with tarfile.open(fileobj=buf, mode="w", format=tarfile.PAX_FORMAT) as tf:
                    for member, payload in ((name, b"not a directory"), ("./patch.json", self.old)):
                        info = tarfile.TarInfo(member)
                        info.size = len(payload)
                        tf.addfile(info, io.BytesIO(payload))
                self.assert_archive_refused(zstandard.ZstdCompressor().compress(buf.getvalue()))

    def test_nested_single_patch_entry_remains_at_same_name(self):
        self.path.write_bytes(self.make_archive(("saved/patch.json",)))
        p.write_patch(self.path, {"version": "new"})
        self.assertEqual(self.members(self.path.read_bytes())[0][0], "saved/patch.json")
        self.assertEqual(p.read_patch(self.path), {"version": "new"})

    def test_explicit_json_cannot_drop_extra_resources(self):
        raw = self.make_archive()
        self.path.write_bytes(raw)
        with self.assertRaises(ValueError):
            p.write_patch(self.path, {"version": "new"}, as_archive=False)
        self.assertEqual(self.path.read_bytes(), raw)

    def test_new_files_and_resource_free_explicit_conversion(self):
        for option in (None, False, True):
            with self.subTest(option=option):
                self.path.unlink(missing_ok=True)
                p.write_patch(self.path, {"version": "new"}, as_archive=option)
                self.assertEqual(p.is_archive(self.path.read_bytes()), option is True)
                self.assertEqual(p.read_patch(self.path), {"version": "new"})
        self.path.write_bytes(self.make_archive(("patch.json",)))
        p.write_patch(self.path, {"version": "converted"}, as_archive=False)
        self.assertFalse(p.is_archive(self.path.read_bytes()))
        self.assertEqual(p.read_patch(self.path), {"version": "converted"})
        self.assertEqual(p.archive_bytes(self.make_archive()), self.make_archive())

    def test_ambiguous_and_unsafe_archives_fail_closed(self):
        cases = [
            ("patch.json", "patch.json"),
            ("a/patch.json", "b/patch.json"),
            ("patch.json", "Patch.JSON"),
            ("no-patch",),
            ("patch.json", "../escape"),
            ("patch.json", "/absolute"),
            ("patch.json", "C:/drive"),
            ("patch.json", "modules/CON.bin"),
            ("patch.json", "modules/LPT1"),
            ("patch.json", "modules/line\nbreak"),
            ("patch.json", "a\\\\escape"),
            ("patch.json", "a/./asset"),
            ("patch.json", "a//asset"),
            ("patch.json", "asset", "asset"),
            ("patch.json", "asset", "asset/child"),
            ("patch.json", "asset/child", "asset"),
            ("patch.json/",),
        ]
        for names in cases:
            with self.subTest(names=names):
                raw = self.make_archive(names)
                self.path.write_bytes(raw)
                with self.assertRaises((ValueError, tarfile.TarError)):
                    p.read_patch(self.path)
                with self.assertRaises((ValueError, tarfile.TarError)):
                    p.write_patch(self.path, {"version": "new"}, as_archive=True)
                self.assertEqual(self.path.read_bytes(), raw)

    def test_links_special_members_and_sparse_fail_closed(self):
        for typ in (tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.CHRTYPE, tarfile.FIFOTYPE):
            with self.subTest(type=typ):
                buf = io.BytesIO()
                with tarfile.open(fileobj=buf, mode="w") as tf:
                    info = tarfile.TarInfo("patch.json")
                    info.size = len(self.old)
                    tf.addfile(info, io.BytesIO(self.old))
                    info = tarfile.TarInfo("asset")
                    info.type, info.linkname = typ, "patch.json"
                    tf.addfile(info)
                raw = zstandard.ZstdCompressor().compress(buf.getvalue())
                self.path.write_bytes(raw)
                with self.assertRaises(ValueError): p.read_patch(self.path)
                with self.assertRaises(ValueError): p.write_patch(self.path, {})
                self.assertEqual(self.path.read_bytes(), raw)

    def test_known_and_unknown_zstd_sizes_obey_hard_stream_cap(self):
        tar = zstandard.ZstdDecompressor().decompress(self.make_archive())
        for known in (True, False):
            with self.subTest(known=known):
                raw = zstandard.ZstdCompressor(write_content_size=known).compress(tar)
                self.path.write_bytes(raw)
                with patch.object(p, "MAX_ARCHIVE_BYTES", 100, create=True):
                    with self.assertRaises(ValueError): p.read_patch(self.path)
                    with self.assertRaises(ValueError): p.describe(self.path)
                    with self.assertRaises(ValueError): p.write_patch(self.path, {})
                self.assertEqual(self.path.read_bytes(), raw)

    def test_raw_json_patch_member_and_member_count_caps(self):
        scenarios = [("MAX_RAW_BYTES", 10, self.old),
                     ("MAX_JSON_BYTES", 10, self.old),
                     ("MAX_JSON_BYTES", 10, self.make_archive()),
                     ("MAX_MEMBERS", 1, self.make_archive())]
        for constant, cap, raw in scenarios:
            with self.subTest(constant=constant, archive=p.is_archive(raw)):
                self.path.write_bytes(raw)
                with patch.object(p, constant, cap, create=True):
                    with self.assertRaises(ValueError): p.read_patch(self.path)
                    with self.assertRaises(ValueError): p.write_patch(self.path, {"version": "too long"})
                self.assertEqual(self.path.read_bytes(), raw)

    def test_oversized_output_is_rejected_before_replace(self):
        for constant, cap, archive in [("MAX_JSON_BYTES", 5, False),
                                       ("MAX_RAW_BYTES", 5, True),
                                       ("MAX_ARCHIVE_BYTES", 100, True)]:
            with self.subTest(constant=constant):
                with patch.object(p, constant, cap, create=True):
                    with self.assertRaises(ValueError):
                        p.write_patch(self.path, {"version": "long new data"}, as_archive=archive)
                self.assert_original()

    def test_compressed_corrupt_payload_is_never_committed(self):
        with patch.object(p, "archive_bytes", return_value=p.ZSTD_MAGIC + b"broken"):
            with self.assertRaises((ValueError, zstandard.ZstdError, tarfile.TarError)):
                p.write_patch(self.path, {}, as_archive=True)
        self.assert_original()

    def test_nonfinite_and_encoding_errors_never_modify_target(self):
        for value in (float("nan"), float("inf"), -float("inf"), object(), "\ud800"):
            with self.subTest(value=repr(value)):
                self.path.write_bytes(self.old)
                with self.assertRaises((ValueError, TypeError, UnicodeError)):
                    p.write_patch(self.path, {"bad": value})
                self.assert_original()

    def test_damaged_archives_are_not_repaired_silently(self):
        tar = zstandard.ZstdDecompressor().decompress(self.make_archive())
        checked = zstandard.ZstdCompressor(write_checksum=True).compress(tar)
        malformed_json = tar.replace(self.old, b"x" * len(self.old), 1)
        cases = [checked[:-1],
                 zstandard.ZstdCompressor().compress(tar[:700]),
                 zstandard.ZstdCompressor().compress(tar + tar),
                 zstandard.ZstdCompressor().compress(malformed_json)]
        for i, raw in enumerate(cases):
            with self.subTest(case=i):
                self.path.write_bytes(raw)
                with self.assertRaises((ValueError, zstandard.ZstdError, tarfile.TarError)):
                    p.read_patch(self.path)
                with self.assertRaises((ValueError, zstandard.ZstdError, tarfile.TarError)):
                    p.write_patch(self.path, {})
                self.assertEqual(self.path.read_bytes(), raw)

    def test_tar_extension_headers_are_counted_before_recursion(self):
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w", format=tarfile.PAX_FORMAT) as tf:
            info = tarfile.TarInfo("patch.json")
            info.pax_headers = {"comment": "extra physical tar header"}
            info.size = len(self.old)
            tf.addfile(info, io.BytesIO(self.old))
        self.path.write_bytes(zstandard.ZstdCompressor().compress(buf.getvalue()))
        with patch.object(p, "MAX_MEMBERS", 1):
            with self.assertRaises(ValueError): p.read_patch(self.path)

    def test_archive_bytes_caps_plain_input_but_keeps_archive_identity(self):
        raw = self.make_archive()
        with patch.object(p, "MAX_RAW_BYTES", 5):
            self.assertIs(p.archive_bytes(raw), raw)
            with self.assertRaises(ValueError): p.archive_bytes(self.old)
        with patch.object(p, "MAX_JSON_BYTES", 5):
            with self.assertRaises(ValueError): p.archive_bytes(self.old)

    def test_backup_sync_failure_cleans_incomplete_backup(self):
        with patch.object(p.os, "fsync", side_effect=OSError("backup sync")):
            with self.assertRaises(OSError): p.write_patch(self.path, {})
        self.assert_original()
        self.assertEqual(list(self.path.parent.glob("*.bak-patchio-*")), [])

    def test_temporary_name_collision_does_not_delete_somebody_elses_file(self):
        from types import SimpleNamespace
        temporary = self.path.with_name("." + self.path.name + ".fixed.tmp")
        temporary.write_bytes(b"unrelated temporary")
        with patch.object(p.uuid, "uuid4", return_value=SimpleNamespace(hex="fixed")):
            with self.assertRaises(FileExistsError): p.write_patch(self.path, {})
        self.assertEqual(temporary.read_bytes(), b"unrelated temporary")
        self.assertEqual(self.path.read_bytes(), self.old)

    def test_archive_recompression_failure_preserves_all_original_bytes(self):
        raw = self.make_archive()
        self.path.write_bytes(raw)
        with patch.object(p.zstandard, "ZstdCompressor", side_effect=OSError("compress")):
            with self.assertRaises(OSError): p.write_patch(self.path, {})
        self.assertEqual(self.path.read_bytes(), raw)
        self.assertEqual(list(self.path.parent.glob("*.tmp")), [])

    def test_exact_caps_accept_valid_input_and_unknown_frame(self):
        self.path.write_bytes(self.old)
        with patch.object(p, "MAX_RAW_BYTES", len(self.old)), \
             patch.object(p, "MAX_JSON_BYTES", len(self.old)):
            self.assertEqual(p.read_patch(self.path)["version"], "old")
        tar = zstandard.ZstdDecompressor().decompress(self.make_archive())
        raw = zstandard.ZstdCompressor(write_content_size=False).compress(tar)
        self.path.write_bytes(raw)
        with patch.object(p, "MAX_ARCHIVE_BYTES", len(tar)):
            self.assertEqual(p.read_patch(self.path)["version"], "old")
        self.assertEqual(p.describe(self.path)["entries"],
                         ["patch.json", "modules", "modules/1/asset.bin"])

    def test_patch_member_pax_size_is_updated_without_resource_changes(self):
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w", format=tarfile.PAX_FORMAT) as tf:
            info = tarfile.TarInfo("patch.json")
            info.size = len(self.old)
            info.pax_headers = {"size": str(info.size), "comment": "keep me"}
            tf.addfile(info, io.BytesIO(self.old))
        self.path.write_bytes(zstandard.ZstdCompressor().compress(buf.getvalue()))
        p.write_patch(self.path, {"version": "new and longer"})
        member = self.members(self.path.read_bytes())[0]
        self.assertEqual(int(member[-2]["size"]), len(member[-1]))
        self.assertEqual(member[-2]["comment"], "keep me")
        self.assertEqual(p.read_patch(self.path), {"version": "new and longer"})

    def test_sparse_pax_member_is_rejected(self):
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w", format=tarfile.PAX_FORMAT) as tf:
            for name, payload in (("patch.json", self.old), ("asset", b"data")):
                info = tarfile.TarInfo(name)
                info.size = len(payload)
                if name == "asset":
                    info.pax_headers = {"GNU.sparse.name": "unsupported sparse resource"}
                tf.addfile(info, io.BytesIO(payload))
        raw = zstandard.ZstdCompressor().compress(buf.getvalue())
        self.path.write_bytes(raw)
        with self.assertRaises(ValueError): p.read_patch(self.path)
        with self.assertRaises(ValueError): p.write_patch(self.path, {})
        self.assertEqual(self.path.read_bytes(), raw)

    def test_versions_are_exclusive_and_discoverable(self):
        p.write_patch(self.path, {"version": "second"})
        second = self.path.read_bytes()
        p.write_patch(self.path, {"version": "third"})
        backups = list(self.path.parent.glob(self.path.name + ".bak-patchio-*"))
        self.assertEqual(len(backups), 2)
        self.assertCountEqual([b.read_bytes() for b in backups], [self.old, second])

    def test_backup_failure_refuses_commit(self):
        real_open = open
        def opening(name, mode="r", *a, **kw):
            if ".bak-patchio-" in str(name) and "x" in mode:
                raise PermissionError("backup unavailable")
            return real_open(name, mode, *a, **kw)
        with patch.object(p, "open", side_effect=opening, create=True):
            with self.assertRaises(PermissionError):
                p.write_patch(self.path, {"version": "new"})
        self.assert_original()

    def test_backup_collision_never_overwrites_or_deletes_prior_backup(self):
        from types import SimpleNamespace
        backup = self.path.with_name(self.path.name + ".bak-patchio-fixed")
        backup.write_bytes(b"prior backup")
        with patch.object(p.uuid, "uuid4", return_value=SimpleNamespace(hex="fixed")):
            with self.assertRaises(FileExistsError):
                p.write_patch(self.path, {"version": "new"})
        self.assertEqual(backup.read_bytes(), b"prior backup")
        self.assert_original()

    def test_compression_failure_preserves_original(self):
        with patch.object(p, "archive_bytes", side_effect=OSError("compress")):
            with self.assertRaises(OSError):
                p.write_patch(self.path, {"version": "new"}, as_archive=True)
        self.assert_original()


if __name__ == "__main__":
    unittest.main(verbosity=2)
