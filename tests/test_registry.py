import unittest
from pipslayer.strategies.msnr.registry import load_registry, validate_registry

class RegistryTests(unittest.TestCase):
    def test_unique_candidate_ids(self):
        rows = load_registry()
        ids = [x.candidate_id for x in rows]
        self.assertGreaterEqual(len(rows), 30)
        self.assertEqual(len(ids), len(set(ids)))
    def test_all_non_executable(self):
        self.assertTrue(all(x.metadata.get("executable") is not True for x in load_registry()))
    def test_review_statuses(self):
        rows = {x.candidate_id:x for x in load_registry()}
        self.assertEqual(rows["ltf.sweep_reclaim"].status, "flag_for_review")
        self.assertEqual(rows["ltf.displacement"].status, "flag_for_review")
    def test_duplicate_rejected(self):
        rows = load_registry()
        with self.assertRaises(ValueError): validate_registry([rows[0], rows[0]])
if __name__ == "__main__": unittest.main()
