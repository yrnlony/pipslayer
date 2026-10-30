"""Read-only verification for published dataset artifacts."""
from __future__ import annotations
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from .candles import Candle, parse_utc_timestamp, validate_candles
from .canonical import dataset_id as make_dataset_id
from .canonical import canonical_sha256


def verify_dataset(manifest_path: str | Path) -> dict[str, Any]:
    path = Path(manifest_path).resolve()
    root = path.parent
    result: dict[str, Any] = {"manifest": str(path), "valid": False, "errors": []}
    if not path.is_file():
        result["errors"].append("manifest_missing")
        return result
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        result["errors"].append(f"manifest_unreadable: {exc}")
        return result
    if manifest.get("schema_version") != 2:
        result["errors"].append("unsupported_or_legacy_manifest_schema")
        return result
    if manifest.get("canonicalization_version") != "candle-canon-v1":
        result["errors"].append("unsupported_canonicalization_version")
        return result
    normalized_name = manifest.get("normalized_file_name", "")
    if not normalized_name or Path(normalized_name).name != normalized_name:
        result["errors"].append("invalid_normalized_file_name")
        return result
    normalized = root / normalized_name
    report_path = root / f"{path.name.removesuffix('.manifest.json')}.quality-report.json"
    stem = path.name.removesuffix(".manifest.json")
    journal = root / f".pipslayer-journal-{stem}.json"
    if journal.exists():
        result["errors"].append("pending_publication_journal")
    if not normalized.is_file():
        result["errors"].append("normalized_file_missing")
        result["valid"] = False
        return result
    normalized_hash = hashlib.sha256(normalized.read_bytes()).hexdigest()
    if normalized_hash != manifest.get("normalized_file_sha256"):
        result["errors"].append("normalized_file_hash_mismatch")
    if not report_path.is_file():
        result["errors"].append("quality_report_missing")
    else:
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
            if report.get("run_id") != manifest.get("run_id"):
                result["errors"].append("report_manifest_run_id_mismatch")
            if report.get("accepted") is not True:
                result["errors"].append("live_quality_report_not_accepted")
        except (OSError, ValueError):
            result["errors"].append("quality_report_unreadable")
    try:
        candles = []
        with normalized.open("r", encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                candles.append(Candle(
                    symbol=row["symbol"], timeframe=row["timeframe"], timestamp=parse_utc_timestamp(row["timestamp"]),
                    open=float(row["open"]), high=float(row["high"]), low=float(row["low"]), close=float(row["close"]),
                    volume=None if row.get("volume", "") == "" else float(row["volume"]), source=row.get("source") or None,
                ))
        if any(c.symbol != manifest.get("symbol") or c.timeframe != manifest.get("timeframe") for c in candles):
            result["errors"].append("normalized_symbol_or_timeframe_mismatch")
        sequence = validate_candles(candles)
        if not sequence.is_valid:
            result["errors"].append("normalized_sequence_invalid")
        digest = canonical_sha256(candles, symbol=manifest["symbol"], timeframe=manifest["timeframe"])
        if digest != manifest.get("canonical_content_sha256"):
            result["errors"].append("canonical_content_hash_mismatch")
        expected_id = make_dataset_id(manifest["symbol"], manifest["timeframe"], digest)
        if expected_id != manifest.get("dataset_id"):
            result["errors"].append("dataset_id_mismatch")
        if len(candles) != manifest.get("row_count"):
            result["errors"].append("row_count_mismatch")
    except (KeyError, TypeError, ValueError, OSError) as exc:
        result["errors"].append(f"normalized_data_unreadable: {exc}")
    result["valid"] = not result["errors"]
    result["dataset_id"] = manifest.get("dataset_id")
    result["row_count"] = manifest.get("row_count")
    return result
