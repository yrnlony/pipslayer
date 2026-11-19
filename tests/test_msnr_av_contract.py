from datetime import datetime, timedelta, timezone
import sys
from pathlib import Path

for candidate in (
    Path(__file__).resolve().parents[2],
    Path(__file__).resolve().parents[1],
):
    if candidate.exists() and str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import pytest

from pipslayer.strategies.msnr.av_contract import (  # type: ignore[reportMissingImports]
    AVRecognitionResult,
    AVStructure,
    RecognitionNote,
    structures_known_at,
)


ANCHOR = datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc)
FORMED = ANCHOR + timedelta(minutes=15)
RECOGNISED = FORMED + timedelta(minutes=15)


def make_structure(**overrides):
    values = {
        "kind": "A",
        "symbol": "XAUUSD",
        "timeframe": "M15",
        "price": 4050.0,
        "anchor_timestamp": ANCHOR,
        "formed_at": FORMED,
        "recognised_at": RECOGNISED,
        "method": "test-method",
        "contributing_timestamps": (ANCHOR,),
        "method_parameters": (
            ("depth", "2"),
            ("policy", "strict"),
        ),
    }
    values.update(overrides)
    return AVStructure(**values)


def test_valid_structure_is_created():
    structure = make_structure()

    assert structure.kind == "A"
    assert structure.symbol == "XAUUSD"
    assert structure.timeframe == "M15"
    assert structure.confirmed_at is None


def test_formed_at_must_equal_anchor_candle_close():
    with pytest.raises(ValueError, match="formed_at"):
        make_structure(
            formed_at=ANCHOR + timedelta(minutes=10)
        )


def test_recognition_cannot_precede_formation():
    with pytest.raises(ValueError, match="recognised_at"):
        make_structure(
            recognised_at=ANCHOR + timedelta(minutes=5)
        )


def test_contributing_timestamps_must_be_unique():
    with pytest.raises(ValueError, match="unique"):
        make_structure(
            contributing_timestamps=(ANCHOR, ANCHOR)
        )


def test_contributing_timestamps_must_be_chronological():
    later = ANCHOR + timedelta(minutes=15)

    with pytest.raises(ValueError, match="chronological"):
        make_structure(
            contributing_timestamps=(later, ANCHOR)
        )


def test_anchor_must_be_a_contributing_timestamp():
    with pytest.raises(ValueError, match="anchor_timestamp"):
        make_structure(
            contributing_timestamps=(
                ANCHOR + timedelta(minutes=15),
            )
        )


def test_method_parameter_order_does_not_change_identity():
    first = make_structure(
        method_parameters=(("depth", "2"), ("policy", "strict"))
    )
    second = make_structure(
        method_parameters=(("policy", "strict"), ("depth", "2"))
    )

    assert first.structure_id == second.structure_id


def test_different_method_parameters_produce_different_identity():
    first = make_structure(
        method_parameters=(("depth", "2"),)
    )
    second = make_structure(
        method_parameters=(("depth", "3"),)
    )

    assert first.structure_id != second.structure_id


def test_duplicate_structure_id_is_rejected():
    structure = make_structure()

    with pytest.raises(ValueError, match="Duplicate structure_id"):
        AVRecognitionResult(
            structures=(structure, structure)
        )


def test_conflicting_structures_with_same_identity_are_rejected():
    first = make_structure(price=4050.0)
    second = make_structure(price=4051.0)

    assert first.structure_id == second.structure_id

    with pytest.raises(ValueError, match="Conflicting structures"):
        AVRecognitionResult(
            structures=(first, second)
        )


def test_structures_known_at_excludes_future_recognition():
    structure = make_structure()

    before_recognition = structures_known_at(
        (structure,),
        RECOGNISED - timedelta(seconds=1),
    )
    at_recognition = structures_known_at(
        (structure,),
        RECOGNISED,
    )

    assert before_recognition == ()
    assert at_recognition == (structure,)


def test_recognition_note_rejects_invalid_time_order():
    with pytest.raises(ValueError, match="first_timestamp"):
        RecognitionNote(
            code="test",
            kind=None,
            first_timestamp=FORMED,
            last_timestamp=ANCHOR,
            recognised_at=RECOGNISED,
            detail="Test note",
        )