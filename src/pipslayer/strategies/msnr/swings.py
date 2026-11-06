
"""Baseline, non-executable MSNR swing-point research detector."""

from dataclasses import dataclass
from typing import Literal, Sequence

from pipslayer.data.candles import Candle


SwingKind = Literal["high", "low"]


@dataclass(frozen=True)
class SwingPoint:
    kind: SwingKind
    symbol: str
    timeframe: str
    timestamp: object
    price: float
    candle_index: int
    confirmation_timestamp: object
    confirmation_index: int


def detect_swings(
    candles: Sequence[Candle],
    *,
    left_bars: int = 2,
    right_bars: int = 2,
) -> tuple[SwingPoint, ...]:
    """
    Identify strict local highs and lows.

    A point is only reported once all right-side confirmation
    candles are available. This is a research baseline, not
    a complete MSNR level detector.
    """
    if type(left_bars) is not int or left_bars < 1:
        raise ValueError("left_bars must be an integer >= 1")

    if type(right_bars) is not int or right_bars < 1:
        raise ValueError("right_bars must be an integer >= 1")

    rows = tuple(candles)

    if not rows:
        return ()

    symbol = rows[0].symbol
    timeframe = rows[0].timeframe

    for index, candle in enumerate(rows):
        if candle.symbol != symbol or candle.timeframe != timeframe:
            raise ValueError("All candles must have the same symbol and timeframe")

        if index and candle.timestamp <= rows[index - 1].timestamp:
            raise ValueError("Candles must be in strictly increasing timestamp order")

    results: list[SwingPoint] = []

    for index in range(left_bars, len(rows) - right_bars):
        candle = rows[index]

        left = rows[index - left_bars:index]
        right = rows[index + 1:index + right_bars + 1]
        neighbours = left + right

        if all(candle.high > other.high for other in neighbours):
            results.append(
                SwingPoint(
                    kind="high",
                    symbol=symbol,
                    timeframe=timeframe,
                    timestamp=candle.timestamp,
                    price=candle.high,
                    candle_index=index,
                    confirmation_timestamp=right[-1].timestamp,
                    confirmation_index=index + right_bars,
                )
            )

        if all(candle.low < other.low for other in neighbours):
            results.append(
                SwingPoint(
                    kind="low",
                    symbol=symbol,
                    timeframe=timeframe,
                    timestamp=candle.timestamp,
                    price=candle.low,
                    candle_index=index,
                    confirmation_timestamp=right[-1].timestamp,
                    confirmation_index=index + right_bars,
                )
            )

    return tuple(results)
