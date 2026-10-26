"""Value/identity regression: scratch fixtures only; sockets forbidden."""
import copy
import io
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
        raise AssertionError('real sockets forbidden')
sys.addaudithook(deny_socket)
with patch.dict(os.environ, CARDINAL_PATCH_DIR=SCRATCH, CARDINAL_SAMPLES_DIR=SCRATCH):
    import cardinal_mcp as cm
    import paramlib as pl
    import musiclib as ml
    import seq
    import songroll
    import samplelib
    import patchio


def entry(plugin, model='Twin', pid=0, lo=0, hi=1, default=.2):
    return {'plugin': plugin, 'model': model, 'params': {str(pid): {
        'name': 'Level', 'kind': 'knob', 'min': lo, 'max': hi, 'default': default}}}

class ValueSafety(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=SCRATCH, prefix='value-safety-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = str(self.root / 'fixture.vcv')
        self.doc = {'version': '2.0', 'cables': [], 'modules': [
            {'id': 1, 'plugin': 'A', 'model': 'Twin', 'params': []},
            {'id': 2, 'plugin': 'B', 'model': 'Twin', 'params': []}]}
        self.lib = {'A/Twin': entry('A'), 'B/Twin': entry('B', pid=7, lo=10, hi=20, default=12)}
        self.addCleanup(patch.stopall)
        patch.object(pl, 'load', return_value=self.lib).start()
        self.store()
    def store(self):
        Path(self.path).write_text(json.dumps(self.doc), encoding='utf-8')
    def refused(self, fn):
        before = Path(self.path).read_bytes()
        names = set(self.root.rglob('*'))
        with patch.object(cm, 'load_patch') as loader:
            out = fn()
        self.assertTrue(out.get('error') or out.get('ok') is False, out)
        self.assertFalse(out.get('written'), out)
        self.assertEqual(Path(self.path).read_bytes(), before)
        self.assertEqual(set(self.root.rglob('*')), names)
        loader.assert_not_called()
        return out
    def test_lookup_identity_fail_closed(self):
        self.assertIsNone(pl.lookup('Missing', 'Twin'))
        self.assertEqual(pl.lookup('a', 'twin'), self.lib['A/Twin'])
        self.lib['a/twin'] = entry('a', 'twin')
        self.assertIsNone(pl.lookup('A', 'Twin'))
        del self.lib['a/twin']
        self.lib['A/Twin'] = entry('B')
        self.assertIsNone(pl.lookup('A', 'Twin'))
    def test_recipe_resolves_each_instance_and_reports_partial(self):
        self.doc['modules'].append({'id': 3, 'plugin': 'Missing', 'model': 'Twin', 'params': []})
        self.store()
        r = {'name': 'fixture', 'settings': [{'module': 'Twin', 'param': 'Level', 'value': 18}]}
        with patch.object(ml, 'recipe', return_value=r):
            out = ml.apply_recipe(self.path, 'fixture', weight=.5)
        self.assertTrue(out['written'], out)
        self.assertTrue(out['partial'], out)
        self.assertEqual([(a['plugin'], a['module_id'], a['param_id'], a['value']) for a in out['applied']],
                         [('A', 1, 0, 1), ('B', 2, 7, 15)])
        self.assertEqual(out['skipped'][0]['plugin'], 'Missing')
        self.assertEqual(out['skipped'][0]['module_id'], 3)
        self.assertEqual(patchio.read_patch(self.path)['modules'][2]['params'], [])

    def sequences(self):
        self.doc['modules'] = [
            {'id': 10, 'plugin': 'rcm', 'model': 'rcm-pianoroll', 'data': {
                'patterns': [{'beatsPerMeasure': 1, 'divisionsPerBeat': 2,
                    'measures': [{'notes': [{'pitch': 60, 'velocity': .5, 'active': True,
                    'retrigger': False} for _ in range(2)]} for _ in range(2)]}]}},
            {'id': 11, 'plugin': 'Starsea', 'model': 'MiniArranger', 'data': {
                'arranger': {'tracks': [{'measures': 2, 'notes': []}]}}}]
        self.store()
    def test_seq_rejects_invalid_types_before_write(self):
        self.sequences()
        for model in ('pianoroll', 'MiniArranger'):
            for key in ('pattern', 'track', 'measure', 'step', 'pitch', 'length'):
                for bad in (True, .5, '0', float('nan'), float('inf'), 10**1000):
                    with self.subTest(model=model, key=key, bad=repr(bad)[:40]):
                        kw = dict(measure=0, step=0, pitch=60)
                        kw[key] = bad
                        self.refused(lambda: seq.edit_note(self.path, model, **kw, load_after=True))
            for key in ('active', 'retrigger', 'clear', 'backup', 'load_after'):
                for bad in (0, 1, 'false'):
                    with self.subTest(key=key, bad=bad):
                        self.refused(lambda: seq.edit_note(self.path, model, 0, 0, **{key: bad}))
            for bad in (True, '0.5', float('nan'), float('inf'), -float('inf'), 10**1000):
                self.refused(lambda: seq.edit_note(self.path, model, 0, 0, velocity=bad, load_after=True))
    def test_seq_rejects_negative_and_actual_upper_bounds(self):
        self.sequences()
        for model, cases in [('pianoroll', [('pattern', -1), ('pattern', 1), ('measure', -1), ('measure', 2), ('step', -1), ('step', 2)]),
                             ('MiniArranger', [('track', -1), ('track', 1), ('measure', -1), ('measure', 2), ('step', -1), ('step', 16)])]:
            for key, bad in cases:
                with self.subTest(model=model, key=key, bad=bad):
                    kw = dict(measure=0, step=0, pitch=60)
                    kw[key] = bad
                    self.refused(lambda: seq.edit_note(self.path, model, **kw, load_after=True))
    def test_seq_running_strict_bool_and_existing_selection(self):
        self.sequences()
        for model, key in [('pianoroll', 'pattern'), ('MiniArranger', 'track')]:
            for bad in (None, 0, 1, 'false', float('nan')):
                self.refused(lambda: seq.set_running(self.path, model, bad, load_after=True))
            for bad in (-1, 1, True, .5, '0', 10**1000):
                self.refused(lambda: seq.set_running(self.path, model, False, **{key: bad}, load_after=True))
            self.assertTrue(seq.set_running(self.path, model, False)['ok'])
    def test_seq_normal_boundaries_and_rcm_warning(self):
        self.sequences()
        out = seq.edit_note(self.path, 'pianoroll', 1, 1, pitch=128, velocity=1)
        self.assertTrue(out['ok'], out)
        self.assertTrue(out['warnings'])
        for pitch, length, velocity in ((12, 1, 0), (108, 16, 1)):
            out = seq.edit_note(self.path, 'MiniArranger', 1, 15, pitch=pitch, length=length, velocity=velocity)
            self.assertTrue(out['ok'], out)
        for kw in ({'pitch': 11}, {'pitch': 109}, {'length': 0}, {'length': 17}):
            self.refused(lambda: seq.edit_note(self.path, 'MiniArranger', 0, 0, **kw))

    def test_recipe_invalid_numeric_inputs_have_no_side_effect(self):
        r = {'name': 'fixture', 'settings': [{'module': 'Twin', 'param': 'Level', 'value': .8}]}
        with patch.object(ml, 'recipe', return_value=r):
            for bad in (True, '0.5', float('nan'), float('inf'), -float('inf'), 10**1000):
                with self.subTest(weight=repr(bad)[:40]):
                    self.refused(lambda: ml.apply_recipe(self.path, 'fixture', weight=bad))
            for bad in (-1, True, .5, '0', float('nan'), float('inf')):
                with self.subTest(index=bad):
                    r['settings'][0]['index'] = bad
                    self.refused(lambda: ml.apply_recipe(self.path, 'fixture'))
            r['settings'][0]['index'] = 0
            for bad in (True, '0.5', float('nan'), float('inf'), 10**1000):
                with self.subTest(target=repr(bad)[:40]):
                    r['settings'][0]['value'] = bad
                    self.refused(lambda: ml.apply_recipe(self.path, 'fixture'))
    def test_recipe_invalid_current_metadata_and_overflow_refuse_prewrite(self):
        r = {'name': 'fixture', 'settings': [{'module': 'Twin', 'param': 'Level', 'value': .8}]}
        with patch.object(ml, 'recipe', return_value=r):
            for field in ('min', 'max', 'default'):
                for bad in (True, '0.2', float('nan'), float('inf'), 10**1000):
                    with self.subTest(field=field, bad=repr(bad)[:40]):
                        info = self.lib['A/Twin']['params']['0']
                        old = info[field]
                        info[field] = bad
                        self.refused(lambda: ml.apply_recipe(self.path, 'fixture'))
                        info[field] = old
            for bad in (True, '0.5', float('nan'), float('inf'), 10**1000):
                self.doc['modules'][0]['params'] = [{'id': 0, 'value': bad}]
                self.store()
                self.refused(lambda: ml.apply_recipe(self.path, 'fixture'))
            self.doc['modules'][0]['params'] = [{'id': 0, 'value': 1e308}]
            self.store()
            r['settings'][0]['value'] = 1e308
            out = ml.apply_recipe(self.path, 'fixture', weight=.5)
            self.assertTrue(out['written'], out)
    def test_recipe_preserves_finite_clamp_and_partial_index_policy(self):
        r = {'name': 'fixture', 'settings': [{'module': 'Twin', 'param': 'Level', 'value': 30, 'index': 10}]}
        with patch.object(ml, 'recipe', return_value=r):
            out = ml.apply_recipe(self.path, 'fixture', weight=2)
            self.assertFalse(out['written'])
            self.assertTrue(out['partial'])
            self.assertEqual(out['weight'], 1)
            r['settings'][0]['index'] = 0
            out = ml.apply_recipe(self.path, 'fixture', weight=-1)
            self.assertEqual(out['weight'], 0)
            self.assertEqual([a['value'] for a in out['applied']], [.2, 12])

    def editors(self):
        self.doc['modules'] = [
            {'id': 10, 'plugin': 'rcm', 'model': 'rcm-songroll', 'data': {
                'running': False, 'songRoll': {'sections': songroll._default_sections(2)}}},
            {'id': 11, 'plugin': 'voxglitch', 'model': 'sampler16p', 'data': {}}]
        self.store()
        (self.root / 'voice.wav').write_bytes(b'existence-only')
    def test_songroll_strict_integer_fields_and_operations(self):
        self.editors()
        for field in ('pattern', 'repeats', 'repeat_mode', 'clock_div'):
            for bad in (True, .5, '1', float('nan'), float('inf')):
                with self.subTest(field=field, bad=bad):
                    sections = songroll._default_sections()
                    sections[0]['channels'][0][field] = bad
                    self.refused(lambda: songroll.write_sections(self.path, None, sections, load_after=True))
        cases = [('set_channel', 'section', {'section': 0, 'channel': 1, 'pattern': 2}),
                 ('set_channel', 'channel', {'section': 0, 'channel': 1, 'pattern': 2}),
                 ('set_channel', 'pattern', {'section': 0, 'channel': 1, 'pattern': 2}),
                 ('remove_section', 'index', {'index': 0}),
                 ('duplicate_section', 'index', {'index': 0}),
                 ('move_section', 'src', {'src': 0, 'dst': 1}),
                 ('move_section', 'dst', {'src': 0, 'dst': 1}),
                 ('add_section', 'after', {'after': 0})]
        for op, key, kw in cases:
            for bad in (True, .5, '0', float('nan'), float('inf'), -1, 10**1000):
                with self.subTest(op=op, key=key, bad=repr(bad)[:40]):
                    opts = dict(kw, **{key: bad})
                    self.refused(lambda: songroll.edit(self.path, None, op, **opts, load_after=True))
    def test_songroll_running_and_flags_strict_boolean(self):
        self.editors()
        for bad in (None, 0, 1, 'false', float('nan')):
            self.refused(lambda: songroll.edit(self.path, None, 'set_running', running=bad, load_after=True))
        for field in ('backup', 'load_after'):
            for bad in (0, 'false'):
                self.refused(lambda: songroll.write_sections(self.path, None, songroll._default_sections(), **{field: bad}))
                self.refused(lambda: songroll.edit(self.path, None, 'add_section', **{field: bad}))
        self.assertTrue(songroll.edit(self.path, None, 'set_running', running=False)['ok'])
    def test_sample_strict_slots_and_flags(self):
        self.editors()
        for bad in (-1, 0, True, .5, '1', float('nan'), float('inf'), 17, 10**1000):
            with self.subTest(slot=repr(bad)[:40]):
                self.refused(lambda: samplelib.load_sample(self.path, str(self.root / 'voice.wav'), bad, load_after=True))
                self.refused(lambda: samplelib.clear_slot(self.path, bad))
        for field in ('backup', 'load_after'):
            self.refused(lambda: samplelib.load_sample(self.path, str(self.root / 'voice.wav'), **{field: 'false'}))
        self.refused(lambda: samplelib.clear_slot(self.path, 1, backup='false'))
    def test_sample_actual_slot_boundaries(self):
        self.editors()
        for slot in (1, 16):
            self.assertTrue(samplelib.load_sample(self.path, str(self.root / 'voice.wav'), slot)['ok'])
            self.assertTrue(samplelib.clear_slot(self.path, slot)['ok'])
        self.doc['modules'][1]['model'] = 'samplerx8'
        self.store()
        self.refused(lambda: samplelib.clear_slot(self.path, 9))
        self.assertTrue(samplelib.clear_slot(self.path, 8)['ok'])

    def test_named_parameter_strict_instance_value_and_identity(self):
        for bad in (-1, True, .5, '0', float('nan'), float('inf'), 10**1000):
            with self.subTest(instance=repr(bad)[:40]):
                self.refused(lambda: cm.set_param_by_name(self.path, 'Twin', 'Level', .5, instance=bad, load_after=True))
                self.refused(lambda: cm.set_params_by_name_batch(self.path, [{'module': 'Twin', 'param': 'Level', 'value': .5, 'instance': bad}], load_after=True))
        for bad in (True, '0.5', float('nan'), float('inf'), -float('inf'), 10**1000):
            with self.subTest(value=repr(bad)[:40]):
                self.refused(lambda: cm.set_param_by_name(self.path, 'Twin', 'Level', bad, load_after=True))
                self.refused(lambda: cm.set_params_by_name_batch(self.path, [{'module': 'Twin', 'param': 'Level', 'value': bad}], load_after=True))
        self.doc['modules'][0]['plugin'] = 'Missing'
        self.store()
        self.refused(lambda: cm.set_param_by_name(self.path, 'Missing/Twin', 'Level', .5, load_after=True))
    def test_named_parameter_bool_param_and_load_flags(self):
        for bad in (True, False, .5, -1):
            self.refused(lambda: cm.set_param_by_name(self.path, 'Twin', bad, .5))
            self.refused(lambda: cm.set_params_by_name_batch(self.path, [{'module': 'Twin', 'param': bad, 'value': .5}]))
        self.refused(lambda: cm.set_param_by_name(self.path, 'Twin', 'Level', .5, load_after='false'))
        self.refused(lambda: cm.set_params_by_name_batch(self.path, [{'module': 'Twin', 'param': 'Level', 'value': .5}], load_after='false'))
        self.refused(lambda: cm.apply_recipe(self.path, 'warm_pad', load_after='false'))
    def test_named_parameter_per_instance_and_existing_partial_batch(self):
        out = cm.set_param_by_name(self.path, 'Twin', 'Level', 15, instance=1)
        self.assertTrue(out['ok'], out)
        self.assertEqual((out['module_id'], out['param_id']), (2, 7))
        out = cm.set_params_by_name_batch(self.path, [
            {'module': 'A/Twin', 'param': 'Level', 'value': 2},
            {'module': 'Missing', 'param': 'Level', 'value': .5}])
        self.assertTrue(out['ok'], out)
        self.assertEqual((out['applied'], out['failed']), (1, 1))
        self.assertTrue(out['results'][0]['warnings'])

    def cli(self, name, args):
        import contextlib
        import runpy
        output = io.StringIO()
        with patch.object(sys, 'argv', ['cardinal_mcp.py', '--call', name, json.dumps(args)]):
            with contextlib.redirect_stdout(output):
                with self.assertRaises(SystemExit) as exit:
                    runpy.run_path(str(Path(cm.__file__)), run_name='__main__')
        return exit.exception.code, json.loads(output.getvalue())
    def mcp(self, name, args):
        return cm.handle({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                          'params': {'name': name, 'arguments': args}})['result']
    def test_mcp_cli_sampler16_and_actual8_boundaries(self):
        self.editors()
        for name, extra in [('cardinal_sample_clear', {}),
                            ('cardinal_sample_load', {'file': str(self.root / 'voice.wav')})]:
            args = dict(patch=self.path, slot=16, **extra)
            result = self.mcp(name, args)
            self.assertFalse(result['isError'], result)
            code, out = self.cli(name, args)
            self.assertEqual(code, 0, out)
            self.assertTrue(out['ok'], out)
        self.doc['modules'][1]['model'] = 'samplerx8'
        self.store()
        args = dict(patch=self.path, slot=16)
        self.assertTrue(self.mcp('cardinal_sample_clear', args)['isError'])
        code, out = self.cli('cardinal_sample_clear', args)
        self.assertEqual(code, 1, out)
    def test_mcp_cli_recipe_plugin_routing_and_clamp(self):
        r = {'name': 'fixture', 'settings': [{'module': 'Twin', 'param': 'Level', 'value': 18}]}
        with patch.dict(ml.RECIPES, fixture=r):
            for via in ('mcp', 'cli'):
                self.store()
                args = dict(patch=self.path, recipe='fixture', weight=2)
                if via == 'mcp':
                    result = self.mcp('cardinal_apply_recipe', args)
                    self.assertFalse(result['isError'], result)
                    out = result['structuredContent']
                else:
                    code, out = self.cli('cardinal_apply_recipe', args)
                    self.assertEqual(code, 0, out)
                self.assertEqual([(a['plugin'], a['param_id'], a['value']) for a in out['applied']],
                                 [('A', 0, 1), ('B', 7, 18)])
    def test_mcp_cli_rejections_preserve_bytes_directory_and_loader(self):
        self.editors()
        cases = [('cardinal_sample_clear', dict(slot=True)),
                 ('cardinal_sample_load', dict(slot='1', file=str(self.root / 'voice.wav'))),
                 ('cardinal_songroll_edit', dict(op='set_running', running=None)),
                 ('cardinal_songroll_edit', dict(op='set_channel', section=0, channel=1, pattern=True)),
                 ('cardinal_seq_edit_note', dict(module='pianoroll', measure=-1, step=0)),
                 ('cardinal_seq_set_running', dict(module='pianoroll', running=1)),
                 ('cardinal_set_param_by_name', dict(module='Twin', param='Level', value=float('nan'))),
                 ('cardinal_set_params_batch', dict(sets=[{'module': 'Twin', 'param': 'Level', 'value': .5, 'instance': .5}])),
                 ('cardinal_apply_recipe', dict(recipe='warm_pad', weight=float('inf')))]
        for name, extra in cases:
            with self.subTest(name=name):
                args = dict(patch=self.path, **extra)
                before, names = Path(self.path).read_bytes(), set(self.root.rglob('*'))
                with patch.object(cm, 'load_patch') as loader:
                    self.assertTrue(self.mcp(name, args)['isError'])
                    code, out = self.cli(name, args)
                    self.assertEqual(code, 1, out)
                self.assertEqual(Path(self.path).read_bytes(), before)
                self.assertEqual(set(self.root.rglob('*')), names)
                loader.assert_not_called()
    def test_seq_velocity_domain_and_required_indices(self):
        self.sequences()
        for model in ('pianoroll', 'MiniArranger'):
            for bad in (-.1, 1.1):
                self.refused(lambda: seq.edit_note(self.path, model, 0, 0, velocity=bad))
            for key in ('measure', 'step', 'pattern', 'track'):
                kw = dict(measure=0, step=0)
                kw[key] = None
                self.refused(lambda: seq.edit_note(self.path, model, **kw))

    def test_mcp_cli_rcm_finite_pitch_warning_compatibility(self):
        self.sequences()
        for pitch in (-1, 128):
            args = dict(patch=self.path, module='pianoroll', measure=0, step=0, pitch=pitch)
            result = self.mcp('cardinal_seq_edit_note', args)
            self.assertFalse(result['isError'], result)
            self.assertTrue(result['structuredContent']['warnings'])
            code, out = self.cli('cardinal_seq_edit_note', args)
            self.assertEqual(code, 0, out)
            self.assertTrue(out['warnings'])
    def test_mcp_cli_alias_missing_ambiguous_dictionary_fail_closed(self):
        self.doc['modules'] = [{'id': 1, 'plugin': 'DrumKit', 'model': 'BD9', 'params': []}]
        self.lib['WSTD-Drums/BassDrum9'] = entry('WSTD-Drums', 'BassDrum9')
        self.store()
        args = dict(patch=self.path, module='BD9', param='Level', value=.6)
        self.assertFalse(self.mcp('cardinal_set_param_by_name', args)['isError'])
        self.assertEqual(self.cli('cardinal_set_param_by_name', args)[0], 0)
        for mode in ('missing', 'ambiguous', 'wrong_payload'):
            with self.subTest(mode=mode):
                self.lib.pop('wstd-drums/bassdrum9', None)
                self.lib['WSTD-Drums/BassDrum9'] = entry('WSTD-Drums', 'BassDrum9')
                if mode == 'missing':
                    del self.lib['WSTD-Drums/BassDrum9']
                    self.lib['Other/BassDrum9'] = entry('Other', 'BassDrum9')
                elif mode == 'ambiguous':
                    self.lib['wstd-drums/bassdrum9'] = entry('wstd-drums', 'bassdrum9')
                else:
                    self.lib['WSTD-Drums/BassDrum9'] = entry('Other', 'BassDrum9')
                before, names = Path(self.path).read_bytes(), set(self.root.rglob('*'))
                self.assertTrue(self.mcp('cardinal_set_param_by_name', args)['isError'])
                self.assertEqual(self.cli('cardinal_set_param_by_name', args)[0], 1)
                self.assertEqual(Path(self.path).read_bytes(), before)
                self.assertEqual(set(self.root.rglob('*')), names)

    def test_lookup_malformed_parameter_dictionary_fails_closed(self):
        for params in (None, [], {'-1': {}}, {'true': {}}, {'0': None}):
            with self.subTest(params=params):
                self.lib['A/Twin'] = {'plugin': 'A', 'model': 'Twin', 'params': params}
                self.assertIsNone(pl.lookup('A', 'Twin'))
                self.refused(lambda: cm.set_param_by_name(self.path, 'A/Twin', 'Level', .5))
    def test_seq_malformed_grid_metadata_never_coerces(self):
        self.sequences()
        for bad in (True, .5, '2', 0, -1, float('nan'), float('inf')):
            for field in ('measures', 'stepsPerMeasure'):
                with self.subTest(field=field, bad=bad):
                    self.sequences()
                    self.doc['modules'][1]['data']['arranger']['tracks'][0][field] = bad
                    self.store()
                    self.refused(lambda: seq.edit_note(self.path, 'MiniArranger', 0, 0, pitch=60, load_after=True))
            for field in ('beatsPerMeasure', 'divisionsPerBeat'):
                with self.subTest(field=field, bad=bad):
                    self.sequences()
                    self.doc['modules'][0]['data']['patterns'][0][field] = bad
                    self.store()
                    self.refused(lambda: seq.edit_note(self.path, 'pianoroll', 0, 0, pitch=60, load_after=True))

    def test_lookup_existing_drum_aliases(self):
        self.lib['WSTD-Drums/BassDrum9'] = entry('WSTD-Drums', 'BassDrum9')
        self.assertEqual(pl.lookup('drumkit', 'bd9'), self.lib['WSTD-Drums/BassDrum9'])
        self.assertIsNone(pl.lookup('Missing', 'BD9'))

    def test_review_unique_model_lookup(self):
        del self.lib['B/Twin']
        self.assertEqual(pl.lookup(None, 'tWIN'), self.lib['A/Twin'])
        self.assertIsNone(pl.lookup('Missing', 'Twin'))
        self.lib['a/twin'] = entry('a', 'twin')
        self.assertIsNone(pl.lookup(None, 'Twin'))
        del self.lib['a/twin']
        self.lib['B/Twin'] = entry('B')
        self.assertIsNone(pl.lookup(None, 'Twin'))
        del self.lib['B/Twin']
        self.lib['A/Twin']['plugin'] = 'Bad'
        self.assertIsNone(pl.lookup(None, 'Twin'))

    def test_review_qualified_parameter_targets_never_match_substrings(self):
        self.doc['modules'] = [{'id': 41, 'plugin': 'XA', 'model': 'Twin', 'params': []}]
        self.lib['XA/Twin'] = entry('XA')
        self.store()
        for target in ('A/Twin', 'A|Twin', 'XA/Twi', 'XA|Twi'):
            for batch in (False, True):
                for via in ('direct', 'mcp', 'cli'):
                    with self.subTest(target=target, batch=batch, via=via):
                        args = dict(patch=self.path, load_after=True)
                        item = dict(module=target, param='Level', value=.75)
                        name = 'cardinal_set_params_batch' if batch else 'cardinal_set_param_by_name'
                        args.update(sets=[item]) if batch else args.update(item)
                        def invoke():
                            cm.load_patch.return_value = {'ok': True}
                            if via == 'direct':
                                fn = cm.set_params_by_name_batch if batch else cm.set_param_by_name
                                return fn(**args)
                            if via == 'mcp':
                                result = self.mcp(name, args)
                                self.assertTrue(result['isError'], result)
                                return result.get('structuredContent') or json.loads(result['content'][0]['text'])
                            import editor_contracts
                            with patch.object(editor_contracts, 'after_write', side_effect=AssertionError('loader stage forbidden')) as stage:
                                code, out = self.cli(name, args)
                                stage.assert_not_called()
                            self.assertEqual(code, 1, out)
                            return out
                        self.refused(invoke)
        for target in ('xa/twin', 'xa|twin', 'Twin', 'Twi'):
            out = cm.set_param_by_name(self.path, target, 'Level', .6)
            self.assertTrue(out.get('ok'), out)
            self.assertEqual(out['module_id'], 41)
            self.assertEqual(patchio.read_patch(self.path)['modules'][0]['params'][0]['value'], .6)

    def test_review_shared_qualified_name_and_id_exact_components(self):
        import editor_contracts as ec
        modules = [{'id': 41, 'plugin': 'XA', 'model': 'Twin'}]
        for name in ('A|Twin', 'A/Twin', 'XA|Twi', 'XA/Twi'):
            for identity in (None, 41):
                with self.subTest(name=name, identity=identity):
                    selected, err = ec.select_target(modules, modules, name, identity)
                    self.assertIsNone(selected)
                    self.assertTrue(err)
        for name in ('xa|twin', 'xa/twin', 'Twi'):
            selected, err = ec.select_target(modules, modules, name, 41)
            self.assertIs(selected, modules[0])
            self.assertIsNone(err)

    def test_review_dictionary_queries_share_unique_resolution(self):
        queries = [('cardinal_module_params', cm.module_params, {}),
                   ('cardinal_find_param', cm.find_param, {'human': 'Level'}),
                   ('cardinal_port_semantics', cm.cardinal_port_semantics, {})]
        for item in self.lib.values():
            item['source'] = 'fixture'
        for name, fn, extra in queries:
            for via in ('direct', 'mcp', 'cli'):
                def query(target):
                    args = dict(module=target, **extra)
                    if via == 'direct':
                        return fn(**args)
                    if via == 'mcp':
                        result = self.mcp(name, args)
                        return result.get('structuredContent') or json.loads(result['content'][0]['text'])
                    return self.cli(name, args)[1]
                with self.subTest(name=name, via=via):
                    out = query('Twin')
                    self.assertTrue(out.get('error'), out)
                    self.assertTrue(out.get('known') or out.get('candidates'), out)
                    saved = self.lib.pop('B/Twin')
                    try:
                        self.assertFalse(query('tWIN').get('error'))
                        self.assertTrue(query('Missing/Twin').get('error'))
                        self.assertFalse(query('a|twin').get('error'))
                        self.lib['a/twin'] = entry('a', 'twin')
                        self.assertTrue(query('Twin').get('error'))
                        self.assertTrue(query('A/Twin').get('error'))
                        del self.lib['a/twin']
                        self.lib['A/Twin']['plugin'] = 'Wrong'
                        self.assertTrue(query('Twin').get('error'))
                    finally:
                        self.lib.pop('a/twin', None)
                        self.lib['A/Twin']['plugin'] = 'A'
                        self.lib['B/Twin'] = saved

    def test_review_patch_queries_never_select_wrong_qualified_identity(self):
        self.doc['modules'] = [{'id': 41, 'plugin': 'XA', 'model': 'Twin', 'params': []}]
        self.lib['XA/Twin'] = entry('XA')
        self.store()
        for fn in (cm.module_params, cm.cardinal_port_semantics):
            for name in ('A/Twin', 'A|Twin', 'XA/Twi', 'XA|Twi'):
                with self.subTest(fn=fn.__name__, name=name):
                    self.assertTrue(fn(patch=self.path, module=name).get('error'))
            self.assertFalse(fn(patch=self.path, module='XA/Twin').get('error'))
        self.doc['modules'].append({'id': 42, 'plugin': 'A', 'model': 'Twin', 'params': []})
        self.store()
        self.assertTrue(cm.cardinal_port_semantics(patch=self.path, module='Twin').get('error'))

    def test_review_starsea_rejects_fake_positive_grids_all_entries(self):
        import editor_contracts as ec
        self.sequences()
        for spm in (1, 17, 32):
            self.doc['modules'][1]['data']['arranger']['tracks'][0]['stepsPerMeasure'] = spm
            self.store()
            for via in ('direct', 'mcp', 'cli'):
                with self.subTest(spm=spm, via=via):
                    args = dict(patch=self.path, module='MiniArranger', measure=1,
                                step=0, pitch=60, load_after=True)
                    def invoke():
                        if via == 'direct':
                            return seq.edit_note(self.path, 'MiniArranger', args['measure'], args['step'], pitch=60, load_after=args['load_after'])
                        if via == 'mcp':
                            result = self.mcp('cardinal_seq_edit_note', args)
                            self.assertTrue(result['isError'], result)
                            return result.get('structuredContent') or json.loads(result['content'][0]['text'])
                        code, out = self.cli('cardinal_seq_edit_note', args)
                        self.assertEqual(code, 1, out)
                        return out
                    with patch.object(ec, 'after_write', return_value={'ok': True, 'written': True}) as stage:
                        self.refused(invoke)
                        stage.assert_not_called()

    def test_review_starsea_fixed16_real_global_step_and_measure_bounds(self):
        for spm in (None, 16):
            for measures in (1, 64):
                for via in ('direct', 'mcp', 'cli'):
                    with self.subTest(spm=spm, measures=measures, via=via):
                        self.sequences()
                        track = self.doc['modules'][1]['data']['arranger']['tracks'][0]
                        track['measures'] = measures
                        if spm is not None:
                            track['stepsPerMeasure'] = spm
                        self.store()
                        args = dict(patch=self.path, module='MiniArranger', measure=measures - 1,
                                    step=15, pitch=60, load_after=False)
                        if via == 'direct':
                            out = seq.edit_note(self.path, 'MiniArranger', args['measure'], args['step'], pitch=60, load_after=args['load_after'])
                        elif via == 'mcp':
                            result = self.mcp('cardinal_seq_edit_note', args)
                            self.assertFalse(result['isError'], result)
                            out = result['structuredContent']
                        else:
                            code, out = self.cli('cardinal_seq_edit_note', args)
                            self.assertEqual(code, 0, out)
                        self.assertTrue(out['ok'], out)
                        track = patchio.read_patch(self.path)['modules'][1]['data']['arranger']['tracks'][0]
                        self.assertEqual(track['notes'][0]['step'], (measures - 1) * 16 + 15)
                        self.refused(lambda: seq.edit_note(self.path, 'MiniArranger', measures, 0, pitch=60))
                        self.refused(lambda: seq.edit_note(self.path, 'MiniArranger', 0, 16, pitch=60))
        for measures in (0, 65):
            self.sequences()
            self.doc['modules'][1]['data']['arranger']['tracks'][0]['measures'] = measures
            self.store()
            self.refused(lambda: seq.edit_note(self.path, 'MiniArranger', 0, 0, pitch=60))

    def test_review_patch_query_name_and_id_must_both_match(self):
        self.doc['modules'] = [{'id': 41, 'plugin': 'XA', 'model': 'Twin', 'params': []}]
        self.lib['XA/Twin'] = entry('XA')
        self.store()
        for fn in (cm.module_params, cm.cardinal_port_semantics):
            for target in ('A/Twin', 'A|Twin'):
                self.assertTrue(fn(patch=self.path, module=target, module_id=41).get('error'))
            self.assertFalse(fn(patch=self.path, module='XA/Twin', module_id=41).get('error'))

if __name__ == '__main__':
    unittest.main()
