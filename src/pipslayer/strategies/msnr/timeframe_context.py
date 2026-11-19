
"""Timeframe-neutral contracts and analysis for MSNR opportunity context research."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import isfinite
from typing import Any, Literal, Mapping, Sequence

from pipslayer.data.candles import (
    Candle,
    SUPPORTED_TIMEFRAMES,
    TIMEFRAME_MINUTES,
)

from .av_close_line import (
    CloseLineTurningPointRecogniser,
    EqualClosePolicy,
)
from .av_contract import AVStructure, structures_known_at


EvidenceStatus = Literal["found", "no_evidence", "insufficient_data"]


def _utc_datetime(value: Any, field_name: str) -> datetime:
    """Parse a datetime value and require an explicit UTC timezone."""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(
                f"{field_name} must be a valid ISO timestamp"
            ) from exc

    if not isinstance(value, datetime):
        raise ValueError(
            f"{field_name} must be a datetime or ISO timestamp"
        )

    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(
            f"{field_name} must be timezone-aware UTC"
        )

    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class TimeframeContextRequest:
    """Validated input for analysing one H4 opportunity on one timeframe."""

    opportunity_snapshot: Mapping[str, Any]
    opportunity_id: str
    source_structure_ids: tuple[str, ...]
    symbol: str
    opportunity_kind: str
    reference_price: float
    snapshot_timestamp: datetime
    timeframe: str
    candles: tuple[Candle, ...]


@dataclass(frozen=True)
class EvidenceSection:
    """Evidence returned for one independent context investigation."""

    status: EvidenceStatus
    records: tuple[Mapping[str, Any], ...] = ()
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class TimeframeContextResult:
    """Result contract for a timeframe-specific context investigation."""

    opportunity_id: str
    symbol: str
    timeframe: str
    snapshot_timestamp: datetime
    exact_level_context: EvidenceSection
    drawdown_context: EvidenceSection
    data_quality: Mapping[str, Any]


def build_timeframe_context_request(
    opportunity_snapshot: Mapping[str, Any],
    symbol: str,
    timeframe: str,
    candles: Sequence[Candle],
) -> TimeframeContextRequest:
    """Validate and package an H4 opportunity with selected-TF candles."""
    if not isinstance(opportunity_snapshot, Mapping):
        raise ValueError("opportunity_snapshot must be a mapping")

    if not isinstance(symbol, str) or not symbol.strip():
        raise ValueError("symbol must be a non-empty string")

    if timeframe not in SUPPORTED_TIMEFRAMES:
        raise ValueError(
            f"Unsupported timeframe {timeframe!r}; "
            f"supported values are {sorted(SUPPORTED_TIMEFRAMES)}"
        )

    level = opportunity_snapshot.get("level")
    if not isinstance(level, Mapping):
        raise ValueError("opportunity_snapshot must contain a level mapping")

    opportunity_id = level.get("level_id")
    if not isinstance(opportunity_id, str) or not opportunity_id.strip():
        raise ValueError("level.level_id must be a non-empty string")

    opportunity_kind = level.get("kind")
    if not isinstance(opportunity_kind, str) or not opportunity_kind.strip():
        raise ValueError("level.kind must be a non-empty string")

    try:
        reference_price = float(level["reference_price"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("level.reference_price must be numeric") from exc

    if not isfinite(reference_price):
        raise ValueError("level.reference_price must be finite")

    source_ids = level.get("source_structure_ids")
    if not isinstance(source_ids, (list, tuple)) or not source_ids:
        raise ValueError(
            "level.source_structure_ids must be a non-empty list or tuple"
        )

    if any(
        not isinstance(item, str) or not item.strip()
        for item in source_ids
    ):
        raise ValueError(
            "source_structure_ids must contain non-empty strings"
        )

    formed_at = _utc_datetime(level.get("formed_at"), "level.formed_at")
    recognised_at = _utc_datetime(
        level.get("recognised_at"), "level.recognised_at"
    )
    snapshot_timestamp = _utc_datetime(
        opportunity_snapshot.get("snapshot_timestamp"),
        "snapshot_timestamp",
    )

    if formed_at > recognised_at:
        raise ValueError("level.formed_at cannot be after level.recognised_at")

    if recognised_at > snapshot_timestamp:
        raise ValueError(
            "Opportunity was not recognised by its snapshot timestamp"
        )

    candle_rows = tuple(candles)
    previous_timestamp = None
    interval = timedelta(minutes=TIMEFRAME_MINUTES[timeframe])

    for candle in candle_rows:
        if not isinstance(candle, Candle):
            raise ValueError("candles must contain only Candle objects")

        if candle.symbol != symbol:
            raise ValueError(
                f"Candle symbol {candle.symbol!r} does not match {symbol!r}"
            )

        if candle.timeframe != timeframe:
            raise ValueError(
                f"Candle timeframe {candle.timeframe!r} "
                f"does not match requested {timeframe!r}"
            )

        timestamp = _utc_datetime(candle.timestamp, "candle.timestamp")

        if previous_timestamp is not None and timestamp <= previous_timestamp:
            raise ValueError(
                "Candles must be strictly ordered with no duplicate timestamps"
            )

        if timestamp + interval > snapshot_timestamp:
            raise ValueError(
                "Candle is not fully closed by the opportunity snapshot timestamp"
            )

        previous_timestamp = timestamp

    return TimeframeContextRequest(
        opportunity_snapshot=opportunity_snapshot,
        opportunity_id=opportunity_id,
        source_structure_ids=tuple(source_ids),
        symbol=symbol,
        opportunity_kind=opportunity_kind,
        reference_price=reference_price,
        snapshot_timestamp=snapshot_timestamp,
        timeframe=timeframe,
        candles=candle_rows,
    )


def _recognise_local_structures(
    request: TimeframeContextRequest,
) -> tuple[tuple[AVStructure, ...], tuple[str, ...]]:
    """Recognise local A/V structures and retain only point-in-time evidence."""
    if len(request.candles) < 3:
        return (), ("At least three candles are required for A/V recognition.",)

    recogniser = CloseLineTurningPointRecogniser(
        equal_close_policy=EqualClosePolicy.EXCLUDE_AND_REPORT,
    )
    recognition = recogniser.recognise(request.candles)

    known = structures_known_at(
        recognition.structures,
        request.snapshot_timestamp,
    )

    # The H4 source structure is not a newly discovered local structure.
    local = tuple(
        structure
        for structure in known
        if structure.structure_id not in request.source_structure_ids
    )

    notes = tuple(
        f"{note.code}: {note.detail}"
        for note in recognition.notes
        if note.recognised_at <= request.snapshot_timestamp
    )

    return local, notes


def _build_exact_level_context(
    request: TimeframeContextRequest,
) -> EvidenceSection:
    structures, recognition_notes = _recognise_local_structures(request)

    if len(request.candles) < 3:
        return EvidenceSection(
            status="insufficient_data",
            notes=recognition_notes,
        )

    records = tuple(
        {
            "structure_id": structure.structure_id,
            "kind": structure.kind,
            "price": structure.price,
            "reference_price": request.reference_price,
            "signed_distance_from_reference": (
                structure.price - request.reference_price
            ),
            "absolute_distance_from_reference": abs(
                structure.price - request.reference_price
            ),
            "anchor_timestamp": structure.anchor_timestamp.isoformat(),
            "formed_at": structure.formed_at.isoformat(),
            "recognised_at": structure.recognised_at.isoformat(),
            "method": structure.method,
        }
        for structure in structures
    )

    return EvidenceSection(
        status="found" if records else "no_evidence",
        records=records,
        notes=(
            "Signed distance is local structure price minus H4 reference price.",
            "No proximity threshold or significance filter is applied.",
            "Recognition uses the provisional close-line A/V method.",
        ) + recognition_notes,
    )


def _build_drawdown_context(
    request: TimeframeContextRequest,
) -> EvidenceSection:
    """Measure price excursions from the H4 reference, not from a trade entry."""
    level = request.opportunity_snapshot["level"]
    recognised_at = _utc_datetime(
        level["recognised_at"],
        "level.recognised_at",
    )

    interval = timedelta(minutes=TIMEFRAME_MINUTES[request.timeframe])

    eligible = tuple(
        candle
        for candle in request.candles
        if candle.timestamp >= recognised_at
        and candle.timestamp + interval <= request.snapshot_timestamp
    )

    if not eligible:
        return EvidenceSection(
            status="insufficient_data",
            notes=(
                "No fully closed timeframe candles are available "
                "from opportunity recognition onward.",
            ),
        )

    highest = max(eligible, key=lambda candle: candle.high)
    lowest = min(eligible, key=lambda candle: candle.low)

    if request.opportunity_kind == "V":
        favourable = max(0.0, highest.high - request.reference_price)
        adverse = max(0.0, request.reference_price - lowest.low)
        favourable_candle = highest
        adverse_candle = lowest

    elif request.opportunity_kind == "A":
        favourable = max(0.0, request.reference_price - lowest.low)
        adverse = max(0.0, highest.high - request.reference_price)
        favourable_candle = lowest
        adverse_candle = highest

    else:
        return EvidenceSection(
            status="insufficient_data",
            notes=("Expected opportunity kind A or V.",),
        )

    return EvidenceSection(
        status="found",
        records=(
            {
                "measurement_type": "price_excursion_from_reference",
                "reference_price": request.reference_price,
                "opportunity_kind": request.opportunity_kind,
                "measurement_start": recognised_at.isoformat(),
                "measurement_end": request.snapshot_timestamp.isoformat(),
                "candle_count": len(eligible),
                "maximum_favourable_excursion": favourable,
                "maximum_adverse_excursion": adverse,
                "favourable_extreme_candle": (
                    favourable_candle.timestamp.isoformat()
                ),
                "adverse_extreme_candle": (
                    adverse_candle.timestamp.isoformat()
                ),
            },
        ),
        notes=(
            "These are price excursions from the H4 reference, not trade MAE/MFE.",
            "No entry price or execution assumption is used.",
        ),
    )


def _build_data_quality(
    request: TimeframeContextRequest,
) -> Mapping[str, Any]:
    """Report observed candle coverage and timestamp gaps."""
    expected_seconds = TIMEFRAME_MINUTES[request.timeframe] * 60
    gaps = []

    for previous, following in zip(
        request.candles,
        request.candles[1:],
    ):
        elapsed = (
            following.timestamp - previous.timestamp
        ).total_seconds()

        if elapsed > expected_seconds:
            multiple = elapsed / expected_seconds

            gaps.append(
                {
                    "previous_candle": previous.timestamp.isoformat(),
                    "following_candle": following.timestamp.isoformat(),
                    "elapsed_seconds": elapsed,
                    "expected_seconds": expected_seconds,
                    "missing_bars_if_exact_multiple": (
                        int(multiple) - 1
                        if multiple.is_integer()
                        else None
                    ),
                }
            )

    return {
        "candle_count": len(request.candles),
        "first_candle": (
            request.candles[0].timestamp.isoformat()
            if request.candles else None
        ),
        "last_candle": (
            request.candles[-1].timestamp.isoformat()
            if request.candles else None
        ),
        "expected_interval_seconds": expected_seconds,
        "gap_count": len(gaps),
        "gaps": tuple(gaps),
        "recognition_minimum_candles": 3,
        "sufficient_candles_for_recognition": len(request.candles) >= 3,
    }


def analyse_timeframe_context(
    request: TimeframeContextRequest,
) -> TimeframeContextResult:
    """Analyse one opportunity on one timeframe without qualifying a trade."""
    if not isinstance(request, TimeframeContextRequest):
        raise ValueError("request must be a TimeframeContextRequest")

    return TimeframeContextResult(
        opportunity_id=request.opportunity_id,
        symbol=request.symbol,
        timeframe=request.timeframe,
        snapshot_timestamp=request.snapshot_timestamp,
        exact_level_context=_build_exact_level_context(request),
        drawdown_context=_build_drawdown_context(request),
        data_quality=_build_data_quality(request),
    )
