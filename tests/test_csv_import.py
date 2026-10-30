import csv
import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from pipslayer.data import import_canonical_csv


class CanonicalCsvImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "gold.csv"
        self.output = self.root / "out"

    def tearDown(self):
        self.temp.cleanup()

    def write_csv(self, rows, headers=("timestamp", "open", "high", "low", "close", "volume")):
        with self.source.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=headers)
            writer.writeheader()
            writer.writerows(rows)

    @staticmethod
    def row(timestamp="2026-10-01T09:00:00Z", **overrides):
        value = {"timestamp": timestamp, "open": "100", "high": "102", "low": "99", "close": "101", "volume": "12"}
        value.update(overrides)
        return value

    def run_import(self, **kwargs):
        defaults = dict(input_path=self.source, output_dir=self.output, symbol="XAUUSD", timeframe="M15", source_name="test-feed")
        defaults.update(kwargs)
        return import_canonical_csv(**defaults)

    def test_valid_csv_writes_normalized_data_manifest_and_report(self):
        self.write_csv([self.row(), self.row("2026-10-01T09:15:00+00:00", open="101", close="101.5")])
        result = self.run_import(expected_interval=timedelta(minutes=15))
        self.assertTrue(result.accepted)
        self.assertEqual(result.parsed_rows, 2)
        self.assertTrue(Path(result.output_csv).exists())
        self.assertTrue(Path(result.manifest_json).exists())
        report = json.loads(Path(result.report_json).read_text(encoding="utf-8"))
        manifest = json.loads(Path(result.manifest_json).read_text(encoding="utf-8"))
        self.assertTrue(report["accepted"])
        self.assertEqual(manifest["row_count"], 2)
        self.assertEqual(manifest["timestamp_semantics"]["verification_status"], "unverified")
        self.assertEqual(manifest["schema_version"], 2)
        self.assertTrue(manifest["canonical_content_sha256"])
        self.assertTrue(manifest["normalized_file_sha256"])
        with Path(result.output_csv).open(encoding="utf-8", newline="") as stream:
            output_rows = list(csv.DictReader(stream))
        self.assertEqual(output_rows[0]["timestamp"], "2026-10-01T09:00:00Z")
        self.assertEqual(output_rows[0]["symbol"], "XAUUSD")

    def test_naive_timestamp_rejected_and_no_normalized_output(self):
        self.write_csv([self.row("2026-10-01 09:00:00")])
        result = self.run_import()
        self.assertFalse(result.accepted)
        self.assertIsNone(result.output_csv)
        self.assertIn("explicit timezone", result.errors[0].message)

    def test_invalid_ohlc_rejected_and_reported(self):
        self.write_csv([self.row(high="98")])
        result = self.run_import()
        self.assertFalse(result.accepted)
        self.assertIsNone(result.output_csv)
        self.assertTrue(any("high" in issue.message for issue in result.errors))

    def test_duplicate_timestamp_blocks_output(self):
        self.write_csv([self.row(), self.row()])
        result = self.run_import()
        self.assertFalse(result.accepted)
        self.assertEqual(len(result.duplicate_timestamps), 1)
        self.assertIsNone(result.output_csv)

    def test_out_of_order_rows_are_not_sorted_automatically(self):
        self.write_csv([self.row("2026-10-01T09:15:00Z"), self.row("2026-10-01T09:00:00Z")])
        result = self.run_import()
        self.assertFalse(result.accepted)
        self.assertEqual(len(result.out_of_order_pairs), 1)
        self.assertIsNone(result.output_csv)

    def test_gap_is_informational_and_can_be_reported(self):
        self.write_csv([self.row(), self.row("2026-10-01T09:30:00Z")])
        result = self.run_import(expected_interval=timedelta(minutes=15))
        self.assertTrue(result.accepted)
        self.assertEqual(len(result.gaps), 1)
        report = json.loads(Path(result.report_json).read_text(encoding="utf-8"))
        self.assertEqual(len(report["gaps"]), 1)

    def test_missing_required_header_fails_before_output(self):
        self.write_csv([{"timestamp": "2026-10-01T09:00:00Z", "open": "100"}], headers=("timestamp", "open"))
        with self.assertRaisesRegex(ValueError, "missing required columns"):
            self.run_import()

    def test_non_numeric_row_is_recorded_and_blocks_entire_dataset(self):
        self.write_csv([self.row(), self.row("2026-10-01T09:15:00Z", close="oops")])
        result = self.run_import()
        self.assertFalse(result.accepted)
        self.assertEqual(result.input_rows, 2)
        self.assertEqual(result.parsed_rows, 1)
        self.assertIsNone(result.output_csv)

    def test_empty_csv_data_is_not_accepted(self):
        self.write_csv([])
        result = self.run_import()
        self.assertEqual(result.input_rows, 0)
        report = json.loads(Path(result.report_json).read_text(encoding="utf-8"))
        self.assertFalse(report["accepted"])
        self.assertIsNone(result.output_csv)
        self.assertFalse((self.output / "gold.normalized.csv").exists())
        self.assertFalse((self.output / "gold.manifest.json").exists())
        self.assertIn("rejections", Path(result.report_json).parts)

if __name__ == "__main__":
    unittest.main()
