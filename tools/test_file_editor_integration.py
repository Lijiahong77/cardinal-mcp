"""Offline cross-editor resource tests; fixtures only, no production patch writes."""
import copy
import io
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

SCRATCH = os.environ['TMPDIR']
os.environ.update(TMPDIR=SCRATCH, TEMP=SCRATCH, TMP=SCRATCH)
sys.path.insert(0, str(Path(__file__).resolve().parent))
def deny_socket(event, args):
    if event == 'socket.__new__':
        raise AssertionError('real socket forbidden by integration harness')
sys.addaudithook(deny_socket)
import zstandard
import patchio
import cardinal_mcp as cm
import musiclib
import paramlib
import samplelib
import seq
import songroll

ASSET = b'\x00\xffprivate-resource-fixture\x10' * 17
PARAMS = {'plugin': 'fixture', 'model': 'Voice', 'params': {
    '0': {'name': 'Level', 'kind': 'param', 'min': 0, 'max': 1, 'default': 0.1}}}

def document():
    return {'version': '2.0', 'zoom': 0.75, 'gridOffset': [10, 20],
            'custom': {'must_keep': '中文'}, 'cables': [], 'modules': [
        {'id': 1, 'plugin': 'rcm', 'model': 'rcm-songroll', 'pos': [0, 0], 'params': [],
         'data': {'running': False, 'songRoll': {'sections': [
             {'channels': [{'pattern': 1, 'repeats': 1, 'repeat_mode': 1, 'clock_div': 1}
                           for _ in range(8)]}]}}},
        {'id': 2, 'plugin': 'rcm', 'model': 'rcm-pianoroll', 'pos': [20, 0], 'params': [],
         'data': {'running': False, 'patterns': [{'beatsPerMeasure': 1,
                  'divisionsPerBeat': 1, 'numberOfMeasures': 1,
                  'measures': [{'notes': [{'pitch': 60, 'velocity': 0.5, 'active': True}]}]}]}},
        {'id': 3, 'plugin': 'fixture', 'model': 'samplerx8', 'pos': [40, 0], 'params': [],
         'data': {'loaded_sample_path_1': 'fixture.wav', 'running': False}},
        {'id': 4, 'plugin': 'fixture', 'model': 'Voice', 'pos': [60, 0],
         'params': [{'id': 0, 'value': 0.1}], 'data': {'running': False}}]}

def make_archive(doc):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w', format=tarfile.PAX_FORMAT) as tf:
        for name, payload, mode in [('modules/3/asset.bin', ASSET, 0o600),
                                    ('patch.json', json.dumps(doc).encode(), 0o644),
                                    ('modules/4/state.txt', b'saved state', 0o640)]:
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            info.mode = mode
            info.uid, info.gid = 123, 456
            info.uname, info.gname, info.mtime = 'fixture-user', 'fixture-group', 123456
            info.pax_headers = {'comment': 'fixture resource'}
            tf.addfile(info, io.BytesIO(payload))
    return zstandard.ZstdCompressor().compress(buf.getvalue())

def members(raw):
    with zstandard.ZstdDecompressor().stream_reader(io.BytesIO(raw)) as reader:
        data = reader.read()
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:') as tf:
        return [(m.name, tf.extractfile(m).read(), m.mode, m.uid, m.gid,
                 m.uname, m.gname, m.mtime, m.pax_headers) for m in tf]

class EditorResourceContracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=SCRATCH, prefix='editor-resource-')
        self.addCleanup(self.temp.cleanup)
        self.path = str(Path(self.temp.name) / 'isolated.vcv')
        self.before = document()
        self.raw = make_archive(self.before)
        Path(self.path).write_bytes(self.raw)

    def perform(self, editor):
        if editor == 'songroll':
            out = songroll.edit(self.path, None, 'set_channel', section=0,
                                channel=1, repeats=200, backup=False, load_after=False)
        elif editor == 'sequence':
            out = seq.edit_note(self.path, 'rcm-pianoroll', 0, 0, pitch=62,
                                backup=False, load_after=False)
        elif editor == 'sample_clear':
            out = samplelib.clear_slot(self.path, 1, 'samplerx8', backup=False)
        elif editor == 'recipe':
            recipe = {'name': 'fixture-recipe', 'settings': [
                {'module': 'Voice', 'param': 'Level', 'value': 0.7}]}
            with patch.object(musiclib, 'recipe', return_value=recipe), \
                 patch.object(paramlib, 'lookup', return_value=PARAMS):
                out = musiclib.apply_recipe(self.path, 'fixture-recipe')
            self.assertTrue(out.get('written'), out)
        elif editor == 'named_parameter':
            with patch.object(paramlib, 'lookup', return_value=PARAMS):
                out = cm.set_param_by_name(self.path, 'Voice', 'Level', 0.8, load_after=False)
        else:
            raise AssertionError(editor)
        self.assertNotIn('error', out, out)
        self.assertIsNot(out.get('ok'), False, out)
        return out

    def test_five_public_editors_preserve_existing_archive_resources(self):
        for editor in ('songroll', 'sequence', 'sample_clear', 'recipe', 'named_parameter'):
            with self.subTest(editor=editor):
                Path(self.path).write_bytes(self.raw)
                self.perform(editor)
                after_raw = Path(self.path).read_bytes()
                self.assertTrue(patchio.is_archive(after_raw), editor)
                before_entries, after_entries = members(self.raw), members(after_raw)
                self.assertEqual([m[0] for m in before_entries], [m[0] for m in after_entries])
                self.assertEqual([m for m in before_entries if m[0] != 'patch.json'],
                                 [m for m in after_entries if m[0] != 'patch.json'])
                after = patchio.read_patch(self.path)
                self.assertEqual(after['custom'], self.before['custom'])
                self.assertEqual(after['gridOffset'], self.before['gridOffset'])
                self.assertEqual([m['pos'] for m in after['modules']],
                                 [m['pos'] for m in self.before['modules']])
                self.assertTrue(all(m['data']['running'] is False for m in after['modules']))
                self.assertNotEqual(after, self.before)

if __name__ == '__main__':
    unittest.main(verbosity=2)
