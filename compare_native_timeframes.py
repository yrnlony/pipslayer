#!/usr/bin/env python3
"""Read-only comparison of native Headway H2/H4 candles against M15 aggregation.

Run from the Pipslayer repository root:
    py compare_native_timeframes.py

Inputs are never modified. The report is written to
reports/native-timeframe-comparison.json.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DEFAULTS = {
    "m15": ROOT / "data/canonical-headway-xauusd-m15-2026-05-to-2026-11/XAUUSD_M15_2026-05_to_2026-11.normalized.csv",
    "h2": ROOT / "data/mt5-headway-xauusd-h2-2026-05-to-2026-11/audit/XAUUSD_H2_mt5_raw.normalized.csv",
    "h4": ROOT / "data/mt5-headway-xauusd-h4-2026-05-to-2026-11/audit/XAUUSD_H4_mt5_raw.normalized.csv",
    "h2_manifest": ROOT / "data/mt5-headway-xauusd-h2-2026-05-to-2026-11/audit/XAUUSD_H2_mt5_raw.manifest.json",
    "h4_manifest": ROOT / "data/mt5-headway-xauusd-h4-2026-05-to-2026-11/audit/XAUUSD_H4_mt5_raw.manifest.json",
}
FIELDS = ("open", "high", "low", "close")


def parse_time(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError(f"Timestamp has no timezone: {value}")
    return dt.astimezone(timezone.utc)


def load_rows(path: Path) -> list[dict[str, Any]]:
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise ValueError(f"No rows found in {path}")
    required = {"timestamp", *FIELDS}
    missing = required - set(rows[0])
    if missing:
        raise ValueError(f"{path} is missing columns: {sorted(missing)}")
    for row in rows:
        row["_time"] = parse_time(row["timestamp"])
        for field in FIELDS:
            try:
                row[field] = Decimal(row[field])
            except (InvalidOperation, TypeError):
                raise ValueError(f"Invalid {field} in {path}: {row}")
    return rows


def read_manifest_status(path: Path) -> str | None:
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return (data.get("last_bar") or {}).get("status")


def month_key(dt: datetime) -> str:
    return dt.strftime("%Y-%m")


def compare(native: list[dict[str, Any]], m15_by_time: dict[datetime, dict[str, Any]],
            timeframe: str, interval_minutes: int, manifest_status: str | None) -> dict[str, Any]:
    required_count = interval_minutes // 15
    counts: Counter[str] = Counter()
    monthly: dict[str, Counter[str]] = defaultdict(Counter)
    mismatches: list[dict[str, Any]] = []
    insufficient_examples: list[dict[str, Any]] = []
    off_grid = 0
    grid_examples: list[str] = []
    skipped_manifest_last = False

    # The manifest identifies whether the final native candle may still be forming.
    for index, bar in enumerate(native):
        start = bar["_time"]
        month = month_key(start)
        epoch_minutes = int(start.timestamp() // 60)
        aligned = (epoch_minutes % interval_minutes == 0 and start.second == 0)
        if not aligned:
            off_grid += 1
            if len(grid_examples) < 10:
                grid_examples.append(start.isoformat())

        if index == len(native) - 1 and manifest_status == "possibly_incomplete":
            counts["excluded_native_last_bar_possibly_incomplete"] += 1
            monthly[month]["excluded_native_last_bar_possibly_incomplete"] += 1
            skipped_manifest_last = True
            continue

        expected_times = [start + timedelta(minutes=15 * i) for i in range(required_count)]
        source = [m15_by_time.get(t) for t in expected_times]
        available = sum(item is not None for item in source)
        if available != required_count:
            counts["insufficient_m15_coverage"] += 1
            monthly[month]["insufficient_m15_coverage"] += 1
            if len(insufficient_examples) < 10:
                missing = [t.isoformat() for t, item in zip(expected_times, source) if item is None]
                insufficient_examples.append({
                    "native_timestamp": start.isoformat(),
                    "available_m15_bars": available,
                    "required_m15_bars": required_count,
                    "first_missing_timestamps": missing[:4],
                })
            continue

        bars = [item for item in source if item is not None]
        reconstructed = {
            "open": bars[0]["open"],
            "high": max(x["high"] for x in bars),
            "low": min(x["low"] for x in bars),
            "close": bars[-1]["close"],
        }
        differences = {
            field: {
                "native": str(bar[field]),
                "from_m15": str(reconstructed[field]),
            }
            for field in FIELDS if bar[field] != reconstructed[field]
        }
        if differences:
            counts["mismatch"] += 1
            monthly[month]["mismatch"] += 1
            if len(mismatches) < 50:
                mismatches.append({
                    "native_timestamp": start.isoformat(),
                    "differences": differences,
                })
        else:
            counts["match"] += 1
            monthly[month]["match"] += 1

    return {
        "timeframe": timeframe,
        "native_rows": len(native),
        "required_m15_bars_per_native_bar": required_count,
        "manifest_last_bar_status": manifest_status,
        "native_timestamp_off_grid_count": off_grid,
        "native_timestamp_off_grid_examples": grid_examples,
        "counts": dict(counts),
        "monthly_counts": {m: dict(c) for m, c in sorted(monthly.items())},
        "mismatch_examples_first_50": mismatches,
        "insufficient_coverage_examples_first_10": insufficient_examples,
        "final_native_bar_excluded_by_manifest": skipped_manifest_last,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for key, default in DEFAULTS.items():
        parser.add_argument(f"--{key.replace('_', '-')}", type=Path, default=default)
    parser.add_argument("--report", type=Path,
                        default=ROOT / "reports/native-timeframe-comparison.json")
    args = parser.parse_args()

    for key in DEFAULTS:
        path = getattr(args, key)
        if not path.is_file():
            raise SystemExit(f"Required input not found: {path}")

    m15 = load_rows(args.m15)
    m15_by_time = {row["_time"]: row for row in m15}
    if len(m15_by_time) != len(m15):
        raise SystemExit("M15 input contains duplicate timestamps; refusing comparison.")

    h2 = load_rows(args.h2)
    h4 = load_rows(args.h4)
    result = {
        "comparison": "native H2/H4 OHLC versus exact M15 time buckets",
        "symbol": "XAUUSD",
        "timestamp_interpretation": "UTC timestamps as stored; no shifting or boundary repair",
        "aggregation_rule": {
            "open": "first M15 open",
            "high": "maximum M15 high",
            "low": "minimum M15 low",
            "close": "last M15 close",
            "volume": "not compared",
        },
        "inputs": {
            "m15": str(args.m15),
            "h2": str(args.h2),
            "h4": str(args.h4),
        },
        "m15_rows": len(m15),
        "m15_start": m15[0]["_time"].isoformat(),
        "m15_end": m15[-1]["_time"].isoformat(),
        "results": {
            "H2": compare(h2, m15_by_time, "H2", 120,
                          read_manifest_status(args.h2_manifest)),
            "H4": compare(h4, m15_by_time, "H4", 240,
                          read_manifest_status(args.h4_manifest)),
        },
        "interpretation_notes": [
            "A bucket is compared only when every expected M15 open timestamp exists.",
            "Insufficient M15 coverage is not labelled a native-candle defect.",
            "The H4 final native bar is excluded when its manifest says possibly_incomplete.",
            "No source files are changed; no candles are synthesized, shifted, or repaired.",
            "Off-grid counts are diagnostics, not automatic proof of broker-time semantics.",
        ],
    }

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    print(f"M15 rows: {len(m15)}")
    print(f"M15 range: {result['m15_start']} -> {result['m15_end']}")
    for tf in ("H2", "H4"):
        r = result["results"][tf]
        print(f"\n{tf}: native={r['native_rows']}  "
              f"matches={r['counts'].get('match', 0)}  "
              f"mismatches={r['counts'].get('mismatch', 0)}  "
              f"insufficient={r['counts'].get('insufficient_m15_coverage', 0)}  "
              f"excluded_incomplete={r['counts'].get('excluded_native_last_bar_possibly_incomplete', 0)}  "
              f"off_grid={r['native_timestamp_off_grid_count']}")
        for item in r["mismatch_examples_first_50"][:10]:
            print(f"  MISMATCH {item['native_timestamp']}: {item['differences']}")
    print(f"\nFull report: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
