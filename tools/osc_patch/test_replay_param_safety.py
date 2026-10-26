"""Offline group-15 tests, using durable real fixed-after14 source bytes."""
import base64
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import unittest
from unittest import mock

import replay_osc as replay
import test_replay_safety as safety

NAME = '15-param-write-safety.patch'
PRE = {'src/CardinalCommon.cpp': 'c365c8cb27c3f22a081f5a6aa1f2a7ebddb9073ef15e5dc69ec30e27362609f7',
       'src/override/Engine.cpp': '5fd2fdf78a45d847bf4ef10d88123800f132055ffde27df97a0ff2c625ac8a33'}
POST = {'src/CardinalCommon.cpp': 'e1c21935deee6190e4fdd28560a3f234c6681e492d09e3072f08e9a458ada300',
        'src/override/Engine.cpp': '28e85b60cdf7be0ee364327e1efa213019f2033d43ad6cdd69598deff9e004f3',
        'src/ParamWriteSafety.hpp': '73e104be6be7f4dc23e405d7e32054ffa6232fd34864d2fb747485e9e0f285e9'}
PATCH_SHA = '51639209029a95a0fcd112dcd1195532a060bb086354b38ceedb74262ea3fe30'
def digest(data):
    return hashlib.sha256(data).hexdigest()


class ReplayParamSafety(unittest.TestCase):
    git = safety.ReplaySafety.git
    main_output = safety.ReplaySafety.main_output

    def setUp(self):
        safety.ReplaySafety.setUp(self)
        self.name = NAME
        self.patches = Path(replay.HERE) / 'patches'
        fixture = json.loads((Path(replay.HERE) / 'fixtures/param-safety-after14.json').read_text())
        self.pre = {p: gzip.decompress(base64.b64decode(row['gzip_base64']))
                    for p, row in fixture['files'].items()}
        self.assertEqual({p: digest(b) for p, b in self.pre.items()}, PRE)
        for p, data in self.pre.items():
            target = self.root / p
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)

    def apply(self, **kwargs):
        return replay.apply_one(str(self.root), str(self.patches), NAME, 'param safety fixture', '', **kwargs)

    def state(self):
        return {p: (self.root / p).read_bytes() if (self.root / p).exists() else None for p in POST}

    def test_group15_unique_last_root_and_exact_payload(self):
        self.assertEqual(len(replay.PATCHES), 17)
        self.assertEqual(replay.PATCHES[14][0], NAME)
        self.assertEqual(replay.PATCHES[14][2], '')
        self.assertEqual(sum(p[0] == NAME for p in replay.PATCHES), 1)
        self.assertEqual(digest((self.patches / NAME).read_bytes()), PATCH_SHA)
        self.assertEqual(replay.EXPECTED_ENDPOINTS, 33)
        self.assertEqual(len(replay.VERIFY_MARKS), 36)

    def test_real_dry_apply_skip_reverse_preserves_bytes_and_index(self):
        self.git('add', '--', *PRE)
        index = self.root / '.git/index'
        before_index = index.read_bytes()
        before = self.state()
        self.assertEqual(self.apply(dry_run=True)[0], 'would_apply')
        self.assertEqual(self.state(), before)
        self.assertEqual(self.apply()[0], 'applied')
        self.assertEqual({p: digest(b) for p, b in self.state().items()}, POST)
        self.assertEqual(self.apply()[0], 'skipped')
        self.assertEqual({p: digest(b) for p, b in self.state().items()}, POST)
        self.assertEqual(index.read_bytes(), before_index)
        for args in [['apply', '--check', '-R', '-v'], ['apply', '-R', '-v']]:
            result = replay.run_git(args + [str(self.patches / NAME)], str(self.root))
            self.assertEqual(result['returncode'], 0, result)
        self.assertEqual(self.state(), before)
        self.assertEqual(index.read_bytes(), before_index)

    def test_partial_installation_is_rejected_without_write(self):
        self.assertEqual(self.apply()[0], 'applied')
        (self.root / 'src/override/Engine.cpp').write_bytes(self.pre['src/override/Engine.cpp'])
        before = self.state()
        self.assertEqual(self.apply()[0], 'conflict')
        self.assertEqual(self.state(), before)

    def test_missing_own_repository_refuses_without_initialization(self):
        shutil.rmtree(self.root / '.git')  # isolated fixture only
        before = self.state()
        self.assertEqual(self.apply()[0], 'conflict')
        self.assertFalse((self.root / '.git').exists())
        self.assertEqual(self.state(), before)

    def test_group15_failure_stops_before_later_group(self):
        (self.root / 'src/override/Engine.cpp').write_bytes(b'wrong context\n')
        before = self.state()
        groups = [(NAME, 'param safety', ''), ('never.patch', 'never', '')]
        with mock.patch.object(replay, 'apply_one', wraps=replay.apply_one) as calls:
            rc, text = self.main_output(groups)
        self.assertEqual(rc, 1)
        self.assertEqual(calls.call_count, 1)
        self.assertIn('notattempted (1): never.patch', text)
        self.assertEqual(self.state(), before)

    def test_documentation_current_scope_and_lock_contract(self):
        readme = (Path(replay.HERE) / 'README.md').read_text(encoding='utf8')
        self.assertIn('17 组', replay.__doc__)
        for text in [NAME, 'Engine_writeParamById', '01–14', '未部署', '不能已持 Engine 锁']:
            self.assertIn(text, readme)


if __name__ == '__main__':
    unittest.main(verbosity=2)
