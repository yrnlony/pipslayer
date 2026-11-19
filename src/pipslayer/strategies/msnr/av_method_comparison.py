"""Compare provisional MSNR A/V recognition methods without trading decisions."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Sequence

from pipslayer.data.candles import TIMEFRAME_MINUTES, Candle

from .av_contract import (
    AVRecognitionResult,
    AVRecogniser,
    AVStructure,
)


@dataclass(frozen=True, order=True)
class AVMatchKey:
    """Exact identity used to compare detections across methods."""

    kind: str
    anchor_timestamp: datetime
    price: float


@dataclass(frozen=True)
class IrregularInterval:
    previous_timestamp: datetime
    current_timestamp: datetime
    actual_interval: timedelta
    expected_interval: timedelta


@dataclass(frozen=True)
class DatasetSpacingReport:
    interval_count: int
    regular_intervals: int
    irregular_intervals: tuple[IrregularInterval, ...]


@dataclass(frozen=True)
class DetectionSpacingReport:
    structure_count: int
    left_irregular: int
    right_irregular: int
    either_irregular: int
    both_regular: int
    missing_left_context: int
    missing_right_context: int


@dataclass(frozen=True)
class AVMethodRun:
    method_id: str
    recognition: AVRecognitionResult
    spacing: DetectionSpacingReport


@dataclass(frozen=True)
class SharedDetection:
    key: AVMatchKey
    structures: tuple[AVStructure, ...]
    method_ids: tuple[str, ...]


@dataclass(frozen=True)
class MethodOnlyDetection:
    method_id: str
    structure: AVStructure


@dataclass(frozen=True)
class AVMethodComparisonResult:
    dataset_id: str
    symbol: str | None
    timeframe: str | None
    candle_count: int
    dataset_spacing: DatasetSpacingReport
    method_runs: tuple[AVMethodRun, ...]
    shared_detections: tuple[SharedDetection, ...]
    method_only_detections: tuple[MethodOnlyDetection, ...]


def _match_key(structure: AVStructure) -> AVMatchKey:
    return AVMatchKey(
        kind=structure.kind,
        anchor_timestamp=structure.anchor_timestamp,
        price=structure.price,
    )


def _dataset_spacing(
    candles: tuple[Candle, ...],
) -> DatasetSpacingReport:
    if not candles:
        return DatasetSpacingReport(0, 0, ())

    expected = timedelta(
        minutes=TIMEFRAME_MINUTES[candles[0].timeframe]
    )
    irregular: list[IrregularInterval] = []
    regular = 0

    for previous, current in zip(candles, candles[1:]):
        actual = current.timestamp - previous.timestamp

        if actual == expected:
            regular += 1
        else:
            irregular.append(
                IrregularInterval(
                    previous_timestamp=previous.timestamp,
                    current_timestamp=current.timestamp,
                    actual_interval=actual,
                    expected_interval=expected,
                )
            )

    return DatasetSpacingReport(
        interval_count=max(0, len(candles) - 1),
        regular_intervals=regular,
        irregular_intervals=tuple(irregular),
    )


def _detection_spacing(
    candles: tuple[Candle, ...],
    structures: tuple[AVStructure, ...],
) -> DetectionSpacingReport:
    left_irregular = 0
    right_irregular = 0
    either_irregular = 0
    both_regular = 0
    missing_left = 0
    missing_right = 0

    if not candles or not structures:
        return DetectionSpacingReport(
            len(structures), 0, 0, 0, 0, 0, 0
        )

    expected = timedelta(
        minutes=TIMEFRAME_MINUTES[candles[0].timeframe]
    )
    index_by_timestamp = {
        candle.timestamp: index
        for index, candle in enumerate(candles)
    }

    for structure in structures:
        anchor_index = index_by_timestamp[structure.anchor_timestamp]

        has_left = anchor_index > 0
        has_right = anchor_index + 1 < len(candles)

        if not has_left:
            missing_left += 1
        if not has_right:
            missing_right += 1

        left_bad = (
            has_left
            and candles[anchor_index].timestamp
            - candles[anchor_index - 1].timestamp != expected
        )
        right_bad = (
            has_right
            and candles[anchor_index + 1].timestamp
            - candles[anchor_index].timestamp != expected
        )

        left_irregular += int(left_bad)
        right_irregular += int(right_bad)
        either_irregular += int(left_bad or right_bad)

        if has_left and has_right and not left_bad and not right_bad:
            both_regular += 1

    return DetectionSpacingReport(
        structure_count=len(structures),
        left_irregular=left_irregular,
        right_irregular=right_irregular,
        either_irregular=either_irregular,
        both_regular=both_regular,
        missing_left_context=missing_left,
        missing_right_context=missing_right,
    )


def compare_av_methods(
    *,
    dataset_id: str,
    candles: Sequence[Candle],
    recognisers: Sequence[AVRecogniser],
) -> AVMethodComparisonResult:
    """Run independent A/V recognisers and compare their exact detections.

    This function does not modify candles, alter recognition results,
    qualify trading opportunities, or rank recognition methods.
    """
    if not isinstance(dataset_id, str) or not dataset_id.strip():
        raise ValueError("dataset_id must not be blank")

    rows = tuple(candles)
    methods = tuple(recognisers)

    symbol = rows[0].symbol if rows else None
    timeframe = rows[0].timeframe if rows else None

    for index, candle in enumerate(rows):
        if candle.symbol != symbol or candle.timeframe != timeframe:
            raise ValueError(
                "All candles must have the same symbol and timeframe"
            )

        if index and candle.timestamp <= rows[index - 1].timestamp:
            raise ValueError(
                "Candles must be in strictly increasing timestamp order"
            )

    method_ids: set[str] = set()
    for recogniser in methods:
        method_id = recogniser.method_id

        if not isinstance(method_id, str) or not method_id.strip():
            raise ValueError("Every recogniser must have a non-blank method_id")

        if method_id in method_ids:
            raise ValueError(
                f"Duplicate method_id in comparison: {method_id}"
            )

        method_ids.add(method_id)

    runs: list[AVMethodRun] = []
    detections: dict[AVMatchKey, list[tuple[str, AVStructure]]] = {}
    method_only: list[MethodOnlyDetection] = []

    for recogniser in methods:
        method_id = recogniser.method_id
        recognition = recogniser.recognise(rows)

        if not isinstance(recognition, AVRecognitionResult):
            raise TypeError(
                f"{method_id} must return AVRecognitionResult"
            )

        seen_keys: set[AVMatchKey] = set()

        for structure in recognition.structures:
            if structure.method != method_id:
                raise ValueError(
                    f"{method_id} returned a structure with a different method ID"
                )

            if structure.symbol != symbol or structure.timeframe != timeframe:
                raise ValueError(
                    f"{method_id} returned a structure outside the supplied dataset"
                )

            if structure.confirmed_at is not None:
                raise ValueError(
                    f"{method_id} returned a confirmed structure; "
                    "this comparison is research-only"
                )

            if structure.anchor_timestamp not in {
                candle.timestamp for candle in rows
            }:
                raise ValueError(
                    f"{method_id} returned an anchor outside the supplied dataset"
                )

            key = _match_key(structure)

            if key in seen_keys:
                raise ValueError(
                    f"{method_id} returned duplicate comparison key: {key}"
                )

            seen_keys.add(key)
            detections.setdefault(key, []).append(
                (method_id, structure)
            )

        runs.append(
            AVMethodRun(
                method_id=method_id,
                recognition=recognition,
                spacing=_detection_spacing(
                    rows, recognition.structures
                ),
            )
        )

    shared: list[SharedDetection] = []

    for key, entries in detections.items():
        if len(entries) > 1:
            shared.append(
                SharedDetection(
                    key=key,
                    structures=tuple(item[1] for item in entries),
                    method_ids=tuple(item[0] for item in entries),
                )
            )
        else:
            method_id, structure = entries[0]
            method_only.append(
                MethodOnlyDetection(method_id, structure)
            )

    shared.sort(
        key=lambda item: (
            item.key.anchor_timestamp,
            item.key.kind,
            item.key.price,
        )
    )
    method_only.sort(
        key=lambda item: (
            item.structure.anchor_timestamp,
            item.method_id,
            item.structure.kind,
            item.structure.price,
        )
    )

    return AVMethodComparisonResult(
        dataset_id=dataset_id,
        symbol=symbol,
        timeframe=timeframe,
        candle_count=len(rows),
        dataset_spacing=_dataset_spacing(rows),
        method_runs=tuple(runs),
        shared_detections=tuple(shared),
        method_only_detections=tuple(method_only),
    )
