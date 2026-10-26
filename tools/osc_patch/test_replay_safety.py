"""Offline recovery safety tests. All git writes are isolated scratch fixtures."""
import contextlib
import hashlib
import io
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

import replay_osc as replay

SCRATCH = Path(os.environ['TMPDIR'])


class ReplaySafety(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='replay-safety-', dir=SCRATCH)
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / 'repo'
        self.root.mkdir()
        self.git('init', '-q')
        self.git('config', '--local', 'core.autocrlf', 'false')
        self.git('config', '--local', 'core.safecrlf', 'false')
        self.patches = self.base / 'patches'
        self.patches.mkdir()
        self.name = '01-osc-core.patch'
        self.patch = self.patches / self.name
        self.patch.write_text('diff --git a/new.txt b/new.txt\nnew file mode 100644\n--- /dev/null\n+++ b/new.txt\n@@ -0,0 +1 @@\n+expected\n', encoding='utf-8', newline='\n')

    def git(self, *args):
        p = subprocess.run(['git', '-C', str(self.root), *args], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        return p.stdout

    def apply(self, **kwargs):
        return replay.apply_one(str(self.root), str(self.patches), self.name, 'fixture', '', **kwargs)

    def test_missing_repository_never_initialized_or_staged(self):
        root = self.base / 'not-a-repository'
        root.mkdir()
        with mock.patch.object(replay, 'run_git', wraps=replay.run_git) as calls:
            status, detail = replay.apply_one(str(root), str(self.patches), self.name, '', '')
        self.assertEqual(status, 'conflict')
        self.assertFalse((root / '.git').exists())
        self.assertFalse((root / 'new.txt').exists())
        self.assertFalse(any(c.args[0][0] in ('init', 'add') for c in calls.call_args_list))

    def test_repository_subdirectory_is_rejected(self):
        sub = self.root / 'ordinary'
        sub.mkdir()
        self.assertEqual(replay.apply_one(str(self.root), str(self.patches), self.name, '', 'ordinary')[0], 'conflict')
        self.assertFalse((sub / 'new.txt').exists())

    def test_reverse_skip_rc0_is_failure(self):
        real = replay.run_git
        def command(args, cwd):
            if args[0] == 'rev-parse':
                return real(args, cwd)
            if '-R' in args:
                return {'returncode': 0, 'stdout': '', 'stderr': "Skipped patch 'new.txt'\n", 'exception': None}
            return {'returncode': 1, 'stdout': 'forward conflict\n', 'stderr': '', 'exception': None}
        with mock.patch.object(replay, 'run_git', side_effect=command):
            self.assertEqual(self.apply()[0], 'conflict')

    def test_actual_skip_rc0_is_failure(self):
        real = replay.run_git
        def command(args, cwd):
            if args[0] == 'apply' and '--check' not in args:
                return {'returncode': 0, 'stdout': '', 'stderr': "Skipped patch 'new.txt'\n", 'exception': None}
            return real(args, cwd)
        with mock.patch.object(replay, 'run_git', side_effect=command):
            self.assertEqual(self.apply()[0], 'conflict')

    def test_git_exception_is_structured_and_stops(self):
        with mock.patch.object(replay.subprocess, 'run', side_effect=OSError('fixture git unavailable')) as call:
            status, detail = self.apply()
        self.assertEqual(status, 'conflict')
        self.assertIsInstance(detail, dict)
        self.assertIn('fixture git unavailable', str(detail))
        self.assertEqual(call.call_count, 1)

    def main_output(self, groups=None, argv=None, **patches):
        output = io.StringIO()
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(replay, 'CARDINAL_ROOT', str(self.root)))
            stack.enter_context(mock.patch.object(replay, 'find_patch_dir', return_value=str(self.patches)))
            stack.enter_context(mock.patch.object(replay, 'PATCHES', groups or [(self.name, 'fixture', '')]))
            stack.enter_context(mock.patch.object(replay.sys, 'argv', ['replay', *(argv or [])]))
            for key, value in patches.items():
                stack.enter_context(mock.patch.object(replay, key, value))
            stack.enter_context(contextlib.redirect_stdout(output))
            rc = replay.main()
        return rc, output.getvalue()

    def test_main_stops_after_partial_application(self):
        second = 'second.patch'
        (self.patches / second).write_bytes(self.patch.read_bytes())
        groups = [(self.name, 'first', ''), (second, 'bad', ''), ('third.patch', 'never', '')]
        # Different expected bytes make second neither applicable nor reversible.
        (self.patches / second).write_text(self.patch.read_text().replace('+expected', '+other'))
        with mock.patch.object(replay, 'apply_one', wraps=replay.apply_one) as calls:
            rc, text = self.main_output(groups)
        self.assertEqual(rc, 1)
        self.assertEqual(calls.call_count, 2)
        self.assertEqual((self.root / 'new.txt').read_text(), 'expected\n')
        for expected in ['applied (1): ' + self.name, 'failed (1): second.patch',
                         'notattempted (1): third.patch', '未自动回滚']:
            self.assertIn(expected, text)

    def test_unknown_and_unexpected_status_fail_fast(self):
        for status in ['unknown', 'surprise', 'would_apply']:
            with self.subTest(status=status):
                call = mock.Mock(return_value=(status, {'message': 'fixture'}))
                rc, text = self.main_output([('first', '', ''), ('later', '', '')], apply_one=call)
                self.assertEqual(rc, 1)
                self.assertEqual(call.call_count, 1)
                self.assertIn('failed (1): first', text)
                self.assertIn('notattempted (1): later', text)

    def test_verify_failure_reports_changes_not_accepted(self):
        rc, text = self.main_output(verify=mock.Mock(return_value=(False, ['missing'], 0)))
        self.assertEqual(rc, 1)
        self.assertIn('已生效', text)
        self.assertIn('未验收', text)
        self.assertNotIn('下一步：编译', text)

    def test_check_disclaims_dependency_simulation(self):
        rc, text = self.main_output(argv=['--check'])
        self.assertEqual(rc, 0)
        self.assertIn('不是依赖序列模拟', text)
        self.assertIn('不能', text)
        self.assertIn('完整重放', text)
        self.assertIn('applied (0)', text)
        self.assertIn('would_apply (1)', text)

    def test_verify_only_disclaims_certification(self):
        rc, text = self.main_output(argv=['--verify'], verify=mock.Mock(return_value=(True, [], 33)))
        self.assertEqual(rc, 0)
        self.assertIn('仅端点计数与标记清单', text)
        self.assertIn('不认证完整 patch', text)

    def test_help_documents_current_scope(self):
        self.assertIn('17 组', replay.__doc__)
        self.assertNotIn('CARDINAL_SRC=', replay.__doc__)
        self.assertIn('CARDINAL_ROOT=', replay.__doc__)
        self.assertIn('反向检查', replay.__doc__)

    def test_verify_only_exception_is_reported(self):
        rc, text = self.main_output(argv=['--verify'], verify=mock.Mock(side_effect=OSError('fixture read failed')))
        self.assertEqual(rc, 1)
        self.assertIn('fixture read failed', text)
        self.assertIn('未验收', text)

    def test_missing_patch_directory_reports_unattempted(self):
        with mock.patch.object(replay, 'PATCH_SEARCH', [str(self.base / 'absent')]):
            # Use real resolver instead of main_output's fixture resolver.
            resolver = replay.find_patch_dir
            rc, text = self.main_output([('first', '', ''), ('later', '', '')], find_patch_dir=resolver)
        self.assertEqual(rc, 1)
        self.assertIn('failed (1): first', text)
        self.assertIn('notattempted (1): later', text)

    def test_normal_apply_then_reverse_proven_skip(self):
        self.assertEqual(self.apply()[0], 'applied')
        self.assertEqual((self.root / 'new.txt').read_bytes(), b'expected\n')
        self.assertEqual(self.apply()[0], 'skipped')

    def test_existing_wrong_file_is_rejected(self):
        (self.root / 'new.txt').write_bytes(b'incorrect\n')
        status, detail = self.apply()
        self.assertEqual(status, 'conflict')
        self.assertEqual((self.root / 'new.txt').read_bytes(), b'incorrect\n')
        self.assertEqual(len(detail['commands']), 3)
        self.assertIn('不是要求重新应用', detail['message'])

    def test_later_overlap_is_not_claimed_installed(self):
        self.assertEqual(self.apply()[0], 'applied')
        (self.root / 'new.txt').write_text('expected\nlater overlay\n')
        status, detail = self.apply()
        self.assertEqual(status, 'conflict')
        self.assertIn('后续叠加', detail['message'])

    def test_missing_patch_is_structured(self):
        self.patch.unlink()
        status, detail = self.apply()
        self.assertEqual(status, 'conflict')
        self.assertEqual(detail['commands'], [])

    def test_missing_root_is_structured(self):
        status, detail = replay.apply_one(str(self.base / 'missing'), str(self.patches), self.name, '', '')
        self.assertEqual(status, 'conflict')
        self.assertEqual(detail['commands'], [])

    def test_gitfile_worktree_root_is_supported(self):
        root = self.base / 'gitfile'
        root.mkdir()
        result = subprocess.run(['git', 'init', '-q', '--separate-git-dir', str(self.base / 'metadata'), str(root)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((root / '.git').is_file())
        self.assertEqual(replay.apply_one(str(root), str(self.patches), self.name, '', '')[0], 'applied')
        self.assertEqual((root / 'new.txt').read_text(), 'expected\n')

    def test_nested_repository_uses_its_own_top_level(self):
        nested = self.root / 'nested'
        nested.mkdir()
        result = subprocess.run(['git', 'init', '-q', str(nested)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(replay.apply_one(str(self.root), str(self.patches), self.name, '', 'nested')[0], 'applied')
        self.assertTrue((nested / 'new.txt').is_file())
        self.assertFalse((self.root / 'new.txt').exists())

    def test_dry_run_preserves_files_and_index_hash(self):
        (self.root / 'seed').write_bytes(b'seed\n')
        self.git('add', '--', 'seed')  # Fixture only, never the user's index.
        def snapshot():
            return {str(p.relative_to(self.root)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in self.root.rglob('*') if p.is_file()}
        before = snapshot()
        self.assertIn('.git\\index' if os.name == 'nt' else '.git/index', before)
        self.assertEqual(self.apply(dry_run=True)[0], 'would_apply')
        self.assertEqual(snapshot(), before)
        self.assertFalse((self.root / 'new.txt').exists())

    def test_git_fatal_error_does_not_trigger_reverse(self):
        real = replay.run_git
        def command(args, cwd):
            if args[0] == 'rev-parse':
                return real(args, cwd)
            return {'returncode': 128, 'stdout': 'full stdout\n', 'stderr': 'fatal diagnostic\n', 'exception': None}
        with mock.patch.object(replay, 'run_git', side_effect=command) as calls:
            status, detail = self.apply()
        self.assertEqual(status, 'conflict')
        self.assertEqual(calls.call_count, 2)
        self.assertEqual(detail['commands'][-1]['stdout'], 'full stdout\n')
        self.assertEqual(detail['commands'][-1]['stderr'], 'fatal diagnostic\n')

    def test_skip_or_path_filter_vetoes_every_phase_and_stream(self):
        real = replay.run_git
        for phase in ['forward', 'reverse', 'actual']:
            for stream in ['stdout', 'stderr']:
                for message in ["Skipped patch 'new.txt'", 'Skipping path new.txt', 'excluded path new.txt', 'path-filtered new.txt', 'partially applied']:
                    with self.subTest(phase=phase, stream=stream, message=message):
                        def command(args, cwd):
                            if args[0] == 'rev-parse':
                                return real(args, cwd)
                            current = 'reverse' if '-R' in args else 'forward' if '--check' in args else 'actual'
                            result = {'returncode': 0, 'stdout': '', 'stderr': '', 'exception': None}
                            if current == phase:
                                result[stream] = message
                            elif phase == 'reverse' and current == 'forward':
                                result['returncode'] = 1
                            return result
                        with mock.patch.object(replay, 'run_git', side_effect=command):
                            self.assertEqual(self.apply()[0], 'conflict')

    def test_apply_failure_retains_full_output(self):
        real = replay.run_git
        def command(args, cwd):
            if args[0] == 'apply' and '--check' not in args:
                return {'returncode': 1, 'stdout': 'first\nlast\n', 'stderr': 'error\n', 'exception': None}
            return real(args, cwd)
        with mock.patch.object(replay, 'run_git', side_effect=command):
            status, detail = self.apply()
        self.assertEqual(status, 'conflict')
        self.assertTrue(detail['apply_attempted'])
        self.assertEqual(detail['commands'][-1]['stdout'], 'first\nlast\n')
        self.assertEqual(detail['commands'][-1]['stderr'], 'error\n')

    def test_main_exception_is_fail_fast(self):
        call = mock.Mock(side_effect=OSError('fixture unexpected'))
        rc, text = self.main_output([('first', '', ''), ('later', '', '')], apply_one=call)
        self.assertEqual(rc, 1)
        self.assertEqual(call.call_count, 1)
        self.assertIn('fixture unexpected', text)
        self.assertIn('notattempted (1): later', text)

    def test_post_apply_verify_exception_preserves_partial_state(self):
        rc, text = self.main_output(verify=mock.Mock(side_effect=OSError('fixture verify error')))
        self.assertEqual(rc, 1)
        self.assertEqual((self.root / 'new.txt').read_text(), 'expected\n')
        self.assertIn('已生效', text)
        self.assertIn('未验收', text)

    def test_dry_run_skipped_and_conflict_leave_index_unchanged(self):
        self.assertEqual(self.apply()[0], 'applied')
        self.git('add', '--', 'new.txt')
        for expected in ['skipped', 'conflict']:
            if expected == 'conflict':
                (self.root / 'new.txt').write_bytes(b'wrong\n')
            before = {p.relative_to(self.root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in self.root.rglob('*') if p.is_file()}
            self.assertEqual(self.apply(dry_run=True)[0], expected)
            after = {p.relative_to(self.root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in self.root.rglob('*') if p.is_file()}
            self.assertEqual(after, before)

    def test_actual_submodule_gitfile_is_supported(self):
        child = self.base / 'child'
        child.mkdir()
        def git_at(path, *args):
            p = subprocess.run(['git', '-C', str(path), *args], capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        git_at(child, 'init', '-q')
        (child / 'seed').write_bytes(b'seed\n')
        git_at(child, 'add', '--', 'seed')
        # Identity and protocol permission are scoped to these fixture commands.
        git_at(child, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
               '-c', 'commit.gpgsign=false', 'commit', '-q', '-m', 'isolated fixture')
        git_at(self.root, '-c', 'protocol.file.allow=always', 'submodule', 'add', '-q', str(child), 'module')
        self.assertTrue((self.root / 'module/.git').is_file())
        self.assertEqual(replay.apply_one(str(self.root), str(self.patches), self.name, '', 'module')[0], 'applied')
        self.assertEqual((self.root / 'module/new.txt').read_text(), 'expected\n')

    def test_check_does_not_simulate_dependent_patch(self):
        dependent = self.patches / 'dependent.patch'
        dependent.write_text('diff --git a/new.txt b/new.txt\n--- a/new.txt\n+++ b/new.txt\n@@ -1 +1 @@\n-expected\n+dependent\n', newline='\n')
        groups = [(self.name, '', ''), ('dependent.patch', '', ''), ('later.patch', '', '')]
        rc, text = self.main_output(groups, argv=['--check'])
        self.assertEqual(rc, 1)
        self.assertIn('would_apply (1): ' + self.name, text)
        self.assertIn('failed (1): dependent.patch', text)
        self.assertIn('notattempted (1): later.patch', text)
        self.assertIn('未真正改动目标文件或索引', text)
        self.assertNotIn('先前组可能已生效', text)
        self.assertFalse((self.root / 'new.txt').exists())

    def test_git_diagnostic_locale_is_deterministic(self):
        result = subprocess.CompletedProcess(['git'], 0, 'fixture stdout', 'fixture stderr')
        with mock.patch.object(replay.subprocess, 'run', return_value=result) as call:
            record = replay.run_git(['apply', '--check', '-v', str(self.patch)], str(self.root))
        self.assertEqual(call.call_args.kwargs.get('env', {}).get('LC_ALL'), 'C')
        self.assertEqual(record['stdout'], 'fixture stdout')
        self.assertEqual(record['stderr'], 'fixture stderr')

    def test_marker_only_is_not_proof(self):
        (self.root / 'new.txt').write_text('wrong\n')
        for rel, mark in [('src/CardinalCommon.cpp', 'CARDINAL-MCP-READ-PROBES-BEGIN'),
                          ('src/override/MenuBar.cpp', 'oscAutostartEnabled')]:
            p = self.root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(mark)
        self.assertEqual(self.apply()[0], 'conflict')


    @contextlib.contextmanager
    def injected_config(self, source, key, value):
        with contextlib.ExitStack() as stack:
            if source == 'local':
                self.git('config', '--local', key, value)
            elif source == 'global':
                home = self.base / 'isolated-home'
                home.mkdir(exist_ok=True)
                config = home / '.gitconfig'
                config.write_text('[%s]\n\t%s = %s\n' % (*key.split('.', 1), value))
                stack.enter_context(mock.patch.dict(os.environ, {
                    'HOME': str(home), 'USERPROFILE': str(home), 'XDG_CONFIG_HOME': str(home / '.config')}))
                # Verify this is real Git global configuration, not an ignored
                # GIT_CONFIG_* override or a mock of configuration lookup.
                p = subprocess.run(['git', 'config', '--global', '--get', key], capture_output=True, text=True)
                self.assertEqual(p.returncode, 0, p.stderr)
                self.assertEqual(p.stdout.strip(), value)
            else:
                stack.enter_context(mock.patch.dict(os.environ, {
                    'GIT_CONFIG_COUNT': '1', 'GIT_CONFIG_KEY_0': key, 'GIT_CONFIG_VALUE_0': value}))
            yield
            if source == 'local':
                self.git('config', '--local', '--unset', key)

    def test_whitespace_fix_never_rewrites_patch_bytes(self):
        self.patch.write_bytes(self.patch.read_bytes().replace(b'+expected\n', b'+expected   \n'))
        for source in ['local', 'global', 'env']:
            target = self.root / 'new.txt'
            target.unlink(missing_ok=True)
            with self.subTest(source=source), self.injected_config(source, 'apply.whitespace', 'fix'):
                status, detail = self.apply()
                self.assertEqual(status, 'applied', detail)
                self.assertEqual(target.read_bytes(), b'expected   \n')
                target.unlink()

    def test_whitespace_fix_cannot_prove_wrong_reverse_bytes(self):
        self.patch.write_bytes(self.patch.read_bytes().replace(b'+expected\n', b'+expected   \n'))
        target = self.root / 'new.txt'
        target.write_bytes(b'expected\n')
        for source in ['local', 'global', 'env']:
            with self.subTest(source=source), self.injected_config(source, 'apply.whitespace', 'fix'):
                self.assertEqual(self.apply(dry_run=True)[0], 'conflict')
                self.assertEqual(target.read_bytes(), b'expected\n')

    def test_ignorewhitespace_cannot_weaken_context_matching(self):
        self.patch.write_bytes(b'diff --git a/new.txt b/new.txt\n--- a/new.txt\n+++ b/new.txt\n@@ -1,2 +1,2 @@\n context exact\n-old\n+new\n')
        target = self.root / 'new.txt'
        for source in ['local', 'global', 'env']:
            for content in [b'context    exact\nold\n', b'context    exact\nnew\n']:
                with self.subTest(source=source, content=content), self.injected_config(source, 'apply.ignorewhitespace', 'change'):
                    target.write_bytes(content)
                    self.assertEqual(self.apply(dry_run=True)[0], 'conflict')
                    self.assertEqual(target.read_bytes(), content)

    def test_env_cannot_bind_directory_without_own_git(self):
        target = self.base / 'not-repo'
        target.mkdir()
        injected = {'GIT_DIR': str(self.root / '.git'), 'GIT_WORK_TREE': str(target)}
        with mock.patch.dict(os.environ, injected):
            # Real Git accepts the inherited binding; replay must not.
            probe = subprocess.run(['git', '-C', str(target), 'rev-parse', '--show-toplevel'], capture_output=True, text=True)
            self.assertEqual(probe.returncode, 0, probe.stderr)
            self.assertEqual(Path(probe.stdout.strip()).resolve(), target.resolve())
            self.assertEqual(replay.apply_one(str(target), str(self.patches), self.name, '', '')[0], 'conflict')
        self.assertFalse((target / 'new.txt').exists())
        self.assertFalse((target / '.git').exists())

    def test_git_environment_cannot_redirect_repo_index_or_config(self):
        external = self.base / 'external'
        external.mkdir()
        p = subprocess.run(['git', 'init', '-q', str(external)], capture_output=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        (external / 'sentinel').write_bytes(b'external\n')
        def snapshot(path):
            return {p.relative_to(path).as_posix(): p.read_bytes() for p in path.rglob('*') if p.is_file()}
        before = snapshot(external)
        foreign_index = self.base / 'foreign.index'
        foreign_index.write_bytes(b'not-an-index')
        env = {'GIT_DIR': str(external / '.git'), 'GIT_WORK_TREE': str(external),
               'GIT_COMMON_DIR': str(external / '.git'), 'GIT_INDEX_FILE': str(foreign_index),
               'GIT_CONFIG_PARAMETERS': "'apply.whitespace=fix'", 'GIT_CONFIG_COUNT': '1',
               'GIT_CONFIG_KEY_0': 'core.worktree', 'GIT_CONFIG_VALUE_0': str(external)}
        with mock.patch.dict(os.environ, env):
            status, detail = self.apply()
        self.assertEqual(status, 'applied', detail)
        self.assertEqual((self.root / 'new.txt').read_bytes(), b'expected\n')
        self.assertEqual(snapshot(external), before)
        self.assertEqual(foreign_index.read_bytes(), b'not-an-index')

    def test_diagnostic_words_in_legitimate_paths_are_not_skips(self):
        for name in ['skip.txt', 'skipped.txt', 'excluded.txt', 'partial.txt', 'path-filtered.txt']:
            with self.subTest(name=name):
                self.patch.write_bytes(('diff --git a/{0} b/{0}\nnew file mode 100644\n--- /dev/null\n+++ b/{0}\n@@ -0,0 +1 @@\n+expected\n'.format(name)).encode())
                self.assertEqual(self.apply(dry_run=True)[0], 'would_apply')
                self.assertEqual(self.apply()[0], 'applied')
                self.assertEqual(self.apply(dry_run=True)[0], 'skipped')
                self.assertEqual((self.root / name).read_bytes(), b'expected\n')

    def test_real_git_skipped_patch_is_rejected_in_all_phases(self):
        sub = self.root / 'ordinary'
        sub.mkdir()
        real = replay.run_git
        for phase in ['forward', 'reverse', 'actual']:
            with self.subTest(phase=phase):
                def command(args, cwd):
                    if args[0] != 'apply':
                        return real(args, cwd)
                    current = 'reverse' if '-R' in args else 'forward' if '--check' in args else 'actual'
                    if current == phase:
                        return real(args, str(sub))  # Real Git path-prefix skip.
                    if phase == 'reverse' and current == 'forward':
                        return dict(real(args, cwd), returncode=1)
                    return real(args, cwd)
                with mock.patch.object(replay, 'run_git', side_effect=command):
                    status, detail = self.apply()
                self.assertEqual(status, 'conflict', detail)
                diagnostic = [r for r in detail['commands'] if "Skipped patch 'new.txt'" in r['stderr']]
                self.assertEqual(len(diagnostic), 1, detail)
                self.assertEqual(diagnostic[0]['returncode'], 0)
                self.assertFalse((self.root / 'new.txt').exists())

    def test_cli_invalid_arguments_fail_closed_before_any_work(self):
        invalid = [['--chek'], ['--check', '--verify'], ['--check=true'],
                   ['--verify', 'value'], ['value'], ['--check', '--check'],
                   ['--help', '--chek'], ['--check', 'false'], ['--ver']]
        for argv in invalid:
            with self.subTest(argv=argv):
                apply = mock.Mock(return_value=('applied', {}))
                verify = mock.Mock(return_value=(True, [], 33))
                resolver = mock.Mock(return_value=str(self.patches))
                with mock.patch.object(replay.os, 'makedirs') as mkdir, \
                     mock.patch.object(replay.subprocess, 'run') as command, \
                     contextlib.redirect_stderr(io.StringIO()):
                    rc, text = self.main_output(argv=argv, apply_one=apply, verify=verify,
                                                find_patch_dir=resolver)
                self.assertEqual(rc, 2)
                for call in [apply, verify, resolver, mkdir, command]:
                    call.assert_not_called()
                self.assertFalse((self.root / 'new.txt').exists())

    def test_cli_help_remains_read_only(self):
        for flag in ['--help', '-h']:
            apply = mock.Mock()
            rc, text = self.main_output(argv=[flag], apply_one=apply)
            self.assertEqual(rc, 0)
            self.assertIn('17 组', text)
            apply.assert_not_called()

    def test_autocrlf_policy_is_command_scoped_and_dryrun_is_readonly(self):
        self.git('config', '--local', 'core.autocrlf', 'true')
        self.git('config', '--local', 'core.eol', 'crlf')
        (self.root / 'seed').write_bytes(b'seed\n')
        self.git('-c', 'core.autocrlf=false', 'add', '--', 'seed')
        def snapshot():
            return {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        before = snapshot()
        self.assertEqual(self.apply(dry_run=True)[0], 'would_apply')
        self.assertEqual(snapshot(), before)
        self.assertEqual(self.apply()[0], 'applied')
        self.assertEqual((self.root / 'new.txt').read_bytes(), b'expected\n')
        before = snapshot()
        self.assertEqual(self.apply(dry_run=True)[0], 'skipped')
        self.assertEqual(snapshot(), before)
        self.assertEqual(self.git('config', '--local', '--get', 'core.autocrlf').strip(), 'true')
        self.assertEqual(self.git('config', '--local', '--get', 'core.eol').strip(), 'crlf')

    def test_all_inherited_git_variables_are_removed(self):
        result = subprocess.CompletedProcess(['git'], 0, '', '')
        with mock.patch.dict(os.environ, {'GIT_CONFIG_GLOBAL': 'bad', 'GIT_CONFIG_SYSTEM': 'bad',
                                        'GIT_CEILING_DIRECTORIES': 'bad', 'GIT_INDEX_FILE': 'bad'}), \
             mock.patch.object(replay.subprocess, 'run', return_value=result) as call:
            record = replay.run_git(['rev-parse', '--show-toplevel'], str(self.root))
        env = call.call_args.kwargs['env']
        self.assertFalse([key for key in env if key.upper().startswith('GIT_')])
        self.assertIn('core.autocrlf=false', record['command'])
        self.assertIn('apply.whitespace=nowarn', record['command'])
        self.assertIn('apply.ignorewhitespace=no', record['command'])

    def test_invalid_gitfile_is_not_a_repository(self):
        target = self.base / 'invalid-gitfile'
        target.mkdir()
        (target / '.git').write_text('gitdir: missing-metadata\n')
        status, detail = replay.apply_one(str(target), str(self.patches), self.name, '', '')
        self.assertEqual(status, 'conflict', detail)
        self.assertFalse((target / 'new.txt').exists())

if __name__ == '__main__':
    unittest.main()
