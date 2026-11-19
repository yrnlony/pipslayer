
"""Gap-context annotations for already-recognised MSNR A/V structures.

This is a separate research layer. It does not change A/V recognition,
remove structures, or repair candle data.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Sequence

from pipslayer.data.candles import Candle, TIMEFRAME_MINUTES

from .av_contract import AVStructure


@dataclass(frozen=True)
class GapObservation:
    location: str
    previous_timestamp: datetime
    next_timestamp: datetime
    elapsed_seconds: float
    expected_seconds: int
    missing_bars_if_exact_multiple: int | None


@dataclass(frozen=True)
class AVGapContext:
    structure_id: str
    anchor_timestamp: datetime
    continuous_neighbours: bool
    gap_between_neighbours: bool
    gap_before_candidate: bool
    gap_after_candidate: bool
    observations: tuple[GapObservation, ...]

    @property
    def has_gap_context(self) -> bool:
        return bool(self.observations)


def _gap(
    previous: Candle,
    following: Candle,
    expected_seconds: int,
    location: str,
) -> GapObservation | None:
    elapsed = (
        following.timestamp - previous.timestamp
    ).total_seconds()

    # Only longer-than-expected intervals are classified as gaps.
    if elapsed <= expected_seconds:
        return None

    multiple = elapsed / expected_seconds
    exact = multiple.is_integer()

    return GapObservation(
        location=location,
        previous_timestamp=previous.timestamp,
        next_timestamp=following.timestamp,
        elapsed_seconds=elapsed,
        expected_seconds=expected_seconds,
        missing_bars_if_exact_multiple=(
            int(multiple) - 1 if exact else None
        ),
    )


def annotate_av_gap_context(
    candles: Sequence[Candle],
    structures: Sequence[AVStructure],
) -> tuple[AVGapContext, ...]:
    """Annotate each A/V structure with nearby candle-sequence gaps.

    Definitions:
    - before: gap immediately before the left comparison candle;
    - between: gap anywhere across the left comparison candle, plateau,
      and right comparison candle;
    - after: gap immediately after the right comparison candle.

    A missing boundary candle is not itself treated as a gap.
    """
    rows = tuple(candles)

    if not rows or not structures:
        return ()

    symbol = rows[0].symbol
    timeframe = rows[0].timeframe

    for index, candle in enumerate(rows):
        if candle.symbol != symbol or candle.timeframe != timeframe:
            raise ValueError("All candles must share symbol and timeframe")
        if index and candle.timestamp <= rows[index - 1].timestamp:
            raise ValueError("Candles must be in strictly increasing order")

    expected_seconds = TIMEFRAME_MINUTES[timeframe] * 60
    index_by_timestamp = {
        candle.timestamp: index for index, candle in enumerate(rows)
    }

    results: list[AVGapContext] = []

    for structure in structures:
        if structure.symbol != symbol or structure.timeframe != timeframe:
            raise ValueError("Structure symbol/timeframe does not match candles")

        if structure.anchor_timestamp not in index_by_timestamp:
            raise ValueError("Structure anchor is absent from supplied candles")

        contributing = [
            index_by_timestamp[stamp]
            for stamp in structure.contributing_timestamps
            if stamp in index_by_timestamp
        ]

        if len(contributing) != len(structure.contributing_timestamps):
            raise ValueError("A contributing candle is absent from supplied candles")

        first = min(contributing)
        last = max(contributing)

        if tuple(sorted(contributing)) != tuple(range(first, last + 1)):
            raise ValueError("Structure contributing candles are not contiguous")

        if first == 0 or last == len(rows) - 1:
            raise ValueError(
                "A/V structure lacks the left or right comparison candle"
            )

        observations: list[GapObservation] = []

        # Gap before the left comparison candle.
        if first >= 2:
            observation = _gap(
                rows[first - 2], rows[first - 1],
                expected_seconds, "before_candidate",
            )
            if observation:
                observations.append(observation)

        # Gaps across the actual recognition neighbourhood.
        for index in range(first - 1, last + 1):
            observation = _gap(
                rows[index], rows[index + 1],
                expected_seconds, "between_neighbours",
            )
            if observation:
                observations.append(observation)

        # Gap immediately after the right comparison candle.
        right = last + 1
        if right + 1 < len(rows):
            observation = _gap(
                rows[right], rows[right + 1],
                expected_seconds, "after_candidate",
            )
            if observation:
                observations.append(observation)

        before = any(x.location == "before_candidate" for x in observations)
        between = any(x.location == "between_neighbours" for x in observations)
        after = any(x.location == "after_candidate" for x in observations)

        results.append(
            AVGapContext(
                structure_id=structure.structure_id,
                anchor_timestamp=structure.anchor_timestamp,
                continuous_neighbours=not between,
                gap_between_neighbours=between,
                gap_before_candidate=before,
                gap_after_candidate=after,
                observations=tuple(observations),
            )
        )

    return tuple(results)
