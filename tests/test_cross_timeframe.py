
import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

# Add the project's src directory to Python's import path.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIRECTORY = PROJECT_ROOT / "src"

if str(SRC_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SRC_DIRECTORY))

from pipslayer.data.cross_timeframe import compare_timeframes  # pyright: ignore[reportMissingImports]


class CrossTimeframeTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

        self.native_path = self.root / "native.csv"
        self.lower_path = self.root / "lower.csv"
        self.manifest_path = self.root / "manifest.json"

    def tearDown(self):
        self.temp.cleanup()

    def write_csv(self, path, timeframe, rows):
        fields = [
            "timestamp",
            "symbol",
            "timeframe",
            "open",
            "high",
            "low",
            "close",
        ]

        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()

            for timestamp, open_, high, low, close in rows:
                writer.writerow({
                    "timestamp": timestamp,
                    "symbol": "XAUUSD",
                    "timeframe": timeframe,
                    "open": open_,
                    "high": high,
                    "low": low,
                    "close": close,
                })

    def write_h2_and_m15(self):
        lower = [
            ("2026-01-01T00:00:00Z", "100", "102", "99", "101"),
            ("2026-01-01T00:15:00Z", "101", "104", "100", "103"),
            ("2026-01-01T00:30:00Z", "103", "105", "101", "102"),
            ("2026-01-01T00:45:00Z", "102", "103", "98", "99"),
            ("2026-01-01T01:00:00Z", "99", "101", "97", "100"),
            ("2026-01-01T01:15:00Z", "100", "102", "98", "101"),
            ("2026-01-01T01:30:00Z", "101", "103", "99", "102"),
            ("2026-01-01T01:45:00Z", "102", "104", "100", "103"),
        ]

        native = [
            ("2026-01-01T00:00:00Z", "100", "105", "97", "103"),
        ]

        self.write_csv(self.lower_path, "M15", lower)
        self.write_csv(self.native_path, "H2", native)

    def compare(self, **kwargs):
        return compare_timeframes(
            self.native_path,
            self.lower_path,
            native_timeframe="H2",
            lower_timeframe="M15",
            **kwargs,
        )

    def test_exact_ohlc_aggregation_matches(self):
        self.write_h2_and_m15()

        result = self.compare()

        self.assertEqual(result["counts"]["match"], 1)
        self.assertEqual(result["counts"].get("mismatch", 0), 0)
        self.assertEqual(result["required_lower_bars_per_native_bar"], 8)

    def test_close_mismatch_is_reported_exactly(self):
        self.write_h2_and_m15()

        native = [
            ("2026-01-01T00:00:00Z", "100", "105", "97", "103.01"),
        ]

        self.write_csv(self.native_path, "H2", native)

        result = self.compare()

        self.assertEqual(result["counts"]["mismatch"], 1)

        difference = result["mismatch_examples"][0]["differences"]["close"]

        self.assertEqual(difference["native"], "103.01")
        self.assertEqual(difference["from_lower_timeframe"], "103")

    def test_missing_lower_candle_is_insufficient_coverage(self):
        self.write_h2_and_m15()

        lower = [
            ("2026-01-01T00:00:00Z", "100", "102", "99", "101"),
            ("2026-01-01T00:15:00Z", "101", "104", "100", "103"),
        ]

        self.write_csv(self.lower_path, "M15", lower)

        result = self.compare()

        self.assertEqual(
            result["counts"]["insufficient_lower_timeframe_coverage"], 1
        )
        self.assertEqual(result["counts"].get("mismatch", 0), 0)

    def test_manifest_excludes_possibly_incomplete_final_native_bar(self):
        self.write_h2_and_m15()

        self.manifest_path.write_text(
            json.dumps({
                "last_bar": {
                    "status": "possibly_incomplete"
                }
            }),
            encoding="utf-8",
        )

        result = self.compare(manifest_path=self.manifest_path)

        self.assertTrue(result["final_native_bar_excluded_by_manifest"])

        self.assertEqual(
            result["counts"]["excluded_native_last_bar_possibly_incomplete"],
            1,
        )

        self.assertNotIn("match", result["counts"])

    def test_duplicate_lower_timestamp_is_rejected(self):
        self.write_h2_and_m15()

        lower = [
            ("2026-01-01T00:00:00Z", "100", "102", "99", "101"),
            ("2026-01-01T00:00:00Z", "100", "102", "99", "101"),
        ]

        self.write_csv(self.lower_path, "M15", lower)

        with self.assertRaisesRegex(ValueError, "Duplicate timestamp"):
            self.compare()

    def test_out_of_order_lower_timestamps_are_rejected(self):
        self.write_h2_and_m15()

        lower = [
            ("2026-01-01T00:15:00Z", "101", "104", "100", "103"),
            ("2026-01-01T00:00:00Z", "100", "102", "99", "101"),
        ]

        self.write_csv(self.lower_path, "M15", lower)

        with self.assertRaisesRegex(ValueError, "Out-of-order timestamp"):
            self.compare()

    def test_invalid_timeframe_relationship_is_rejected(self):
        self.write_h2_and_m15()

        with self.assertRaisesRegex(ValueError, "exact multiple"):
            compare_timeframes(
                self.native_path,
                self.lower_path,
                native_timeframe="H1",
                lower_timeframe="H2",
            )

    def test_off_grid_timestamp_is_reported_not_repaired(self):
        self.write_h2_and_m15()

        native = [
            ("2026-01-01T00:05:00Z", "100", "105", "97", "103"),
        ]

        self.write_csv(self.native_path, "H2", native)

        result = self.compare()

        self.assertEqual(result["native_timestamp_off_grid_count"], 1)

        self.assertEqual(
            result["native_timestamp_off_grid_examples"],
            ["2026-01-01T00:05:00+00:00"],
        )


if __name__ == "__main__":
    unittest.main()
