
import json
from collections import defaultdict
from pathlib import Path

path = Path("reports/xauusd-h4-precontact-evidence.json")

with path.open("r", encoding="utf-8") as f:
    report = json.load(f)

stats = defaultdict(
    lambda: {
        h: {
            "total": 0,
            "complete": 0,
            "insufficient": 0,
            "gaps": 0,
            "true_range_incomplete": 0,
            "other_incomplete": 0,
        }
        for h in ("6", "12", "24")
    }
)

for snapshot in report["snapshots"]:
    month = snapshot["snapshot_timestamp"][:7]

    for h in ("6", "12", "24"):
        context = snapshot["market_context"][h]
        measurements = context["measurements"]
        row = stats[month][h]

        row["total"] += 1

        if context["complete"]:
            row["complete"] += 1
            continue

        if context["observed_candles"] < context["requested_candles"]:
            row["insufficient"] += 1

        if context["missing_intervals"]:
            row["gaps"] += 1

        if not measurements["true_range_complete"]:
            row["true_range_incomplete"] += 1

        if (
            context["observed_candles"] == context["requested_candles"]
            and not context["missing_intervals"]
            and measurements["true_range_complete"]
        ):
            row["other_incomplete"] += 1

print("\nINCOMPLETE LOOKBACK DIAGNOSTICS")
print("Reason counts can overlap.")
print("-" * 85)

for month in sorted(stats):
    print(f"\n{month}")

    for h in ("6", "12", "24"):
        r = stats[month][h]
        print(
            f"{h:>2} | total={r['total']:4} "
            f"complete={r['complete']:4} "
            f"insufficient={r['insufficient']:4} "
            f"gaps={r['gaps']:4} "
            f"TR-incomplete={r['true_range_incomplete']:4} "
            f"other={r['other_incomplete']:4}"
        )
