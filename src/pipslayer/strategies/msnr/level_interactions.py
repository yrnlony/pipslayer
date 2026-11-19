"""Research-only detection of historical interactions with MSNR levels."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping

from pipslayer.data.candles import Candle, TIMEFRAME_MINUTES


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Level timestamps must be timezone-aware")

    return parsed.astimezone(timezone.utc)


def _close_position(close: float, level: float) -> str:
    if close > level:
        return "above"
    if close < level:
        return "below"
    return "at"


def _approach_direction(
    first_contact: Candle,
    candles_by_time: Mapping[datetime, Candle],
    interval: timedelta,
    level: float,
) -> str:
    previous_time = first_contact.timestamp - interval
    previous = candles_by_time.get(previous_time)

    if previous is None:
        return "unknown"

    if previous.close > level:
        return "from_above"
    if previous.close < level:
        return "from_below"
    return "unknown"


def _make_episode(
    level: Mapping[str, Any],
    episode_number: int,
    episode_candles: list[Candle],
    approach_direction: str,
) -> dict[str, Any]:
    price = level["reference_price"]

    closes = [
        _close_position(candle.close, price)
        for candle in episode_candles
    ]

    return {
        "episode_id": f"{level['level_id']}-interaction-{episode_number:03d}",
        "level_id": level["level_id"],
        "source_structure_ids": level["source_structure_ids"],
        "reference_price": price,
        "approach_direction": approach_direction,
        "first_contact_timestamp": episode_candles[0].timestamp.isoformat(),
        "last_contact_timestamp": episode_candles[-1].timestamp.isoformat(),
        "contact_candle_count": len(episode_candles),
        "contact_timestamps": [
            candle.timestamp.isoformat() for candle in episode_candles
        ],
        "maximum_price_above_level": max(
            max(0.0, candle.high - price) for candle in episode_candles
        ),
        "maximum_price_below_level": max(
            max(0.0, price - candle.low) for candle in episode_candles
        ),
        "close_positions": {
            "above": closes.count("above"),
            "below": closes.count("below"),
            "at": closes.count("at"),
        },
        "ending_close_position": closes[-1],
    }


def build_interaction_report(
    candles: Iterable[Candle],
    catalogue: Mapping[str, Any],
) -> dict[str, Any]:
    """Detect exact-price contact episodes without assigning significance."""

    candle_rows = tuple(candles)

    if not candle_rows:
        raise ValueError("Cannot analyse an empty candle sequence")

    symbol = candle_rows[0].symbol
    timeframe = candle_rows[0].timeframe

    if timeframe not in TIMEFRAME_MINUTES:
        raise ValueError(f"Unsupported timeframe: {timeframe}")

    if catalogue["symbol"] != symbol:
        raise ValueError("Catalogue symbol does not match candle data")

    if catalogue["timeframe"] != timeframe:
        raise ValueError("Catalogue timeframe does not match candle data")

    for index, candle in enumerate(candle_rows):
        if candle.symbol != symbol or candle.timeframe != timeframe:
            raise ValueError("Mixed symbol/timeframe in candle sequence")

        if index:
            previous = candle_rows[index - 1]
            if candle.timestamp <= previous.timestamp:
                raise ValueError(
                    "Candles must be unique and in chronological order"
                )

    interval = timedelta(minutes=TIMEFRAME_MINUTES[timeframe])
    candles_by_time = {candle.timestamp: candle for candle in candle_rows}

    episodes: list[dict[str, Any]] = []

    for level in catalogue["levels"]:
        price = level["reference_price"]
        recognised_at = _parse_timestamp(level["recognised_at"])

        if not isinstance(price, (int, float)) or isinstance(price, bool):
            raise ValueError(f"Invalid reference price: {level['level_id']}")

        eligible = [
            candle for candle in candle_rows
            if candle.timestamp >= recognised_at
        ]

        active_episode: list[Candle] = []
        episode_number = 0

        def finish_episode() -> None:
            nonlocal episode_number, active_episode

            if not active_episode:
                return

            episode_number += 1
            direction = _approach_direction(
                active_episode[0],
                candles_by_time,
                interval,
                price,
            )

            episodes.append(
                _make_episode(
                    level,
                    episode_number,
                    active_episode,
                    direction,
                )
            )
            active_episode = []

        for candle in eligible:
            contacts_level = candle.low <= price <= candle.high

            if not contacts_level:
                finish_episode()
                continue

            if active_episode:
                expected_next = active_episode[-1].timestamp + interval

                if candle.timestamp != expected_next:
                    finish_episode()

            active_episode.append(candle)

        finish_episode()

    return {
        "interaction_version": "level-interactions-v0.1",
        "dataset_id": catalogue.get("dataset_id"),
        "symbol": symbol,
        "timeframe": timeframe,
        "level_count": catalogue["level_count"],
        "interaction_episode_count": len(episodes),
        "episodes": episodes,
    }
