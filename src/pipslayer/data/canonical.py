"""Versioned canonical candle encoding used for stable logical dataset identity."""
from __future__ import annotations

import hashlib
import math
import unicodedata
from datetime import datetime, timezone
from typing import Iterable

from .candles import Candle, TIMEFRAME_MINUTES

CANONICALIZATION_VERSION = "candle-canon-v1"
CANONICALIZATION_TAG = "pipslayer-candles-canon-1"


def _validate_symbol(symbol: str) -> str:
    cleaned = symbol.strip()
    if not cleaned:
        raise ValueError("symbol must not be blank")
    if any(ch in "|\r\n" or unicodedata.category(ch).startswith("C") for ch in cleaned):
        raise ValueError("symbol contains a canonicalization delimiter or control character")
    return cleaned


def _number(value: float | None, *, row: int, field: str) -> str:
    if value is None:
        return ""
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"row {row}: '{field}' must be finite for canonicalization")
    if number == 0:
        return "0.0"
    rendered = repr(number)
    if "e" in rendered.lower():
        raise ValueError(f"row {row}: '{field}' uses unsupported exponent notation ({rendered})")
    return rendered


def canonical_bytes(candles: Iterable[Candle], *, symbol: str, timeframe: str) -> bytes:
    canonicalization_self_test()
    symbol = _validate_symbol(symbol)
    timeframe = timeframe.strip().upper()
    if timeframe not in TIMEFRAME_MINUTES:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    rows = list(candles)
    lines = [f"{CANONICALIZATION_TAG}|{symbol}|{timeframe}"]
    for row_number, candle in enumerate(rows, start=1):
        stamp = candle.timestamp.astimezone(timezone.utc)
        timestamp = stamp.strftime("%Y-%m-%dT%H:%M:%S")
        if stamp.microsecond:
            timestamp += f".{stamp.microsecond:06d}"
        timestamp += "Z"
        values = [_number(getattr(candle, field), row=row_number, field=field)
                  for field in ("open", "high", "low", "close", "volume")]
        lines.append("|".join([timestamp, *values]))
    return ("\n".join(lines) + "\n").encode("utf-8")


def canonical_sha256(candles: Iterable[Candle], *, symbol: str, timeframe: str) -> str:
    return hashlib.sha256(canonical_bytes(candles, symbol=symbol, timeframe=timeframe)).hexdigest()


def dataset_id(symbol: str, timeframe: str, digest: str) -> str:
    return f"{_validate_symbol(symbol)}-{timeframe.strip().upper()}-c1-{digest[:16]}"


def canonicalization_self_test() -> None:
    """Small runtime guard; golden digest tests remain the authoritative contract."""
    vectors = [(100.0, "100.0"), (0.0, "0.0"), (-0.0, "0.0"), (0.1 + 0.2, "0.30000000000000004")]
    for value, expected in vectors:
        if _number(value, row=0, field="self_test") != expected:
            raise RuntimeError("Canonicalization runtime self-test failed; refusing to hash dataset")
