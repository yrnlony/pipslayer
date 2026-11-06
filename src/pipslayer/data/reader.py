"""Read-only loader for published normalized candle CSV files."""
from __future__ import annotations

import csv
from pathlib import Path

from .candles import Candle, parse_utc_timestamp, validate_candles


def load_canonical_csv(path: str | Path) -> tuple[Candle, ...]:
    """Load and validate candles without sorting, repairing, or changing the file."""
    source = Path(path)

    if not source.is_file():
        raise FileNotFoundError(f"Normalized dataset not found: {source}")

    candles: list[Candle] = []

    with source.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)

        required = {
            "timestamp", "symbol", "timeframe",
            "open", "high", "low", "close", "volume", "source",
        }

        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError("Normalized CSV is missing required columns")

        for row_number, row in enumerate(reader, start=2):
            try:
                candles.append(Candle(
                    symbol=row["symbol"],
                    timeframe=row["timeframe"],
                    timestamp=parse_utc_timestamp(row["timestamp"]),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=None if row["volume"] == "" else float(row["volume"]),
                    source=row["source"] or None,
                ))
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    f"Invalid normalized CSV row {row_number}: {exc}"
                ) from exc

    if not candles:
        raise ValueError("Normalized CSV contains no candles")

    report = validate_candles(candles)
    if not report.is_valid:
        raise ValueError(
            "Normalized candle sequence is invalid: " + "; ".join(report.errors)
        )

    return tuple(candles)
