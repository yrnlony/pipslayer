"""Last-candle completeness assessment; never silently discards observations."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from .candles import Candle, TIMEFRAME_MINUTES


def assess_last_bar(candles: list[Candle], *, data_as_of: datetime | None = None) -> dict:
    if not candles or data_as_of is None:
        return {"status": "cannot_assess", "policy": "flag", "data_as_of": None if data_as_of is None else data_as_of.isoformat()}
    if data_as_of.tzinfo is None or data_as_of.utcoffset() is None:
        raise ValueError("data_as_of must include a timezone/UTC offset")
    reference = data_as_of.astimezone(timezone.utc)
    last = candles[-1]
    close_time = last.timestamp + timedelta(minutes=TIMEFRAME_MINUTES[last.timeframe])
    status = "possibly_incomplete" if close_time > reference else "no_evidence_of_incompleteness"
    return {"status": status, "last_bar_open": last.timestamp.isoformat().replace("+00:00", "Z"),
            "expected_close": close_time.isoformat().replace("+00:00", "Z"),
            "data_as_of": reference.isoformat().replace("+00:00", "Z"), "policy": "flag"}
