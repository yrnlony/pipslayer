"""Provider-neutral OHLC candle schema and conservative data-quality checks."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import math
from typing import Iterable

TIMEFRAME_MINUTES = {
    "M1": 1, "M5": 5, "M15": 15, "M30": 30,
    "H1": 60, "H2": 120, "H4": 240, "D1": 1440, "W1": 10080,
}
SUPPORTED_TIMEFRAMES = frozenset(TIMEFRAME_MINUTES)


def _require_aware_utc(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware; normalize source timestamps to UTC")


@dataclass(frozen=True)
class Candle:
    symbol: str
    timeframe: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None
    source: str | None = None

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("symbol must not be blank")
        if self.timeframe not in SUPPORTED_TIMEFRAMES:
            raise ValueError(f"Unsupported timeframe: {self.timeframe}")
        _require_aware_utc(self.timestamp)
        if self.timestamp.utcoffset() != timedelta(0):
            raise ValueError("timestamp must be normalized to UTC")
        values = (self.open, self.high, self.low, self.close)
        if not all(math.isfinite(float(v)) for v in values):
            raise ValueError("OHLC values must be finite numbers")
        if self.high < max(self.open, self.close, self.low):
            raise ValueError("high must be >= open, close, and low")
        if self.low > min(self.open, self.close, self.high):
            raise ValueError("low must be <= open, close, and high")
        if self.volume is not None:
            if not math.isfinite(float(self.volume)) or self.volume < 0:
                raise ValueError("volume must be finite and non-negative when provided")


@dataclass(frozen=True)
class CandleValidationReport:
    candle_count: int
    errors: tuple[str, ...]
    duplicate_timestamps: tuple[str, ...]
    out_of_order_pairs: tuple[str, ...]
    gaps: tuple[str, ...]

    @property
    def is_valid(self) -> bool:
        return not self.errors and not self.duplicate_timestamps and not self.out_of_order_pairs


def validate_candles(candles: Iterable[Candle], *, expected_interval: timedelta | None = None) -> CandleValidationReport:
    """Check a sequence without sorting or silently repairing it. Gaps are informational."""
    rows = list(candles)
    errors: list[str] = []
    duplicates: list[str] = []
    out_of_order: list[str] = []
    gaps: list[str] = []
    seen: set[datetime] = set()
    for i, candle in enumerate(rows):
        if i and (candle.symbol != rows[0].symbol or candle.timeframe != rows[0].timeframe):
            errors.append(f"row {i}: mixed symbol/timeframe in one candle sequence")
        stamp = candle.timestamp
        if stamp in seen:
            duplicates.append(stamp.isoformat())
        seen.add(stamp)
        if i:
            previous = rows[i - 1].timestamp
            if stamp < previous:
                out_of_order.append(f"row {i - 1}->{i}: {previous.isoformat()} then {stamp.isoformat()}")
            elif expected_interval is not None and stamp - previous > expected_interval:
                gaps.append(f"{previous.isoformat()} -> {stamp.isoformat()} ({stamp - previous})")
    if expected_interval is not None and expected_interval <= timedelta(0):
        errors.append("expected_interval must be positive")
    return CandleValidationReport(len(rows), tuple(errors), tuple(duplicates), tuple(out_of_order), tuple(gaps))


def parse_utc_timestamp(value: str) -> datetime:
    """Parse ISO-8601 with an explicit offset and normalize to UTC."""
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    _require_aware_utc(parsed)
    return parsed.astimezone(timezone.utc)
