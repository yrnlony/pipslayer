
from datetime import datetime, timezone

import pytest

from pipslayer.data.candles import Candle
from pipslayer.strategies.msnr.timeframe_context import (
    EvidenceSection,
    analyse_timeframe_context,
    build_timeframe_context_request,
)


def utc(value):
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def make_candle(timeframe, timestamp, price=100.0):
    return Candle(
        symbol="XAUUSD",
        timeframe=timeframe,
        timestamp=utc(timestamp),
        open=price,
        high=price + 2,
        low=price - 2,
        close=price + 1,
    )


def make_custom_candle(timeframe, timestamp, open_, high, low, close):
    return Candle(
        symbol="XAUUSD",
        timeframe=timeframe,
        timestamp=utc(timestamp),
        open=open_,
        high=high,
        low=low,
        close=close,
    )


@pytest.fixture
def opportunity():
    return {
        "snapshot_timestamp": "2026-05-04T12:00:00Z",
        "level": {
            "level_id": "level-example",
            "source_structure_ids": ["av-example"],
            "kind": "V",
            "reference_price": 4568.55,
            "formed_at": "2026-05-01T12:00:00Z",
            "recognised_at": "2026-05-01T16:00:00Z",
        },
    }


def test_builds_h2_context_request(opportunity):
    candles = [
        make_candle("H2", "2026-05-04T08:00:00"),
        make_candle("H2", "2026-05-04T10:00:00"),
    ]

    request = build_timeframe_context_request(
        opportunity, "XAUUSD", "H2", candles
    )

    assert request.opportunity_id == "level-example"
    assert request.source_structure_ids == ("av-example",)
    assert request.timeframe == "H2"
    assert request.symbol == "XAUUSD"
    assert request.reference_price == 4568.55
    assert len(request.candles) == 2


def test_builds_m15_context_request(opportunity):
    candles = [
        make_candle("M15", "2026-05-04T11:30:00"),
        make_candle("M15", "2026-05-04T11:45:00"),
    ]

    request = build_timeframe_context_request(
        opportunity, "XAUUSD", "M15", candles
    )

    assert request.timeframe == "M15"
    assert len(request.candles) == 2


def test_preserves_original_opportunity_snapshot(opportunity):
    request = build_timeframe_context_request(
        opportunity,
        "XAUUSD",
        "H2",
        [make_candle("H2", "2026-05-04T10:00:00")],
    )

    assert request.opportunity_snapshot is opportunity
    assert request.opportunity_id == opportunity["level"]["level_id"]


def test_rejects_unsupported_timeframe(opportunity):
    with pytest.raises(ValueError, match="Unsupported timeframe"):
        build_timeframe_context_request(opportunity, "XAUUSD", "H3", [])


def test_rejects_candle_timeframe_mismatch(opportunity):
    candles = [make_candle("M15", "2026-05-04T11:45:00")]

    with pytest.raises(ValueError, match="does not match requested"):
        build_timeframe_context_request(
            opportunity, "XAUUSD", "H2", candles
        )


def test_rejects_candle_not_closed_at_snapshot(opportunity):
    candles = [make_candle("H2", "2026-05-04T12:00:00")]

    with pytest.raises(ValueError, match="not fully closed"):
        build_timeframe_context_request(
            opportunity, "XAUUSD", "H2", candles
        )


def test_rejects_out_of_order_candles(opportunity):
    candles = [
        make_candle("H2", "2026-05-04T10:00:00"),
        make_candle("H2", "2026-05-04T08:00:00"),
    ]

    with pytest.raises(ValueError, match="strictly ordered"):
        build_timeframe_context_request(
            opportunity, "XAUUSD", "H2", candles
        )


def test_rejects_opportunity_recognised_after_snapshot(opportunity):
    opportunity["level"]["recognised_at"] = "2026-05-04T16:00:00Z"

    with pytest.raises(ValueError, match="not recognised"):
        build_timeframe_context_request(
            opportunity, "XAUUSD", "H2", []
        )


def test_evidence_section_contract():
    section = EvidenceSection(
        status="found",
        records=({"structure_id": "structure-1"},),
        notes=("Structure was known at snapshot time.",),
    )

    assert section.status == "found"
    assert len(section.records) == 1


def test_analyser_reports_insufficient_data_for_fewer_than_three_candles(
    opportunity,
):
    candles = [
        make_candle("H2", "2026-05-04T08:00:00"),
        make_candle("H2", "2026-05-04T10:00:00"),
    ]

    request = build_timeframe_context_request(
        opportunity, "XAUUSD", "H2", candles
    )

    result = analyse_timeframe_context(request)

    assert result.opportunity_id == "level-example"
    assert result.timeframe == "H2"
    assert result.exact_level_context.status == "insufficient_data"
    assert result.drawdown_context.status == "found"
    assert result.data_quality["candle_count"] == 2


def test_analyser_detects_v_structure_and_measures_exact_distance(
    opportunity,
):
    candles = [
        make_custom_candle(
            "H2", "2026-05-04T04:00:00",
            4569, 4572, 4568, 4570,
        ),
        make_custom_candle(
            "H2", "2026-05-04T06:00:00",
            4561, 4562, 4558, 4560,
        ),
        make_custom_candle(
            "H2", "2026-05-04T08:00:00",
            4574, 4577, 4572, 4575,
        ),
    ]

    request = build_timeframe_context_request(
        opportunity, "XAUUSD", "H2", candles
    )

    result = analyse_timeframe_context(request)

    assert result.exact_level_context.status == "found"

    v_structures = [
        record
        for record in result.exact_level_context.records
        if record["kind"] == "V"
    ]

    assert len(v_structures) == 1

    v_structure = v_structures[0]

    assert v_structure["price"] == 4560
    assert v_structure["signed_distance_from_reference"] == pytest.approx(
        -8.55
    )
    assert v_structure["absolute_distance_from_reference"] == pytest.approx(
        8.55
    )
    assert v_structure["recognised_at"] == "2026-05-04T10:00:00+00:00"
def test_analyser_reports_missing_h2_candle_without_repairing(
    opportunity,
):
    candles = [
        make_candle("H2", "2026-05-04T04:00:00"),
        make_candle("H2", "2026-05-04T08:00:00"),
    ]

    request = build_timeframe_context_request(
        opportunity, "XAUUSD", "H2", candles
    )
    result = analyse_timeframe_context(request)

    quality = result.data_quality

    assert quality["gap_count"] == 1
    assert quality["expected_interval_seconds"] == 7200

    gap = quality["gaps"][0]

    assert gap["elapsed_seconds"] == 14400
    assert gap["missing_bars_if_exact_multiple"] == 1
    assert len(request.candles) == 2