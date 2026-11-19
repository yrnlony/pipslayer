
"""Summarise H4 pre-contact snapshot completeness by month."""

import json
from collections import defaultdict
from pathlib import Path

REPORT = Path("reports/xauusd-h4-precontact-evidence.json")

with REPORT.open("r", encoding="utf-8") as file:
    report = json.load(file)

monthly = defaultdict(
    lambda: {
        "snapshots": 0,
        "six": 0,
        "twelve": 0,
        "twentyfour": 0,
    }
)

for snapshot in report["snapshots"]:
    month = snapshot["snapshot_timestamp"][:7]
    row = monthly[month]

    row["snapshots"] += 1

    context = snapshot["market_context"]

    if context["6"]["complete"]:
        row["six"] += 1

    if context["12"]["complete"]:
        row["twelve"] += 1

    if context["24"]["complete"]:
        row["twentyfour"] += 1

print("\nH4 SNAPSHOT COMPLETENESS BY MONTH")
print("-" * 75)
print(
    f"{'Month':<10}"
    f"{'Snapshots':>12}"
    f"{'6 Complete':>14}"
    f"{'12 Complete':>15}"
    f"{'24 Complete':>15}"
)
print("-" * 75)

for month in sorted(monthly):
    row = monthly[month]
    print(
        f"{month:<10}"
        f"{row['snapshots']:>12}"
        f"{row['six']:>14}"
        f"{row['twelve']:>15}"
        f"{row['twentyfour']:>15}"
    )

print("-" * 75)
print(f"Total snapshots: {len(report['snapshots'])}")
