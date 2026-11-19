
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace as Candle

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = PROJECT_ROOT / "pipslayer"

if not PACKAGE_ROOT.exists():
    PROJECT_ROOT = Path(__file__).resolve().parents[1]
    PACKAGE_ROOT = PROJECT_ROOT / "pipslayer"

for candidate in (PROJECT_ROOT, PACKAGE_ROOT):
    candidate_str = str(candidate)
    if candidate.exists() and candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

from pipslayer.strategies.msnr.av_contract import AVStructure  # pyright: ignore[reportMissingImports]
from pipslayer.strategies.msnr.av_gap_context import (  # pyright: ignore[reportMissingImports]
    annotate_av_gap_context,
)


BASE = datetime(2026, 5, 4, 10, 0, tzinfo=timezone.utc)


def make_candles(gap_after_index=None):
    rows = []
    timestamp = BASE

    for index in range(5):
        if index:
            timestamp += timedelta(minutes=15)

            if gap_after_index == index - 1:
                timestamp += timedelta(minutes=60)

        rows.append(
            Candle(
                symbol="XAUUSD",
                timeframe="M15",
                timestamp=timestamp,
                open=100.0,
                high=102.0,
                low=98.0,
                close=100.0,
                volume=10.0,
                source="test",
            )
        )

    return tuple(rows)


def make_structure(candles):
    anchor = candles[2]

    return AVStructure(
        kind="A",
        symbol="XAUUSD",
        timeframe="M15",
        price=anchor.close,
        anchor_timestamp=anchor.timestamp,
        formed_at=anchor.timestamp + timedelta(minutes=15),
        recognised_at=candles[3].timestamp + timedelta(minutes=15),
        method="test-method",
        contributing_timestamps=(anchor.timestamp,),
    )


def test_continuous_neighbourhood_has_no_gap_flags():
    candles = make_candles()
    result = annotate_av_gap_context(
        candles, (make_structure(candles),)
    )

    context = result[0]

    assert context.continuous_neighbours is True
    assert context.gap_between_neighbours is False
    assert context.gap_before_candidate is False
    assert context.gap_after_candidate is False
    assert context.observations == ()


def test_gap_between_recognition_neighbours_is_flagged():
    candles = make_candles(gap_after_index=1)
    result = annotate_av_gap_context(
        candles, (make_structure(candles),)
    )

    context = result[0]

    assert context.gap_between_neighbours is True
    assert context.continuous_neighbours is False
    assert context.observations[0].location == "between_neighbours"
    assert context.observations[0].missing_bars_if_exact_multiple == 4


def test_gap_before_candidate_is_flagged_separately():
    candles = make_candles(gap_after_index=0)
    result = annotate_av_gap_context(
        candles, (make_structure(candles),)
    )

    context = result[0]

    assert context.gap_before_candidate is True
    assert context.gap_between_neighbours is False
    assert context.gap_after_candidate is False


def test_gap_after_candidate_is_flagged_separately():
    candles = make_candles(gap_after_index=3)
    result = annotate_av_gap_context(
        candles, (make_structure(candles),)
    )

    context = result[0]

    assert context.gap_after_candidate is True
    assert context.gap_between_neighbours is False
    assert context.gap_before_candidate is False


def test_empty_inputs_return_empty_result():
    assert annotate_av_gap_context((), ()) == ()
