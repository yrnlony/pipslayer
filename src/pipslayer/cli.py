"""Command-line tools for inspecting the registry and auditing canonical candle CSVs."""
import argparse
from datetime import timedelta
import json
from pathlib import Path
from datetime import datetime

from pipslayer.data import import_canonical_csv
from pipslayer.data.gap_audit import audit_timestamp_gaps, write_gap_audit_report
from pipslayer.data.mt5_adapter import fetch_mt5_rates, write_mt5_rates_csv
from pipslayer.strategies.msnr.registry import load_registry


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pipslayer")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list-candidates", help="list registered strategy research candidates")

    importer = subparsers.add_parser("import-csv", help="audit canonical OHLC CSV and normalize accepted datasets")
    importer.add_argument("input_csv", help="input CSV path")
    importer.add_argument("--output-dir", required=True, help="directory for normalized data and reports")
    importer.add_argument("--symbol", required=True, help="instrument symbol, e.g. XAUUSD")
    importer.add_argument("--timeframe", required=True, help="timeframe, e.g. M15")
    importer.add_argument("--source-name", required=True, help="broker/provider/source label")
    importer.add_argument("--source-notes", default="", help="optional notes about source or export settings")
    importer.add_argument("--expected-interval-minutes", type=int, default=None,
                          help="explicitly report gaps larger than this interval; does not assume session calendars")
    importer.add_argument("--synthetic", action="store_true", help="mark dataset as synthetic/test data")

    gap_audit = subparsers.add_parser("audit-gaps", help="diagnose timestamp gaps without modifying candle data")
    gap_audit.add_argument("input_csv", help="CSV with a timestamp column, e.g. an accepted normalized dataset")
    gap_audit.add_argument("--expected-interval-minutes", required=True, type=int,
                           help="expected candle interval in minutes, e.g. 15 for M15")
    gap_audit.add_argument("--output-json", required=True, help="path for the diagnostic JSON report")

    mt5_fetch = subparsers.add_parser(
        "fetch-mt5", help="read historical candles from a running/logged-in MT5 terminal; no trading actions"
    )
    mt5_fetch.add_argument("--symbol", required=True, help="exact symbol name as shown in MT5 Market Watch")
    mt5_fetch.add_argument("--timeframe", required=True, choices=["M1", "M5", "M15", "M30", "H1", "H2", "H4", "D1", "W1"])
    mt5_fetch.add_argument("--start", required=True, help="ISO-8601 start timestamp with timezone, e.g. 2026-01-01T00:00:00Z")
    mt5_fetch.add_argument("--end", required=True, help="ISO-8601 end timestamp with timezone")
    mt5_fetch.add_argument("--output-dir", required=True, help="directory for raw CSV, normalized CSV, and reports")
    mt5_fetch.add_argument("--source-name", default="MetaTrader5", help="source label for dataset provenance")
    mt5_fetch.add_argument("--source-notes", default="Read-only MT5 Python API export; volume column is MT5 tick_volume")
    mt5_fetch.add_argument("--terminal-path", default=None, help="optional full path to terminal64.exe when multiple terminals are installed")
    mt5_fetch.add_argument("--expected-interval-minutes", type=int, default=None,
                           help="optional gap diagnostic; does not account for market closures/session calendars")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "list-candidates":
        for candidate in load_registry():
            print(f"{candidate.candidate_id:38} {candidate.status:20} v{candidate.version}  {candidate.name}")
        return 0
    if args.command == "import-csv":
        if args.expected_interval_minutes is not None and args.expected_interval_minutes <= 0:
            parser.error("--expected-interval-minutes must be positive")
        interval = (timedelta(minutes=args.expected_interval_minutes)
                    if args.expected_interval_minutes is not None else None)
        try:
            result = import_canonical_csv(
                args.input_csv, args.output_dir, symbol=args.symbol, timeframe=args.timeframe,
                source_name=args.source_name, source_notes=args.source_notes,
                expected_interval=interval, synthetic=args.synthetic,
            )
        except (OSError, ValueError) as exc:
            parser.error(str(exc))
        print(json.dumps({
            "accepted": result.accepted and result.input_rows > 0,
            "input_rows": result.input_rows, "parsed_rows": result.parsed_rows,
            "issues": len(result.errors), "duplicates": len(result.duplicate_timestamps),
            "out_of_order_pairs": len(result.out_of_order_pairs), "gaps": len(result.gaps),
            "normalized_csv": result.output_csv, "manifest": result.manifest_json,
            "quality_report": result.report_json,
        }, indent=2))
        return 0 if result.accepted and result.input_rows > 0 else 1

    if args.command == "audit-gaps":
        if args.expected_interval_minutes <= 0:
            parser.error("--expected-interval-minutes must be positive")
        try:
            report = audit_timestamp_gaps(
                args.input_csv, expected_interval=timedelta(minutes=args.expected_interval_minutes)
            )
            report_path = write_gap_audit_report(report, args.output_json)
        except (OSError, ValueError) as exc:
            parser.error(str(exc))
        print(json.dumps({
            "source_csv": report["source_csv"], "row_count": report["row_count"],
            "gap_count": report["gap_count"], "sequence_issue_count": report["sequence_issue_count"],
            "report_json": str(report_path),
            "note": "Calendar hints are candidates only; no bars are filled and no market calendar is assumed.",
        }, indent=2))
        return 0 if report["sequence_issue_count"] == 0 else 1

    if args.command == "fetch-mt5":
        if args.expected_interval_minutes is not None and args.expected_interval_minutes <= 0:
            parser.error("--expected-interval-minutes must be positive")
        try:
            start = datetime.fromisoformat(args.start.replace("Z", "+00:00"))
            end = datetime.fromisoformat(args.end.replace("Z", "+00:00"))
            output_dir = Path(args.output_dir).expanduser().resolve()
            output_dir.mkdir(parents=True, exist_ok=True)
            raw_path = output_dir / f"{args.symbol}_{args.timeframe}_mt5_raw.csv"
            rates = fetch_mt5_rates(args.symbol, args.timeframe, start, end, terminal_path=args.terminal_path)
            write_mt5_rates_csv(rates, raw_path, symbol=args.symbol, timeframe=args.timeframe,
                                source_name=args.source_name)
            interval = (timedelta(minutes=args.expected_interval_minutes)
                        if args.expected_interval_minutes is not None else None)
            audit_dir = output_dir / "audit"
            result = import_canonical_csv(
                raw_path, audit_dir, symbol=args.symbol, timeframe=args.timeframe,
                source_name=args.source_name, source_notes=args.source_notes,
                expected_interval=interval, synthetic=False,
            )
        except ImportError as exc:
            parser.error("MetaTrader5 Python package is missing. Install it with: py -m pip install -r requirements-mt5.txt")
        except (OSError, RuntimeError, ValueError) as exc:
            parser.error(str(exc))
        print(json.dumps({
            "source": args.source_name, "symbol": args.symbol, "timeframe": args.timeframe,
            "requested_start_utc": start.isoformat(), "requested_end_utc": end.isoformat(),
            "fetched_rows": len(rates), "accepted": result.accepted and result.input_rows > 0,
            "issues": len(result.errors), "duplicates": len(result.duplicate_timestamps),
            "out_of_order_pairs": len(result.out_of_order_pairs), "gaps": len(result.gaps),
            "raw_csv": str(raw_path), "normalized_csv": result.output_csv,
            "manifest": result.manifest_json, "quality_report": result.report_json,
            "note": "MT5 volume is tick volume; data acceptance does not establish feed completeness or strategy profitability.",
        }, indent=2))
        return 0 if result.accepted and result.input_rows > 0 else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
