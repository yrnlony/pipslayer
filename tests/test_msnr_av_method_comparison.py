import sys
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest

from pipslayer.data.candles import TIMEFRAME_MINUTES, Candle
from pipslayer.strategies.msnr.av_close_line import (
    CloseLineTurningPointRecogniser,
    EqualClosePolicy,
)
from pipslayer.strategies.msnr.av_candle_transition import (
    CandleColourTransitionRecogniser,
)
from pipslayer.strategies.msnr.av_method_comparison import (
    compare_av_methods,
)

START = datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc)


def make_candles(closes, *, timeframe="M15", opens=None, indexes=None):
    interval = TIMEFRAME_MINUTES[timeframe]
    opens = opens if opens is not None else closes
    indexes = indexes if indexes is not None else range(len(closes))

    return tuple(
        Candle(
            symbol="XAUUSD",
            timeframe=timeframe,
            timestamp=START + timedelta(minutes=interval * index),
            open=open_price,
            high=max(open_price, close) + 1,
            low=min(open_price, close) - 1,
            close=close,
            volume=100,
            source="test",
        )
        for open_price, close, index in zip(opens, closes, indexes)
    )


def methods():
    return (
        CloseLineTurningPointRecogniser(
            EqualClosePolicy.EXCLUDE_AND_REPORT
        ),
        CandleColourTransitionRecogniser(),
    )


def test_exact_matching_between_methods():
    candles = make_candles([10, 12, 11], opens=[9, 11, 12])
    result = compare_av_methods(
        dataset_id="test-h2", candles=candles, recognisers=methods()
    )

    assert result.dataset_id == "test-h2"
    assert result.symbol == "XAUUSD"
    assert result.timeframe == "M15"
    assert result.candle_count == 3
    assert len(result.shared_detections) == 1
    assert result.shared_detections[0].key.kind == "A"
    assert result.shared_detections[0].key.price == 12
    assert len(result.shared_detections[0].structures) == 2
    assert result.method_only_detections == ()


def test_irregular_spacing_preserves_method_difference():
    candles = make_candles(
        [10, 12, 11],
        opens=[9, 11, 12],
        indexes=[0, 1, 3],
    )
    result = compare_av_methods(
        dataset_id="gap-test", candles=candles, recognisers=methods()
    )

    close_line, colour_transition = result.method_runs
    assert len(close_line.recognition.structures) == 1
    assert close_line.recognition.structures[0].kind == "A"
    assert colour_transition.recognition.structures == ()
    assert any(
        note.code == "irregular_candle_spacing"
        for note in colour_transition.recognition.notes
    )
    assert result.dataset_spacing.interval_count == 2
    assert result.dataset_spacing.regular_intervals == 1
    assert len(result.dataset_spacing.irregular_intervals) == 1
    assert close_line.spacing.right_irregular == 1
    assert close_line.spacing.either_irregular == 1


def test_h2_dataset_is_supported():
    candles = make_candles(
        [10, 12, 11], timeframe="H2", opens=[9, 11, 12]
    )
    result = compare_av_methods(
        dataset_id="test-h2", candles=candles, recognisers=methods()
    )
    assert result.timeframe == "H2"
    assert len(result.shared_detections) == 1


def test_empty_dataset_returns_empty_comparison():
    result = compare_av_methods(
        dataset_id="empty-test", candles=(), recognisers=methods()
    )
    assert result.symbol is None
    assert result.timeframe is None
    assert result.candle_count == 0
    assert result.shared_detections == ()
    assert result.method_only_detections == ()
    assert len(result.method_runs) == 2


def test_mixed_symbol_dataset_is_rejected():
    candles = make_candles([10, 12, 11])
    candles = (
        candles[0],
        replace(candles[1], symbol="EURUSD"),
        candles[2],
    )
    with pytest.raises(ValueError, match="same symbol and timeframe"):
        compare_av_methods(
            dataset_id="mixed-test", candles=candles, recognisers=methods()
        )


def test_duplicate_method_ids_are_rejected():
    recogniser = CloseLineTurningPointRecogniser(
        EqualClosePolicy.EXCLUDE_AND_REPORT
    )
    with pytest.raises(ValueError, match="Duplicate method_id"):
        compare_av_methods(
            dataset_id="duplicate-test",
            candles=make_candles([10, 12, 11]),
            recognisers=(recogniser, recogniser),
        )


def test_blank_dataset_id_is_rejected():
    with pytest.raises(ValueError, match="dataset_id"):
        compare_av_methods(
            dataset_id=" ", candles=(), recognisers=methods()
        )
