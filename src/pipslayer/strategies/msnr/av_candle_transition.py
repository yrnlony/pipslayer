"""Provisional MSNR A/V candidate: candle-colour transitions.

Research only; not an approved MSNR definition and non-executable.

Rules:
- Bullish -> bearish: A at the previous candle's close.
- Bearish -> bullish: V at the previous candle's close.
- Dojis (open == close) are excluded and reported.
- Irregular candle spacing is excluded and reported.
- Recognition occurs at the close of the second candle.
- Every valid transition is retained independently.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Sequence

from pipslayer.data.candles import TIMEFRAME_MINUTES, Candle

from .av_contract import (
    AVRecognitionResult,
    AVStructure,
    RecognitionNote,
    candle_close_time,
)

METHOD_ID = "msnr.av.candle_colour_transition.v0-provisional"


@dataclass(frozen=True)
class CandleColourTransitionRecogniser:
    """Recognise A/V candidates from consecutive candle colour changes."""

    @property
    def method_id(self) -> str:
        return METHOD_ID

    @property
    def method_parameters(self) -> tuple[tuple[str, str], ...]:
        return (
            ("transition", "bullish_bearish_or_bearish_bullish"),
            ("doji_policy", "exclude_and_report"),
            ("spacing_policy", "require_exact_timeframe_interval"),
            ("level_price", "previous_candle_close"),
        )

    def recognise(self, candles: Sequence[Candle]) -> AVRecognitionResult:
        rows = tuple(candles)

        if not rows:
            return AVRecognitionResult()

        symbol = rows[0].symbol
        timeframe = rows[0].timeframe
        expected_interval = timedelta(
            minutes=TIMEFRAME_MINUTES[timeframe]
        )

        for index, candle in enumerate(rows):
            if candle.symbol != symbol or candle.timeframe != timeframe:
                raise ValueError(
                    "All candles must have the same symbol and timeframe"
                )

            if index and candle.timestamp <= rows[index - 1].timestamp:
                raise ValueError(
                    "Candles must be in strictly increasing timestamp order"
                )

        structures: list[AVStructure] = []
        notes: list[RecognitionNote] = []

        # Report each doji once, independently of its neighbouring pairs.
        for candle in rows:
            if candle.open == candle.close:
                close_time = candle_close_time(candle)
                notes.append(
                    RecognitionNote(
                        code="doji_candle_excluded",
                        kind=None,
                        first_timestamp=candle.timestamp,
                        last_timestamp=candle.timestamp,
                        recognised_at=close_time,
                        detail=(
                            "Open equals close exactly; this candle has "
                            "no bullish or bearish colour and cannot "
                            "participate in a colour transition."
                        ),
                    )
                )

        for index in range(1, len(rows)):
            previous = rows[index - 1]
            current = rows[index]

            previous_close_time = candle_close_time(previous)
            current_close_time = candle_close_time(current)

            actual_interval = current.timestamp - previous.timestamp

            if actual_interval != expected_interval:
                notes.append(
                    RecognitionNote(
                        code="irregular_candle_spacing",
                        kind=None,
                        first_timestamp=previous.timestamp,
                        last_timestamp=current.timestamp,
                        recognised_at=current_close_time,
                        detail=(
                            f"Adjacent supplied candles are separated by "
                            f"{actual_interval}; expected "
                            f"{expected_interval}. This pair was excluded."
                        ),
                    )
                )
                continue

            previous_bullish = previous.close > previous.open
            previous_bearish = previous.close < previous.open
            current_bullish = current.close > current.open
            current_bearish = current.close < current.open

            kind = None

            if previous_bullish and current_bearish:
                kind = "A"
            elif previous_bearish and current_bullish:
                kind = "V"

            if kind is None:
                continue

            structures.append(
                AVStructure(
                    kind=kind,
                    symbol=symbol,
                    timeframe=timeframe,
                    price=previous.close,
                    anchor_timestamp=previous.timestamp,
                    formed_at=previous_close_time,
                    recognised_at=current_close_time,
                    method=METHOD_ID,
                    contributing_timestamps=(
                        previous.timestamp,
                        current.timestamp,
                    ),
                    method_parameters=self.method_parameters,
                    confirmed_at=None,
                )
            )

        return AVRecognitionResult(
            structures=tuple(structures),
            notes=tuple(notes),
        )
