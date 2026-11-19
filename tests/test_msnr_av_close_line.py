
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest

from pipslayer.data.candles import Candle  # pyright: ignore[reportMissingImports]
from pipslayer.strategies.msnr.av_close_line import (  # pyright: ignore[reportMissingImports]
    CloseLineTurningPointRecogniser,
    EqualClosePolicy,
)


START = datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc)


def make_candles(closes):
    candles = []

    for index, close in enumerate(closes):
        timestamp = START + timedelta(minutes=15 * index)

        candles.append(
            Candle(
                symbol="XAUUSD",
                timeframe="M15",
                timestamp=timestamp,
                open=close,
                high=close + 1,
                low=close - 1,
                close=close,
                volume=100,
                source="test",
            )
        )

    return tuple(candles)


def recogniser(policy=EqualClosePolicy.EXCLUDE_AND_REPORT):
    return CloseLineTurningPointRecogniser(
        equal_close_policy=policy
    )


def test_recognises_a_close_line_peak():
    result = recogniser().recognise(
        make_candles([10, 12, 11])
    )

    assert len(result.structures) == 1

    structure = result.structures[0]

    assert structure.kind == "A"
    assert structure.price == 12
    assert structure.anchor_timestamp == START + timedelta(minutes=15)
    assert structure.recognised_at == START + timedelta(minutes=45)
    assert structure.confirmed_at is None


def test_recognises_a_close_line_valley():
    result = recogniser().recognise(
        make_candles([12, 10, 11])
    )

    assert len(result.structures) == 1

    structure = result.structures[0]

    assert structure.kind == "V"
    assert structure.price == 10


def test_wicks_do_not_determine_turning_points():
    candles = list(make_candles([10, 12, 11]))

    candles[1] = Candle(
        symbol="XAUUSD",
        timeframe="M15",
        timestamp=candles[1].timestamp,
        open=12,
        high=100,
        low=1,
        close=12,
        volume=100,
        source="test",
    )

    result = recogniser().recognise(tuple(candles))

    assert len(result.structures) == 1
    assert result.structures[0].kind == "A"
    assert result.structures[0].price == 12


def test_equal_close_plateau_is_excluded_and_reported():
    result = recogniser().recognise(
        make_candles([10, 12, 12, 11])
    )

    assert result.structures == ()
    assert len(result.notes) == 3

    plateau_note = next(
        note for note in result.notes
        if note.code == "equal_close_run_excluded"
    )

    assert plateau_note.kind == "A"
    assert plateau_note.first_timestamp == START + timedelta(minutes=15)
    assert plateau_note.last_timestamp == START + timedelta(minutes=30)


def test_plateau_first_policy_uses_first_candle_as_anchor():
    result = recogniser(
        EqualClosePolicy.PLATEAU_FIRST_CANDLE
    ).recognise(
        make_candles([10, 12, 12, 11])
    )

    assert len(result.structures) == 1

    structure = result.structures[0]

    assert structure.kind == "A"
    assert structure.anchor_timestamp == START + timedelta(minutes=15)
    assert len(structure.contributing_timestamps) == 2


def test_plateau_last_policy_uses_last_candle_as_anchor():
    result = recogniser(
        EqualClosePolicy.PLATEAU_LAST_CANDLE
    ).recognise(
        make_candles([10, 12, 12, 11])
    )

    assert len(result.structures) == 1

    structure = result.structures[0]

    assert structure.kind == "A"
    assert structure.anchor_timestamp == START + timedelta(minutes=30)
    assert len(structure.contributing_timestamps) == 2


def test_first_run_without_left_context_is_reported():
    result = recogniser().recognise(
        make_candles([10, 12, 11])
    )

    note = next(
        note for note in result.notes
        if note.code == "insufficient_left_context"
    )

    assert note.kind is None


def test_final_run_without_right_context_is_reported():
    result = recogniser().recognise(
        make_candles([10, 12, 11])
    )

    note = next(
        note for note in result.notes
        if note.code == "insufficient_right_context"
    )

    assert note.kind is None


def test_empty_input_returns_empty_result():
    result = recogniser().recognise(())

    assert result.structures == ()
    assert result.notes == ()


def test_candles_must_be_in_strict_timestamp_order():
    candles = list(make_candles([10, 12, 11]))
    candles[2] = candles[1]

    with pytest.raises(ValueError, match="strictly increasing"):
        recogniser().recognise(tuple(candles))


def test_mixed_symbols_are_rejected():
    candles = list(make_candles([10, 12, 11]))

    candles[1] = Candle(
        symbol="EURUSD",
        timeframe="M15",
        timestamp=candles[1].timestamp,
        open=12,
        high=13,
        low=11,
        close=12,
        volume=100,
        source="test",
    )

    with pytest.raises(ValueError, match="same symbol and timeframe"):
        recogniser().recognise(tuple(candles))


def test_mixed_timeframes_are_rejected():
    candles = list(make_candles([10, 12, 11]))

    candles[1] = Candle(
        symbol="XAUUSD",
        timeframe="H1",
        timestamp=candles[1].timestamp,
        open=12,
        high=13,
        low=11,
        close=12,
        volume=100,
        source="test",
    )

    with pytest.raises(ValueError, match="same symbol and timeframe"):
        recogniser().recognise(tuple(candles))

@pytest.mark.parametrize(
    "policy",
    list(EqualClosePolicy),
)
def test_recognition_is_prefix_invariant(policy):
    candles = make_candles([
        10, 12, 11, 9, 13, 13, 10,
        8, 9, 11, 11, 7, 8,
    ])

    detector = recogniser(policy)
    complete_result = detector.recognise(candles)

    for prefix_length in range(1, len(candles) + 1):
        prefix = candles[:prefix_length]
        prefix_result = detector.recognise(prefix)

        prefix_end = (
            prefix[-1].timestamp + timedelta(minutes=15)
        )

        expected_structures = tuple(
            structure
            for structure in complete_result.structures
            if structure.recognised_at <= prefix_end
        )

        assert prefix_result.structures == expected_structures, (
            f"Earlier recognition changed with future candles "
            f"under policy {policy.value}, "
            f"at prefix length {prefix_length}"
        )
