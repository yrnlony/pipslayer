"""Provisional A/V recognition candidate: close-line turning points.

Blueprint v0.3 section 3.4, method 1.

This is a provisional research method, not an approved MSNR definition,
and is non-executable.

A candidate:
- A: close strictly higher than both immediate neighbours.
- V: close strictly lower than both immediate neighbours.

Wicks and opens are never consulted.

Equal-close plateaus are handled by one of three configurable policies:
- EXCLUDE_AND_REPORT
- PLATEAU_FIRST_CANDLE
- PLATEAU_LAST_CANDLE

The full plateau is preserved in contributing_timestamps.

Recognition timing:
- formed_at: close of the anchor candle.
- recognised_at: close of the right-hand neighbouring candle.
- confirmed_at: None.

Runs without sufficient boundary context are reported as notes.
No missing-bar spacing check is performed. Adjacent supplied candles
are treated as neighbours, even across a timestamp gap.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Sequence

from pipslayer.data.candles import Candle

from .av_contract import (
    AVKind,
    AVRecognitionResult,
    AVStructure,
    RecognitionNote,
    candle_close_time,
)

METHOD_ID = "msnr.av.close_line_turning_point.v0-provisional"


class EqualClosePolicy(str, Enum):
    EXCLUDE_AND_REPORT = "exclude_and_report"
    PLATEAU_FIRST_CANDLE = "plateau_first_candle"
    PLATEAU_LAST_CANDLE = "plateau_last_candle"


@dataclass(frozen=True)
class CloseLineTurningPointRecogniser:
    """Close-line turning-point recogniser."""

    equal_close_policy: EqualClosePolicy

    def __post_init__(self) -> None:
        if not isinstance(self.equal_close_policy, EqualClosePolicy):
            raise ValueError(
                "equal_close_policy must be an EqualClosePolicy member"
            )

    @property
    def method_id(self) -> str:
        return METHOD_ID

    @property
    def method_parameters(self) -> tuple[tuple[str, str], ...]:
        return (
            ("neighbours", "immediate"),
            ("equal_close_policy", self.equal_close_policy.value),
        )

    def recognise(self, candles: Sequence[Candle]) -> AVRecognitionResult:
        rows = tuple(candles)

        if not rows:
            return AVRecognitionResult()

        symbol = rows[0].symbol
        timeframe = rows[0].timeframe

        for index, candle in enumerate(rows):
            if candle.symbol != symbol or candle.timeframe != timeframe:
                raise ValueError(
                    "All candles must have the same symbol and timeframe"
                )

            if index and candle.timestamp <= rows[index - 1].timestamp:
                raise ValueError(
                    "Candles must be in strictly increasing timestamp order"
                )

        closes = [candle.close for candle in rows]
        structures: list[AVStructure] = []
        notes: list[RecognitionNote] = []

        first = 0

        while first < len(rows):
            last = first

            while (
                last + 1 < len(rows)
                and closes[last + 1] == closes[first]
            ):
                last += 1

            # The first run has no left neighbour.
            if first == 0:
                notes.append(
                    RecognitionNote(
                        code="insufficient_left_context",
                        kind=None,
                        first_timestamp=rows[first].timestamp,
                        last_timestamp=rows[last].timestamp,
                        recognised_at=candle_close_time(rows[last]),
                        detail=(
                            "The first close run has no supplied left "
                            "neighbour and cannot yet be classified."
                        ),
                    )
                )

            # The final run has no right neighbour.
            elif last == len(rows) - 1:
                notes.append(
                    RecognitionNote(
                        code="insufficient_right_context",
                        kind=None,
                        first_timestamp=rows[first].timestamp,
                        last_timestamp=rows[last].timestamp,
                        recognised_at=candle_close_time(rows[last]),
                        detail=(
                            "The final close run has no supplied right "
                            "neighbour and cannot yet be classified."
                        ),
                    )
                )

            else:
                value = closes[first]
                left = closes[first - 1]
                right = closes[last + 1]

                kind: AVKind | None = None

                if left < value and right < value:
                    kind = "A"
                elif left > value and right > value:
                    kind = "V"

                if kind is not None:
                    self._handle_run(
                        rows,
                        first,
                        last,
                        kind,
                        structures,
                        notes,
                    )

            first = last + 1

        return AVRecognitionResult(
            tuple(structures),
            tuple(notes),
        )

    def _handle_run(
        self,
        rows: tuple[Candle, ...],
        first: int,
        last: int,
        kind: AVKind,
        structures: list[AVStructure],
        notes: list[RecognitionNote],
    ) -> None:
        recognised_at = candle_close_time(rows[last + 1])
        policy = self.equal_close_policy

        if first == last:
            anchor = first

        elif policy is EqualClosePolicy.PLATEAU_FIRST_CANDLE:
            anchor = first

        elif policy is EqualClosePolicy.PLATEAU_LAST_CANDLE:
            anchor = last

        else:
            notes.append(
                RecognitionNote(
                    code="equal_close_run_excluded",
                    kind=kind,
                    first_timestamp=rows[first].timestamp,
                    last_timestamp=rows[last].timestamp,
                    recognised_at=recognised_at,
                    detail=(
                        f"{last - first + 1} consecutive exactly-equal "
                        f"closes at {rows[first].close!r} sit beyond both "
                        f"neighbours; excluded under policy "
                        f"{policy.value}. Not evidence of invalidity."
                    ),
                )
            )
            return

        structures.append(
            AVStructure(
                kind=kind,
                symbol=rows[anchor].symbol,
                timeframe=rows[anchor].timeframe,
                price=rows[anchor].close,
                anchor_timestamp=rows[anchor].timestamp,
                formed_at=candle_close_time(rows[anchor]),
                recognised_at=recognised_at,
                method=METHOD_ID,
                contributing_timestamps=tuple(
                    row.timestamp for row in rows[first:last + 1]
                ),
                method_parameters=self.method_parameters,
            )
        )