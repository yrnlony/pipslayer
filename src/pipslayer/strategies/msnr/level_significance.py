"""Research-only catalogue of MSNR candidate levels."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Mapping


def _validate_timestamp(value: str, field: str) -> None:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a timestamp string")

    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Invalid {field}: {value}") from exc

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must include a timezone")


def build_level_catalogue(
    report: Mapping[str, Any],
    *,
    symbol: str,
) -> dict[str, Any]:
    """Convert an A/V recognition report into individual level candidates."""

    if not symbol or not symbol.strip():
        raise ValueError("symbol must not be empty")

    required_report_fields = (
        "dataset_id",
        "timeframe",
        "method",
        "structure_count",
        "structures",
    )

    for field in required_report_fields:
        if field not in report:
            raise ValueError(f"Report is missing required field: {field}")

    structures = report["structures"]

    if not isinstance(structures, list):
        raise ValueError("structures must be a list")

    if len(structures) != report["structure_count"]:
        raise ValueError("structure_count does not match structures list")

    levels = []
    seen_ids = set()

    for structure in structures:
        structure_id = structure["structure_id"]

        if not isinstance(structure_id, str) or not structure_id:
            raise ValueError("Every structure needs a valid structure_id")

        if structure_id in seen_ids:
            raise ValueError(f"Duplicate structure ID: {structure_id}")

        seen_ids.add(structure_id)

        kind = structure["kind"]
        if kind not in ("A", "V"):
            raise ValueError(f"Unsupported structure kind: {kind}")

        price = structure["price"]
        if (
            isinstance(price, bool)
            or not isinstance(price, (int, float))
            or not math.isfinite(price)
        ):
            raise ValueError(f"Invalid price for {structure_id}")

        for field in ("anchor_timestamp", "formed_at", "recognised_at"):
            _validate_timestamp(structure[field], field)

        gap_context = structure.get("gap_context", {})

        levels.append({
            "level_id": f"level-{structure_id}",
            "source_structure_ids": [structure_id],
            "symbol": symbol,
            "timeframe": report["timeframe"],
            "kind": kind,
            "reference_price": price,
            "anchor_timestamp": structure["anchor_timestamp"],
            "formed_at": structure["formed_at"],
            "recognised_at": structure["recognised_at"],
            "gap_context": gap_context,
            "structural_scale": "unclassified",
            "importance_tier": "unclassified",
            "evidence": [],
            "classification_reasons": [],
            "assessment_status": "catalogued",
        })

    return {
        "catalogue_version": "level-catalogue-v1",
        "dataset_id": report["dataset_id"],
        "symbol": symbol,
        "timeframe": report["timeframe"],
        "source_method": report["method"],
        "source_structure_count": len(structures),
        "level_count": len(levels),
        "levels": levels,
    }
