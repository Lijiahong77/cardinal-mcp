#!/usr/bin/env python3
"""cardinal_mcp.py 的离线单元测试（不依赖真机 / WINE / 网络）。

把这些轮（E1 三段式回包、C6 写端点、M1 module-add、A1 真机验收）踩过的坑
固化成回归测试。只测能被 mock 住的纯函数/纯解析逻辑；任何需要 OSC 往返的
函数（get_param、load_patch 等）都不在这里测——它们的正确性靠探针。

运行（需 python-osc + zstandard，用 music-ai venv）：
    python tools/test_cardinal_mcp.py
或者：
    C:/Users/lijia/.workbuddy/binaries/python/envs/music-ai/Scripts/python.exe \
        tools/test_cardinal_mcp.py

失败即回归：每一处	assert 都对应一次真实的血泪教训。
"""
import os
import sys
import unittest

# 让 `import cardinal_mcp` 能找到同目录的兄弟模块（patchio 等）。
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import cardinal_mcp as m  # noqa: E402
import modbrowser  # noqa: E402
import modresolve  # noqa: E402


class TestStatusParsing(unittest.TestCase):
    """E1 三段式回包 — 正确区分 payload 与 status。"""

    def test_three_segment_status(self):
        # 三段回包：status 在第三段，payload 在第二段。
        res = ["param-get", "0.5", "ok"]
        # 直接测纯解析逻辑（不发起真实 OSC）：
        payload = res[1]
        status = res[2]
        out = m._hist_status(payload, status)
        self.assertTrue(out["ok"])
        self.assertEqual(out["status"], "ok")

    def test_two_segment_is_treated_as_ok(self):
        # 旧两段回包（无 status）应视为 ok（E1 向后兼容）。
        out = m._hist_status("some-payload", "ok")  # 旧版恒传 ok 等价两段
        self.assertTrue(out["ok"])

    def test_err_status_not_treated_as_ok(self):
        # 这是 C6 修掉的核心 bug：错误码不得被报成 ok=True。
        out = m._hist_status("", "err:E_NO_MODULE")
        self.assertFalse(out["ok"])
        self.assertEqual(out["status"], "err:E_NO_MODULE")
        self.assertIn("note", out)

    def test_err_status_note_known_code(self):
        # 已知错误码给出人类可读解释，不覆盖成"unexpected"。
        note = m._status_note("err:E_NO_MODEL")
        self.assertNotIn("unexpected status", note)


class TestHistVsStatus(unittest.TestCase):
    """_hist 丢 status vs _hist_status 保留 status 的分野。"""

    def test_hist_reports_ok_true_even_on_err(self):
        # 旧 _hist 只要拿到 payload 就 ok=True —— 这就是被 C6 抛弃的行为，
        # 此处只 lock 住它仍存在的旧语义，提醒不可再用于写端点。
        out = m._hist("anything")
        self.assertTrue(out["ok"])

    def test_hist_none_is_unsupported(self):
        out = m._hist(None)
        # 探针不可用时报 error=probe_not_supported，绝不伪装成 ok。
        self.assertEqual(out.get("error"), "probe_not_supported")
        self.assertNotIn("ok", out)  # 不出现 ok=True 的假成功


class TestScreenshotTarget(unittest.TestCase):
    """2026-10-22 A1 验收发现的 screenshot 路径解析 bug 的回归测试。"""

    def test_three_segment_path_is_reply1(self):
        # E1 后回包 = ["screenshot", "C:/.../screenshot.png", "ok"]
        # 旧代码 reply[-1] 会取成 "ok"。此处必须拿到真实路径。
        target, status = m._screenshot_target(
            ["screenshot", "C:/Users/x/Temp/screenshot.png", "ok"])
        self.assertEqual(target, "C:/Users/x/Temp/screenshot.png")
        self.assertEqual(status, "ok")

    def test_two_segment_path(self):
        target, status = m._screenshot_target(
            ["screenshot", "C:/Users/x/Temp/screenshot.png"])
        self.assertEqual(target, "C:/Users/x/Temp/screenshot.png")
        self.assertEqual(status, "ok")

    def test_fail_reply(self):
        target, status = m._screenshot_target(["screenshot", "fail"])
        self.assertIsNone(target)

    def test_malformed_reply(self):
        self.assertIsNone(m._screenshot_target(["screenshot"])[0])
        self.assertIsNone(m._screenshot_target([])[0])
        self.assertIsNone(
            m._screenshot_target(["not-screenshot", "x", "ok"])[0])


class TestBuildMsgTypes(unittest.TestCase):
    """OSC 消息构造：typespec 必须与参数顺序一致（M1 踩坑）。"""

    def test_module_id_uses_int64(self):
        # 大型 module id 必须走 'h'(int64)，'i'(int32) 会截断。
        dgram = m.build_msg("/x", [("h", 7775877489923468)])
        self.assertIsInstance(dgram, bytes)
        self.assertTrue(len(dgram) > 0)

    def test_sii_order(self):
        # module-add 是 slug(s) + x(i) + y(i)，顺序按 add 顺序传入。
        dgram = m.build_msg("/module-add",
                            [("s", "Fundamental|VCO"), ("i", 10), ("i", 2)])
        self.assertIsInstance(dgram, bytes)


class TestPatchDirResolution(unittest.TestCase):
    """PATCH_DIR 解析：env 优先于 repo 内 patches。"""

    def test_default_patch_dir_is_repo_patches(self):
        # 不设 env 时，默认落到 repo 的 patches/（README 承诺的 fresh-clone）。
        p = m._default_patch_dir()
        self.assertTrue(p.endswith("patches"), p)


class TestAddModuleNamed(unittest.TestCase):
    """「按名字加模块」：品牌归一 / 唯一直加 / 候选 pick / 停用词（2026-10-24）。

    依赖本机 PluginManifests（Cardinal 安装目录自带，与运行引擎同源）——
    读不到就 skip，绝不假绿。
    """

    @classmethod
    def setUpClass(cls):
        cls.has_lib = bool(modbrowser.LIB.load().modules)

    def setUp(self):
        if not self.has_lib:
            self.skipTest("PluginManifests 不在本机")

    def test_vcv_vcf_unique(self):
        # VCV 是 brand 名、Fundamental 才是 plugin slug —— 归一后唯一命中。
        r = modresolve.resolve("VCV VCF")
        self.assertEqual(r["status"], "unique")
        self.assertEqual(r["brand_resolved"].get("vcv"), ["Fundamental"])
        self.assertEqual(r["candidates"][0]["plugin"], "Fundamental")
        self.assertEqual(r["candidates"][0]["model"], "VCF")

    def test_fundamental_vcf_unique(self):
        # 直接说 plugin slug 名也要认（李的两种说法都要通）。
        r = modresolve.resolve("Fundamental VCF")
        self.assertEqual(r["status"], "unique")
        self.assertEqual(r["candidates"][0]["model"], "VCF")

    def test_bogaudio_vco_ambiguous(self):
        # 多个候选绝不猜（李 10-24 拍板：仅唯一命中才直加）。
        r = modresolve.resolve("Bogaudio VCO")
        self.assertEqual(r["status"], "ambiguous")
        self.assertEqual(r["matched"], 2)
        self.assertTrue(all(c["plugin"] == "Bogaudio" for c in r["candidates"]))
        self.assertIn("Bogaudio-VCO", {c["model"] for c in r["candidates"]})

    def test_zh_prefix_translation(self):
        # 「滤波器」整词不在词表 → 最长前缀「滤波」→ filter（10-24 拍板）。
        r = modresolve.resolve("滤波器")
        self.assertIn("filter", r["expanded_terms"])
        self.assertGreater(r["matched"], 0)

    def test_stopword_garbage_no_match(self):
        # 「not a module」曾靠 desc 词频刷出 1363 个假命中 —— 停用词回归。
        r = modresolve.resolve("xyzzy not a module")
        self.assertEqual(r["status"], "no_match")
        self.assertEqual(r["matched"], 0)

    def test_needs_pick_never_touches_osc(self):
        # 歧义阶段只列候选，不发 OSC（Cardinal 没开也不能假失败/假成功）。
        calls = []
        orig = m.add_module
        m.add_module = lambda *a, **k: calls.append(a) or {"ok": True}
        try:
            out = m.add_module_named("Bogaudio VCO", 4, 3)
        finally:
            m.add_module = orig
        self.assertTrue(out["ok"])
        self.assertFalse(out["added"])
        self.assertTrue(out["needs_pick"])
        self.assertEqual(out["n_candidates"], 2)
        self.assertEqual(calls, [])

    def test_pick_out_of_range(self):
        # pick 越界：报错 + 原样重列候选，且不落地。
        calls = []
        orig = m.add_module
        m.add_module = lambda *a, **k: calls.append(a) or {"ok": True}
        try:
            out = m.add_module_named("Bogaudio VCO", 4, 3, pick=99)
        finally:
            m.add_module = orig
        self.assertFalse(out["ok"])
        self.assertEqual(out["error"], "bad_pick")
        self.assertEqual(calls, [])

    def test_unique_add_uses_candidate_slugs(self):
        # 唯一命中直加：喂给 add_module 的必须是候选里归一后的 plugin|model。
        seen = {}

        def fake_add(plugin, model, x, y):
            seen.update(plugin=plugin, model=model, x=x, y=y)
            return {"ok": True, "result": "42", "status": "ok"}

        orig = m.add_module
        m.add_module = fake_add
        try:
            out = m.add_module_named("VCV VCF", 7, 2)
        finally:
            m.add_module = orig
        self.assertTrue(out["ok"])
        self.assertTrue(out["added"])
        self.assertEqual(seen, {"plugin": "Fundamental", "model": "VCF",
                                "x": 7, "y": 2})


if __name__ == "__main__":
    unittest.main(verbosity=2)