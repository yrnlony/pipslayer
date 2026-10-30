import csv
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from pipslayer.data.mt5_adapter import fetch_mt5_rates, fetch_mt5_rates_with_context, write_mt5_rates_csv


class FakeMT5:
    TIMEFRAME_M15 = 15

    def __init__(self, rates=None, initialize_ok=True, select_ok=True):
        self.rates = rates if rates is not None else []
        self.initialize_ok = initialize_ok
        self.select_ok = select_ok
        self.initialized = False
        self.shutdown_called = False
        self.range_args = None

    def initialize(self, **kwargs):
        self.initialized = self.initialize_ok
        return self.initialize_ok

    def symbol_select(self, symbol, enabled):
        return self.select_ok

    def copy_rates_range(self, symbol, timeframe, start, end):
        self.range_args = (symbol, timeframe, start, end)
        return self.rates

    def last_error(self):
        return (0, "fake error")

    def shutdown(self):
        self.shutdown_called = True
        self.initialized = False


class MT5AdapterTests(unittest.TestCase):
    def setUp(self):
        self.start = datetime(2026, 10, 1, tzinfo=timezone.utc)
        self.end = datetime(2026, 10, 2, tzinfo=timezone.utc)
        self.rates = [{"time": 1790816400, "open": 3900.1, "high": 3901.2,
                       "low": 3899.9, "close": 3900.8, "tick_volume": 321}]

    def test_fetches_rates_and_always_shuts_down(self):
        fake = FakeMT5(self.rates)
        rates = fetch_mt5_rates("XAUUSD", "M15", self.start, self.end, mt5_module=fake)
        self.assertEqual(rates, self.rates)
        self.assertTrue(fake.shutdown_called)
        self.assertEqual(fake.range_args[0:2], ("XAUUSD", 15))

    def test_context_fetch_marks_timestamp_semantics_unverified(self):
        fake = FakeMT5(self.rates)
        result = fetch_mt5_rates_with_context("XAUUSD", "M15", self.start, self.end, mt5_module=fake)
        self.assertEqual(result["timestamp_semantics"], "unverified")
        self.assertEqual(result["rates"], self.rates)
        self.assertTrue(fake.shutdown_called)

    def test_rejects_naive_datetime(self):
        fake = FakeMT5(self.rates)
        with self.assertRaisesRegex(ValueError, "timezone"):
            fetch_mt5_rates("XAUUSD", "M15", datetime(2026, 10, 1), self.end, mt5_module=fake)
        self.assertFalse(fake.initialized)

    def test_rejects_start_after_end(self):
        with self.assertRaisesRegex(ValueError, "earlier"):
            fetch_mt5_rates("XAUUSD", "M15", self.end, self.start, mt5_module=FakeMT5())

    def test_shutdown_occurs_if_symbol_selection_fails(self):
        fake = FakeMT5(self.rates, select_ok=False)
        with self.assertRaisesRegex(RuntimeError, "Could not select"):
            fetch_mt5_rates("XAUUSD", "M15", self.start, self.end, mt5_module=fake)
        self.assertTrue(fake.shutdown_called)

    def test_writes_canonical_csv_with_utc_and_tick_volume(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_mt5_rates_csv(self.rates, Path(tmp) / "rates.csv", symbol="XAUUSD",
                                       timeframe="M15", source_name="Headway MT5")
            with path.open(newline="", encoding="utf-8") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(list(rows[0]), ["timestamp", "open", "high", "low", "close", "volume"])
            self.assertTrue(rows[0]["timestamp"].endswith("Z"))
            self.assertEqual(rows[0]["volume"], "321")

    def test_malformed_refetch_does_not_truncate_existing_raw_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rates.csv"
            path.write_text("previous accepted export\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Malformed MT5 rate"):
                write_mt5_rates_csv([{"time": "bad"}], path, symbol="XAUUSD", timeframe="M15", source_name="test")
            self.assertEqual(path.read_text(encoding="utf-8"), "previous accepted export\n")

    def test_rejects_empty_rate_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "zero candles"):
                write_mt5_rates_csv([], Path(tmp) / "rates.csv", symbol="XAUUSD",
                                    timeframe="M15", source_name="Headway MT5")


if __name__ == "__main__":
    unittest.main()
