"""Offline group-14 regressions; real pinned blob, isolated repositories only."""
import contextlib
import hashlib
import io
import os
from pathlib import Path
import subprocess
import unittest
from unittest import mock

import replay_osc as replay
import test_replay_safety as safety

NAME = '14-rackwindows-nearfar.patch'
REL = 'plugins/rackwindows'
PIN = '60dfe5dff94b82fc42a43d971e41e64e296b0220'
PRE = '52ead73b28a7f6305c0360793040a7cf403d425032affea1f9e729de0d64868d'
POST = '6b6bbd83e978db09e1121db3c5a800bc2994802781fd91f926f8c93ab33681a1'
def digest(data):
    return hashlib.sha256(data).hexdigest()


class ReplayCompat(unittest.TestCase):
    # Reuse fixture/CLI idioms without inheriting/recounting unrelated tests.
    git = safety.ReplaySafety.git
    main_output = safety.ReplaySafety.main_output

    @classmethod
    def setUpClass(cls):
        command = ['git', '-C', os.environ['CARDINAL_TEST_WSL_SOURCE'].rstrip('/') + '/plugins/rackwindows',
                   'show', PIN + ':src/rwlib.h']
        if os.name == 'nt':
            command = ['wsl.exe', '-d', 'Ubuntu-26.04', '--', *command]
        result = subprocess.run(command, capture_output=True, timeout=60)
        if result.returncode:
            raise AssertionError(result.stderr)
        cls.pre = result.stdout
        if digest(cls.pre) != PRE:
            raise AssertionError('fixed blob identity mismatch')

    def setUp(self):
        safety.ReplaySafety.setUp(self)
        self.name = NAME
        self.patches = Path(replay.HERE) / 'patches'
        self.plugin = self.root / REL
        (self.plugin / 'src').mkdir(parents=True)
        p = subprocess.run(['git', 'init', '-q', str(self.plugin)], capture_output=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.source = self.plugin / 'src/rwlib.h'
        self.source.write_bytes(self.pre)

    def apply(self, rel=REL, **kwargs):
        return replay.apply_one(str(self.root), str(self.patches), NAME, 'compat fixture', rel, **kwargs)

    def test_group14_contract_and_payload_identity(self):
        self.assertEqual(len(replay.PATCHES), 17)
        self.assertEqual(replay.PATCHES[13][0], NAME)
        self.assertEqual(replay.PATCHES[13][2], REL)
        self.assertEqual(sum(p[0] == NAME for p in replay.PATCHES), 1)
        self.assertEqual(replay.EXPECTED_ENDPOINTS, 33)
        self.assertFalse(any('rwlib' in p[0] for p in replay.VERIFY_MARKS))
        self.assertEqual(digest((self.patches / NAME).read_bytes()),
                         'cb98d70d9a58b5cf06897f6f8d8a2c1dbed1c0ac042677cf00e4f8a0cc1db4f9')

    def test_real_apply_dry_reverse_and_skip_preserve_bytes_and_index(self):
        # Create a fixture index so preservation is a positive assertion.
        p = subprocess.run(['git', '-C', str(self.plugin), '-c', 'core.autocrlf=false',
                            'add', '--', 'src/rwlib.h'], capture_output=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        index = self.plugin / '.git/index'
        before_index = index.read_bytes()
        self.assertEqual(self.apply(dry_run=True)[0], 'would_apply')
        self.assertEqual(self.source.read_bytes(), self.pre)
        self.assertEqual(index.read_bytes(), before_index)
        self.assertEqual(self.apply()[0], 'applied')
        self.assertEqual(digest(self.source.read_bytes()), POST)
        self.assertEqual(self.apply()[0], 'skipped')
        self.assertEqual(digest(self.source.read_bytes()), POST)
        self.assertEqual(index.read_bytes(), before_index)
        result = replay.run_git(['apply', '--check', '-R', '-v', str(self.patches / NAME)], str(self.plugin))
        self.assertEqual(result['returncode'], 0, result)
        result = replay.run_git(['apply', '-R', '-v', str(self.patches / NAME)], str(self.plugin))
        self.assertEqual(result['returncode'], 0, result)
        self.assertEqual(self.source.read_bytes(), self.pre)

    def test_wrong_main_root_and_missing_target_are_rejected(self):
        for root in ['', 'plugins/missing']:
            with self.subTest(root=root):
                self.assertEqual(self.apply(root)[0], 'conflict')
                self.assertEqual(self.source.read_bytes(), self.pre)

    def test_missing_own_repository_never_inherits_parent_or_initializes(self):
        import shutil
        shutil.rmtree(self.plugin / '.git')  # fixture only
        self.assertEqual(self.apply()[0], 'conflict')
        self.assertFalse((self.plugin / '.git').exists())
        self.assertEqual(self.source.read_bytes(), self.pre)

    def test_partial_or_wrong_context_conflicts_without_write(self):
        self.assertEqual(self.apply()[0], 'applied')
        partial = self.source.read_bytes().replace(b'#undef far', b'// missing far undef')
        for data in [partial, self.pre.replace(b'#include "math.h"', b'#include <cmath>')]:
            with self.subTest(sha256=digest(data)):
                self.source.write_bytes(data)
                self.assertEqual(self.apply()[0], 'conflict')
                self.assertEqual(self.source.read_bytes(), data)

    def test_group14_failure_stops_cli_before_later_group(self):
        self.source.write_bytes(self.pre.replace(b'#include "math.h"', b'#include <cmath>'))
        groups = [(NAME, 'compat', REL), ('never.patch', 'never', '')]
        with mock.patch.object(replay, 'apply_one', wraps=replay.apply_one) as calls:
            rc, text = self.main_output(groups)
        self.assertEqual(rc, 1)
        self.assertEqual(calls.call_count, 1)
        self.assertIn('failed (1): ' + NAME, text)
        self.assertIn('notattempted (1): never.patch', text)
        self.assertIn('未自动回滚', text)

    def test_documentation_matches_strict_current_contract(self):
        readme = (Path(replay.HERE) / 'README.md').read_text(encoding='utf8')
        self.assertIn('17 组', replay.__doc__)
        self.assertIn(NAME, readme)
        self.assertIn(PIN, readme)
        self.assertNotIn('自动 `git init`', readme)
        self.assertNotIn('30 个端点注册 + 18', readme)


if __name__ == '__main__':
    unittest.main(verbosity=2)
