from datetime import datetime, timedelta, timezone

from pipslayer.data.candles import Candle
from pipslayer.strategies.msnr.level_interactions import (
    build_interaction_report,
)


START = datetime(2026, 5, 1, 0, 0, tzinfo=timezone.utc)


def candle(hour, low, high, close, open_price=None):
    return Candle(
        symbol="XAUUSD",
        timeframe="H4",
        timestamp=START + timedelta(hours=hour),
        open=close if open_price is None else open_price,
        high=high,
        low=low,
        close=close,
    )


def catalogue(recognised_at=None):
    return {
        "dataset_id": "test-dataset",
        "symbol": "XAUUSD",
        "timeframe": "H4",
        "level_count": 1,
        "levels": [{
            "level_id": "level-test",
            "source_structure_ids": ["av-test"],
            "reference_price": 100.0,
            "recognised_at": recognised_at or (
                START + timedelta(hours=4)
            ).isoformat(),
        }],
    }


def test_consecutive_contacts_form_one_episode():
    candles = [
        candle(0, 98, 99, 99),
        candle(4, 99, 102, 101),
        candle(8, 98, 103, 99),
    ]

    report = build_interaction_report(candles, catalogue())

    assert report["interaction_episode_count"] == 1
    episode = report["episodes"][0]
    assert episode["contact_candle_count"] == 2
    assert episode["approach_direction"] == "from_below"


def test_non_contact_candle_splits_episodes():
    candles = [
        candle(0, 98, 99, 99),
        candle(4, 99, 102, 101),
        candle(8, 96, 99, 98),
        candle(12, 98, 101, 100),
    ]

    report = build_interaction_report(candles, catalogue())

    assert report["interaction_episode_count"] == 2
    assert [e["contact_candle_count"] for e in report["episodes"]] == [1, 1]


def test_missing_candle_gap_splits_episodes():
    candles = [
        candle(0, 98, 99, 99),
        candle(4, 99, 102, 101),
        candle(12, 98, 101, 100),
    ]

    report = build_interaction_report(candles, catalogue())

    assert report["interaction_episode_count"] == 2


def test_pre_recognition_candles_are_not_counted():
    candles = [
        candle(0, 99, 101, 100),
        candle(4, 99, 102, 101),
    ]

    report = build_interaction_report(candles, catalogue())

    assert report["interaction_episode_count"] == 1
    assert report["episodes"][0]["contact_candle_count"] == 1
    assert report["episodes"][0]["first_contact_timestamp"] == (
        START + timedelta(hours=4)
    ).isoformat()


def test_penetration_and_close_positions_are_recorded():
    candles = [
        candle(0, 98, 99, 99),
        candle(4, 98, 103, 101),
        candle(8, 97, 102, 99),
    ]

    report = build_interaction_report(candles, catalogue())
    episode = report["episodes"][0]

    assert episode["maximum_price_above_level"] == 3
    assert episode["maximum_price_below_level"] == 3
    assert episode["close_positions"] == {
        "above": 1,
        "below": 1,
        "at": 0,
    }
    assert episode["ending_close_position"] == "below"


def test_candle_sequence_must_be_chronological():
    candles = [
        candle(4, 99, 102, 101),
        candle(0, 98, 99, 99),
    ]

    try:
        build_interaction_report(candles, catalogue())
    except ValueError as exc:
        assert "chronological order" in str(exc)
    else:
        raise AssertionError("Out-of-order candles were accepted")

