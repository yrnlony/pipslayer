
"""Research-only measurement of price reactions after MSNR level interactions."""

from __future__ import annotations

from datetime import timedelta
from math import isfinite
from typing import Any, Iterable, Mapping

from pipslayer.data.candles import Candle, TIMEFRAME_MINUTES


REACTION_HORIZONS = (1, 2, 3, 6)


def _measure_horizon(
    *,
    candles: tuple[Candle, ...],
    start_index: int,
    horizon: int,
    level_price: float,
    kind: str,
    interval: timedelta,
) -> dict[str, Any]:
    observed = candles[start_index:start_index + horizon]
    timestamps = [c.timestamp.isoformat() for c in observed]

    expected_timestamps = [
        candles[start_index - 1].timestamp + interval * offset
        for offset in range(1, horizon + 1)
    ]

    complete = (
        len(observed) == horizon
        and all(
            candle.timestamp == expected
            for candle, expected in zip(observed, expected_timestamps)
        )
    )

    result: dict[str, Any] = {
        "horizon_candles": horizon,
        "observed_candle_count": len(observed),
        "complete": complete,
        "observed_timestamps": timestamps,
        "first_return_timestamp": None,
        "candles_until_return": None,
        "favourable_excursion": None,
        "adverse_excursion": None,
        "ending_close": None,
        "ending_close_position": None,
        "ending_close_displacement": None,
    }

    # Do not calculate a supposedly fixed-time horizon from incomplete data.
    if not complete:
        return result

    if kind == "V":
        favourable = max(
            max(0.0, candle.high - level_price)
            for candle in observed
        )
        adverse = max(
            max(0.0, level_price - candle.low)
            for candle in observed
        )
        close_displacement = observed[-1].close - level_price
    else:
        favourable = max(
            max(0.0, level_price - candle.low)
            for candle in observed
        )
        adverse = max(
            max(0.0, candle.high - level_price)
            for candle in observed
        )
        close_displacement = level_price - observed[-1].close

    for offset, candle in enumerate(observed, start=1):
        if candle.low <= level_price <= candle.high:
            result["first_return_timestamp"] = candle.timestamp.isoformat()
            result["candles_until_return"] = offset
            break

    ending_close = observed[-1].close

    result.update({
        "favourable_excursion": favourable,
        "adverse_excursion": adverse,
        "ending_close": ending_close,
        "ending_close_position": (
            "above" if ending_close > level_price
            else "below" if ending_close < level_price
            else "at"
        ),
        "ending_close_displacement": close_displacement,
    })

    return result


def build_reaction_report(
    candles: Iterable[Candle],
    catalogue: Mapping[str, Any],
    interaction_report: Mapping[str, Any],
) -> dict[str, Any]:
    """Measure post-interaction price behaviour at fixed candle horizons."""

    rows = tuple(candles)

    if not rows:
        raise ValueError("Cannot analyse an empty candle sequence")

    symbol = rows[0].symbol
    timeframe = rows[0].timeframe

    if timeframe not in TIMEFRAME_MINUTES:
        raise ValueError(f"Unsupported timeframe: {timeframe}")

    if catalogue["symbol"] != symbol:
        raise ValueError("Catalogue symbol does not match candle data")

    if catalogue["timeframe"] != timeframe:
        raise ValueError("Catalogue timeframe does not match candle data")

    if interaction_report["symbol"] != symbol:
        raise ValueError("Interaction report symbol does not match candle data")

    if interaction_report["timeframe"] != timeframe:
        raise ValueError("Interaction report timeframe does not match candle data")

    for index, candle in enumerate(rows):
        if candle.symbol != symbol or candle.timeframe != timeframe:
            raise ValueError("Mixed symbol/timeframe in candle sequence")

        if index and candle.timestamp <= rows[index - 1].timestamp:
            raise ValueError("Candles must be unique and chronological")

    levels = {
        level["level_id"]: level
        for level in catalogue["levels"]
    }

    if len(levels) != len(catalogue["levels"]):
        raise ValueError("Duplicate level IDs in catalogue")

    candle_index = {
        candle.timestamp: index
        for index, candle in enumerate(rows)
    }

    interval = timedelta(minutes=TIMEFRAME_MINUTES[timeframe])
    reactions: list[dict[str, Any]] = []

    for episode in interaction_report["episodes"]:
        level_id = episode["level_id"]

        if level_id not in levels:
            raise ValueError(f"Unknown level in interaction report: {level_id}")

        level = levels[level_id]
        kind = level["kind"]

        if kind not in ("A", "V"):
            raise ValueError(f"Invalid level kind: {kind}")

        price = level["reference_price"]

        if (
            not isinstance(price, (int, float))
            or isinstance(price, bool)
            or not isfinite(price)
        ):
            raise ValueError(f"Invalid reference price: {level_id}")

        last_contact = episode["last_contact_timestamp"]

        from datetime import datetime
        last_contact_time = datetime.fromisoformat(
            last_contact.replace("Z", "+00:00")
        )

        if last_contact_time not in candle_index:
            raise ValueError(
                f"Episode's last contact candle is missing: {episode['episode_id']}"
            )

        last_index = candle_index[last_contact_time]
        start_index = last_index + 1

        horizons = {
            str(horizon): _measure_horizon(
                candles=rows,
                start_index=start_index,
                horizon=horizon,
                level_price=price,
                kind=kind,
                interval=interval,
            )
            for horizon in REACTION_HORIZONS
        }

        reactions.append({
            "episode_id": episode["episode_id"],
            "level_id": level_id,
            "source_structure_ids": episode["source_structure_ids"],
            "kind": kind,
            "reference_price": price,
            "last_contact_timestamp": last_contact,
            "expected_reaction_direction": (
                "upward" if kind == "V" else "downward"
            ),
            "horizons": horizons,
        })

    return {
        "reaction_version": "level-reactions-v0.1",
        "dataset_id": interaction_report.get("dataset_id"),
        "symbol": symbol,
        "timeframe": timeframe,
        "episode_count": len(reactions),
        "horizons": list(REACTION_HORIZONS),
        "reactions": reactions,
    }
