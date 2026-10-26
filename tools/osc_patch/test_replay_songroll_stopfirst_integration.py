"""Group17 exact registration contract. Behavioral cases stay in the 58-method suite."""
import hashlib
from pathlib import Path
import unittest
import replay_osc as replay

NAME='17-songroll-stopfirst.patch'
ROOT='plugins/rcm-modules'
SHA='3a76957569a39344f8e322a2f72e4dded607587ad42aedcbb210630d2c8ec3a4'
class StopFirstIntegration(unittest.TestCase):
    def test_group17_unique_last_root_and_exact_reviewed_payload(self):
        self.assertEqual(len(replay.PATCHES),17)
        self.assertEqual(replay.PATCHES[-1][0],NAME)
        self.assertEqual(replay.PATCHES[-1][2],ROOT)
        self.assertEqual(sum(row[0]==NAME for row in replay.PATCHES),1)
        self.assertEqual(len({row[0] for row in replay.PATCHES}),17)
        payload=(Path(replay.HERE)/'patches'/NAME).read_bytes()
        self.assertEqual(hashlib.sha256(payload).hexdigest(),SHA)
        self.assertEqual(payload,(Path(replay.HERE)/'songroll_stopfirst_harness/candidate.patch').read_bytes())
        self.assertEqual(replay.EXPECTED_ENDPOINTS,33)
        self.assertEqual(len(replay.VERIFY_MARKS),36)
if __name__=='__main__':unittest.main(verbosity=2)
