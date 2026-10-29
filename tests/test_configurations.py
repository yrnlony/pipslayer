import json
import unittest
from pathlib import Path

P = Path(__file__).resolve().parents[1] / "src/pipslayer/strategies/msnr/configurations.json"

class ConfigurationTests(unittest.TestCase):
    def test_approved_configurations(self):
        c = {x["config_id"]:x for x in json.loads(P.read_text(encoding="utf-8"))}
        self.assertEqual((c["PRIMARY"]["reference_timeframe"], c["PRIMARY"]["setup_timeframe"], c["PRIMARY"]["reaction_timeframe"]), ("H4","H2","M15"))
        self.assertEqual(c["PRIMARY_M5"]["status"], "inert_alternative")
        self.assertIsNone(c["TWO_H_ONE_H"]["reference_timeframe"])
        self.assertEqual(c["TWO_H_ONE_H"]["reaction_timeframe"], "H1")
if __name__ == "__main__": unittest.main()
