
"""Point-in-time H4 evidence snapshots for MSNR level-filtration research.

Research only. This module does not score, rank, or qualify trading levels.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math
from statistics import mean, median


HORIZONS = ("1", "2", "3", "6")
LOOKBACKS = (6, 12, 24)


def _timestamp(value, field):
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO timestamp")

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Invalid timestamp in {field}") from exc

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")

    return parsed.astimezone(timezone.utc)


def _iso(value):
    return value.isoformat()


def _number(value, field):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be numeric")
    if not math.isfinite(value):
        raise ValueError(f"{field} must be finite")
    return float(value)


def _direction(value):
    if value > 0:
        return "upward"
    if value < 0:
        return "downward"
    return "unchanged"


def _validate_candles(candles, symbol, timeframe):
    if not candles:
        raise ValueError("H4 candles cannot be empty")

    if timeframe != "H4":
        raise ValueError("Pre-contact evidence requires H4 data")

    interval = timedelta(hours=4)
    by_time = {}
    previous = None

    for candle in candles:
        if candle.symbol != symbol:
            raise ValueError("Candle symbol does not match catalogue")
        if candle.timeframe != timeframe:
            raise ValueError("Candle timeframe does not match catalogue")
        if candle.timestamp.tzinfo is None:
            raise ValueError("Candle timestamps must be timezone-aware")

        timestamp = candle.timestamp.astimezone(timezone.utc)

        if previous is not None and timestamp <= previous:
            raise ValueError("Candles must be in unique chronological order")

        values = (candle.open, candle.high, candle.low, candle.close)

        if any(not math.isfinite(float(value)) for value in values):
            raise ValueError("Candle contains a non-finite OHLC value")

        if candle.high < max(candle.open, candle.close, candle.low):
            raise ValueError("Invalid candle high")
        if candle.low > min(candle.open, candle.close, candle.high):
            raise ValueError("Invalid candle low")

        by_time[timestamp] = candle
        previous = timestamp

    return by_time, interval


def _market_lookback(candles_by_time, snapshot_time, level_price, count):
    """Measure observed H4 candles while preserving gaps between segments."""
    interval = timedelta(hours=4)

    eligible = [
        (timestamp, candle)
        for timestamp, candle in candles_by_time.items()
        if timestamp + interval <= snapshot_time
    ]
    eligible.sort(key=lambda item: item[0])

    selected = eligible[-count:]
    timestamps = [timestamp for timestamp, _ in selected]
    selected_candles = [candle for _, candle in selected]

    missing_intervals = []
    segment_boundaries = [0]

    for index in range(1, len(timestamps)):
        previous = timestamps[index - 1]
        current = timestamps[index]

        if current - previous != interval:
            missing_intervals.append({
                "after": _iso(previous),
                "before": _iso(current),
                "missing_hours": (
                    current - previous
                ).total_seconds() / 3600 - 4,
            })
            segment_boundaries.append(index)

    if selected:
        segment_boundaries.append(len(selected))

    def build_segment(start, end, segment_index):
        segment_timestamps = timestamps[start:end]
        segment_candles = selected_candles[start:end]

        highs = [float(c.high) for c in segment_candles]
        lows = [float(c.low) for c in segment_candles]
        ranges = [
            float(c.high) - float(c.low)
            for c in segment_candles
        ]

        true_ranges = []

        for local_index, candle in enumerate(segment_candles):
            previous_close = None

            if local_index > 0:
                previous_close = float(
                    segment_candles[local_index - 1].close
                )
            elif start == 0:
                previous_timestamp = (
                    segment_timestamps[0] - interval
                )
                previous_candle = candles_by_time.get(
                    previous_timestamp
                )

                if previous_candle is not None:
                    previous_close = float(previous_candle.close)

            # Never calculate True Range across an internal gap.
            if previous_close is None:
                true_ranges.append(None)
                continue

            high = float(candle.high)
            low = float(candle.low)

            true_ranges.append(max(
                high - low,
                abs(high - previous_close),
                abs(low - previous_close),
            ))

        valid_true_ranges = [
            value for value in true_ranges
            if value is not None
        ]

        first_close = float(segment_candles[0].close)
        last_close = float(segment_candles[-1].close)
        displacement = last_close - first_close

        return {
            "segment_index": segment_index,
            "candle_count": len(segment_candles),
            "first_candle_timestamp": _iso(segment_timestamps[0]),
            "last_candle_timestamp": _iso(segment_timestamps[-1]),
            "highest_high": max(highs),
            "lowest_low": min(lows),
            "price_range": max(highs) - min(lows),
            "candle_ranges": ranges,
            "mean_candle_range": mean(ranges),
            "median_candle_range": median(ranges),
            "true_ranges": true_ranges,
            "mean_true_range": (
                mean(valid_true_ranges)
                if valid_true_ranges else None
            ),
            "median_true_range": (
                median(valid_true_ranges)
                if valid_true_ranges else None
            ),
            "true_range_complete": (
                len(valid_true_ranges) == len(true_ranges)
            ),
            "first_close": first_close,
            "last_close": last_close,
            "net_displacement": displacement,
            "direction": _direction(displacement),
        }

    segments = [
        build_segment(
            segment_boundaries[index],
            segment_boundaries[index + 1],
            index,
        )
        for index in range(len(segment_boundaries) - 1)
    ]

    ends_at_snapshot = bool(
        selected
        and timestamps[-1] + interval == snapshot_time
    )

    complete = (
        len(selected_candles) == count
        and not missing_intervals
        and ends_at_snapshot
    )

    if not selected_candles:
        return {
            "requested_candles": count,
            "observed_candles": 0,
            "complete": False,
            "status": "unavailable",
            "missing_intervals": [],
            "segment_count": 0,
            "segments": [],
            "ends_at_snapshot": False,
            "last_candle_close_time": None,
            "time_since_last_candle_close_hours": None,
            "measurements": None,
        }

    highs = [float(c.high) for c in selected_candles]
    lows = [float(c.low) for c in selected_candles]
    ranges = [
        float(c.high) - float(c.low)
        for c in selected_candles
    ]

    true_ranges = [
        value
        for segment in segments
        for value in segment["true_ranges"]
    ]

    valid_true_ranges = [
        value for value in true_ranges
        if value is not None
    ]

    first_close = float(selected_candles[0].close)
    last_close = float(selected_candles[-1].close)
    displacement = last_close - first_close

    last_candle_close = timestamps[-1] + interval

    measurements = {
        "first_candle_timestamp": _iso(timestamps[0]),
        "last_candle_timestamp": _iso(timestamps[-1]),
        "highest_high": max(highs),
        "lowest_low": min(lows),
        "price_range": max(highs) - min(lows),
        "candle_ranges": ranges,
        "mean_candle_range": mean(ranges),
        "median_candle_range": median(ranges),
        "true_ranges": true_ranges,
        "mean_true_range": (
            mean(valid_true_ranges)
            if valid_true_ranges else None
        ),
        "median_true_range": (
            median(valid_true_ranges)
            if valid_true_ranges else None
        ),
        "true_range_complete": (
            len(valid_true_ranges) == len(true_ranges)
        ),
        "first_close": first_close,
        "last_close": last_close,
        "net_displacement": displacement,
        "direction": _direction(displacement),
        "latest_close": last_close,
        "latest_close_signed_distance_to_level": (
            last_close - level_price
        ),
        "latest_close_absolute_distance_to_level": abs(
            last_close - level_price
        ),
        "net_displacement_spans_gaps": bool(missing_intervals),
        "price_range_spans_gaps": bool(missing_intervals),
    }

    return {
        "requested_candles": count,
        "observed_candles": len(selected_candles),
        "complete": complete,
        "status": "complete" if complete else "incomplete",
        "missing_intervals": missing_intervals,
        "segment_count": len(segments),
        "segments": segments,
        "ends_at_snapshot": ends_at_snapshot,
        "last_candle_close_time": _iso(last_candle_close),
        "time_since_last_candle_close_hours": (
            snapshot_time - last_candle_close
        ).total_seconds() / 3600,
        "measurements": measurements,
    }


def _previous_interaction_behaviour(
    episode,
    candles_by_time,
    interval,
    level_price,
):
    contact_times = [
        _timestamp(value, "contact_timestamps")
        for value in episode.get("contact_timestamps", [])
    ]

    contact_candles = [
        candles_by_time[timestamp]
        for timestamp in contact_times
        if timestamp in candles_by_time
    ]

    above = below = at = 0
    bullish = bearish = crossing = 0

    for candle in contact_candles:
        close = float(candle.close)
        open_price = float(candle.open)

        if close > level_price:
            above += 1
        elif close < level_price:
            below += 1
        else:
            at += 1

        if close > open_price:
            bullish += 1
        elif close < open_price:
            bearish += 1

        if (
            (open_price > level_price and close < level_price)
            or (open_price < level_price and close > level_price)
        ):
            crossing += 1

    count = len(contact_candles)

    first = _timestamp(
        episode["first_contact_timestamp"],
        "first_contact_timestamp",
    )
    last = _timestamp(
        episode["last_contact_timestamp"],
        "last_contact_timestamp",
    )

    duration = (
        last + interval - first
    ).total_seconds() / 3600

    return {
        "contact_duration_hours": duration,
        "contact_candle_count": count,
        "bullish_contact_candle_count": bullish,
        "bearish_contact_candle_count": bearish,
        "strict_body_crossing_count": crossing,
        "close_positions": {
            "above": above,
            "below": below,
            "at": at,
        },
        "close_proportions": {
            "above": above / count if count else None,
            "below": below / count if count else None,
            "at": at / count if count else None,
        },
        "contact_candles_available": count == len(contact_times),
    }


def _reaction_evidence(
    previous_episode,
    reaction_by_episode,
    same_level_episodes,
    snapshot_time,
    interval,
):
    reaction = reaction_by_episode.get(previous_episode["episode_id"])

    if reaction is None:
        return {
            "episode_id": previous_episode["episode_id"],
            "status": "reaction_record_unavailable",
            "horizons": {},
        }

    horizons = {}

    for horizon in HORIZONS:
        measurement = reaction.get("horizons", {}).get(horizon)

        if measurement is None:
            horizons[horizon] = {
                "status": "horizon_unavailable",
                "measurement": None,
            }
            continue

        observed = measurement.get("observed_timestamps", [])

        last_observed = (
            _timestamp(observed[-1], "observed_timestamps")
            if observed else None
        )

        if not observed:
            status = "no_observed_candles"
            completion_time = None
        else:
            completion_time = last_observed + interval

            if completion_time > snapshot_time:
                status = "not_yet_completed_at_snapshot"
            elif measurement.get("complete") is not True:
                status = "incomplete"
            else:
                status = "available"

        overlap_ids = []

        if last_observed is not None:
            reaction_start = (
                _timestamp(
                    previous_episode["last_contact_timestamp"],
                    "last_contact_timestamp",
                ) + interval
            )

            for later in same_level_episodes:
                if later["episode_id"] == previous_episode["episode_id"]:
                    continue

                later_first = _timestamp(
                    later["first_contact_timestamp"],
                    "first_contact_timestamp",
                )

                if (
                    reaction_start <= later_first <= last_observed
                    and later_first <= snapshot_time
                ):
                    overlap_ids.append(later["episode_id"])

        # Never expose reaction measurements that were not fully
        # completed by the point-in-time snapshot.
        safe_measurement = (
            measurement if status == "available" else None
        )

        horizons[horizon] = {
            "status": status,
            "completion_timestamp": (
                _iso(completion_time)
                if completion_time and completion_time <= snapshot_time
                else None
            ),
            "overlaps_later_interaction": bool(overlap_ids),
            "overlapping_episode_ids": overlap_ids,
            "measurement": safe_measurement,
        }

    return {
        "episode_id": previous_episode["episode_id"],
        "status": "reaction_record_available",
        "horizons": horizons,
    }


def build_precontact_evidence(
    candles,
    catalogue,
    interaction_report,
    reaction_report,
):
    """Build one pre-contact evidence snapshot per interaction episode."""
    symbol = catalogue.get("symbol")
    timeframe = catalogue.get("timeframe")

    if not symbol or timeframe != "H4":
        raise ValueError("Catalogue must identify an H4 symbol")

    if interaction_report.get("symbol") != symbol:
        raise ValueError("Interaction report symbol mismatch")
    if interaction_report.get("timeframe") != timeframe:
        raise ValueError("Interaction report timeframe mismatch")
    if reaction_report.get("symbol") != symbol:
        raise ValueError("Reaction report symbol mismatch")
    if reaction_report.get("timeframe") != timeframe:
        raise ValueError("Reaction report timeframe mismatch")

    dataset_id = catalogue.get("dataset_id")

    if not dataset_id:
        raise ValueError("Catalogue dataset ID is missing")

    if interaction_report.get("dataset_id") != dataset_id:
        raise ValueError("Interaction report dataset ID mismatch")

    if reaction_report.get("dataset_id") != dataset_id:
        raise ValueError("Reaction report dataset ID mismatch")

    candles_by_time, interval = _validate_candles(
        candles, symbol, timeframe
    )

    levels = catalogue.get("levels")
    episodes = interaction_report.get("episodes")
    reactions = reaction_report.get("reactions")

    if not isinstance(levels, list) or not isinstance(episodes, list):
        raise ValueError(
            "Catalogue levels and interaction episodes must be lists"
        )
    if not isinstance(reactions, list):
        raise ValueError("Reaction records must be a list")

    levels_by_id = {}

    for level in levels:
        level_id = level.get("level_id")

        if not level_id or level_id in levels_by_id:
            raise ValueError("Missing or duplicate level ID")

        levels_by_id[level_id] = level

    reaction_by_episode = {}

    for reaction in reactions:
        episode_id = reaction.get("episode_id")

        if not episode_id or episode_id in reaction_by_episode:
            raise ValueError("Missing or duplicate reaction episode ID")

        reaction_by_episode[episode_id] = reaction

    episodes_by_level = {}
    seen_episode_ids = set()

    for episode in episodes:
        episode_id = episode.get("episode_id")
        level_id = episode.get("level_id")

        if not episode_id or episode_id in seen_episode_ids:
            raise ValueError("Missing or duplicate interaction episode ID")

        if level_id not in levels_by_id:
            raise ValueError(f"Unknown level: {level_id}")

        seen_episode_ids.add(episode_id)
        episodes_by_level.setdefault(level_id, []).append(episode)

    for level_episodes in episodes_by_level.values():
        level_episodes.sort(
            key=lambda item: _timestamp(
                item["first_contact_timestamp"],
                "first_contact_timestamp",
            )
        )

    first_contact_by_level = {
        level_id: _timestamp(
            level_episodes[0]["first_contact_timestamp"],
            "first_contact_timestamp",
        )
        for level_id, level_episodes in episodes_by_level.items()
        if level_episodes
    }

    snapshots = []

    for episode in episodes:
        level_id = episode["level_id"]
        level = levels_by_id[level_id]

        snapshot_time = _timestamp(
            episode["first_contact_timestamp"],
            "first_contact_timestamp",
        )

        level_price = _number(
            level["reference_price"], "reference_price"
        )

        recognised_at = _timestamp(
            level["recognised_at"], "recognised_at"
        )

        if recognised_at > snapshot_time:
            raise ValueError(
                "Interaction occurs before level recognition"
            )

        same_level = episodes_by_level[level_id]

        previous_episodes = [
            previous
            for previous in same_level
            if _timestamp(
                previous["first_contact_timestamp"],
                "first_contact_timestamp",
            ) < snapshot_time
        ]

        previous_episodes.sort(
            key=lambda item: _timestamp(
                item["first_contact_timestamp"],
                "first_contact_timestamp",
            )
        )

        previous_interactions = []
        previous_reactions = []

        for previous in previous_episodes:
            previous_interactions.append({
                "episode": previous,
                "derived_behaviour": _previous_interaction_behaviour(
                    previous,
                    candles_by_time,
                    interval,
                    level_price,
                ),
            })

            previous_reactions.append(_reaction_evidence(
                previous,
                reaction_by_episode,
                same_level,
                snapshot_time,
                interval,
            ))

        behaviour_records = [
            item["derived_behaviour"]
            for item in previous_interactions
        ]

        total_contact_candles = sum(
            item["contact_candle_count"]
            for item in behaviour_records
        )

        total_above = sum(
            item["close_positions"]["above"]
            for item in behaviour_records
        )
        total_below = sum(
            item["close_positions"]["below"]
            for item in behaviour_records
        )
        total_at = sum(
            item["close_positions"]["at"]
            for item in behaviour_records
        )

        previous_interaction_aggregates = {
            "previous_episode_count": len(previous_episodes),
            "episodes_with_incomplete_contact_data": sum(
                not item["contact_candles_available"]
                for item in behaviour_records
            ),
            "total_observed_contact_candles": total_contact_candles,
            "bullish_contact_candle_count": sum(
                item["bullish_contact_candle_count"]
                for item in behaviour_records
            ),
            "bearish_contact_candle_count": sum(
                item["bearish_contact_candle_count"]
                for item in behaviour_records
            ),
            "strict_body_crossing_count": sum(
                item["strict_body_crossing_count"]
                for item in behaviour_records
            ),
            "close_positions": {
                "above": total_above,
                "below": total_below,
                "at": total_at,
            },
            "close_proportions": {
                "above": (
                    total_above / total_contact_candles
                    if total_contact_candles else None
                ),
                "below": (
                    total_below / total_contact_candles
                    if total_contact_candles else None
                ),
                "at": (
                    total_at / total_contact_candles
                    if total_contact_candles else None
                ),
            },
        }

        structural_context = []

        for other in levels:
            if other["level_id"] == level_id:
                continue

            other_recognised = _timestamp(
                other["recognised_at"], "recognised_at"
            )

            if other_recognised > snapshot_time:
                continue

            other_price = _number(
                other["reference_price"], "reference_price"
            )

            signed_distance = other_price - level_price

            structural_context.append({
                "level_id": other["level_id"],
                "source_structure_ids": other.get(
                    "source_structure_ids", []
                ),
                "kind": other.get("kind"),
                "reference_price": other_price,
                "signed_distance": signed_distance,
                "absolute_distance": abs(signed_distance),
                "relative_position": (
                    "above" if signed_distance > 0
                    else "below" if signed_distance < 0
                    else "same_price"
                ),
                "recognised_at": _iso(other_recognised),
                "age_hours": (
                    snapshot_time - other_recognised
                ).total_seconds() / 3600,
                "previously_contacted": (
                    other["level_id"] in first_contact_by_level
                    and first_contact_by_level[other["level_id"]]
                    < snapshot_time
                ),
            })

        completed_since_recognition = [
            timestamp
            for timestamp in candles_by_time
            if timestamp >= recognised_at
            and timestamp + interval <= snapshot_time
        ]

        completed_before_snapshot = [
            timestamp
            for timestamp in candles_by_time
            if timestamp + interval <= snapshot_time
        ]

        available_timestamps = sorted(completed_before_snapshot)

        observed_timestamp_gaps = []

        for previous_time, current_time in zip(
            available_timestamps,
            available_timestamps[1:],
        ):
            elapsed = current_time - previous_time

            if elapsed > interval:
                observed_timestamp_gaps.append({
                    "previous_candle_open": _iso(previous_time),
                    "next_candle_open": _iso(current_time),
                    "elapsed_hours": elapsed.total_seconds() / 3600,
                })

        lookbacks = {
            str(count): _market_lookback(
                candles_by_time,
                snapshot_time,
                level_price,
                count,
            )
            for count in LOOKBACKS
        }

        age_hours = (
            snapshot_time - recognised_at
        ).total_seconds() / 3600

        snapshots.append({
            "episode_id": episode["episode_id"],
            "snapshot_timestamp": _iso(snapshot_time),
            "level": {
                "level_id": level_id,
                "source_structure_ids": level.get(
                    "source_structure_ids", []
                ),
                "kind": level.get("kind"),
                "reference_price": level_price,
                "anchor_timestamp": level.get("anchor_timestamp"),
                "formed_at": level.get("formed_at"),
                "recognised_at": _iso(recognised_at),
                "age_hours": age_hours,
                "completed_h4_candles_since_recognition": len(
                    completed_since_recognition
                ),
            },
            "previous_interaction_count": len(previous_episodes),
            "previous_interaction_aggregates": (
                previous_interaction_aggregates
            ),
            "previous_interactions": previous_interactions,
            "previous_reactions": previous_reactions,
            "structural_context": structural_context,
            "market_context": lookbacks,
            "data_quality": {
                "snapshot_valid": True,
                "input_h4_candle_count": len(candles_by_time),
                "completed_h4_candles_at_snapshot": len(
                    completed_before_snapshot
                ),
                "observed_timestamp_gaps": observed_timestamp_gaps,
                "snapshot_precedes_contact_candle": True,
                "lookback_completeness": {
                    key: value["complete"]
                    for key, value in lookbacks.items()
                },
                "previous_interaction_count": len(previous_episodes),
                "previous_reaction_records_available": sum(
                    item["status"] == "reaction_record_available"
                    for item in previous_reactions
                ),
            },
        })

    return {
        "evidence_version": "precontact-evidence-v0.2",
        "dataset_id": catalogue.get("dataset_id"),
        "symbol": symbol,
        "timeframe": timeframe,
        "level_count": len(levels),
        "interaction_episode_count": len(episodes),
        "snapshot_count": len(snapshots),
        "snapshots": snapshots,
    }
