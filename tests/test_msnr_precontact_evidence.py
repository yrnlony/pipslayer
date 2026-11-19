
from datetime import datetime, timedelta, timezone
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest

try:
    from pipslayer.data.candles import Candle  # type: ignore[reportMissingImports]
except ModuleNotFoundError:
    candidates = [
        PROJECT_ROOT / "src",
        PROJECT_ROOT / "pipslayer",
        PROJECT_ROOT.parent,
        PROJECT_ROOT.parent / "pipslayer",
    ]

    for candidate in candidates:
        if candidate.exists() and str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))

    from pipslayer.data.candles import Candle  # type: ignore[reportMissingImports]

try:
    from pipslayer.strategies.msnr.precontact_evidence import (  # type: ignore[reportMissingImports]
        build_precontact_evidence,
    )
except ModuleNotFoundError:
    candidates = [
        PROJECT_ROOT / "src",
        PROJECT_ROOT / "pipslayer",
        PROJECT_ROOT.parent,
        PROJECT_ROOT.parent / "pipslayer",
    ]

    for candidate in candidates:
        if candidate.exists() and str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))

    from pipslayer.strategies.msnr.precontact_evidence import (  # type: ignore[reportMissingImports]
        build_precontact_evidence,
    )


START = datetime(2026, 5, 1, 0, tzinfo=timezone.utc)


def candle(hour, low, high, close, open_price=None):
    return Candle(
        symbol="XAUUSD",
        timeframe="H4",
        timestamp=START + timedelta(hours=hour),
        open=close if open_price is None else open_price,
        high=high,
        low=low,
        close=close,
        volume=100,
    )


def make_inputs():
    level = {
        "level_id": "level-test",
        "source_structure_ids": ["av-test"],
        "kind": "V",
        "reference_price": 100.0,
        "anchor_timestamp": "2026-04-30T16:00:00+00:00",
        "formed_at": "2026-04-30T20:00:00+00:00",
        "recognised_at": "2026-05-01T00:00:00+00:00",
    }

    catalogue = {
        "dataset_id": "test-dataset",
        "symbol": "XAUUSD",
        "timeframe": "H4",
        "levels": [level],
    }

    interaction_report = {
        "dataset_id": "test-dataset",
        "symbol": "XAUUSD",
        "timeframe": "H4",
        "episodes": [
            {
                "episode_id": "episode-001",
                "level_id": "level-test",
                "source_structure_ids": ["av-test"],
                "reference_price": 100.0,
                "first_contact_timestamp": "2026-05-01T08:00:00+00:00",
                "last_contact_timestamp": "2026-05-01T08:00:00+00:00",
                "contact_candle_count": 1,
                "contact_timestamps": [
                    "2026-05-01T08:00:00+00:00"
                ],
            },
        ],
    }

    reaction_report = {
        "dataset_id": "test-dataset",
        "symbol": "XAUUSD",
        "timeframe": "H4",
        "reactions": [],
    }

    return catalogue, interaction_report, reaction_report


def test_one_snapshot_is_created_per_interaction():
    candles = [
        candle(0, 98, 99, 99),
        candle(4, 99, 101, 100),
        candle(8, 98, 103, 102),
    ]

    catalogue, interactions, reactions = make_inputs()

    report = build_precontact_evidence(
        candles, catalogue, interactions, reactions
    )

    assert report["snapshot_count"] == 1
    assert report["snapshots"][0]["episode_id"] == "episode-001"

    quality = report["snapshots"][0]["data_quality"]

    assert quality["input_h4_candle_count"] == 3
    assert quality["completed_h4_candles_at_snapshot"] == 2
    assert quality["observed_timestamp_gaps"] == []


def test_contact_candle_is_excluded_from_market_lookback():
    candles = [
        candle(0, 98, 99, 99),
        candle(4, 97, 99, 98),
        candle(8, 50, 150, 140),
    ]

    catalogue, interactions, reactions = make_inputs()

    report = build_precontact_evidence(
        candles, catalogue, interactions, reactions
    )

    snapshot = report["snapshots"][0]

    six = snapshot["market_context"]["6"]

    assert six["observed_candles"] == 2
    assert six["measurements"]["highest_high"] == 99
    assert six["measurements"]["lowest_low"] == 97


def test_first_interaction_has_no_previous_history():
    candles = [
        candle(0, 98, 99, 99),
        candle(4, 99, 101, 100),
        candle(8, 98, 103, 102),
    ]

    catalogue, interactions, reactions = make_inputs()

    report = build_precontact_evidence(
        candles, catalogue, interactions, reactions
    )

    snapshot = report["snapshots"][0]

    assert snapshot["previous_interaction_count"] == 0
    assert snapshot["previous_interactions"] == []
    assert snapshot["previous_reactions"] == []
    aggregates = snapshot["previous_interaction_aggregates"]

    assert aggregates["previous_episode_count"] == 0
    assert aggregates["episodes_with_incomplete_contact_data"] == 0
    assert aggregates["total_observed_contact_candles"] == 0
    assert aggregates["bullish_contact_candle_count"] == 0
    assert aggregates["bearish_contact_candle_count"] == 0
    assert aggregates["strict_body_crossing_count"] == 0

    assert aggregates["close_positions"] == {
        "above": 0,
        "below": 0,
        "at": 0,
    }

    assert aggregates["close_proportions"] == {
        "above": None,
        "below": None,
        "at": None,
    }

def test_future_structure_is_excluded_from_context():
    catalogue, interactions, reactions = make_inputs()

    catalogue["levels"].append({
        "level_id": "future-level",
        "source_structure_ids": ["av-future"],
        "kind": "A",
        "reference_price": 110.0,
        "recognised_at": "2026-05-01T12:00:00+00:00",
    })

    candles = [
        candle(0, 98, 99, 99),
        candle(4, 97, 99, 98),
        candle(8, 98, 103, 102),
    ]

    report = build_precontact_evidence(
        candles, catalogue, interactions, reactions
    )

    assert report["snapshots"][0]["structural_context"] == []


def test_missing_h4_candles_make_lookback_incomplete():
    candles = [
        candle(-16, 98, 99, 99),
        candle(-12, 97, 99, 98),
        # Missing the -8 hour candle
        candle(-4, 97, 99, 98),
        candle(0, 98, 99, 99),
        candle(4, 97, 99, 98),
        candle(8, 98, 103, 102),
    ]

    catalogue, interactions, reactions = make_inputs()

    report = build_precontact_evidence(
        candles, catalogue, interactions, reactions
    )

    six = report["snapshots"][0]["market_context"]["6"]

    assert six["complete"] is False
    assert six["status"] == "incomplete"
    assert six["missing_intervals"]

    quality = report["snapshots"][0]["data_quality"]

    assert quality["observed_timestamp_gaps"]
    assert quality["observed_timestamp_gaps"][0]["previous_candle_open"] == (
        "2026-04-30T12:00:00+00:00"
    )
    assert quality["observed_timestamp_gaps"][0]["next_candle_open"] == (
        "2026-04-30T20:00:00+00:00"
    )
    assert quality["observed_timestamp_gaps"][0]["elapsed_hours"] == 8


def test_unknown_level_is_rejected():
    candles = [
        candle(0, 98, 99, 99),
        candle(4, 97, 99, 98),
        candle(8, 98, 103, 102),
    ]

    catalogue, interactions, reactions = make_inputs()
    interactions["episodes"][0]["level_id"] = "unknown-level"

    with pytest.raises(ValueError, match="Unknown level"):
        build_precontact_evidence(
            candles, catalogue, interactions, reactions
        )

def test_future_reaction_measurement_is_hidden():
    candles = [
        candle(0, 98, 99, 99),
        candle(4, 97, 99, 98),
        candle(8, 98, 103, 102),
        candle(12, 98, 104, 103),
        candle(16, 99, 105, 104),
    ]

    catalogue, interactions, reactions = make_inputs()

    # Add a previous interaction before the current snapshot.
    interactions["episodes"].insert(0, {
        "episode_id": "episode-previous",
        "level_id": "level-test",
        "source_structure_ids": ["av-test"],
        "reference_price": 100.0,
        "first_contact_timestamp": "2026-05-01T00:00:00+00:00",
        "last_contact_timestamp": "2026-05-01T00:00:00+00:00",
        "contact_candle_count": 1,
        "contact_timestamps": ["2026-05-01T00:00:00+00:00"],
    })

    # The current interaction starts at 08:00.
    # Its snapshot must not see reaction data extending beyond 08:00.
    reactions["reactions"] = [{
        "episode_id": "episode-previous",
        "horizons": {
            "1": {
                "complete": True,
                "observed_timestamps": [
                    "2026-05-01T04:00:00+00:00"
                ],
                "favourable_excursion": 50.0,
            },
            "2": {
                "complete": True,
                "observed_timestamps": [
                    "2026-05-01T04:00:00+00:00",
                    "2026-05-01T08:00:00+00:00",
                ],
                "favourable_excursion": 75.0,
            },
        },
    }]

    report = build_precontact_evidence(
        candles, catalogue, interactions, reactions
    )

    current = next(
        item for item in report["snapshots"]
        if item["episode_id"] == "episode-001"
    )

    previous_reaction = current["previous_reactions"][0]
    horizons = previous_reaction["horizons"]

    assert horizons["1"]["status"] == "available"
    assert horizons["1"]["measurement"] is not None

    assert horizons["2"]["status"] == "not_yet_completed_at_snapshot"
    assert horizons["2"]["measurement"] is None
    assert horizons["2"]["completion_timestamp"] is None

def test_previous_interaction_behaviour_is_calculated_correctly():
    candles = [
        candle(0, 98, 101, 100, open_price=99),
        candle(4, 98, 102, 99, open_price=101),
        candle(8, 99, 102, 101, open_price=99),
        candle(12, 98, 103, 102),
    ]

    catalogue, interactions, reactions = make_inputs()

    interactions["episodes"] = [
        {
            "episode_id": "episode-previous",
            "level_id": "level-test",
            "source_structure_ids": ["av-test"],
            "reference_price": 100.0,
            "first_contact_timestamp": "2026-05-01T00:00:00+00:00",
            "last_contact_timestamp": "2026-05-01T08:00:00+00:00",
            "contact_candle_count": 3,
            "contact_timestamps": [
                "2026-05-01T00:00:00+00:00",
                "2026-05-01T04:00:00+00:00",
                "2026-05-01T08:00:00+00:00",
            ],
        },
        {
            "episode_id": "episode-001",
            "level_id": "level-test",
            "source_structure_ids": ["av-test"],
            "reference_price": 100.0,
            "first_contact_timestamp": "2026-05-01T12:00:00+00:00",
            "last_contact_timestamp": "2026-05-01T12:00:00+00:00",
            "contact_candle_count": 1,
            "contact_timestamps": [
                "2026-05-01T12:00:00+00:00"
            ],
        },
    ]

    report = build_precontact_evidence(
        candles, catalogue, interactions, reactions
    )

    current = next(
        item for item in report["snapshots"]
        if item["episode_id"] == "episode-001"
    )

    previous = current["previous_interactions"][0]
    behaviour = previous["derived_behaviour"]

    assert behaviour["contact_duration_hours"] == 12
    assert behaviour["contact_candle_count"] == 3
    assert behaviour["bullish_contact_candle_count"] == 2
    assert behaviour["bearish_contact_candle_count"] == 1
    assert behaviour["strict_body_crossing_count"] == 2

    assert behaviour["close_positions"] == {
        "above": 1,
        "below": 1,
        "at": 1,
    }

    assert behaviour["close_proportions"] == {
        "above": pytest.approx(1 / 3),
        "below": pytest.approx(1 / 3),
        "at": pytest.approx(1 / 3),
    }

    aggregates = current["previous_interaction_aggregates"]

    assert aggregates["previous_episode_count"] == 1
    assert aggregates["episodes_with_incomplete_contact_data"] == 0
    assert aggregates["total_observed_contact_candles"] == 3
    assert aggregates["bullish_contact_candle_count"] == 2
    assert aggregates["bearish_contact_candle_count"] == 1
    assert aggregates["strict_body_crossing_count"] == 2

    assert aggregates["close_positions"] == {
        "above": 1,
        "below": 1,
        "at": 1,
    }

    assert aggregates["close_proportions"] == {
        "above": pytest.approx(1 / 3),
        "below": pytest.approx(1 / 3),
        "at": pytest.approx(1 / 3),
    }

    assert behaviour["contact_candles_available"] is True
def test_interaction_dataset_mismatch_is_rejected():
    candles = [
        candle(0, 98, 99, 99),
        candle(4, 99, 101, 100),
        candle(8, 98, 103, 102),
    ]

    catalogue, interactions, reactions = make_inputs()
    interactions["dataset_id"] = "different-dataset"

    with pytest.raises(ValueError, match="Interaction report dataset ID mismatch"):
        build_precontact_evidence(
            candles, catalogue, interactions, reactions
        )


def test_reaction_dataset_mismatch_is_rejected():
    candles = [
        candle(0, 98, 99, 99),
        candle(4, 99, 101, 100),
        candle(8, 98, 103, 102),
    ]

    catalogue, interactions, reactions = make_inputs()
    reactions["dataset_id"] = "different-dataset"

    with pytest.raises(ValueError, match="Reaction report dataset ID mismatch"):
        build_precontact_evidence(
            candles, catalogue, interactions, reactions
        )
        
def test_market_lookback_splits_observations_at_internal_gaps():
    from pipslayer.strategies.msnr.precontact_evidence import (
        _market_lookback,
    )

    candles = [
        candle(-16, 90, 100, 95),
        candle(-12, 91, 101, 96),
        # Missing H4 candle at -8.
        candle(-4, 95, 105, 100),
        candle(0, 96, 106, 101),
        candle(4, 97, 107, 102),
    ]

    candles_by_time = {
        item.timestamp: item
        for item in candles
    }

    snapshot_time = START + timedelta(hours=8)

    result = _market_lookback(
        candles_by_time,
        snapshot_time,
        level_price=100,
        count=6,
    )

    assert result["complete"] is False
    assert result["status"] == "incomplete"
    assert result["observed_candles"] == 5

    assert result["segment_count"] == 2
    assert [
        segment["candle_count"]
        for segment in result["segments"]
    ] == [2, 3]

    assert result["missing_intervals"] == [{
        "after": (START + timedelta(hours=-12)).isoformat(),
        "before": (START + timedelta(hours=-4)).isoformat(),
        "missing_hours": 4.0,
    }]


def test_true_range_does_not_cross_internal_gap():
    from pipslayer.strategies.msnr.precontact_evidence import (
        _market_lookback,
    )

    candles = [
        candle(-16, 90, 100, 95),
        candle(-12, 91, 101, 96),
        # Missing H4 candle at -8.
        candle(-4, 95, 105, 100),
        candle(0, 96, 106, 101),
        candle(4, 97, 107, 102),
    ]

    candles_by_time = {
        item.timestamp: item
        for item in candles
    }

    result = _market_lookback(
        candles_by_time,
        START + timedelta(hours=8),
        level_price=100,
        count=6,
    )

    first_segment = result["segments"][0]
    second_segment = result["segments"][1]

    # The first observed candle has no preceding candle.
    assert first_segment["true_ranges"][0] is None

    # The second segment starts after a gap.
    # Its first candle must not use the previous segment's close.
    assert second_segment["true_ranges"][0] is None

    # Subsequent candles within the segment have valid True Range.
    assert all(
        value is not None
        for value in second_segment["true_ranges"][1:]
    )

    assert result["measurements"]["true_range_complete"] is False


def test_segment_displacement_is_calculated_independently():
    from pipslayer.strategies.msnr.precontact_evidence import (
        _market_lookback,
    )

    candles = [
        candle(-16, 90, 100, 95),
        candle(-12, 91, 101, 96),
        # Missing H4 candle at -8.
        candle(-4, 95, 105, 100),
        candle(0, 96, 106, 101),
        candle(4, 97, 107, 102),
    ]

    candles_by_time = {
        item.timestamp: item
        for item in candles
    }

    result = _market_lookback(
        candles_by_time,
        START + timedelta(hours=8),
        level_price=100,
        count=6,
    )

    first_segment, second_segment = result["segments"]

    assert first_segment["net_displacement"] == 1.0
    assert second_segment["net_displacement"] == 2.0

    # The aggregate endpoint displacement is retained,
    # but explicitly marked as spanning a gap.
    assert result["measurements"]["net_displacement"] == 7.0
    assert result["measurements"]["net_displacement_spans_gaps"] is True
