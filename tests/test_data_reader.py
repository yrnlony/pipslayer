import tempfile
import unittest
from pathlib import Path

from pipslayer.data.reader import load_canonical_csv


class CanonicalReaderTests(unittest.TestCase):
    def write_csv(self, folder, content):
        path = Path(folder) / "candles.normalized.csv"
        path.write_text(content, encoding="utf-8")
        return path

    def test_loads_valid_candles(self):
        content = (
            "timestamp,symbol,timeframe,open,high,low,close,volume,source\n"
            "2026-05-01T01:00:00Z,XAUUSD,M15,100,102,99,101,10,Headway\n"
            "2026-05-01T01:15:00Z,XAUUSD,M15,101,103,100,102,12,Headway\n"
        )
        with tempfile.TemporaryDirectory() as folder:
            candles = load_canonical_csv(self.write_csv(folder, content))

        self.assertEqual(len(candles), 2)
        self.assertEqual(candles[0].symbol, "XAUUSD")
        self.assertEqual(candles[0].timeframe, "M15")
        self.assertEqual(candles[0].close, 101.0)

    def test_rejects_out_of_order_rows_without_sorting(self):
        content = (
            "timestamp,symbol,timeframe,open,high,low,close,volume,source\n"
            "2026-05-01T01:15:00Z,XAUUSD,M15,100,102,99,101,10,Headway\n"
            "2026-05-01T01:00:00Z,XAUUSD,M15,101,103,100,102,12,Headway\n"
        )
        with tempfile.TemporaryDirectory() as folder:
            path = self.write_csv(folder, content)
            with self.assertRaisesRegex(ValueError, "sequence is invalid"):
                load_canonical_csv(path)

    def test_rejects_mixed_symbols(self):
        content = (
            "timestamp,symbol,timeframe,open,high,low,close,volume,source\n"
            "2026-05-01T01:00:00Z,XAUUSD,M15,100,102,99,101,10,Headway\n"
            "2026-05-01T01:15:00Z,EURUSD,M15,101,103,100,102,12,Headway\n"
        )
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, "sequence is invalid"):
                load_canonical_csv(self.write_csv(folder, content))

    def test_rejects_missing_columns(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.write_csv(folder, "timestamp,symbol\\n")
            with self.assertRaisesRegex(ValueError, "missing required columns"):
                load_canonical_csv(path)


if __name__ == "__main__":
    unittest.main()
