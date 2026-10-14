import tempfile
import unittest
from pathlib import Path
from h3_adapter.ledger import Journal, JournalError


class JournalTests(unittest.TestCase):
    def test_claim_is_atomic_and_replay_cannot_submit_twice(self):
        with tempfile.TemporaryDirectory() as d:
            journal = Journal(Path(d))
            journal.begin('request1', 'fingerprint')
            journal.reserve('request1', 'primary', 'model1', {}, 0.2, 'USD', 1)
            with self.assertRaises(JournalError):
                Journal(Path(d)).reserve('request1', 'backup', 'model2', {}, 0.2, 'USD', 1)
            self.assertEqual(journal.get('request1')['state'], 'submitting')


if __name__ == '__main__':
    unittest.main()
