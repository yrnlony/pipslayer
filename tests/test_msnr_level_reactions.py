from datetime import datetime, timezone
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest

from pipslayer.data.candles import Candle  # pyright: ignore[reportMissingImports]
from pipslayer.strategies.msnr.level_reactions import (  # pyright: ignore[reportMissingImports]
    build_reaction_report,
)


def candle(hour, low, high, close, open_price=None):
    return Candle(
        symbol="XAUUSD",
        timeframe="H4",
        timestamp=datetime(2026, 5, 1, hour, tzinfo=timezone.utc),
        open=close if open_price is None else open_price,
        high=high,
        low=low,
        close=close,
        volume=100,
    )


def make_inputs(kind="V"):
    level = {
        "level_id": "level-test",
        "source_structure_ids": ["av-test"],
        "kind": kind,
        "reference_price": 100.0,
        "recognised_at": "2026-05-01T00:00:00+00:00",
    }

    catalogue = {
        "symbol": "XAUUSD",
        "timeframe": "H4",
        "levels": [level],
    }

    interaction_report = {
        "symbol": "XAUUSD",
        "timeframe": "H4",
        "dataset_id": "test-dataset",
        "episodes": [
            {
                "episode_id": "level-test-interaction-001",
                "level_id": "level-test",
                "source_structure_ids": ["av-test"],
                "last_contact_timestamp": "2026-05-01T00:00:00+00:00",
            }
        ],
    }

    return catalogue, interaction_report


def test_v_level_measures_upward_favourable_excursion():
    candles = (
        candle(0, 99, 101, 100),
        candle(4, 100, 110, 108),
        candle(8, 101, 115, 112),
        candle(12, 102, 120, 118),
        candle(16, 103, 125, 123),
        candle(20, 104, 130, 128),
        candle(0, 104, 135, 132),
    )

    # The final candle above needs the following day.
    next_day = Candle(
        symbol="XAUUSD",
        timeframe="H4",
        timestamp=datetime(2026, 5, 2, 0, tzinfo=timezone.utc),
        open=130,
        high=135,
        low=104,
        close=132,
        volume=100,
    )
    candles = candles[:-1] + (next_day,)

    catalogue, interactions = make_inputs()
    report = build_reaction_report(candles, catalogue, interactions)

    one = report["reactions"][0]["horizons"]["1"]
    assert one["complete"] is True
    assert one["favourable_excursion"] == 10
    assert one["adverse_excursion"] == 0
    assert one["ending_close_position"] == "above"


def test_a_level_measures_downward_favourable_excursion():
    candles = (
        candle(0, 99, 101, 100),
        candle(4, 90, 100, 92),
        candle(8, 85, 99, 88),
        candle(12, 80, 98, 82),
        candle(16, 75, 97, 77),
        candle(20, 70, 96, 72),
        Candle(
            symbol="XAUUSD",
            timeframe="H4",
            timestamp=datetime(2026, 5, 2, 0, tzinfo=timezone.utc),
            open=70,
            high=95,
            low=65,
            close=67,
            volume=100,
        ),
    )

    catalogue, interactions = make_inputs("A")
    report = build_reaction_report(candles, catalogue, interactions)

    one = report["reactions"][0]["horizons"]["1"]
    assert one["favourable_excursion"] == 10
    assert one["adverse_excursion"] == 0
    assert one["ending_close_position"] == "below"


def test_incomplete_horizon_is_not_scored():
    candles = (
        candle(0, 99, 101, 100),
        candle(4, 100, 110, 108),
    )

    catalogue, interactions = make_inputs()
    report = build_reaction_report(candles, catalogue, interactions)

    six = report["reactions"][0]["horizons"]["6"]
    assert six["complete"] is False
    assert six["favourable_excursion"] is None


def test_return_to_level_is_detected():
    candles = (
        candle(0, 99, 101, 100),
        candle(4, 102, 110, 108),
        candle(8, 99, 105, 101),
        candle(12, 103, 115, 110),
        candle(16, 104, 120, 118),
        candle(20, 105, 125, 123),
        Candle(
            symbol="XAUUSD",
            timeframe="H4",
            timestamp=datetime(2026, 5, 2, 0, tzinfo=timezone.utc),
            open=120,
            high=130,
            low=110,
            close=125,
            volume=100,
        ),
    )

    catalogue, interactions = make_inputs()
    report = build_reaction_report(candles, catalogue, interactions)

    two = report["reactions"][0]["horizons"]["2"]
    assert two["first_return_timestamp"] == "2026-05-01T08:00:00+00:00"
    assert two["candles_until_return"] == 2


def test_missing_h4_candle_marks_horizon_incomplete():
    candles = (
        candle(0, 99, 101, 100),
        candle(4, 100, 110, 108),
        candle(12, 102, 115, 112),
    )

    catalogue, interactions = make_inputs()
    report = build_reaction_report(candles, catalogue, interactions)

    two = report["reactions"][0]["horizons"]["2"]
    assert two["complete"] is False


def test_unknown_episode_level_is_rejected():
    candles = (
        candle(0, 99, 101, 100),
        candle(4, 100, 110, 108),
    )

    catalogue, interactions = make_inputs()
    interactions["episodes"][0]["level_id"] = "unknown-level"

    with pytest.raises(ValueError, match="Unknown level"):
        build_reaction_report(candles, catalogue, interactions)