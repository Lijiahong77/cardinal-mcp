"""Group 16 registration/public contract; behavioral cases remain in candidate suite."""
import hashlib
from pathlib import Path
import unittest
import replay_osc as replay

NAME='16-songroll-history-ui.patch'
ROOT='plugins/rcm-modules'
SHA='9a005a3a850c0b9cbb3c55e44f650d4f1269d06fe7b63817cfade44355488b73'

class HistoryIntegration(unittest.TestCase):
    def test_group16_unique_last_root_and_exact_candidate_bytes(self):
        self.assertEqual(len(replay.PATCHES),17)
        self.assertEqual(replay.PATCHES[15][0],NAME)
        self.assertEqual(replay.PATCHES[15][2],ROOT)
        self.assertEqual(sum(row[0]==NAME for row in replay.PATCHES),1)
        self.assertEqual(len({row[0] for row in replay.PATCHES}),17)
        here=Path(replay.HERE)
        payload=(here/'patches'/NAME).read_bytes()
        self.assertEqual(hashlib.sha256(payload).hexdigest(),SHA)
        self.assertEqual(payload,(here/'songroll_history_harness/candidate.patch').read_bytes())
        self.assertEqual(replay.EXPECTED_ENDPOINTS,33)
        self.assertEqual(len(replay.VERIFY_MARKS),36)

    def test_scope16_documents_full_restore_and_no_deployment_claim(self):
        self.assertIn('17 组',replay.__doc__)
        readme=(Path(replay.HERE)/'README.md').read_text(encoding='utf8')
        for text in ['17 组',NAME,ROOT,'running/currentSection','enterSection','repeatsLeft','线程安全','未部署','缺currentSection']:
            self.assertIn(text,readme)
        for text in ['running/currentSection','enterSection','线程安全','未部署']:
            self.assertIn(text,replay.__doc__)

if __name__=='__main__': unittest.main(verbosity=2)
