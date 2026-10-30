"""Read-only historical candle adapter for the MetaTrader 5 Python package.

MT5 bar timestamps are epoch seconds. M2e preserves the numeric source timestamp
but records the interpretation as unverified; this adapter does not establish
broker-server timezone or daily-boundary semantics.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import importlib
import os
from pathlib import Path
import tempfile
from typing import Any

from .candles import TIMEFRAME_MINUTES

MT5_TIMEFRAMES = {name: f"TIMEFRAME_{name}" for name in TIMEFRAME_MINUTES}


def _aware_utc(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must include a timezone/UTC offset")
    return value.astimezone(timezone.utc)


def _rate_field(rate: Any, name: str, default: Any = None) -> Any:
    """Read a field from either a mapping or NumPy structured MT5 rate row."""
    if isinstance(rate, dict):
        return rate.get(name, default)
    try:
        return rate[name]
    except (KeyError, IndexError, TypeError, ValueError):
        return default


def fetch_mt5_rates_with_context(symbol: str, timeframe: str, start: datetime, end: datetime, *,
                                 terminal_path: str | None = None, mt5_module: Any | None = None) -> dict[str, Any]:
    """Fetch rates plus source context without claiming timestamp semantics are verified."""
    rates = fetch_mt5_rates(symbol, timeframe, start, end, terminal_path=terminal_path, mt5_module=mt5_module)
    return {"rates": rates, "source": "MetaTrader5", "symbol": symbol, "timeframe": timeframe.upper(),
            "requested_start_utc": _aware_utc(start, "start").isoformat().replace("+00:00", "Z"),
            "requested_end_utc": _aware_utc(end, "end").isoformat().replace("+00:00", "Z"),
            "timestamp_semantics": "unverified", "timestamp_note": "MT5 epoch values are exported as UTC-shaped timestamps; broker clock semantics are not independently verified."}


def fetch_mt5_rates(symbol: str, timeframe: str, start: datetime, end: datetime, *,
                    terminal_path: str | None = None, mt5_module: Any | None = None) -> list[dict[str, Any]]:
    """Connect to an already configured MT5 terminal and fetch historical rates."""
    if not symbol or not symbol.strip():
        raise ValueError("symbol must not be blank")
    timeframe = timeframe.upper()
    if timeframe not in MT5_TIMEFRAMES:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    start_utc = _aware_utc(start, "start")
    end_utc = _aware_utc(end, "end")
    if start_utc >= end_utc:
        raise ValueError("start must be earlier than end")
    mt5 = mt5_module or importlib.import_module("MetaTrader5")
    init_kwargs = {"path": terminal_path} if terminal_path else {}
    if not mt5.initialize(**init_kwargs):
        raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")
    try:
        if not mt5.symbol_select(symbol, True):
            raise RuntimeError(f"Could not select MT5 symbol {symbol!r}: {mt5.last_error()}")
        constant = getattr(mt5, MT5_TIMEFRAMES[timeframe])
        rates = mt5.copy_rates_range(symbol, constant, start_utc, end_utc)
        if rates is None:
            raise RuntimeError(f"MT5 returned no rate array for {symbol} {timeframe}: {mt5.last_error()}")
        return list(rates)
    finally:
        mt5.shutdown()


def shutdown_mt5(mt5_module: Any | None = None) -> None:
    """Shut down an MT5 connection after a successful initialize."""
    mt5 = mt5_module or importlib.import_module("MetaTrader5")
    mt5.shutdown()


def write_mt5_rates_csv(rates: list[dict[str, Any]], output_csv: str | Path, *,
                        symbol: str, timeframe: str, source_name: str) -> Path:
    """Atomically replace a raw MT5 CSV only after the entire export is written."""
    if not rates:
        raise ValueError("MT5 returned zero candles for the requested range")
    destination = Path(output_csv).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
    os.close(fd)
    temp = Path(temp_name)
    try:
        with temp.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=["timestamp", "open", "high", "low", "close", "volume"], lineterminator="\n")
            writer.writeheader()
            for index, rate in enumerate(rates, start=1):
                try:
                    stamp = datetime.fromtimestamp(int(_rate_field(rate, "time")), tz=timezone.utc)
                    values = [_rate_field(rate, name) for name in ("open", "high", "low", "close")]
                    if any(value is None for value in values):
                        raise ValueError("missing OHLC field")
                    writer.writerow({"timestamp": stamp.isoformat().replace("+00:00", "Z"),
                                     "open": values[0], "high": values[1], "low": values[2], "close": values[3],
                                     "volume": _rate_field(rate, "tick_volume", "")})
                except (KeyError, TypeError, ValueError, OverflowError) as exc:
                    raise ValueError(f"Malformed MT5 rate at returned row {index}: {exc}") from exc
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, destination)
    finally:
        temp.unlink(missing_ok=True)
    return destination
