import csv
import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pipslayer.data import Candle, import_canonical_csv
from pipslayer.data.canonical import canonical_bytes, canonical_sha256, canonicalization_self_test
from pipslayer.data.candles import parse_utc_timestamp
from pipslayer.data.last_bar import assess_last_bar
from pipslayer.data.manifest import DatasetManifest, TimestampSemantics, read_manifest, write_manifest
from pipslayer.data.mt5_clock_check import run_mt5_clock_check
from pipslayer.data.outputs import FileOps, check_output_invariants, publish_dataset, recover_outputs, sha256_file
from pipslayer.data.timeframe_check import TimeframeCheckPolicy, assess_timeframe_spacing
from pipslayer.data.verify import verify_dataset

FIXTURE = Path(__file__).parents[1] / "fixtures" / "infrastructure" / "canonical_xauusd_m15_example.csv"
GOLDEN_SHA256 = "2c65a7112990c5f7fa6b41202bd915da0838742ce03774484dbcc49c87e71d67"


def candle(minute: int, *, timeframe="M15", value=100.0, volume=12.0):
    return Candle("XAUUSD", timeframe, datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=minute),
                  value, value + 2, value - 1, value + 1, volume)


def write_source(path: Path, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["timestamp", "open", "high", "low", "close", "volume"], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def row(ts="2026-01-01T00:00:00Z", op="100", hi="102", lo="99", close="101", volume="12"):
    return {"timestamp": ts, "open": op, "high": hi, "low": lo, "close": close, "volume": volume}


def accepted_payloads(root: Path, *, close: str):
    root.mkdir(parents=True, exist_ok=True)
    source = root / "gold.csv"
    write_source(source, [row(close=close), row("2026-01-01T00:15:00Z", op=close, hi="103", lo="100", close="102")])
    result = import_canonical_csv(source, root / "seed", symbol="XAUUSD", timeframe="M15", source_name="test")
    assert result.accepted, result
    return {"normalized": Path(result.output_csv).read_bytes(), "report": Path(result.report_json).read_bytes(),
            "manifest": Path(result.manifest_json).read_bytes()}


class CanonicalizationTests(unittest.TestCase):
    def test_golden_digest(self):
        rows = []
        with FIXTURE.open(encoding="utf-8-sig", newline="") as stream:
            for item in csv.DictReader(stream):
                rows.append(Candle("XAUUSD", "M15", parse_utc_timestamp(item["timestamp"]), float(item["open"]),
                                   float(item["high"]), float(item["low"]), float(item["close"]), float(item["volume"])))
        self.assertEqual(canonical_sha256(rows, symbol="XAUUSD", timeframe="M15"), GOLDEN_SHA256)
        canonicalization_self_test()

    def test_equivalent_numeric_and_csv_formatting_has_same_identity(self):
        rows_a = [candle(0), candle(15, value=101)]
        rows_b = [candle(0, value=100.0), candle(15, value=101.0)]
        self.assertEqual(canonical_sha256(rows_a, symbol="XAUUSD", timeframe="M15"),
                         canonical_sha256(rows_b, symbol="XAUUSD", timeframe="M15"))

    def test_source_label_is_not_part_of_canonical_identity(self):
        a = Candle("XAUUSD", "M15", datetime(2026, 1, 1, tzinfo=timezone.utc), 100, 102, 99, 101, 12, source="broker-a")
        b = Candle("XAUUSD", "M15", datetime(2026, 1, 1, tzinfo=timezone.utc), 100, 102, 99, 101, 12, source="broker-b")
        self.assertEqual(canonical_sha256([a], symbol="XAUUSD", timeframe="M15"),
                         canonical_sha256([b], symbol="XAUUSD", timeframe="M15"))

    def test_row_order_and_empty_vs_zero_volume_change_hash(self):
        a, b = candle(0), candle(15, value=101)
        digest = canonical_sha256([a, b], symbol="XAUUSD", timeframe="M15")
        self.assertNotEqual(digest, canonical_sha256([b, a], symbol="XAUUSD", timeframe="M15"))
        self.assertNotEqual(digest, canonical_sha256([candle(0, volume=None), b], symbol="XAUUSD", timeframe="M15"))

    def test_exponent_and_symbol_delimiter_are_rejected_with_field(self):
        with self.assertRaisesRegex(ValueError, "row 1: 'open'.*exponent"):
            canonical_bytes([candle(0, value=1e-5)], symbol="XAUUSD", timeframe="M15")
        with self.assertRaisesRegex(ValueError, "symbol contains"):
            canonical_bytes([candle(0)], symbol="XAUUSD|bad", timeframe="M15")


class ManifestV2Tests(unittest.TestCase):
    def test_manifest_round_trip_and_unverified_is_enforced(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        manifest = DatasetManifest(
            dataset_id="XAUUSD-M15-c1-0123456789abcdef", symbol="XAUUSD", timeframe="M15", source_name="test",
            start_time=start, end_time=start + timedelta(minutes=15), synthetic=True, source_sha256="a" * 64,
            canonical_content_sha256="b" * 64, normalized_file_sha256="c" * 64,
            normalized_file_name="gold.normalized.csv", source_file_name="gold.csv", row_count=2,
            timestamp_semantics=TimestampSemantics("explicit offset, source clock unverified"), run_id="run-v2")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gold.manifest.json"
            write_manifest(path, manifest)
            loaded = read_manifest(path)
            self.assertEqual(loaded.to_dict(), manifest.to_dict())
        with self.assertRaisesRegex(ValueError, "only permits"):
            TimestampSemantics("claim", verification_status="verified")
        with self.assertRaisesRegex(ValueError, "legacy manifest"):
            DatasetManifest.from_dict({"schema_version": 1})


class TimeframeAndLastBarTests(unittest.TestCase):
    def test_matching_and_conflicting_spacing(self):
        rows = [candle(i * 15) for i in range(21)]
        self.assertEqual(assess_timeframe_spacing(rows)["status"], "matches")
        wrong = [Candle("XAUUSD", "M15", datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(hours=i),
                        100, 102, 99, 101, 12) for i in range(21)]
        self.assertEqual(assess_timeframe_spacing(wrong)["status"], "conflicts")

    def test_timeframe_threshold_boundaries(self):
        nineteen = [candle(i * 15) for i in range(20)]
        self.assertEqual(assess_timeframe_spacing(nineteen)["status"], "insufficient_evidence")
        # Exactly 70% expected intervals satisfies the match threshold.
        mixed = [candle(i * (15 if i <= 14 else 30)) for i in range(21)]
        # Use explicit alternating spacing counts to pin the boundary without relying on market calendars.
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        deltas = [15] * 14 + [30] * 6
        timestamps = [base]
        for delta in deltas:
            timestamps.append(timestamps[-1] + timedelta(minutes=delta))
        rows = [Candle("XAUUSD", "M15", stamp, 100, 102, 99, 101, 12) for stamp in timestamps]
        self.assertEqual(assess_timeframe_spacing(rows)["status"], "matches")
        # 20% declared spacing is not below the conflict threshold; this remains ambiguous.
        deltas = [15] * 4 + [30] * 16
        timestamps = [base]
        for delta in deltas:
            timestamps.append(timestamps[-1] + timedelta(minutes=delta))
        rows = [Candle("XAUUSD", "M15", stamp, 100, 102, 99, 101, 12) for stamp in timestamps]
        self.assertEqual(assess_timeframe_spacing(rows)["status"], "ambiguous")

    def test_weekend_gap_does_not_create_false_timeframe_conflict(self):
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        timestamps = [base + timedelta(minutes=15 * i) for i in range(29)]
        timestamps.append(timestamps[-1] + timedelta(days=2))
        rows = [Candle("XAUUSD", "M15", stamp, 100, 102, 99, 101, 12) for stamp in timestamps]
        self.assertEqual(assess_timeframe_spacing(rows)["status"], "matches")

    def test_enforce_blocks_clear_conflict_but_report_only_accepts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "gold.csv"
            rows = [row((datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(hours=i)).isoformat().replace("+00:00", "Z")) for i in range(21)]
            write_source(source, rows)
            report_only = import_canonical_csv(source, root / "report", symbol="XAUUSD", timeframe="M15", source_name="test")
            enforced = import_canonical_csv(source, root / "enforce", symbol="XAUUSD", timeframe="M15", source_name="test", timeframe_check="enforce")
            self.assertTrue(report_only.accepted)
            self.assertEqual(report_only.timeframe_check["status"], "conflicts")
            self.assertFalse(enforced.accepted)
            self.assertTrue(any(issue.code == "timeframe_conflict" for issue in enforced.errors))

    def test_policy_validation_and_file_load(self):
        with self.assertRaisesRegex(ValueError, "at least 10"):
            TimeframeCheckPolicy(min_deltas=2)

    def test_last_bar_flag_and_exclusion_assessment(self):
        rows = [candle(0), candle(15)]
        as_of = datetime(2026, 1, 1, 0, 20, tzinfo=timezone.utc)
        self.assertEqual(assess_last_bar(rows, data_as_of=as_of)["status"], "possibly_incomplete")
        self.assertEqual(assess_last_bar(rows)["status"], "cannot_assess")


class ImportAndVerificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "gold.csv"
        self.output = self.root / "out"

    def tearDown(self):
        self.temp.cleanup()

    def test_rejected_replacement_preserves_live_accepted_dataset(self):
        write_source(self.source, [row(), row("2026-01-01T00:15:00Z", op="101", close="102")])
        first = import_canonical_csv(self.source, self.output, symbol="XAUUSD", timeframe="M15", source_name="test")
        self.assertTrue(first.accepted)
        manifest_before = Path(first.manifest_json).read_bytes()
        normalized_before = Path(first.output_csv).read_bytes()
        write_source(self.source, [row(hi="90")])
        rejected = import_canonical_csv(self.source, self.output, symbol="XAUUSD", timeframe="M15", source_name="test")
        self.assertFalse(rejected.accepted)
        self.assertNotEqual(rejected.report_json, first.report_json)
        self.assertEqual(Path(first.manifest_json).read_bytes(), manifest_before)
        self.assertEqual(Path(first.output_csv).read_bytes(), normalized_before)
        self.assertTrue(verify_dataset(first.manifest_json)["valid"])

    def test_pending_journal_blocks_import(self):
        write_source(self.source, [row(), row("2026-01-01T00:15:00Z", op="101", close="102")])
        self.output.mkdir(parents=True)
        (self.output / ".pipslayer-journal-gold.json").write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "recover-outputs"):
            import_canonical_csv(self.source, self.output, symbol="XAUUSD", timeframe="M15", source_name="test")

    def test_equivalent_reimport_is_noop_and_dataset_verifies(self):
        write_source(self.source, [row(), row("2026-01-01T00:15:00Z", op="101", close="102")])
        first = import_canonical_csv(self.source, self.output, symbol="XAUUSD", timeframe="M15", source_name="test")
        write_source(self.source, [row(op="100.0", hi="102.00", lo="99.0", close="101.00", volume="12.0"),
                                   row("2026-01-01T00:15:00Z", op="101.0", hi="102.0", lo="99.0", close="102.0", volume="12.0")])
        second = import_canonical_csv(self.source, self.output, symbol="XAUUSD", timeframe="M15", source_name="test")
        self.assertTrue(second.accepted)
        self.assertTrue(second.unchanged)
        self.assertEqual(first.dataset_id, second.dataset_id)
        self.assertTrue(verify_dataset(second.manifest_json)["valid"])

    def test_bom_crlf_whitespace_and_decimal_format_do_not_change_identity(self):
        write_source(self.source, [row(), row("2026-01-01T00:15:00Z", op="101", close="102")])
        first = import_canonical_csv(self.source, self.output, symbol="XAUUSD", timeframe="M15", source_name="test")
        alternate = self.root / "alternate.csv"
        alternate.write_bytes(("\ufefftimestamp,open,high,low,close,volume\r\n"
                               " 2026-01-01T00:00:00Z ,100.00,102.000,99.0,101.00,12.0\r\n"
                               "2026-01-01T00:15:00Z,101.0,102.0,99.00,102.00,12\r\n").encode("utf-8"))
        second = import_canonical_csv(alternate, self.output / "alternate", symbol="XAUUSD", timeframe="M15", source_name="test")
        self.assertEqual(first.dataset_id, second.dataset_id)
        self.assertEqual(first.canonical_content_sha256, second.canonical_content_sha256)

    def test_verifier_detects_normalized_tampering(self):
        write_source(self.source, [row(), row("2026-01-01T00:15:00Z", op="101", close="102")])
        result = import_canonical_csv(self.source, self.output, symbol="XAUUSD", timeframe="M15", source_name="test")
        Path(result.output_csv).write_text("tampered", encoding="utf-8")
        verified = verify_dataset(result.manifest_json)
        self.assertFalse(verified["valid"])
        self.assertIn("normalized_file_hash_mismatch", verified["errors"])

    def test_last_bar_exclusion_is_opt_in(self):
        write_source(self.source, [row(), row("2026-01-01T00:15:00Z", op="101", close="102")])
        as_of = datetime(2026, 1, 1, 0, 20, tzinfo=timezone.utc)
        flagged = import_canonical_csv(self.source, self.output / "flag", symbol="XAUUSD", timeframe="M15", source_name="test", data_as_of=as_of)
        excluded = import_canonical_csv(self.source, self.output / "exclude", symbol="XAUUSD", timeframe="M15", source_name="test", data_as_of=as_of, last_bar_policy="exclude-if-possibly-incomplete")
        self.assertEqual(flagged.excluded_rows, 0)
        self.assertEqual(excluded.excluded_rows, 1)
        self.assertEqual(json.loads(Path(excluded.manifest_json).read_text())["row_count"], 1)


class CountingOps(FileOps):
    def __init__(self, fail_at=None, crash=False):
        self.calls = 0
        self.fail_at = fail_at
        self.crash = crash

    def _tick(self):
        self.calls += 1
        if self.calls == self.fail_at:
            if self.crash:
                raise SimulatedCrash()
            raise OSError(f"injected failure at operation {self.calls}")

    def mkdir(self, path): self._tick(); super().mkdir(path)
    def replace(self, source, destination): self._tick(); super().replace(source, destination)
    def write_bytes(self, path, data, *, exclusive=False): self._tick(); super().write_bytes(path, data, exclusive=exclusive)
    def fsync_file(self, path): self._tick(); super().fsync_file(path)
    def open_for_append(self, path): self._tick(); super().open_for_append(path)
    def unlink(self, path): self._tick(); super().unlink(path)
    def rmtree(self, path): self._tick(); super().rmtree(path)


class SimulatedCrash(BaseException):
    pass


def assert_live_manifest_invariant(test: unittest.TestCase, output: Path):
    manifests = list(output.glob("*.manifest.json"))
    if manifests:
        verified = verify_dataset(manifests[0])
        test.assertTrue(verified["valid"], verified)
    invariants = check_output_invariants(output, "gold")
    test.assertTrue(invariants["valid"], invariants)


class PublicationRecoveryTests(unittest.TestCase):
    def _seed_live(self, root: Path):
        root.mkdir(parents=True, exist_ok=True)
        payloads = accepted_payloads(root, close="101")
        publish_dataset(root / "live", "gold", payloads)
        return root / "live"

    def _candidate(self, root: Path):
        return accepted_payloads(root, close="102")

    def test_accepted_replacement_supersedes_previous_and_verifies(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            live = self._seed_live(root)
            payload = self._candidate(root)
            old_id = json.loads((live / "gold.manifest.json").read_text())["dataset_id"]
            outcome = publish_dataset(live, "gold", payload)
            self.assertTrue(outcome["superseded_dir"])
            new_manifest = json.loads((live / "gold.manifest.json").read_text())
            self.assertNotEqual(new_manifest["dataset_id"], old_id)
            self.assertTrue(verify_dataset(live / "gold.manifest.json")["valid"])

    def test_exhaustive_single_operation_faults_restore_previous_dataset(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            live = self._seed_live(base / "count")
            payload = self._candidate(base / "candidate")
            counter = CountingOps()
            publish_dataset(live, "gold", payload, file_ops=counter)
            operation_count = counter.calls
        for fault in range(1, operation_count + 1):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as tmp:
                base = Path(tmp)
                live = self._seed_live(base / "live")
                before = {p.name: p.read_bytes() for p in live.glob("gold.*")}
                payload = self._candidate(base / "candidate")
                try:
                    publish_dataset(live, "gold", payload, file_ops=CountingOps(fail_at=fault))
                except (OSError, RuntimeError):
                    pass
                if (live / ".pipslayer-journal-gold.json").exists():
                    recover_outputs(live, "gold")
                assert_live_manifest_invariant(self, live)
                after = {p.name: p.read_bytes() for p in live.glob("gold.*")}
                self.assertEqual(after, before)

    def test_exhaustive_crash_sweep_recovers_previous_or_committed_dataset(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            live = self._seed_live(base / "count")
            payload = self._candidate(base / "candidate")
            counter = CountingOps()
            publish_dataset(live, "gold", payload, file_ops=counter)
            operation_count = counter.calls
        for fault in range(1, operation_count + 1):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as tmp:
                base = Path(tmp)
                live = self._seed_live(base / "live")
                before = {p.name: p.read_bytes() for p in live.glob("gold.*")}
                payload = self._candidate(base / "candidate")
                try:
                    publish_dataset(live, "gold", payload, file_ops=CountingOps(fail_at=fault, crash=True))
                except SimulatedCrash:
                    pass
                journal = live / ".pipslayer-journal-gold.json"
                if journal.exists():
                    recover_outputs(live, "gold")
                assert_live_manifest_invariant(self, live)
                self.assertFalse(journal.exists())
                actual = {p.name: p.read_bytes() for p in live.glob("gold.*")}
                expected_new = {"gold.normalized.csv": payload["normalized"],
                                "gold.quality-report.json": payload["report"],
                                "gold.manifest.json": payload["manifest"]}
                # A simulated process crash can happen after the commit marker is durable;
                # recovery may validly finalize N' or restore P.
                self.assertIn(actual, [before, expected_new])

    def test_double_fault_leaves_journal_and_recovery_restores_previous(self):
        class DoubleFaultOps(CountingOps):
            def __init__(self):
                super().__init__()
            def _tick(self):
                self.calls += 1
                if self.calls in (12, 13):
                    raise OSError(f"injected double fault at operation {self.calls}")
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            live = self._seed_live(base / "live")
            before = {p.name: p.read_bytes() for p in live.glob("gold.*")}
            payload = self._candidate(base / "candidate")
            with self.assertRaisesRegex(RuntimeError, "PENDING-RECOVERY"):
                publish_dataset(live, "gold", payload, file_ops=DoubleFaultOps())
            self.assertTrue((live / ".pipslayer-journal-gold.json").exists())
            self.assertTrue(check_output_invariants(live, "gold")["valid"])
            recovered = recover_outputs(live, "gold")
            self.assertEqual(recovered["status"], "rolled-back")
            self.assertEqual({p.name: p.read_bytes() for p in live.glob("gold.*")}, before)
            self.assertEqual(recover_outputs(live, "gold")["status"], "nothing-to-recover")

    def test_each_rollback_failure_keeps_journal_recoverable(self):
        class TwoFaultOps(CountingOps):
            def __init__(self, first, second):
                super().__init__()
                self.first, self.second = first, second
            def _tick(self):
                self.calls += 1
                if self.calls in (self.first, self.second):
                    raise OSError(f"injected failure at operation {self.calls}")
        for rollback_offset in (1, 2):
            with self.subTest(rollback_offset=rollback_offset), tempfile.TemporaryDirectory() as tmp:
                base = Path(tmp)
                live = self._seed_live(base / "live")
                before = {p.name: p.read_bytes() for p in live.glob("gold.*")}
                payload = self._candidate(base / "candidate")
                with self.assertRaisesRegex(RuntimeError, "PENDING-RECOVERY"):
                    publish_dataset(live, "gold", payload, file_ops=TwoFaultOps(12, 12 + rollback_offset))
                self.assertTrue((live / ".pipslayer-journal-gold.json").exists())
                recover_outputs(live, "gold")
                self.assertEqual({p.name: p.read_bytes() for p in live.glob("gold.*")}, before)
                assert_live_manifest_invariant(self, live)

    def test_unknown_file_content_blocks_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            live = self._seed_live(base / "live")
            payload = self._candidate(base / "candidate")
            try:
                publish_dataset(live, "gold", payload, file_ops=CountingOps(fail_at=12, crash=True))
            except SimulatedCrash:
                pass
            journal = live / ".pipslayer-journal-gold.json"
            self.assertTrue(journal.exists())
            (live / "gold.normalized.csv").write_text("unknown external modification", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "Unknown file content"):
                recover_outputs(live, "gold")
            self.assertTrue(journal.exists())


class FakeClockMT5:
    TIMEFRAME_M1 = 1
    TIMEFRAME_H4 = 4
    TIMEFRAME_D1 = 5
    def __init__(self): self.shutdown_called = False
    def initialize(self, **kwargs): return True
    def symbol_select(self, symbol, enabled): return True
    def symbol_info_tick(self, symbol): return {"time": 1790816400}
    def copy_rates_from_pos(self, symbol, timeframe, start, count): return [{"time": 1790816400}]
    def last_error(self): return (0, "fake")
    def shutdown(self): self.shutdown_called = True


class ClockDiagnosticTests(unittest.TestCase):
    def test_clock_check_never_decides_or_verifies(self):
        fake = FakeClockMT5()
        report = run_mt5_clock_check("XAUUSD", mt5_module=fake)
        self.assertIsNone(report["decision"])
        self.assertEqual(report["timestamp_verification_status"], "unverified")
        self.assertEqual(report["overall"], "inconclusive")
        self.assertTrue(fake.shutdown_called)


class CliSmokeTests(unittest.TestCase):
    def test_import_verify_and_recovery_cli(self):
        from pipslayer.cli import main
        from contextlib import redirect_stdout
        import io
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "out"
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                code = main(["import-csv", str(FIXTURE), "--output-dir", str(output), "--symbol", "XAUUSD",
                             "--timeframe", "M15", "--source-name", "synthetic", "--synthetic"])
            self.assertEqual(code, 0, stdout.getvalue())
            manifest = output / "canonical_xauusd_m15_example.manifest.json"
            with redirect_stdout(stdout := io.StringIO()):
                self.assertEqual(main(["verify-dataset", str(manifest)]), 0, stdout.getvalue())
            with redirect_stdout(stdout := io.StringIO()):
                self.assertEqual(main(["recover-outputs", "--output-dir", str(output), "--stem", "canonical_xauusd_m15_example"]), 0)


if __name__ == "__main__":
    unittest.main()
