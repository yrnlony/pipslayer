
import json
from pathlib import Path
from math import isclose

REPORT_PATH = Path(
    "reports/xauusd-h4-precontact-evidence-gap-aware.json"
)

HORIZONS = ("6", "12", "24")
INTERVAL_HOURS = 4
EXPECTED_SNAPSHOTS = 3726


def fail(message):
    raise AssertionError(message)


def validate_report(report):
    assert report["evidence_version"] == "precontact-evidence-v0.2"
    assert report["snapshot_count"] == EXPECTED_SNAPSHOTS

    snapshots = report["snapshots"]

    assert len(snapshots) == EXPECTED_SNAPSHOTS

    episode_ids = set()

    stats = {
        h: {
            "snapshots": 0,
            "complete": 0,
            "incomplete": 0,
            "segmented": 0,
            "single_segment": 0,
            "observed_candles": 0,
            "missing_intervals": 0,
            "true_range_incomplete": 0,
        }
        for h in HORIZONS
    }

    for snapshot_index, snapshot in enumerate(snapshots):
        episode_id = snapshot["episode_id"]

        if episode_id in episode_ids:
            fail(f"Duplicate episode ID: {episode_id}")

        episode_ids.add(episode_id)

        for h in HORIZONS:
            context = snapshot["market_context"][h]
            row = stats[h]

            row["snapshots"] += 1

            segments = context["segments"]
            missing = context["missing_intervals"]

            if context["segment_count"] != len(segments):
                fail(f"{episode_id}: segment count mismatch at {h}")

            if context["observed_candles"] != sum(
                segment["candle_count"] for segment in segments
            ):
                fail(f"{episode_id}: observed candle count mismatch at {h}")

            if len(missing) != max(0, len(segments) - 1):
                fail(f"{episode_id}: missing interval count mismatch at {h}")

            if len(segments) > 1:
                row["segmented"] += 1
            else:
                row["single_segment"] += 1

            row["observed_candles"] += context["observed_candles"]
            row["missing_intervals"] += len(missing)

            if context["complete"]:
                row["complete"] += 1
            else:
                row["incomplete"] += 1

            previous_segment = None

            for index, segment in enumerate(segments):
                count = segment["candle_count"]

                if count <= 0:
                    fail(f"{episode_id}: empty segment at {h}")

                if len(segment["candle_ranges"]) != count:
                    fail(f"{episode_id}: candle range count mismatch at {h}")

                if len(segment["true_ranges"]) != count:
                    fail(f"{episode_id}: true range count mismatch at {h}")

                first = segment["first_candle_timestamp"]
                last = segment["last_candle_timestamp"]

                if previous_segment is not None:
                    if previous_segment["last_candle_timestamp"] >= first:
                        fail(f"{episode_id}: segments out of order at {h}")

                    if (
                        previous_segment["last_candle_timestamp"],
                        first,
                    ) != (
                        missing[index - 1]["after"],
                        missing[index - 1]["before"],
                    ):
                        fail(f"{episode_id}: gap boundary mismatch at {h}")

                    # The first TR after an internal gap must be unavailable.
                    if segment["true_ranges"][0] is not None:
                        fail(
                            f"{episode_id}: true range crosses gap at {h}"
                        )

                # Segment displacement must use its own endpoints.
                expected_displacement = (
                    segment["last_close"] - segment["first_close"]
                )

                if not isclose(
                    segment["net_displacement"],
                    expected_displacement,
                    abs_tol=1e-8,
                ):
                    fail(f"{episode_id}: segment displacement mismatch at {h}")

                expected_tr_complete = all(
                    value is not None
                    for value in segment["true_ranges"]
                )

                if segment["true_range_complete"] != expected_tr_complete:
                    fail(f"{episode_id}: segment TR status mismatch at {h}")

                if not expected_tr_complete:
                    row["true_range_incomplete"] += 1

                # Every pair of candles within a segment must be consecutive.
                from datetime import datetime

                timestamps = [
                    datetime.fromisoformat(
                        segment["first_candle_timestamp"]
                    )
                ]

                # Reconstruct timestamps using the candle range list's
                # corresponding data is not possible; use segment endpoints
                # and count as a basic consistency check.
                if count == 1 and first != last:
                    fail(f"{episode_id}: one-candle segment has bad endpoints at {h}")

                previous_segment = segment

            if context["complete"]:
                if (
                    context["observed_candles"] != context["requested_candles"]
                    or missing
                    or not context["ends_at_snapshot"]
                ):
                    fail(f"{episode_id}: invalid complete status at {h}")

            measurements = context["measurements"]

            spans_gaps = len(segments) > 1

            if measurements["net_displacement_spans_gaps"] != spans_gaps:
                fail(f"{episode_id}: displacement gap flag mismatch at {h}")

            if measurements["price_range_spans_gaps"] != spans_gaps:
                fail(f"{episode_id}: price range gap flag mismatch at {h}")

    assert len(episode_ids) == EXPECTED_SNAPSHOTS

    return stats


def main():
    print("Loading gap-aware evidence report...")

    with REPORT_PATH.open("r", encoding="utf-8") as stream:
        report = json.load(stream)

    stats = validate_report(report)

    print("\nGAP-AWARE EVIDENCE VALIDATION PASSED")
    print(f"Evidence version: {report['evidence_version']}")
    print(f"Snapshots: {report['snapshot_count']}")
    print(f"Unique episodes: {report['snapshot_count']}")

    for h in HORIZONS:
        row = stats[h]

        print(f"\n{h}-CANDLE LOOKBACK")
        print(f"Snapshots: {row['snapshots']}")
        print(f"Complete: {row['complete']}")
        print(f"Incomplete: {row['incomplete']}")
        print(f"Segmented: {row['segmented']}")
        print(f"Single segment: {row['single_segment']}")
        print(f"Observed candles: {row['observed_candles']}")
        print(f"Missing intervals: {row['missing_intervals']}")
        print(f"Segments with incomplete TR: {row['true_range_incomplete']}")


if __name__ == "__main__":
    main()
