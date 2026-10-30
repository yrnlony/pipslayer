import unittest
from datetime import datetime, timedelta, timezone

from pipslayer.data import Candle, DatasetManifest, TimestampSemantics, validate_candles
from pipslayer.data.candles import parse_utc_timestamp

UTC = timezone.utc
T0 = datetime(2030, 1, 1, tzinfo=UTC)

def candle(minute=0, **overrides):
    values = dict(symbol="XAUUSD", timeframe="M15", timestamp=T0 + timedelta(minutes=minute),
                  open=100.0, high=102.0, low=99.0, close=101.0, volume=None, source="synthetic")
    values.update(overrides)
    return Candle(**values)

class CandleTests(unittest.TestCase):
    def test_valid_candle_and_sequence(self):
        report = validate_candles([candle(0), candle(15)], expected_interval=timedelta(minutes=15))
        self.assertTrue(report.is_valid)
        self.assertEqual(report.candle_count, 2)
        self.assertEqual(report.gaps, ())

    def test_invalid_ohlc_rejected(self):
        with self.assertRaisesRegex(ValueError, "high"):
            candle(high=100.5)

    def test_naive_timestamp_rejected(self):
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            candle(timestamp=datetime(2030, 1, 1))

    def test_non_utc_timestamp_rejected(self):
        from datetime import timedelta as td
        with self.assertRaisesRegex(ValueError, "normalized to UTC"):
            candle(timestamp=datetime(2030, 1, 1, tzinfo=timezone(td(hours=3))))

    def test_duplicate_and_order_are_reported_not_repaired(self):
        report = validate_candles([candle(15), candle(15), candle(0)])
        self.assertFalse(report.is_valid)
        self.assertEqual(len(report.duplicate_timestamps), 1)
        self.assertEqual(len(report.out_of_order_pairs), 1)

    def test_gaps_are_reported_only_when_interval_given(self):
        rows = [candle(0), candle(30)]
        self.assertEqual(validate_candles(rows).gaps, ())
        self.assertEqual(len(validate_candles(rows, expected_interval=timedelta(minutes=15)).gaps), 1)

    def test_mixed_symbol_is_reported(self):
        report = validate_candles([candle(), candle(15, symbol="EURUSD")])
        self.assertTrue(any("mixed symbol/timeframe" in error for error in report.errors))

    def test_timestamp_parser_normalizes_to_utc(self):
        self.assertEqual(parse_utc_timestamp("2030-01-01T03:00:00+03:00"), T0)
        with self.assertRaises(ValueError):
            parse_utc_timestamp("2030-01-01T00:00:00")

class ManifestTests(unittest.TestCase):
    def test_manifest_validates_date_range(self):
        fields = dict(dataset_id="fixture-1", symbol="XAUUSD", timeframe="M15", source_name="synthetic fixture",
                      start_time=T0, end_time=T0 + timedelta(days=1), synthetic=True, source_sha256="a" * 64,
                      canonical_content_sha256="b" * 64, normalized_file_sha256="c" * 64,
                      normalized_file_name="fixture.normalized.csv", source_file_name="fixture.csv", row_count=2,
                      timestamp_semantics=TimestampSemantics("synthetic UTC timestamps"), run_id="run-1")
        manifest = DatasetManifest(**fields)
        self.assertTrue(manifest.synthetic)
        with self.assertRaisesRegex(ValueError, "start_time"):
            DatasetManifest(**{**fields, "dataset_id": "fixture-2", "start_time": T0 + timedelta(days=1), "end_time": T0})

if __name__ == "__main__":
    unittest.main()
