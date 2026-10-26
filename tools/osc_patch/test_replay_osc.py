#!/usr/bin/env python3
"""Offline regression tests for replay_osc.verify(); never apply patches."""
import tempfile
import unittest
from pathlib import Path

import replay_osc as replay


class TestSongRollVerification(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="replay_verify_test_")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        # Synthetic source layout: all unrelated checks are satisfied using
        # their declared markers; SongRoll's layout is fixed independently.
        for rel, mark, _ in replay.VERIFY_MARKS:
            if "modelSongRollModule" == mark:
                continue
            self._append(rel, "// fixture marker: " + mark + "\n")
        self._append(
            "src/CardinalCommon.cpp",
            "".join('REG("/test-%d", "", handler)\n' % i
                    for i in range(replay.EXPECTED_ENDPOINTS)),
        )
        self.glue = self.root / "plugins/rcm-modules/src/SongRollModule.cpp"
        self._append(
            "plugins/rcm-modules/src/SongRollModule.cpp",
            'Model* modelSongRollModule = '
            'createModel<SongRollModule, SongRollWidget>("rcm-songroll");\n',
        )
        self._append(
            "plugins/rcm-modules/src/SongRoll/SongRollModule.cpp",
            "// Engine implementation; model registration belongs to the glue file.\n",
        )

    def _append(self, rel, text):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(text)

    def test_model_in_glue_file_passes(self):
        ok, problems, endpoints = replay.verify(str(self.root))
        self.assertEqual(endpoints, replay.EXPECTED_ENDPOINTS)
        self.assertTrue(ok, problems)
        self.assertEqual(problems, [])

    def test_missing_glue_file_is_rejected(self):
        self.glue.unlink()
        ok, problems, _ = replay.verify(str(self.root))
        self.assertFalse(ok)
        self.assertTrue(any("缺文件" in p and
                            "plugins/rcm-modules/src/SongRollModule.cpp" in p
                            for p in problems), problems)

    def test_marker_in_engine_cannot_replace_glue_definition(self):
        self.glue.write_text("// Model definition missing.\n", encoding="utf-8")
        self._append("plugins/rcm-modules/src/SongRoll/SongRollModule.cpp",
                     "modelSongRollModule\n")
        ok, problems, _ = replay.verify(str(self.root))
        self.assertFalse(ok)
        self.assertTrue(any("缺标记" in p and
                            "plugins/rcm-modules/src/SongRollModule.cpp" in p
                            for p in problems), problems)

    def test_wrong_endpoint_count_is_still_rejected(self):
        self._append("src/CardinalCommon.cpp", 'REG("/extra", "", handler)\n')
        ok, problems, endpoints = replay.verify(str(self.root))
        self.assertFalse(ok)
        self.assertEqual(endpoints, replay.EXPECTED_ENDPOINTS + 1)
        self.assertTrue(any("端点数" in p for p in problems), problems)


if __name__ == "__main__":
    unittest.main(verbosity=2)
