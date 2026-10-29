import csv
import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from pipslayer.data.gap_audit import audit_timestamp_gaps, write_gap_audit_report


class GapAuditTests(unittest.TestCase):
    def make_csv(self, directory, stamps):
        path = Path(directory) / "candles.csv"
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(["timestamp", "open", "high", "low", "close"])
            for stamp in stamps:
                writer.writerow([stamp, 1, 2, 0.5, 1.5])
        return path

    def test_weekday_gap_has_missing_bar_estimate_and_is_not_repaired(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.make_csv(tmp, ["2026-01-05T10:00:00Z", "2026-01-05T10:45:00Z"])
            report = audit_timestamp_gaps(path, expected_interval=timedelta(minutes=15))
            self.assertEqual(report["gap_count"], 1)
            gap = report["gaps"][0]
            self.assertEqual(gap["estimated_missing_bars_if_continuous"], 2)
            self.assertEqual(gap["calendar_hint_not_a_verdict"], "weekday_gap_review_feed_or_session")
            self.assertTrue(gap["review_required"])
            self.assertEqual(report["row_count"], 2)

    def test_weekend_crossing_is_only_a_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.make_csv(tmp, ["2026-01-09T21:45:00Z", "2026-01-12T00:00:00Z"])
            report = audit_timestamp_gaps(path, expected_interval=timedelta(minutes=15))
            self.assertEqual(report["gaps"][0]["calendar_hint_not_a_verdict"], "crosses_weekend_closure_candidate")
            self.assertIn("not proof", report["policy"][2])

    def test_duplicate_and_out_of_order_are_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.make_csv(tmp, ["2026-01-05T10:15:00Z", "2026-01-05T10:15:00Z", "2026-01-05T10:00:00Z"])
            report = audit_timestamp_gaps(path, expected_interval=timedelta(minutes=15))
            self.assertEqual(report["sequence_issue_count"], 2)

    def test_invalid_timestamp_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.make_csv(tmp, ["2026-01-05T10:00:00"])
            with self.assertRaisesRegex(ValueError, "timezone-aware"):
                audit_timestamp_gaps(path, expected_interval=timedelta(minutes=15))

    def test_report_writer_creates_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.make_csv(tmp, ["2026-01-05T10:00:00Z"])
            report = audit_timestamp_gaps(path, expected_interval=timedelta(minutes=15))
            out = write_gap_audit_report(report, Path(tmp) / "reports" / "gap.json")
            self.assertEqual(json.loads(out.read_text())["gap_count"], 0)


if __name__ == "__main__":
    unittest.main()
