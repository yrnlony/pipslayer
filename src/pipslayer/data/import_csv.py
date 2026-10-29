"""Canonical CSV import, validation, and reproducible dataset audit reports.

Input timestamps must be ISO-8601 and include a timezone/UTC offset. The importer
never guesses a broker timezone or repairs rows. It writes a normalized dataset
only when every row parses and sequence validation passes.
"""
from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from .candles import Candle, parse_utc_timestamp, validate_candles

REQUIRED_COLUMNS = {"timestamp", "open", "high", "low", "close"}
OPTIONAL_COLUMNS = {"volume"}
OUTPUT_COLUMNS = ["timestamp", "symbol", "timeframe", "open", "high", "low", "close", "volume", "source"]


@dataclass(frozen=True)
class ImportIssue:
    row: int
    code: str
    message: str


@dataclass(frozen=True)
class ImportResult:
    input_path: str
    input_sha256: str
    symbol: str
    timeframe: str
    source_name: str
    input_rows: int
    parsed_rows: int
    errors: tuple[ImportIssue, ...]
    duplicate_timestamps: tuple[str, ...]
    out_of_order_pairs: tuple[str, ...]
    gaps: tuple[str, ...]
    output_csv: str | None
    manifest_json: str | None
    report_json: str

    @property
    def accepted(self) -> bool:
        return not self.errors and not self.duplicate_timestamps and not self.out_of_order_pairs


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _float_cell(value: str, *, row: int, column: str, required: bool = True) -> float | None:
    cleaned = value.strip()
    if not cleaned and not required:
        return None
    if not cleaned:
        raise ValueError(f"row {row}: '{column}' is required")
    try:
        number = float(cleaned)
    except ValueError as exc:
        raise ValueError(f"row {row}: '{column}' must be numeric") from exc
    if not math.isfinite(number):
        raise ValueError(f"row {row}: '{column}' must be finite")
    return number


def import_canonical_csv(
    input_path: str | Path,
    output_dir: str | Path,
    *,
    symbol: str,
    timeframe: str,
    source_name: str,
    source_notes: str = "",
    expected_interval: timedelta | None = None,
    synthetic: bool = False,
) -> ImportResult:
    """Audit a canonical CSV and write outputs only for an accepted sequence.

    CSV columns: timestamp,open,high,low,close; optional volume.
    Timestamp must be ISO-8601 with an explicit timezone, e.g. 2026-10-01T09:15:00Z.
    """
    source_path = Path(input_path).expanduser().resolve()
    destination = Path(output_dir).expanduser().resolve()
    if not source_path.is_file():
        raise FileNotFoundError(f"Input CSV not found: {source_path}")
    if not symbol.strip() or not source_name.strip():
        raise ValueError("symbol and source_name must not be blank")

    row_issues: list[ImportIssue] = []
    candles: list[Candle] = []
    input_rows = 0
    with source_path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None:
            raise ValueError("CSV is empty or has no header row")
        headers = {name.strip().lower() for name in reader.fieldnames if name is not None}
        missing = sorted(REQUIRED_COLUMNS - headers)
        if missing:
            raise ValueError("CSV missing required columns: " + ", ".join(missing))
        if "volume" in headers:
            has_volume = True
        else:
            has_volume = False
        for row_number, raw in enumerate(reader, start=2):
            input_rows += 1
            normalized = {(key or "").strip().lower(): (value or "") for key, value in raw.items()}
            try:
                timestamp_text = normalized.get("timestamp", "").strip()
                if not timestamp_text:
                    raise ValueError(f"row {row_number}: 'timestamp' is required")
                try:
                    timestamp = parse_utc_timestamp(timestamp_text)
                except (ValueError, TypeError) as exc:
                    raise ValueError(f"row {row_number}: timestamp must be ISO-8601 with an explicit timezone/UTC offset ({exc})") from exc
                open_value = _float_cell(normalized.get("open", ""), row=row_number, column="open")
                high_value = _float_cell(normalized.get("high", ""), row=row_number, column="high")
                low_value = _float_cell(normalized.get("low", ""), row=row_number, column="low")
                close_value = _float_cell(normalized.get("close", ""), row=row_number, column="close")
                volume_value = _float_cell(normalized.get("volume", ""), row=row_number, column="volume", required=False) if has_volume else None
                candle = Candle(
                    symbol=symbol.strip(), timeframe=timeframe.strip().upper(), timestamp=timestamp,
                    open=float(open_value), high=float(high_value), low=float(low_value), close=float(close_value),
                    volume=volume_value, source=source_name.strip(),
                )
                candles.append(candle)
            except (ValueError, OverflowError) as exc:
                row_issues.append(ImportIssue(row=row_number, code="row_invalid", message=str(exc)))

    validation = validate_candles(candles, expected_interval=expected_interval)
    for error in validation.errors:
        row_issues.append(ImportIssue(row=0, code="sequence_invalid", message=error))
    for duplicate in validation.duplicate_timestamps:
        row_issues.append(ImportIssue(row=0, code="duplicate_timestamp", message=duplicate))
    for pair in validation.out_of_order_pairs:
        row_issues.append(ImportIssue(row=0, code="out_of_order", message=pair))

    destination.mkdir(parents=True, exist_ok=True)
    stem = source_path.stem
    report_path = destination / f"{stem}.quality-report.json"
    output_path: Path | None = None
    manifest_path: Path | None = None
    accepted = not row_issues and bool(candles)

    if accepted:
        output_path = destination / f"{stem}.normalized.csv"
        with output_path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=OUTPUT_COLUMNS)
            writer.writeheader()
            for candle in candles:
                writer.writerow({
                    "timestamp": candle.timestamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                    "symbol": candle.symbol, "timeframe": candle.timeframe,
                    "open": candle.open, "high": candle.high, "low": candle.low, "close": candle.close,
                    "volume": "" if candle.volume is None else candle.volume,
                    "source": candle.source or "",
                })
        manifest_path = destination / f"{stem}.manifest.json"
        timestamps = [c.timestamp for c in candles]
        manifest = {
            "schema_version": 1,
            "dataset_id": f"{symbol.strip()}-{timeframe.strip().upper()}-{_sha256(source_path)[:12]}",
            "symbol": symbol.strip(), "timeframe": timeframe.strip().upper(),
            "source_name": source_name.strip(), "timestamp_timezone": "UTC",
            "start_time": min(timestamps).isoformat().replace("+00:00", "Z"),
            "end_time": max(timestamps).isoformat().replace("+00:00", "Z"),
            "row_count": len(candles), "synthetic": bool(synthetic),
            "source_notes": source_notes,
            "source_file_name": source_path.name,
            "source_file_sha256": _sha256(source_path),
            "normalized_file_name": output_path.name,
            "processing_steps": ["canonical_csv_import", "timestamp_normalized_to_utc", "ohlc_validation", "sequence_validation"],
        }
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    result = ImportResult(
        input_path=str(source_path), input_sha256=_sha256(source_path), symbol=symbol.strip(),
        timeframe=timeframe.strip().upper(), source_name=source_name.strip(), input_rows=input_rows,
        parsed_rows=len(candles), errors=tuple(row_issues),
        duplicate_timestamps=validation.duplicate_timestamps,
        out_of_order_pairs=validation.out_of_order_pairs, gaps=validation.gaps,
        output_csv=str(output_path) if output_path else None,
        manifest_json=str(manifest_path) if manifest_path else None,
        report_json=str(report_path),
    )
    report_payload: dict[str, Any] = {
        "schema_version": 1, "accepted": result.accepted and input_rows > 0,
        "input_path": result.input_path, "input_sha256": result.input_sha256,
        "symbol": result.symbol, "timeframe": result.timeframe, "source_name": result.source_name,
        "input_rows": result.input_rows, "parsed_rows": result.parsed_rows,
        "error_count": len(result.errors), "errors": [asdict(issue) for issue in result.errors],
        "duplicate_timestamps": list(result.duplicate_timestamps),
        "out_of_order_pairs": list(result.out_of_order_pairs), "gaps": list(result.gaps),
        "gap_policy": "informational; expected interval only checked when explicitly supplied",
        "output_csv": result.output_csv, "manifest_json": result.manifest_json,
        "notes": [
            "No rows are sorted, repaired, or silently dropped.",
            "Timestamps must include an explicit timezone or UTC offset.",
            "Gaps do not automatically invalidate data because trading sessions and feed calendars vary.",
            "Acceptance is a structural data check, not a guarantee of market-data completeness or strategy validity.",
        ],
    }
    report_path.write_text(json.dumps(report_payload, indent=2) + "\n", encoding="utf-8")
    return result
