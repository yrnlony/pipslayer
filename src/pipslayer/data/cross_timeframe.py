"""Read-only exact OHLC comparison between native and reconstructed timeframes.

The higher-timeframe candle is reconstructed from lower-timeframe candles whose
stored UTC open timestamps fall in the interval beginning at the native candle's
stored timestamp. No timestamps or prices are shifted, rounded, or repaired.
"""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from .candles import TIMEFRAME_MINUTES

OHLC_FIELDS = ("open", "high", "low", "close")


def _parse_timestamp(value: str, *, path: Path, row_number: int) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid timestamp in {path}, row {row_number}: {value!r}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"Timestamp has no timezone in {path}, row {row_number}: {value!r}")
    return parsed.astimezone(timezone.utc)


def _load_rows(path: str | Path) -> list[dict[str, Any]]:
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)

    with source.open("r", newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        required = {"timestamp", *OHLC_FIELDS}
        if reader.fieldnames is None:
            raise ValueError(f"No CSV header found in {source}")
        missing = required - set(reader.fieldnames)
        if missing:
            raise ValueError(f"{source} is missing columns: {sorted(missing)}")

        rows: list[dict[str, Any]] = []
        seen: set[datetime] = set()
        previous: datetime | None = None
        for row_number, raw in enumerate(reader, start=2):
            timestamp = _parse_timestamp(raw.get("timestamp"), path=source, row_number=row_number)
            if timestamp in seen:
                raise ValueError(f"Duplicate timestamp in {source}, row {row_number}: {timestamp.isoformat()}")
            if previous is not None and timestamp < previous:
                raise ValueError(f"Out-of-order timestamp in {source}, row {row_number}: {timestamp.isoformat()}")
            seen.add(timestamp)
            previous = timestamp

            row: dict[str, Any] = {"_time": timestamp}
            for field in OHLC_FIELDS:
                try:
                    value = Decimal(raw[field].strip())
                except (InvalidOperation, AttributeError, TypeError):
                    raise ValueError(f"Invalid {field} in {source}, row {row_number}: {raw.get(field)!r}")
                if not value.is_finite():
                    raise ValueError(f"Non-finite {field} in {source}, row {row_number}: {raw.get(field)!r}")
                row[field] = value

            for optional in ("symbol", "timeframe"):
                if optional in raw:
                    row[optional] = raw[optional]
            rows.append(row)

    if not rows:
        raise ValueError(f"No rows found in {source}")
    return rows


def _check_metadata(rows: list[dict[str, Any]], *, path: str | Path,
                    expected_timeframe: str) -> str | None:
    source = Path(path)
    symbols = {row.get("symbol") for row in rows if row.get("symbol") not in (None, "")}
    timeframes = {row.get("timeframe") for row in rows if row.get("timeframe") not in (None, "")}
    if len(symbols) > 1:
        raise ValueError(f"Mixed symbols in {source}: {sorted(symbols)}")
    if len(timeframes) > 1:
        raise ValueError(f"Mixed timeframes in {source}: {sorted(timeframes)}")
    if timeframes and next(iter(timeframes)) != expected_timeframe:
        raise ValueError(
            f"Timeframe metadata in {source} is {next(iter(timeframes))!r}, "
            f"not requested {expected_timeframe!r}"
        )
    return next(iter(symbols)) if symbols else None


def _manifest_last_bar_status(path: str | Path | None) -> str | None:
    if path is None:
        return None
    manifest_path = Path(path)
    if not manifest_path.exists():
        return None
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    last_bar = payload.get("last_bar") or {}
    return last_bar.get("status")


def _month(timestamp: datetime) -> str:
    return timestamp.strftime("%Y-%m")


def compare_timeframes(
    native_path: str | Path,
    lower_path: str | Path,
    *,
    native_timeframe: str,
    lower_timeframe: str,
    manifest_path: str | Path | None = None,
    mismatch_limit: int = 50,
    example_limit: int = 10,
) -> dict[str, Any]:
    """Compare native OHLC candles with exact aggregation of lower-timeframe data.

    Both CSVs must contain timestamp/open/high/low/close. If symbol/timeframe
    columns exist, their values are checked for consistency. Timestamps must be
    timezone-aware and rows must be in ascending order.

    A final native candle is excluded only when the supplied manifest explicitly
    reports ``last_bar.status == "possibly_incomplete"``. Other manifest states
    do not alter the comparison.
    """
    if native_timeframe not in TIMEFRAME_MINUTES:
        raise ValueError(f"Unsupported native timeframe: {native_timeframe}")
    if lower_timeframe not in TIMEFRAME_MINUTES:
        raise ValueError(f"Unsupported lower timeframe: {lower_timeframe}")
    native_minutes = TIMEFRAME_MINUTES[native_timeframe]
    lower_minutes = TIMEFRAME_MINUTES[lower_timeframe]
    if native_minutes <= lower_minutes or native_minutes % lower_minutes:
        raise ValueError("Native timeframe must be a larger exact multiple of lower timeframe")
    if mismatch_limit < 0 or example_limit < 0:
        raise ValueError("Example limits must be non-negative")

    native = _load_rows(native_path)
    lower = _load_rows(lower_path)
    native_symbol = _check_metadata(native, path=native_path, expected_timeframe=native_timeframe)
    lower_symbol = _check_metadata(lower, path=lower_path, expected_timeframe=lower_timeframe)
    if native_symbol and lower_symbol and native_symbol != lower_symbol:
        raise ValueError(f"Symbol mismatch: native={native_symbol!r}, lower={lower_symbol!r}")

    lower_by_time = {row["_time"]: row for row in lower}
    required_count = native_minutes // lower_minutes
    status = _manifest_last_bar_status(manifest_path)

    counts: Counter[str] = Counter()
    monthly: dict[str, Counter[str]] = defaultdict(Counter)
    mismatches: list[dict[str, Any]] = []
    insufficient: list[dict[str, Any]] = []
    off_grid_examples: list[str] = []
    off_grid_count = 0
    excluded_final = False

    for index, native_bar in enumerate(native):
        start = native_bar["_time"]
        month = _month(start)
        epoch_minutes = int(start.timestamp() // 60)
        aligned = epoch_minutes % native_minutes == 0 and start.second == 0 and start.microsecond == 0
        if not aligned:
            off_grid_count += 1
            if len(off_grid_examples) < example_limit:
                off_grid_examples.append(start.isoformat())

        if index == len(native) - 1 and status == "possibly_incomplete":
            counts["excluded_native_last_bar_possibly_incomplete"] += 1
            monthly[month]["excluded_native_last_bar_possibly_incomplete"] += 1
            excluded_final = True
            continue

        expected_times = [
            start + timedelta(minutes=lower_minutes * offset)
            for offset in range(required_count)
        ]
        source_rows = [lower_by_time.get(timestamp) for timestamp in expected_times]
        available = sum(row is not None for row in source_rows)
        if available != required_count:
            counts["insufficient_lower_timeframe_coverage"] += 1
            monthly[month]["insufficient_lower_timeframe_coverage"] += 1
            if len(insufficient) < example_limit:
                missing = [
                    timestamp.isoformat()
                    for timestamp, row in zip(expected_times, source_rows)
                    if row is None
                ]
                insufficient.append({
                    "native_timestamp": start.isoformat(),
                    "available_lower_bars": available,
                    "required_lower_bars": required_count,
                    "first_missing_timestamps": missing[:4],
                })
            continue

        bars = [row for row in source_rows if row is not None]
        reconstructed = {
            "open": bars[0]["open"],
            "high": max(row["high"] for row in bars),
            "low": min(row["low"] for row in bars),
            "close": bars[-1]["close"],
        }
        differences = {
            field: {
                "native": str(native_bar[field]),
                "from_lower_timeframe": str(reconstructed[field]),
            }
            for field in OHLC_FIELDS
            if native_bar[field] != reconstructed[field]
        }
        if differences:
            counts["mismatch"] += 1
            monthly[month]["mismatch"] += 1
            if len(mismatches) < mismatch_limit:
                mismatches.append({
                    "native_timestamp": start.isoformat(),
                    "differences": differences,
                })
        else:
            counts["match"] += 1
            monthly[month]["match"] += 1

    return {
        "comparison": "native OHLC versus exact lower-timeframe aggregation",
        "symbol": native_symbol or lower_symbol,
        "native_timeframe": native_timeframe,
        "lower_timeframe": lower_timeframe,
        "native_rows": len(native),
        "lower_rows": len(lower),
        "native_start": native[0]["_time"].isoformat(),
        "native_end": native[-1]["_time"].isoformat(),
        "lower_start": lower[0]["_time"].isoformat(),
        "lower_end": lower[-1]["_time"].isoformat(),
        "required_lower_bars_per_native_bar": required_count,
        "manifest_last_bar_status": status,
        "native_timestamp_off_grid_count": off_grid_count,
        "native_timestamp_off_grid_examples": off_grid_examples,
        "counts": dict(counts),
        "monthly_counts": {key: dict(value) for key, value in sorted(monthly.items())},
        "mismatch_examples": mismatches,
        "insufficient_coverage_examples": insufficient,
        "final_native_bar_excluded_by_manifest": excluded_final,
        "aggregation_rule": {
            "open": "first lower-timeframe open",
            "high": "maximum lower-timeframe high",
            "low": "minimum lower-timeframe low",
            "close": "last lower-timeframe close",
            "volume": "not compared",
        },
        "interpretation_notes": [
            "Stored timestamps are interpreted as UTC instants; no shifting or boundary repair is performed.",
            "A native candle is compared only when every expected lower-timeframe open timestamp exists.",
            "Insufficient lower-timeframe coverage is not labelled a native-candle defect.",
            "Off-grid timestamps are diagnostics, not proof of broker-time semantics.",
            "Timestamp semantics remain whatever the source manifest declares; this comparison does not verify them.",
            "No source files are changed and no candles are synthesized, shifted, or repaired.",
        ],
    }
