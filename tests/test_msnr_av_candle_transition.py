from datetime import datetime, timedelta, timezone

import pytest

from pipslayer.data.candles import Candle
from pipslayer.strategies.msnr.av_candle_transition import (
    CandleColourTransitionRecogniser,
    METHOD_ID,
)


START = datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc)


def candle(index, open_price, close_price, *, timeframe="M15"):
    interval = {"M15": 15, "H2": 120}[timeframe]
    return Candle(
        symbol="XAUUSD",
        timeframe=timeframe,
        timestamp=START + timedelta(minutes=interval * index),
        open=open_price,
        high=max(open_price, close_price) + 1,
        low=min(open_price, close_price) - 1,
        close=close_price,
        volume=100,
        source="test",
    )


def recogniser():
    return CandleColourTransitionRecogniser()


def test_bullish_to_bearish_recognises_a_at_previous_close():
    result = recogniser().recognise((
        candle(0, 10, 12),
        candle(1, 12, 11),
    ))

    assert len(result.structures) == 1
    structure = result.structures[0]

    assert structure.kind == "A"
    assert structure.price == 12
    assert structure.anchor_timestamp == START
    assert structure.formed_at == START + timedelta(minutes=15)
    assert structure.recognised_at == START + timedelta(minutes=30)
    assert structure.method == METHOD_ID
    assert structure.confirmed_at is None
    assert structure.contributing_timestamps == (
        START,
        START + timedelta(minutes=15),
    )


def test_bearish_to_bullish_recognises_v_at_previous_close():
    result = recogniser().recognise((
        candle(0, 12, 10),
        candle(1, 10, 11),
    ))

    assert len(result.structures) == 1
    structure = result.structures[0]

    assert structure.kind == "V"
    assert structure.price == 10


def test_same_colour_candles_do_not_create_structures():
    result = recogniser().recognise((
        candle(0, 10, 12),
        candle(1, 11, 13),
        candle(2, 13, 12),
    ))

    assert len(result.structures) == 1
    assert result.structures[0].kind == "A"


def test_doji_is_reported_and_does_not_participate():
    result = recogniser().recognise((
        candle(0, 10, 12),
        candle(1, 12, 12),
        candle(2, 12, 10),
    ))

    assert result.structures == ()
    assert len(result.notes) == 1
    assert result.notes[0].code == "doji_candle_excluded"


def test_near_doji_is_classified_by_exact_direction():
    result = recogniser().recognise((
        candle(0, 10, 10.000001),
        candle(1, 10.000001, 10),
    ))

    assert len(result.structures) == 1
    assert result.structures[0].kind == "A"


def test_irregular_spacing_excludes_pair_and_reports_note():
    first = candle(0, 10, 12)
    second = Candle(
        symbol="XAUUSD",
        timeframe="M15",
        timestamp=first.timestamp + timedelta(minutes=30),
        open=12,
        high=13,
        low=10,
        close=11,
        volume=100,
        source="test",
    )

    result = recogniser().recognise((first, second))

    assert result.structures == ()
    assert len(result.notes) == 1
    assert result.notes[0].code == "irregular_candle_spacing"


def test_h2_spacing_uses_h2_interval():
    result = recogniser().recognise((
        candle(0, 12, 10, timeframe="H2"),
        candle(1, 10, 11, timeframe="H2"),
    ))

    assert len(result.structures) == 1
    assert result.structures[0].kind == "V"


def test_consecutive_transitions_are_all_retained():
    result = recogniser().recognise((
        candle(0, 10, 12),
        candle(1, 12, 11),
        candle(2, 11, 13),
        candle(3, 13, 12),
    ))

    assert [item.kind for item in result.structures] == ["A", "V", "A"]


def test_empty_input_returns_empty_result():
    result = recogniser().recognise(())

    assert result.structures == ()
    assert result.notes == ()


def test_mixed_symbols_are_rejected():
    first = candle(0, 10, 12)
    second = Candle(
        symbol="EURUSD",
        timeframe="M15",
        timestamp=START + timedelta(minutes=15),
        open=12,
        high=13,
        low=10,
        close=11,
    )

    with pytest.raises(ValueError, match="same symbol and timeframe"):
        recogniser().recognise((first, second))


def test_recognition_is_prefix_invariant():
    candles = (
        candle(0, 10, 12),
        candle(1, 12, 11),
        candle(2, 11, 13),
        candle(3, 13, 12),
    )

    complete = recogniser().recognise(candles)

    for length in range(1, len(candles) + 1):
        prefix = recogniser().recognise(candles[:length])
        prefix_end = candles[length - 1].timestamp + timedelta(minutes=15)

        expected = tuple(
            structure
            for structure in complete.structures
            if structure.recognised_at <= prefix_end
        )

        assert prefix.structures == expected
