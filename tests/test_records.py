import unittest
from pipslayer.contracts.records import CandidateRecord

class RecordTests(unittest.TestCase):
    def test_valid_record(self):
        r = CandidateRecord("x","EXAMPLE","Example","test",1,"draft","Metadata only")
        self.assertEqual(r.version, 1)
    def test_unknown_status_rejected(self):
        with self.assertRaises(ValueError):
            CandidateRecord("x","EXAMPLE","Example","test",1,"profitable","Not a valid lifecycle status")
    def test_zero_version_rejected(self):
        with self.assertRaises(ValueError):
            CandidateRecord("x","EXAMPLE","Example","test",0,"draft","Metadata only")
if __name__ == "__main__": unittest.main()
