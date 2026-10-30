"""Command-line tools for Pipslayer research metadata and market-data integrity."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from pipslayer.data import import_canonical_csv
from pipslayer.data.candles import SUPPORTED_TIMEFRAMES, TIMEFRAME_MINUTES, parse_utc_timestamp
from pipslayer.data.gap_audit import audit_timestamp_gaps, write_gap_audit_report
from pipslayer.data.mt5_adapter import fetch_mt5_rates, write_mt5_rates_csv
from pipslayer.data.mt5_clock_check import run_mt5_clock_check
from pipslayer.data.outputs import recover_outputs
from pipslayer.data.timeframe_check import TimeframeCheckPolicy
from pipslayer.data.verify import verify_dataset
from pipslayer.strategies.msnr.registry import load_registry


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pipslayer")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list-candidates", help="list registered strategy research candidates")

    importer = subparsers.add_parser("import-csv", help="audit canonical OHLC CSV and normalize accepted datasets")
    importer.add_argument("input_csv", help="input CSV path")
    importer.add_argument("--output-dir", required=True, help="directory for normalized data and reports")
    importer.add_argument("--symbol", required=True, help="instrument symbol, e.g. XAUUSD")
    importer.add_argument("--timeframe", required=True, choices=sorted(SUPPORTED_TIMEFRAMES))
    importer.add_argument("--source-name", required=True, help="broker/provider/source label")
    importer.add_argument("--source-notes", default="", help="optional notes about source or export settings")
    importer.add_argument("--expected-interval-minutes", type=int, default=None,
                          help="gap diagnostic interval; must match declared timeframe in M2e")
    importer.add_argument("--synthetic", action="store_true", help="mark dataset as synthetic/test data")
    importer.add_argument("--timeframe-check", choices=("report-only", "enforce"), default="report-only")
    importer.add_argument("--timeframe-policy", default=None, help="JSON file overriding provisional spacing thresholds")
    importer.add_argument("--last-bar-policy", choices=("flag", "exclude-if-possibly-incomplete"), default="flag")
    importer.add_argument("--data-as-of", default=None, help="reference timestamp with explicit timezone/UTC offset")

    gap_audit = subparsers.add_parser("audit-gaps", help="diagnose timestamp gaps without modifying candle data")
    gap_audit.add_argument("input_csv")
    gap_audit.add_argument("--expected-interval-minutes", required=True, type=int)
    gap_audit.add_argument("--output-json", required=True)

    mt5_fetch = subparsers.add_parser("fetch-mt5", help="read historical candles from MT5; no trading actions")
    mt5_fetch.add_argument("--symbol", required=True)
    mt5_fetch.add_argument("--timeframe", required=True, choices=sorted(SUPPORTED_TIMEFRAMES))
    mt5_fetch.add_argument("--start", required=True, help="ISO-8601 start timestamp with timezone")
    mt5_fetch.add_argument("--end", required=True, help="ISO-8601 end timestamp with timezone")
    mt5_fetch.add_argument("--output-dir", required=True)
    mt5_fetch.add_argument("--source-name", default="MetaTrader5")
    mt5_fetch.add_argument("--source-notes", default="Read-only MT5 Python API export; volume column is MT5 tick_volume")
    mt5_fetch.add_argument("--terminal-path", default=None)
    mt5_fetch.add_argument("--expected-interval-minutes", type=int, default=None)
    mt5_fetch.add_argument("--timeframe-check", choices=("report-only", "enforce"), default="report-only")
    mt5_fetch.add_argument("--timeframe-policy", default=None)
    mt5_fetch.add_argument("--last-bar-policy", choices=("flag", "exclude-if-possibly-incomplete"), default="flag")

    verify = subparsers.add_parser("verify-dataset", help="verify normalized data and manifest hashes")
    verify.add_argument("manifest", help="path to a schema-v2 manifest")

    recover = subparsers.add_parser("recover-outputs", help="recover or finalize an interrupted publication")
    recover.add_argument("--output-dir", required=True)
    recover.add_argument("--stem", required=True)

    clock = subparsers.add_parser("mt5-clock-check", help="collect non-conclusive, read-only MT5 clock observations")
    clock.add_argument("--symbol", required=True)
    clock.add_argument("--output-json", required=True)
    clock.add_argument("--terminal-path", default=None)
    return parser


def _load_policy(path: str | None) -> tuple[TimeframeCheckPolicy, str]:
    if path is None:
        return TimeframeCheckPolicy(), "default"
    return TimeframeCheckPolicy.from_json(path), "file"


def _parse_explicit_timestamp(value: str, name: str) -> datetime:
    try:
        return parse_utc_timestamp(value)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{name} must be ISO-8601 with an explicit timezone/UTC offset: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "list-candidates":
        for candidate in load_registry():
            print(f"{candidate.candidate_id:38} {candidate.status:20} v{candidate.version}  {candidate.name}")
        return 0
    if args.command == "import-csv":
        if args.expected_interval_minutes is not None and args.expected_interval_minutes <= 0:
            parser.error("--expected-interval-minutes must be positive")
        if args.expected_interval_minutes is not None and args.expected_interval_minutes != TIMEFRAME_MINUTES[args.timeframe]:
            parser.error("--expected-interval-minutes must match --timeframe in M2e")
        try:
            interval = timedelta(minutes=args.expected_interval_minutes) if args.expected_interval_minutes is not None else None
            data_as_of = _parse_explicit_timestamp(args.data_as_of, "--data-as-of") if args.data_as_of else None
            policy, policy_source = _load_policy(args.timeframe_policy)
            result = import_canonical_csv(
                args.input_csv, args.output_dir, symbol=args.symbol, timeframe=args.timeframe,
                source_name=args.source_name, source_notes=args.source_notes, expected_interval=interval,
                synthetic=args.synthetic, timeframe_check=args.timeframe_check, timeframe_policy=policy,
                timeframe_policy_source=policy_source, last_bar_policy=args.last_bar_policy, data_as_of=data_as_of,
            )
        except (OSError, ValueError, RuntimeError) as exc:
            parser.error(str(exc))
        print(json.dumps({"accepted": result.accepted, "unchanged": result.unchanged, "run_id": result.run_id,
                          "dataset_id": result.dataset_id, "input_rows": result.input_rows,
                          "parsed_rows": result.parsed_rows, "excluded_rows": result.excluded_rows,
                          "issues": len(result.errors), "duplicates": len(result.duplicate_timestamps),
                          "out_of_order_pairs": len(result.out_of_order_pairs), "gaps": len(result.gaps),
                          "timeframe_check": result.timeframe_check, "last_bar": result.last_bar,
                          "normalized_csv": result.output_csv, "manifest": result.manifest_json,
                          "quality_report": result.report_json, "superseded_dir": result.superseded_dir}, indent=2))
        return 0 if result.accepted else 1
    if args.command == "audit-gaps":
        if args.expected_interval_minutes <= 0:
            parser.error("--expected-interval-minutes must be positive")
        try:
            report = audit_timestamp_gaps(args.input_csv, expected_interval=timedelta(minutes=args.expected_interval_minutes))
            report_path = write_gap_audit_report(report, args.output_json)
        except (OSError, ValueError) as exc:
            parser.error(str(exc))
        print(json.dumps({"source_csv": report["source_csv"], "row_count": report["row_count"],
                          "gap_count": report["gap_count"], "sequence_issue_count": report["sequence_issue_count"],
                          "report_json": str(report_path),
                          "note": "Calendar hints are candidates only; no bars are filled and no market calendar is assumed."}, indent=2))
        return 0 if report["sequence_issue_count"] == 0 else 1
    if args.command == "verify-dataset":
        result = verify_dataset(args.manifest)
        print(json.dumps(result, indent=2))
        return 0 if result["valid"] else 1
    if args.command == "recover-outputs":
        try:
            result = recover_outputs(args.output_dir, args.stem)
        except (OSError, ValueError, RuntimeError) as exc:
            parser.error(str(exc))
        print(json.dumps(result, indent=2))
        return 0
    if args.command == "mt5-clock-check":
        try:
            report = run_mt5_clock_check(args.symbol, output_json=args.output_json, terminal_path=args.terminal_path)
        except (ImportError, OSError, ValueError) as exc:
            parser.error(str(exc))
        print(json.dumps(report, indent=2))
        return 0 if "error" not in report else 1
    if args.command == "fetch-mt5":
        if args.expected_interval_minutes is not None and args.expected_interval_minutes <= 0:
            parser.error("--expected-interval-minutes must be positive")
        if args.expected_interval_minutes is not None and args.expected_interval_minutes != TIMEFRAME_MINUTES[args.timeframe]:
            parser.error("--expected-interval-minutes must match --timeframe in M2e")
        try:
            start = _parse_explicit_timestamp(args.start, "--start")
            end = _parse_explicit_timestamp(args.end, "--end")
            output_dir = Path(args.output_dir).expanduser().resolve()
            output_dir.mkdir(parents=True, exist_ok=True)
            raw_path = output_dir / f"{args.symbol}_{args.timeframe}_mt5_raw.csv"
            rates = fetch_mt5_rates(args.symbol, args.timeframe, start, end, terminal_path=args.terminal_path)
            write_mt5_rates_csv(rates, raw_path, symbol=args.symbol, timeframe=args.timeframe, source_name=args.source_name)
            interval = timedelta(minutes=args.expected_interval_minutes) if args.expected_interval_minutes is not None else None
            policy, policy_source = _load_policy(args.timeframe_policy)
            result = import_canonical_csv(
                raw_path, output_dir / "audit", symbol=args.symbol, timeframe=args.timeframe,
                source_name=args.source_name, source_notes=args.source_notes, expected_interval=interval,
                timeframe_check=args.timeframe_check, timeframe_policy=policy, timeframe_policy_source=policy_source,
                last_bar_policy=args.last_bar_policy, data_as_of=datetime.now(timezone.utc),
            )
        except ImportError as exc:
            parser.error("MetaTrader5 Python package is missing. Install it with: py -m pip install -r requirements-mt5.txt")
        except (OSError, RuntimeError, ValueError) as exc:
            parser.error(str(exc))
        print(json.dumps({"source": args.source_name, "symbol": args.symbol, "timeframe": args.timeframe,
                          "requested_start_utc": start.isoformat(), "requested_end_utc": end.isoformat(),
                          "fetched_rows": len(rates), "accepted": result.accepted, "run_id": result.run_id,
                          "dataset_id": result.dataset_id, "issues": len(result.errors),
                          "raw_csv": str(raw_path), "normalized_csv": result.output_csv,
                          "manifest": result.manifest_json, "quality_report": result.report_json,
                          "timestamp_semantics": "unverified",
                          "note": "MT5 volume is tick volume; data acceptance does not establish feed completeness or strategy profitability."}, indent=2))
        return 0 if result.accepted else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
