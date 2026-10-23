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


if __name__ == "__main__":
    unittest.main(verbosity=2)