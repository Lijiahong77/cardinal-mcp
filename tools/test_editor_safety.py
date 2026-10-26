"""Offline editor contracts: scratch fixtures, no sockets, mocked loaders only."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRATCH = os.environ['TMPDIR']
os.environ.update(TMPDIR=SCRATCH, TEMP=SCRATCH, TMP=SCRATCH)
def deny_socket(event, args):
    if event == 'socket.__new__':
        raise AssertionError('real socket forbidden')
sys.addaudithook(deny_socket)
import songroll
import seq
import samplelib
import patchio
import cardinal_mcp as cm


def document():
    return {'version': '2.0', 'zoom': .7, 'gridOffset': [3, 5], 'cables': [], 'modules': [
        {'id': 11, 'plugin': 'rcm', 'model': 'rcm-songroll', 'pos': [1, 2],
         'data': {'running': False, 'songRoll': {'sections': songroll._default_sections()}}},
        {'id': 12, 'plugin': 'rcm', 'model': 'rcm-pianoroll', 'pos': [2, 2],
         'data': {'sequenceRunning': False, 'patterns': [{'beatsPerMeasure': 1,
          'divisionsPerBeat': 1, 'measures': [{'notes': [{'pitch': 60, 'active': True,
          'velocity': .5, 'retrigger': False}]}]}]}},
        {'id': 13, 'plugin': 'voxglitch', 'model': 'samplerx8', 'pos': [3, 2],
         'data': {'loaded_sample_path_1': 'old/voice.wav',
                  'loaded_sample_path_2': 'untouched/voice.wav', 'samples_root_dir': 'old'}}]}


class EditorSafety(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=SCRATCH, prefix='editor-safety-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = str(self.root / 'outside.vcv')
        self.doc = document()
        self.save()

    def save(self):
        Path(self.path).write_text(json.dumps(self.doc), encoding='utf-8')

    def calls(self):
        return [lambda **kw: songroll.read_sections(self.path, **kw),
                lambda **kw: songroll.write_sections(self.path, kw.pop('module', None), songroll._default_sections(2), **kw),
                lambda **kw: songroll.edit(self.path, kw.pop('module', None), 'add_section', **kw),
                lambda **kw: seq.edit_note(self.path, kw.pop('module', 'pianoroll'), 0, 0, pitch=62, **kw),
                lambda **kw: seq.set_running(self.path, kw.pop('module', 'pianoroll'), False, **kw),
                lambda **kw: samplelib.load_sample(self.path, str(self.root / 'voice.wav'), module=kw.pop('module', None), **kw),
                lambda **kw: samplelib.clear_slot(self.path, 1, **kw)]

    def test_ambiguous_targets_refuse_without_any_file_or_load(self):
        for index, module_index in enumerate((0, 0, 0, 1, 1, 2, 2)):
            with self.subTest(entry=index):
                self.doc = document()
                duplicate = copy.deepcopy(self.doc['modules'][module_index])
                duplicate['id'] += 100
                self.doc['modules'].append(duplicate)
                self.save()
                before = Path(self.path).read_bytes()
                names = set(self.root.iterdir())
                with patch.object(cm, 'load_patch') as loader:
                    out = self.calls()[index]()
                self.assertIs(out.get('ok'), False, out)
                self.assertEqual(len(out['candidates']), 2)
                self.assertEqual(set(out['candidates'][0]), {'module_id', 'plugin', 'model'})
                self.assertEqual(Path(self.path).read_bytes(), before)
                self.assertEqual(set(self.root.iterdir()), names)
                loader.assert_not_called()

    def test_exact_id_selects_one_and_rejects_invalid_conflicting_or_duplicate(self):
        (self.root / 'voice.wav').write_bytes(b'existence only')
        for index, mi in enumerate((0, 0, 0, 1, 1, 2, 2)):
            with self.subTest(entry=index):
                self.doc = document()
                twin = copy.deepcopy(self.doc['modules'][mi])
                twin['id'] += 100
                self.doc['modules'].append(twin)
                self.save()
                out = self.calls()[index](module_id=twin['id'])
                self.assertTrue(out.get('ok'), out)
                self.assertEqual(patchio.read_patch(self.path)['modules'][mi], self.doc['modules'][mi])
                for bad in (True, '11', 1.0, -1, 2**63, 999):
                    before, names = Path(self.path).read_bytes(), set(self.root.iterdir())
                    out = self.calls()[index](module_id=bad)
                    self.assertIs(out.get('ok'), False, out)
                    self.assertEqual(Path(self.path).read_bytes(), before)
                    self.assertEqual(set(self.root.iterdir()), names)
                out = self.calls()[index](module='not-the-module', module_id=twin['id'])
                self.assertIs(out.get('ok'), False, out)
                self.doc['modules'].append(copy.deepcopy(twin))
                self.save()
                before, names = Path(self.path).read_bytes(), set(self.root.iterdir())
                out = self.calls()[index](module_id=twin['id'])
                self.assertIs(out.get('ok'), False, out)
                self.assertEqual(Path(self.path).read_bytes(), before)
                self.assertEqual(set(self.root.iterdir()), names)

    def test_mcp_schema_dispatch_carries_exact_id(self):
        (self.root / 'voice.wav').write_bytes(b'existence only')
        entries = [
            ('cardinal_songroll_read', {}),
            ('cardinal_songroll_write', {'sections': songroll._default_sections(2)}),
            ('cardinal_songroll_edit', {'op': 'add_section'}),
            ('cardinal_seq_edit_note', {'module': 'pianoroll', 'measure': 0, 'step': 0, 'pitch': 62}),
            ('cardinal_seq_set_running', {'module': 'pianoroll', 'running': False}),
            ('cardinal_sample_load', {'file': str(self.root / 'voice.wav'), 'slot': 1}),
            ('cardinal_sample_clear', {'slot': 1})]
        for (name, extra), mi in zip(entries, (0, 0, 0, 1, 1, 2, 2)):
            with self.subTest(tool=name):
                self.doc = document()
                twin = copy.deepcopy(self.doc['modules'][mi])
                twin['id'] = 2**62
                self.doc['modules'].append(twin)
                self.save()
                args = dict(patch=self.path, module_id=twin['id'], **extra)
                result = cm.handle({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                                    'params': {'name': name, 'arguments': args}})['result']
                self.assertFalse(result['isError'], result)
                self.assertTrue(result['structuredContent']['ok'])
                self.assertEqual(patchio.read_patch(self.path)['modules'][mi], self.doc['modules'][mi])
                args['module_id'] = str(twin['id'])
                with self.assertRaises(ValueError):
                    cm._call_tool(name, args)

    def test_sample_stores_the_existing_canonical_file_not_old_basename(self):
        first, second = self.root / 'first', self.root / 'second'
        first.mkdir()
        second.mkdir()
        (first / 'voice.wav').write_bytes(b'first')
        (second / 'voice.wav').write_bytes(b'second')
        self.doc['modules'][2]['data']['loaded_sample_path_1'] = str(first / 'voice.wav')
        self.save()
        requested = str(second / '..' / 'second' / 'voice.wav')
        out = samplelib.load_sample(self.path, requested, module='samplerx8', backup=False)
        self.assertTrue(out['ok'], out)
        expected = os.path.realpath(requested).replace('\\', '/')
        data = patchio.read_patch(self.path)['modules'][2]['data']
        self.assertEqual(data['loaded_sample_path_1'], expected)
        self.assertEqual(out['resolved_abs'], expected)
        self.assertEqual(data['samples_root_dir'], str(second.resolve()).replace('\\', '/'))
        self.assertEqual(data['loaded_sample_path_2'], 'untouched/voice.wav')

    def writing_calls(self):
        (self.root / 'voice.wav').write_bytes(b'existence only')
        return [lambda load: songroll.write_sections(self.path, None, songroll._default_sections(2), load_after=load),
                lambda load: songroll.edit(self.path, None, 'add_section', load_after=load),
                lambda load: seq.edit_note(self.path, 'pianoroll', 0, 0, pitch=62, load_after=load),
                lambda load: seq.set_running(self.path, 'pianoroll', False, load_after=load),
                lambda load: samplelib.load_sample(self.path, str(self.root / 'voice.wav'), load_after=load)]

    def test_writes_reload_once_exact_full_path_or_never_when_false(self):
        for index, call in enumerate(self.writing_calls()):
            for requested in (False, True):
                with self.subTest(entry=index, load=requested):
                    self.save()
                    with patch.object(cm, 'load_patch', return_value={'ok': True}) as loader:
                        out = call(requested)
                    self.assertTrue(out['ok'], out)
                    self.assertEqual(out['written_path'], os.path.abspath(self.path))
                    self.assertEqual(out['written'], self.path)
                    self.assertIs(out['load_requested'], requested)
                    self.assertIs(out['verified'], False)
                    if requested:
                        loader.assert_called_once_with(os.path.abspath(self.path))
                        self.assertEqual(out['loaded'], {'ok': True})
                        self.assertIs(out['load_succeeded'], True)
                        self.assertEqual(out['stage'], 'load_succeeded')
                    else:
                        loader.assert_not_called()
                        self.assertIs(out['loaded'], False)
                        self.assertEqual(out['stage'], 'written')

    def parameter_calls(self):
        import musiclib
        import paramlib
        self.doc['modules'].append({'id': 14, 'plugin': 'fixture', 'model': 'Voice',
                                   'pos': [4, 2], 'params': [{'id': 0, 'value': .1}]})
        lookup = {'plugin': 'fixture', 'model': 'Voice', 'params': {
            '0': {'name': 'Level', 'kind': 'param', 'min': 0, 'max': 1}}}
        context = patch.object(paramlib, 'lookup', return_value=lookup)
        context.start()
        self.addCleanup(context.stop)
        context = patch.object(musiclib, 'recipe', return_value={'name': 'fixture', 'settings': [
            {'module': 'Voice', 'param': 'Level', 'value': .7}]})
        context.start()
        self.addCleanup(context.stop)
        return [lambda load: cm.set_param_by_name(self.path, 'Voice', 'Level', .8, load_after=load),
                lambda load: cm.set_params_by_name_batch(self.path, [{'module': 'Voice', 'param': 'Level', 'value': .8}], load_after=load),
                lambda load: cm.apply_recipe(self.path, 'fixture', load_after=load)]

    def test_parameter_recipe_wrappers_use_same_stage_receipt_preserve_written_type(self):
        for index, call in enumerate(self.parameter_calls()):
            for requested in (False, True):
                with self.subTest(entry=index, load=requested):
                    self.save()
                    with patch.object(cm, 'load_patch', return_value={'ok': True}) as loader:
                        out = call(requested)
                    self.assertTrue(out.get('ok'), out)
                    self.assertEqual(out['written_path'], os.path.abspath(self.path))
                    if index in (1, 2):
                        self.assertIs(out['written'], True)
                    self.assertIs(out['verified'], False)
                    if requested:
                        loader.assert_called_once_with(os.path.abspath(self.path))
                    else:
                        loader.assert_not_called()

    def test_loader_errors_warnings_malformed_and_throw_preserve_write_not_success(self):
        calls = self.writing_calls() + self.parameter_calls()
        replies = [{'ok': False, 'error': 'rejected'}, {'ok': True, 'warnings': ['partial']},
                   {'ok': True, 'warning': 'partial'}, None, [], {'ok': 'true'}, RuntimeError('after send')]
        for index, call in enumerate(calls):
            for reply in replies:
                with self.subTest(entry=index, reply=reply):
                    self.save()
                    before = Path(self.path).read_bytes()
                    kwargs = {'side_effect': reply} if isinstance(reply, Exception) else {'return_value': reply}
                    with patch.object(cm, 'load_patch', **kwargs) as loader:
                        out = call(True)
                    loader.assert_called_once_with(os.path.abspath(self.path))
                    self.assertIs(out['ok'], False, out)
                    self.assertTrue(out.get('written'), out)
                    self.assertEqual(out['written_path'], os.path.abspath(self.path))
                    self.assertNotEqual(Path(self.path).read_bytes(), before)
                    self.assertIs(out['verified'], False)
                    self.assertIn(out['stage'], ('load_failed', 'load_unknown'))
                    self.assertIsNot(out['load_succeeded'], True)
                    if isinstance(reply, Exception):
                        self.assertIsNone(out['loaded'])
                        self.assertIsNone(out['load_succeeded'])
                    else:
                        self.assertEqual(out['loaded'], reply)

    def test_backup_and_write_failures_are_structured_and_never_load(self):
        import shutil
        calls = self.writing_calls() + self.parameter_calls()[:2] + [
            lambda load: samplelib.clear_slot(self.path, 1)]
        for index, call in enumerate(calls):
            for failure in ('backup', 'write'):
                with self.subTest(entry=index, failure=failure):
                    self.save()
                    before = Path(self.path).read_bytes()
                    target, attr = (shutil, 'copy2') if failure == 'backup' else (patchio, 'write_patch')
                    with patch.object(target, attr, side_effect=OSError('fixture failure')), patch.object(cm, 'load_patch') as loader:
                        out = call(True)
                    self.assertIs(out['ok'], False, out)
                    self.assertIs(out['written'], False, out)
                    self.assertIsNone(out['written_path'])
                    self.assertEqual(out['stage'], failure + '_failed')
                    self.assertNotIn('已被覆盖', out.get('note', ''))
                    self.assertIs(out['verified'], False)
                    self.assertEqual(Path(self.path).read_bytes(), before)
                    loader.assert_not_called()
                    if failure == 'write':
                        self.assertTrue(Path(out['backup']).is_file())

    def test_backup_false_clear_does_not_claim_business_backup_but_keeps_patchio_version(self):
        out = samplelib.clear_slot(self.path, 1, backup=False)
        self.assertTrue(out['ok'], out)
        self.assertNotIn('backup', out)
        self.assertFalse(Path(self.path + '.bak-sample').exists())
        self.assertEqual(len(list(self.root.glob('*.bak-patchio-*'))), 1)

    def test_shared_selector_rejects_duplicate_identity_even_without_explicit_id(self):
        import editor_contracts
        chosen = self.doc['modules'][0]
        duplicate = dict(self.doc['modules'][2], id=chosen['id'])
        target, error = editor_contracts.select_target([chosen, duplicate], [chosen], 'songroll')
        self.assertIsNone(target)
        self.assertIs(error['ok'], False)
        twin = dict(chosen, plugin='another', id=77)
        target, error = editor_contracts.select_target([chosen, twin], [chosen, twin], 'songroll')
        self.assertIsNone(target)
        self.assertEqual(len(error['candidates']), 2)
        target, error = editor_contracts.select_target([chosen], [chosen], str(chosen['id']))
        self.assertIsNone(target)

    def test_recipe_wrapper_write_exception_returns_no_write_receipt(self):
        call = self.parameter_calls()[2]
        self.save()
        before = Path(self.path).read_bytes()
        with patch.object(patchio, 'write_patch', side_effect=OSError('fixture write failure')), patch.object(cm, 'load_patch') as loader:
            out = call(True)
        self.assertIs(out['ok'], False, out)
        self.assertIs(out['written'], False)
        self.assertIsNone(out['written_path'])
        self.assertEqual(out['stage'], 'write_failed')
        self.assertEqual(Path(self.path).read_bytes(), before)
        loader.assert_not_called()

    def test_cli_exact_id_and_ambiguity_are_offline_with_exit_status(self):
        import contextlib
        import io
        import runpy
        self.doc['modules'].append(dict(copy.deepcopy(self.doc['modules'][0]), id=99))
        for module_id in (None, 99, '99'):
            with self.subTest(module_id=module_id):
                self.save()
                before = Path(self.path).read_bytes()
                args = {'patch': self.path, 'op': 'add_section', 'load_after': False}
                if module_id is not None:
                    args['module_id'] = module_id
                output = io.StringIO()
                with patch.object(sys, 'argv', [cm.__file__, '--call', 'cardinal_songroll_edit', json.dumps(args)]), contextlib.redirect_stdout(output):
                    with self.assertRaises(SystemExit) as caught:
                        runpy.run_path(cm.__file__, run_name='__main__')
                out = json.loads(output.getvalue())
                self.assertEqual(caught.exception.code, 0 if module_id == 99 else 1)
                if module_id == 99:
                    self.assertEqual(out['stage'], 'written')
                    self.assertIs(out['load_requested'], False)
                else:
                    self.assertEqual(Path(self.path).read_bytes(), before)

    def test_new_write_routes_preserve_json_archive_resources_running_and_layout(self):
        import io
        import tarfile
        import zstandard
        calls = self.writing_calls() + self.parameter_calls() + [lambda load: samplelib.clear_slot(self.path, 1)]
        for archive in (False, True):
            for index, call in enumerate(calls):
                with self.subTest(archive=archive, entry=index):
                    payload = json.dumps(self.doc).encode()
                    if archive:
                        stream = io.BytesIO()
                        with tarfile.open(fileobj=stream, mode='w', format=tarfile.PAX_FORMAT) as tf:
                            for name, data in [('patch.json', payload), ('modules/13/keep.bin', b'resource-unchanged')]:
                                info = tarfile.TarInfo(name)
                                info.size, info.mode, info.mtime = len(data), 0o640, 123
                                tf.addfile(info, io.BytesIO(data))
                        payload = zstandard.ZstdCompressor().compress(stream.getvalue())
                    Path(self.path).write_bytes(payload)
                    with patch.object(cm, 'load_patch') as loader:
                        out = call(False)
                    self.assertTrue(out['ok'], out)
                    loader.assert_not_called()
                    raw = Path(self.path).read_bytes()
                    self.assertIs(patchio.is_archive(raw), archive)
                    after = patchio.read_patch(self.path)
                    self.assertEqual(after['zoom'], self.doc['zoom'])
                    self.assertEqual(after['gridOffset'], self.doc['gridOffset'])
                    self.assertEqual([m['pos'] for m in after['modules']], [m['pos'] for m in self.doc['modules']])
                    self.assertIs(after['modules'][0]['data']['running'], False)
                    self.assertIs(after['modules'][1]['data']['sequenceRunning'], False)
                    if archive:
                        with tarfile.open(fileobj=io.BytesIO(zstandard.ZstdDecompressor().decompress(raw)), mode='r:') as tf:
                            resource = tf.getmember('modules/13/keep.bin')
                            self.assertEqual(tf.extractfile(resource).read(), b'resource-unchanged')
                            self.assertEqual((resource.mode, resource.mtime), (0o640, 123))

    def test_recipe_no_applied_settings_reports_no_write_no_reload(self):
        import musiclib
        with patch.object(musiclib, 'recipe', return_value={'name': 'empty', 'settings': []}), patch.object(cm, 'load_patch') as loader:
            out = cm.apply_recipe(self.path, 'empty', load_after=True)
        self.assertIs(out['written'], False)
        self.assertIsNone(out['written_path'])
        self.assertIs(out['load_requested'], True)
        self.assertIs(out['loaded'], False)
        self.assertIs(out['verified'], False)
        self.assertEqual(out['stage'], 'not_written')
        loader.assert_not_called()

    def test_mcp_full_path_reload_failure_does_not_touch_shadow_patch(self):
        shadow_dir = self.root / 'default-patches'
        shadow_dir.mkdir()
        shadow = shadow_dir / Path(self.path).name
        shadow.write_bytes(b'not-the-requested-patch')
        for reply in ({'ok': True}, {'ok': False}, {'ok': True, 'warnings': ['partial']}, RuntimeError('after send')):
            with self.subTest(reply=reply):
                self.save()
                args = {'patch': self.path, 'module_id': 11, 'op': 'add_section', 'load_after': True}
                kwargs = {'side_effect': reply} if isinstance(reply, Exception) else {'return_value': reply}
                with patch.object(cm, 'PATCH_DIR', str(shadow_dir)), patch.object(cm, 'load_patch', **kwargs) as loader:
                    result = cm.handle({'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call',
                                        'params': {'name': 'cardinal_songroll_edit', 'arguments': args}})['result']
                loader.assert_called_once_with(os.path.abspath(self.path))
                self.assertIs(result['isError'], reply != {'ok': True})
                out = result['structuredContent']
                self.assertTrue(out['written'])
                self.assertIs(out['verified'], False)
                self.assertEqual(shadow.read_bytes(), b'not-the-requested-patch')


if __name__ == '__main__':
    unittest.main(verbosity=2)
