"""Independent editor contracts; only scratch fixtures and mocked loaders."""
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
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_file_editor_integration import document, make_archive, members
import patchio
import cardinal_mcp as cm
import samplelib
import seq
import songroll

class IndependentEditorChecks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=SCRATCH, prefix='editor-contract-parent-')
        self.addCleanup(self.tmp.cleanup)
        self.path = str(Path(self.tmp.name) / 'same-name.vcv')
        self.doc = document()

    def store(self, doc=None):
        raw = make_archive(doc or self.doc)
        Path(self.path).write_bytes(raw)
        return raw

    def test_ambiguous_songroll_does_not_write_or_load(self):
        self.doc['modules'].append(copy.deepcopy(self.doc['modules'][0]))
        self.doc['modules'][-1]['id'] = 999
        raw = self.store()
        before_names = set(Path(self.tmp.name).iterdir())
        with patch.object(cm, 'load_patch') as load:
            out = songroll.edit(self.path, None, 'set_channel', section=0, channel=1,
                                repeats=5, load_after=True)
        self.assertTrue(out.get('error') or out.get('ok') is False, out)
        load.assert_not_called()
        self.assertEqual(Path(self.path).read_bytes(), raw)
        self.assertEqual(set(Path(self.tmp.name).iterdir()), before_names)

    def test_sample_saves_exact_verified_path_not_old_directory(self):
        self.store()
        sample = Path(self.tmp.name) / 'new-directory' / 'same.wav'
        sample.parent.mkdir()
        sample.write_bytes(b'RIFF-fixture-only-not-audio-acceptance')
        with patch.object(cm, 'load_patch') as load:
            out = samplelib.load_sample(self.path, str(sample), 2, 'samplerx8',
                                        backup=False, load_after=False)
        self.assertNotIn('error', out, out)
        load.assert_not_called()
        data = patchio.read_patch(self.path)['modules'][2]['data']
        self.assertEqual(Path(data['loaded_sample_path_2']).resolve(), sample.resolve())
        self.assertEqual(data['loaded_sample_path_1'], 'fixture.wav')

    def test_load_failure_retains_written_state_and_exact_path(self):
        for editor in ('songroll', 'sequence'):
            with self.subTest(editor=editor):
                self.store()
                with patch.object(cm, 'load_patch', return_value={'ok': False, 'error': 'mock failure'}) as load:
                    if editor == 'songroll':
                        out = songroll.edit(self.path, None, 'set_channel', section=0,
                                            channel=1, repeats=5, backup=False, load_after=True)
                    else:
                        out = seq.edit_note(self.path, 'rcm-pianoroll', 0, 0, pitch=65,
                                            backup=False, load_after=True)
                load.assert_called_once_with(os.path.abspath(self.path))
                self.assertIs(out.get('ok'), False, out)
                self.assertTrue(out.get('written') or out.get('written_path'), out)
                self.assertIs(out.get('verified'), False, out)
                self.assertNotEqual(patchio.read_patch(self.path), self.doc)

if __name__ == '__main__':
    unittest.main(verbosity=2)
