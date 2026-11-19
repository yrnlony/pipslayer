
import csv
import json
from datetime import datetime, timedelta
from math import isclose
from pathlib import Path
from statistics import mean, median


CSV_PATH = Path(
    "data/mt5-headway-xauusd-h4-2026-05-to-2026-11/"
    "audit/XAUUSD_H4_mt5_raw.normalized.csv"
)

REPORT_PATH = Path(
    "reports/xauusd-h4-precontact-evidence-gap-aware.json"
)

HORIZONS = (6, 12, 24)
INTERVAL = timedelta(hours=4)
EXPECTED_CSV_ROWS = 816
EXPECTED_COMPLETED_ROWS = 815
EXPECTED_SNAPSHOTS = 3726


def parse_time(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def iso(value):
    return value.isoformat()

def direction(value):
    if value > 0:
        return "upward"
    if value < 0:
        return "downward"
    return "unchanged"

def close_enough(actual, expected):
    return isclose(
        float(actual),
        float(expected),
        rel_tol=1e-9,
        abs_tol=1e-7,
    )


def compare(actual, expected, path):
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            raise AssertionError(f"{path}: expected object")

        if set(actual) != set(expected):
            raise AssertionError(
                f"{path}: key mismatch\n"
                f"Actual: {set(actual)}\n"
                f"Expected: {set(expected)}"
            )

        for key in expected:
            compare(actual[key], expected[key], f"{path}.{key}")

        return

    if isinstance(expected, list):
        if not isinstance(actual, list):
            raise AssertionError(f"{path}: expected list")

        if len(actual) != len(expected):
            raise AssertionError(
                f"{path}: list length mismatch "
                f"{len(actual)} != {len(expected)}"
            )

        for index, (a, e) in enumerate(zip(actual, expected)):
            compare(a, e, f"{path}[{index}]")

        return

    if isinstance(expected, bool):
        if actual is not expected:
            raise AssertionError(f"{path}: {actual} != {expected}")
        return

    if expected is None:
        if actual is not None:
            raise AssertionError(f"{path}: expected None, got {actual}")
        return

    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        if not close_enough(actual, expected):
            raise AssertionError(
                f"{path}: {actual} != {expected}"
            )
        return

    if actual != expected:
        raise AssertionError(f"{path}: {actual!r} != {expected!r}")


def load_candles():
    with CSV_PATH.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as stream:
        rows = list(csv.DictReader(stream))

    if len(rows) != EXPECTED_CSV_ROWS:
        raise AssertionError(
            f"CSV row count changed: {len(rows)}"
        )

    # The final row is the manifest-flagged incomplete H4 candle.
    completed_rows = rows[:-1]

    if len(completed_rows) != EXPECTED_COMPLETED_ROWS:
        raise AssertionError("Unexpected completed candle count")

    candles = {}

    for row in completed_rows:
        timestamp = parse_time(row["timestamp"])

        if timestamp in candles:
            raise AssertionError(
                f"Duplicate canonical timestamp: {timestamp}"
            )

        candles[timestamp] = {
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
        }

    return candles


def reconstruct_lookback(candles, snapshot_time, level_price, count):
    eligible_times = sorted(
        timestamp
        for timestamp in candles
        if timestamp + INTERVAL <= snapshot_time
    )

    selected_times = eligible_times[-count:]

    if not selected_times:
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

    selected = [candles[t] for t in selected_times]

    missing = []
    boundaries = [0]

    for index in range(1, len(selected_times)):
        previous = selected_times[index - 1]
        current = selected_times[index]

        if current - previous != INTERVAL:
            missing.append({
                "after": iso(previous),
                "before": iso(current),
                "missing_hours": (
                    current - previous
                ).total_seconds() / 3600 - 4,
            })
            boundaries.append(index)

    boundaries.append(len(selected_times))

    segments = []

    for segment_index in range(len(boundaries) - 1):
        start = boundaries[segment_index]
        end = boundaries[segment_index + 1]

        times = selected_times[start:end]
        group = selected[start:end]

        highs = [c["high"] for c in group]
        lows = [c["low"] for c in group]
        ranges = [
            c["high"] - c["low"]
            for c in group
        ]

        true_ranges = []

        for local_index, candle in enumerate(group):
            previous_close = None

            if local_index > 0:
                previous_close = group[local_index - 1]["close"]

            elif start == 0:
                previous_time = times[0] - INTERVAL
                previous_candle = candles.get(previous_time)

                if previous_candle is not None:
                    previous_close = previous_candle["close"]

            if previous_close is None:
                true_ranges.append(None)
                continue

            true_ranges.append(max(
                candle["high"] - candle["low"],
                abs(candle["high"] - previous_close),
                abs(candle["low"] - previous_close),
            ))

        valid_tr = [
            value for value in true_ranges
            if value is not None
        ]

        first_close = group[0]["close"]
        last_close = group[-1]["close"]
        displacement = last_close - first_close

        segments.append({
            "segment_index": segment_index,
            "candle_count": len(group),
            "first_candle_timestamp": iso(times[0]),
            "last_candle_timestamp": iso(times[-1]),
            "highest_high": max(highs),
            "lowest_low": min(lows),
            "price_range": max(highs) - min(lows),
            "candle_ranges": ranges,
            "mean_candle_range": mean(ranges),
            "median_candle_range": median(ranges),
            "true_ranges": true_ranges,
            "mean_true_range": (
                mean(valid_tr) if valid_tr else None
            ),
            "median_true_range": (
                median(valid_tr) if valid_tr else None
            ),
            "true_range_complete": len(valid_tr) == len(true_ranges),
            "first_close": first_close,
            "last_close": last_close,
            "net_displacement": displacement,
            "direction": direction(displacement),
        })

    highs = [c["high"] for c in selected]
    lows = [c["low"] for c in selected]
    ranges = [
        c["high"] - c["low"]
        for c in selected
    ]

    true_ranges = [
        value
        for segment in segments
        for value in segment["true_ranges"]
    ]

    valid_tr = [
        value for value in true_ranges
        if value is not None
    ]

    first_close = selected[0]["close"]
    last_close = selected[-1]["close"]
    displacement = last_close - first_close

    last_close_time = selected_times[-1] + INTERVAL
    ends_at_snapshot = last_close_time == snapshot_time

    complete = (
        len(selected) == count
        and not missing
        and ends_at_snapshot
    )

    measurements = {
        "first_candle_timestamp": iso(selected_times[0]),
        "last_candle_timestamp": iso(selected_times[-1]),
        "highest_high": max(highs),
        "lowest_low": min(lows),
        "price_range": max(highs) - min(lows),
        "candle_ranges": ranges,
        "mean_candle_range": mean(ranges),
        "median_candle_range": median(ranges),
        "true_ranges": true_ranges,
        "mean_true_range": mean(valid_tr) if valid_tr else None,
        "median_true_range": median(valid_tr) if valid_tr else None,
        "true_range_complete": len(valid_tr) == len(true_ranges),
        "first_close": first_close,
        "last_close": last_close,
        "net_displacement": displacement,
        "direction": direction(displacement),
        "latest_close": last_close,
        "latest_close_signed_distance_to_level": (
            last_close - level_price
        ),
        "latest_close_absolute_distance_to_level": abs(
            last_close - level_price
        ),
        "net_displacement_spans_gaps": bool(missing),
        "price_range_spans_gaps": bool(missing),
    }

    return {
        "requested_candles": count,
        "observed_candles": len(selected),
        "complete": complete,
        "status": "complete" if complete else "incomplete",
        "missing_intervals": missing,
        "segment_count": len(segments),
        "segments": segments,
        "ends_at_snapshot": ends_at_snapshot,
        "last_candle_close_time": iso(last_close_time),
        "time_since_last_candle_close_hours": (
            snapshot_time - last_close_time
        ).total_seconds() / 3600,
        "measurements": measurements,
    }


def main():
    print("Loading canonical H4 candles...")
    candles = load_candles()

    print(f"Completed canonical candles: {len(candles)}")

    print("\nLoading pre-contact evidence...")
    with REPORT_PATH.open("r", encoding="utf-8") as stream:
        report = json.load(stream)

    if report["evidence_version"] != "precontact-evidence-v0.2":
        raise AssertionError("Unexpected evidence version")

    if report["snapshot_count"] != EXPECTED_SNAPSHOTS:
        raise AssertionError("Unexpected snapshot count")

    if len(report["snapshots"]) != EXPECTED_SNAPSHOTS:
        raise AssertionError("Snapshot list length mismatch")

    checks = 0

    print("\nReconstructing all lookbacks from canonical candles...")

    for index, snapshot in enumerate(report["snapshots"]):
        snapshot_time = parse_time(snapshot["snapshot_timestamp"])
        level_price = float(snapshot["level"]["reference_price"])

        for count in HORIZONS:
            expected = reconstruct_lookback(
                candles,
                snapshot_time,
                level_price,
                count,
            )

            actual = snapshot["market_context"][str(count)]

            compare(
                actual,
                expected,
                f"snapshot[{index}].market_context[{count}]",
            )

            checks += 1

        if (index + 1) % 500 == 0:
            print(f"Verified snapshots: {index + 1}")

    print("\n" + "=" * 60)
    print("INDEPENDENT CANONICAL VERIFICATION PASSED")
    print("=" * 60)
    print(f"Evidence version: {report['evidence_version']}")
    print(f"Canonical completed candles: {len(candles)}")
    print(f"Snapshots verified: {len(report['snapshots'])}")
    print(f"Lookback comparisons passed: {checks}")
    print("Horizons: 6, 12 and 24 H4 candles")
    print("OHLC measurements: verified")
    print("Segment boundaries: verified")
    print("True Range calculations: verified")
    print("Snapshot-time eligibility: verified")
    print("Future candle exclusion: verified")


if __name__ == "__main__":
    main()
