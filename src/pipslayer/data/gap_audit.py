"""Explain candle timestamp gaps without assuming a broker trading calendar.

This diagnostic labels calendar clues only. It never asserts that a gap is
expected, fills candles, or changes the source dataset.
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .candles import parse_utc_timestamp


def _parse_row_time(value: str, row_number: int) -> datetime:
    try:
        return parse_utc_timestamp(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"row {row_number}: invalid timezone-aware timestamp: {exc}") from exc


def audit_timestamp_gaps(
    csv_path: str | Path,
    *,
    expected_interval: timedelta,
) -> dict[str, Any]:
    """Return a non-destructive gap audit for a timestamp-ordered candle CSV.

    Input must contain a `timestamp` column. Rows are not sorted; duplicate or
    out-of-order timestamps are surfaced as sequence issues. Gap categories are
    clues based on UTC calendar dates, not broker-session determinations.
    """
    if expected_interval <= timedelta(0):
        raise ValueError("expected_interval must be positive")
    path = Path(csv_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"CSV not found: {path}")

    timestamps: list[datetime] = []
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or "timestamp" not in {x.strip().lower() for x in reader.fieldnames if x}:
            raise ValueError("CSV must contain a timestamp column")
        for row_number, row in enumerate(reader, start=2):
            normalized = {(key or "").strip().lower(): value for key, value in row.items()}
            raw = normalized.get("timestamp")
            if not raw:
                raise ValueError(f"row {row_number}: timestamp is missing")
            timestamps.append(_parse_row_time(raw.strip(), row_number))

    sequence_issues: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    seen: set[datetime] = set()
    for i, current in enumerate(timestamps):
        if current in seen:
            sequence_issues.append({"type": "duplicate_timestamp", "row": i + 2, "timestamp": current.isoformat()})
        seen.add(current)
        if i == 0:
            continue
        previous = timestamps[i - 1]
        delta = current - previous
        if delta < timedelta(0):
            sequence_issues.append({
                "type": "out_of_order", "rows": [i + 1, i + 2],
                "previous_timestamp": previous.isoformat(), "current_timestamp": current.isoformat(),
            })
            continue
        if delta > expected_interval:
            ratio = delta.total_seconds() / expected_interval.total_seconds()
            aligned = abs(ratio - round(ratio)) < 1e-9
            missing_count = max(0, int(round(ratio)) - 1) if aligned else None
            dates = {previous.date(), current.date()}
            day = previous.date()
            while day <= current.date():
                dates.add(day)
                day += timedelta(days=1)
            spans_weekend = any(d.weekday() >= 5 for d in dates)
            if spans_weekend:
                hint = "crosses_weekend_closure_candidate"
            elif delta >= timedelta(hours=12):
                hint = "long_gap_review_session_or_feed"
            else:
                hint = "weekday_gap_review_feed_or_session"
            gaps.append({
                "previous_timestamp_utc": previous.isoformat().replace("+00:00", "Z"),
                "next_timestamp_utc": current.isoformat().replace("+00:00", "Z"),
                "elapsed_seconds": int(delta.total_seconds()),
                "elapsed": str(delta),
                "expected_interval_seconds": int(expected_interval.total_seconds()),
                "estimated_missing_bars_if_continuous": missing_count,
                "interval_multiple_exact": aligned,
                "calendar_hint_not_a_verdict": hint,
                "review_required": True,
            })

    return {
        "schema_version": 1,
        "source_csv": str(path),
        "row_count": len(timestamps),
        "expected_interval_seconds": int(expected_interval.total_seconds()),
        "gap_count": len(gaps),
        "sequence_issue_count": len(sequence_issues),
        "sequence_issues": sequence_issues,
        "gaps": gaps,
        "policy": [
            "This report is diagnostic only; it does not repair or fill missing candles.",
            "Calendar hints use UTC dates and do not encode broker sessions, holidays, daylight-saving rules, or instrument-specific trading hours.",
            "A weekend-crossing gap is a closure candidate, not proof that all missing bars are expected.",
            "Missing-bar estimates are provided only when elapsed time is an exact multiple of the expected interval.",
        ],
    }


def write_gap_audit_report(report: dict[str, Any], output_path: str | Path) -> Path:
    path = Path(output_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return path
