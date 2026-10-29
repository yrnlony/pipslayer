"""Read-only historical candle adapter for the MetaTrader 5 Python package.

This adapter only reads market rates. It never places, modifies, or closes orders.
MT5 bar timestamps are Unix seconds and are interpreted as UTC, per the MT5 API.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import importlib
from pathlib import Path
from typing import Any

MT5_TIMEFRAMES = {
    "M1": "TIMEFRAME_M1",
    "M5": "TIMEFRAME_M5",
    "M15": "TIMEFRAME_M15",
    "M30": "TIMEFRAME_M30",
    "H1": "TIMEFRAME_H1",
    "H2": "TIMEFRAME_H2",
    "H4": "TIMEFRAME_H4",
    "D1": "TIMEFRAME_D1",
    "W1": "TIMEFRAME_W1",
}


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


def fetch_mt5_rates(
    symbol: str,
    timeframe: str,
    start: datetime,
    end: datetime,
    *,
    terminal_path: str | None = None,
    mt5_module: Any | None = None,
) -> list[dict[str, Any]]:
    """Connect to an already configured MT5 terminal and fetch historical rates.

    `mt5_module` is injectable for tests. In normal use the MetaTrader5 package
    is imported lazily. Caller owns terminal shutdown via `shutdown_mt5`.
    """
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
    """Shut down the MT5 connection after a successful initialize."""
    mt5 = mt5_module or importlib.import_module("MetaTrader5")
    mt5.shutdown()


def write_mt5_rates_csv(
    rates: list[dict[str, Any]],
    output_csv: str | Path,
    *,
    symbol: str,
    timeframe: str,
    source_name: str,
) -> Path:
    """Write MT5 rates as Pipslayer's canonical UTC OHLC CSV.

    MT5 `tick_volume` is written to `volume`; it is tick activity, not centralized
    traded volume. Rows are written in the order returned so validation can flag
    ordering problems rather than silently sorting them.
    """
    if not rates:
        raise ValueError("MT5 returned zero candles for the requested range")
    destination = Path(output_csv).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["timestamp", "open", "high", "low", "close", "volume"])
        writer.writeheader()
        for index, rate in enumerate(rates, start=1):
            try:
                stamp = datetime.fromtimestamp(int(_rate_field(rate, "time")), tz=timezone.utc)
                writer.writerow({
                    "timestamp": stamp.isoformat().replace("+00:00", "Z"),
                    "open": _rate_field(rate, "open"), "high": _rate_field(rate, "high"),
                    "low": _rate_field(rate, "low"), "close": _rate_field(rate, "close"),
                    "volume": _rate_field(rate, "tick_volume", ""),
                })
            except (KeyError, TypeError, ValueError, OverflowError) as exc:
                stream.close()
                destination.unlink(missing_ok=True)
                raise ValueError(f"Malformed MT5 rate at returned row {index}: {exc}") from exc
    return destination
