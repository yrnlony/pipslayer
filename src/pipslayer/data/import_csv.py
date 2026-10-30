"""Validated CSV import with canonical identity and recoverable publication."""
from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path
import uuid
from typing import Any

from .candles import Candle, TIMEFRAME_MINUTES, parse_utc_timestamp, validate_candles
from .canonical import canonical_sha256, canonicalization_self_test, dataset_id as make_dataset_id
from .last_bar import assess_last_bar
from .manifest import DatasetManifest, TimestampSemantics
from .outputs import publish_dataset, sha256_bytes
from .timeframe_check import TimeframeCheckPolicy, assess_timeframe_spacing, policy_record

REQUIRED_COLUMNS = {"timestamp", "open", "high", "low", "close"}
OUTPUT_COLUMNS = ["timestamp", "symbol", "timeframe", "open", "high", "low", "close", "volume", "source"]


@dataclass(frozen=True)
class ImportIssue:
    row: int
    code: str
    message: str


@dataclass(frozen=True)
class ImportResult:
    input_path: str
    input_sha256: str
    symbol: str
    timeframe: str
    source_name: str
    input_rows: int
    parsed_rows: int
    errors: tuple[ImportIssue, ...]
    duplicate_timestamps: tuple[str, ...]
    out_of_order_pairs: tuple[str, ...]
    gaps: tuple[str, ...]
    output_csv: str | None
    manifest_json: str | None
    report_json: str
    accepted: bool
    dataset_id: str | None = None
    canonical_content_sha256: str | None = None
    normalized_file_sha256: str | None = None
    run_id: str = ""
    unchanged: bool = False
    superseded_dir: str | None = None
    timeframe_check: dict[str, Any] | None = None
    last_bar: dict[str, Any] | None = None
    excluded_rows: int = 0


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _float_cell(value: str, *, row: int, column: str, required: bool = True) -> float | None:
    cleaned = value.strip()
    if not cleaned and not required:
        return None
    if not cleaned:
        raise ValueError(f"row {row}: '{column}' is required")
    try:
        number = float(cleaned)
    except ValueError as exc:
        raise ValueError(f"row {row}: '{column}' must be numeric") from exc
    if not math.isfinite(number):
        raise ValueError(f"row {row}: '{column}' must be finite")
    return number


def _normalized_csv_bytes(candles: list[Candle]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=OUTPUT_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for candle in candles:
        writer.writerow({
            "timestamp": candle.timestamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "symbol": candle.symbol, "timeframe": candle.timeframe,
            "open": candle.open, "high": candle.high, "low": candle.low, "close": candle.close,
            "volume": "" if candle.volume is None else candle.volume,
            "source": candle.source or "",
        })
    return stream.getvalue().encode("utf-8")


def _atomic_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    data = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    with temp.open("wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)


def import_canonical_csv(
    input_path: str | Path,
    output_dir: str | Path,
    *,
    symbol: str,
    timeframe: str,
    source_name: str,
    source_notes: str = "",
    expected_interval: timedelta | None = None,
    synthetic: bool = False,
    timeframe_check: str = "report-only",
    timeframe_policy: TimeframeCheckPolicy | None = None,
    timeframe_policy_source: str = "default",
    last_bar_policy: str = "flag",
    data_as_of: datetime | None = None,
) -> ImportResult:
    """Parse and validate CSV bytes once, then safely publish accepted datasets.

    A rejected replacement writes a separate report and never displaces a live,
    accepted dataset. CSV timestamps require explicit offsets; broker-clock
    semantics remain unverified.
    """
    source_path = Path(input_path).expanduser().resolve()
    destination = Path(output_dir).expanduser().resolve()
    if not source_path.is_file():
        raise FileNotFoundError(f"Input CSV not found: {source_path}")
    if not symbol.strip() or not source_name.strip():
        raise ValueError("symbol and source_name must not be blank")
    pending_journal = destination / f".pipslayer-journal-{source_path.stem}.json"
    if pending_journal.exists():
        raise RuntimeError(f"Pending output journal exists: {pending_journal}; run recover-outputs first")
    timeframe = timeframe.strip().upper()
    if timeframe not in TIMEFRAME_MINUTES:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    if timeframe_check not in {"report-only", "enforce"}:
        raise ValueError("timeframe_check must be 'report-only' or 'enforce'")
    if last_bar_policy not in {"flag", "exclude-if-possibly-incomplete"}:
        raise ValueError("unsupported last_bar_policy")
    if expected_interval is not None and expected_interval <= timedelta(0):
        raise ValueError("expected_interval must be positive")

    # Read original bytes once: all parsing and source provenance use this snapshot.
    source_bytes = source_path.read_bytes()
    source_hash = _sha256_bytes(source_bytes)
    try:
        text = source_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(f"Input CSV must be UTF-8 encoded: {exc}") from exc

    row_issues: list[ImportIssue] = []
    candles: list[Candle] = []
    input_rows = 0
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if reader.fieldnames is None:
        raise ValueError("CSV is empty or has no header row")
    headers = {name.strip().lower() for name in reader.fieldnames if name is not None}
    missing = sorted(REQUIRED_COLUMNS - headers)
    if missing:
        raise ValueError("CSV missing required columns: " + ", ".join(missing))
    has_volume = "volume" in headers
    for row_number, raw in enumerate(reader, start=2):
        input_rows += 1
        normalized = {(key or "").strip().lower(): (value or "") for key, value in raw.items() if key is not None}
        try:
            timestamp_text = normalized.get("timestamp", "").strip()
            if not timestamp_text:
                raise ValueError(f"row {row_number}: 'timestamp' is required")
            try:
                timestamp = parse_utc_timestamp(timestamp_text)
            except (ValueError, TypeError) as exc:
                raise ValueError(f"row {row_number}: timestamp must be ISO-8601 with an explicit timezone/UTC offset ({exc})") from exc
            candle = Candle(
                symbol=symbol.strip(), timeframe=timeframe, timestamp=timestamp,
                open=float(_float_cell(normalized.get("open", ""), row=row_number, column="open")),
                high=float(_float_cell(normalized.get("high", ""), row=row_number, column="high")),
                low=float(_float_cell(normalized.get("low", ""), row=row_number, column="low")),
                close=float(_float_cell(normalized.get("close", ""), row=row_number, column="close")),
                volume=_float_cell(normalized.get("volume", ""), row=row_number, column="volume", required=False) if has_volume else None,
                source=source_name.strip(),
            )
            candles.append(candle)
        except (ValueError, OverflowError) as exc:
            row_issues.append(ImportIssue(row=row_number, code="row_invalid", message=str(exc)))

    validation = validate_candles(candles, expected_interval=expected_interval)
    row_issues.extend(ImportIssue(0, "sequence_invalid", error) for error in validation.errors)
    row_issues.extend(ImportIssue(0, "duplicate_timestamp", value) for value in validation.duplicate_timestamps)
    row_issues.extend(ImportIssue(0, "out_of_order", value) for value in validation.out_of_order_pairs)
    policy = timeframe_policy or TimeframeCheckPolicy()
    tf_result = assess_timeframe_spacing(candles, policy)
    tf_record = {**tf_result, "mode": timeframe_check, "policy": policy_record(policy, timeframe_policy_source)}
    if timeframe_check == "enforce" and tf_result["status"] == "conflicts":
        row_issues.append(ImportIssue(0, "timeframe_conflict", "Observed spacing conflicts with the declared timeframe under the configured provisional policy"))

    last_bar = assess_last_bar(candles, data_as_of=data_as_of)
    kept_candles = list(candles)
    excluded_rows = 0
    if last_bar_policy == "exclude-if-possibly-incomplete" and last_bar["status"] == "possibly_incomplete" and kept_candles:
        kept_candles.pop()
        excluded_rows = 1
    if not kept_candles:
        row_issues.append(ImportIssue(0, "empty_dataset", "No candles remain after validation and last-bar policy"))

    if input_rows == 0:
        row_issues.append(ImportIssue(0, "empty_dataset", "CSV contains no candle rows"))
    accepted = not row_issues and input_rows > 0 and bool(kept_candles)
    destination.mkdir(parents=True, exist_ok=True)
    stem = source_path.stem
    live_normalized = destination / f"{stem}.normalized.csv"
    live_manifest = destination / f"{stem}.manifest.json"
    live_report = destination / f"{stem}.quality-report.json"
    run_id = uuid.uuid4().hex
    output_path: Path | None = None
    manifest_path: Path | None = None
    dataset_hash: str | None = None
    normalized_hash: str | None = None
    dataset_key: str | None = None
    superseded_dir: str | None = None
    unchanged = False

    if accepted:
        canonicalization_self_test()
        try:
            dataset_hash = canonical_sha256(kept_candles, symbol=symbol.strip(), timeframe=timeframe)
        except ValueError as exc:
            # The canonicalizer's row-indexed diagnostic is preserved as an import issue.
            row_issues.append(ImportIssue(0, "canonicalization_unsupported", str(exc)))
            accepted = False
        if accepted:
            dataset_key = make_dataset_id(symbol.strip(), timeframe, dataset_hash)
            normalized_bytes = _normalized_csv_bytes(kept_candles)
            normalized_hash = _sha256_bytes(normalized_bytes)
            # Exact same logical dataset and normalized bytes are a no-op if current output verifies.
            if live_manifest.is_file() and live_normalized.is_file() and live_report.is_file():
                try:
                    existing_manifest = json.loads(live_manifest.read_text(encoding="utf-8"))
                    existing_report = json.loads(live_report.read_text(encoding="utf-8"))
                    existing_bytes = live_normalized.read_bytes()
                    from .verify import verify_dataset
                    current_verification = verify_dataset(live_manifest)
                    if (current_verification["valid"]
                            and existing_manifest.get("dataset_id") == dataset_key
                            and existing_manifest.get("canonical_content_sha256") == dataset_hash
                            and existing_manifest.get("normalized_file_sha256") == _sha256_bytes(existing_bytes)
                            and _sha256_bytes(existing_bytes) == normalized_hash
                            and existing_report.get("run_id") == existing_manifest.get("run_id")):
                        unchanged = True
                        run_id = existing_manifest["run_id"]
                        output_path, manifest_path = live_normalized, live_manifest
                except (OSError, ValueError, KeyError):
                    unchanged = False
            if not unchanged:
                output_path = live_normalized
                manifest_path = live_manifest
                report_payload = _report_payload(
                    accepted=True, run_id=run_id, input_path=str(source_path), input_hash=source_hash,
                    symbol=symbol.strip(), timeframe=timeframe, source_name=source_name.strip(),
                    input_rows=input_rows, parsed_rows=len(candles), kept_rows=len(kept_candles),
                    errors=row_issues, validation=validation, output_csv=str(live_normalized),
                    manifest_json=str(live_manifest), dataset_key=dataset_key, dataset_hash=dataset_hash,
                    normalized_hash=normalized_hash, timeframe_record=tf_record, last_bar=last_bar,
                    last_bar_policy=last_bar_policy, excluded_rows=excluded_rows,
                )
                manifest = DatasetManifest(
                    dataset_id=dataset_key, symbol=symbol.strip(), timeframe=timeframe, source_name=source_name.strip(),
                    start_time=kept_candles[0].timestamp, end_time=kept_candles[-1].timestamp, synthetic=bool(synthetic),
                    source_sha256=source_hash, canonical_content_sha256=dataset_hash,
                    normalized_file_sha256=normalized_hash, normalized_file_name=live_normalized.name,
                    source_file_name=source_path.name, row_count=len(kept_candles),
                    timestamp_semantics=TimestampSemantics(
                        source_claim="CSV timestamps include explicit offsets and are normalized to UTC; source clock semantics are not independently verified.",
                        verification_status="unverified", verification_ref=None,
                        uncertainty="An explicit timestamp offset does not establish the original broker clock or bar-boundary semantics.",
                    ), source_notes=source_notes,
                    processing_steps=("read_source_bytes_once", "parse_explicit_offsets", "validate_ohlc_and_sequence", "canonicalize_v1", "normalize_csv"),
                    timeframe_check=tf_result, timeframe_policy=policy_record(policy, timeframe_policy_source),
                    last_bar={**last_bar, "policy": last_bar_policy}, excluded_rows=excluded_rows,
                    provenance={"input_path": str(source_path), "source_hash": source_hash, "imported_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")},
                    run_id=run_id,
                )
                from .outputs import publish_dataset
                outcome = publish_dataset(destination, stem, {
                    "normalized": normalized_bytes,
                    "report": (json.dumps(report_payload, indent=2, sort_keys=True) + "\n").encode("utf-8"),
                    "manifest": (json.dumps(manifest.to_dict(), indent=2, sort_keys=True) + "\n").encode("utf-8"),
                })
                superseded_dir = outcome.get("superseded_dir")

    if not accepted:
        # Rejections are immutable, separately identified diagnostics. They never touch live accepted files.
        report_dir = destination / "rejections" / run_id
        report_path = report_dir / f"{stem}.quality-report.json"
        report_payload = _report_payload(
            accepted=False, run_id=run_id, input_path=str(source_path), input_hash=source_hash,
            symbol=symbol.strip(), timeframe=timeframe, source_name=source_name.strip(),
            input_rows=input_rows, parsed_rows=len(candles), kept_rows=len(kept_candles), errors=row_issues,
            validation=validation, output_csv=None, manifest_json=None, dataset_key=None, dataset_hash=None,
            normalized_hash=None, timeframe_record=tf_record, last_bar=last_bar,
            last_bar_policy=last_bar_policy, excluded_rows=excluded_rows,
        )
        _atomic_report(report_path, report_payload)
        output_report_path = report_path
    else:
        output_report_path = live_report

    return ImportResult(
        input_path=str(source_path), input_sha256=source_hash, symbol=symbol.strip(), timeframe=timeframe,
        source_name=source_name.strip(), input_rows=input_rows, parsed_rows=len(candles), errors=tuple(row_issues),
        duplicate_timestamps=validation.duplicate_timestamps, out_of_order_pairs=validation.out_of_order_pairs,
        gaps=validation.gaps, output_csv=str(output_path) if accepted and output_path else None,
        manifest_json=str(manifest_path) if accepted and manifest_path else None, report_json=str(output_report_path),
        accepted=accepted, dataset_id=dataset_key if accepted else None,
        canonical_content_sha256=dataset_hash if accepted else None,
        normalized_file_sha256=normalized_hash if accepted else None, run_id=run_id, unchanged=unchanged,
        superseded_dir=superseded_dir, timeframe_check=tf_record, last_bar=last_bar, excluded_rows=excluded_rows,
    )


def _report_payload(*, accepted: bool, run_id: str, input_path: str, input_hash: str, symbol: str,
                    timeframe: str, source_name: str, input_rows: int, parsed_rows: int, kept_rows: int,
                    errors: list[ImportIssue], validation, output_csv: str | None, manifest_json: str | None,
                    dataset_key: str | None, dataset_hash: str | None, normalized_hash: str | None,
                    timeframe_record: dict, last_bar: dict, last_bar_policy: str, excluded_rows: int) -> dict[str, Any]:
    return {
        "schema_version": 2, "run_id": run_id, "accepted": bool(accepted), "input_path": input_path,
        "source_sha256": input_hash, "symbol": symbol, "timeframe": timeframe, "source_name": source_name,
        "input_rows": input_rows, "parsed_rows": parsed_rows, "kept_rows": kept_rows,
        "error_count": len(errors), "errors": [asdict(issue) for issue in errors],
        "duplicate_timestamps": list(validation.duplicate_timestamps),
        "out_of_order_pairs": list(validation.out_of_order_pairs), "gaps": list(validation.gaps),
        "dataset_id": dataset_key, "canonical_content_sha256": dataset_hash,
        "normalized_file_sha256": normalized_hash, "output_csv": output_csv, "manifest_json": manifest_json,
        "timeframe_check": timeframe_record, "last_bar": {**last_bar, "policy": last_bar_policy},
        "excluded_rows": excluded_rows,
        "timestamp_semantics": {"verification_status": "unverified"},
        "notes": [
            "No rows are sorted or repaired.",
            "Rejected reports are stored separately and do not displace an accepted live dataset.",
            "Timeframe thresholds are provisional; report-only is the default.",
            "Timestamp semantics remain unverified.",
            "Structural acceptance is not proof of feed completeness or strategy profitability.",
        ],
    }
