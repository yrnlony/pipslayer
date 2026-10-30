"""Versioned dataset manifest and provenance schema."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping

from .candles import SUPPORTED_TIMEFRAMES


@dataclass(frozen=True)
class TimestampSemantics:
    source_claim: str
    verification_status: str = "unverified"
    verification_ref: str | None = None
    uncertainty: str = "Source timestamp semantics have not been independently verified."

    def __post_init__(self) -> None:
        if self.verification_status != "unverified":
            raise ValueError("M2e only permits verification_status='unverified'")
        if not self.source_claim.strip():
            raise ValueError("source_claim must not be blank")


@dataclass(frozen=True)
class DatasetManifest:
    dataset_id: str
    symbol: str
    timeframe: str
    source_name: str
    start_time: datetime
    end_time: datetime
    synthetic: bool
    source_sha256: str
    canonical_content_sha256: str
    normalized_file_sha256: str
    normalized_file_name: str
    source_file_name: str
    row_count: int
    timestamp_semantics: TimestampSemantics
    source_notes: str = ""
    processing_steps: tuple[str, ...] = ()
    canonicalization_version: str = "candle-canon-v1"
    timeframe_check: Mapping[str, Any] = field(default_factory=dict)
    timeframe_policy: Mapping[str, Any] = field(default_factory=dict)
    last_bar: Mapping[str, Any] = field(default_factory=dict)
    excluded_rows: int = 0
    provenance: Mapping[str, Any] = field(default_factory=dict)
    run_id: str = ""
    schema_version: int = 2

    def __post_init__(self) -> None:
        for name in ("dataset_id", "symbol", "source_name", "source_sha256", "canonical_content_sha256", "normalized_file_sha256", "run_id"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} must not be blank")
        if self.timeframe not in SUPPORTED_TIMEFRAMES:
            raise ValueError(f"Unsupported timeframe: {self.timeframe}")
        for name, value in (("start_time", self.start_time), ("end_time", self.end_time)):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{name} must be timezone-aware")
        if self.start_time > self.end_time:
            raise ValueError("start_time must be <= end_time")
        if self.row_count < 1 or self.excluded_rows < 0:
            raise ValueError("row_count must be positive and excluded_rows non-negative")
        if self.schema_version != 2:
            raise ValueError("M2e manifest schema_version must be 2")

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["start_time"] = self.start_time.isoformat().replace("+00:00", "Z")
        result["end_time"] = self.end_time.isoformat().replace("+00:00", "Z")
        result["processing_steps"] = list(self.processing_steps)
        return result

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "DatasetManifest":
        if int(data.get("schema_version", 0)) != 2:
            raise ValueError("Unsupported or legacy manifest schema; expected schema_version 2")
        raw = dict(data)
        raw["start_time"] = _parse_datetime(raw["start_time"])
        raw["end_time"] = _parse_datetime(raw["end_time"])
        raw["timestamp_semantics"] = TimestampSemantics(**raw["timestamp_semantics"])
        raw["processing_steps"] = tuple(raw.get("processing_steps", ()))
        return cls(**raw)


def _parse_datetime(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def write_manifest(path: str | Path, manifest: DatasetManifest) -> Path:
    """Write a schema-v2 manifest through a same-directory temporary file."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(manifest.to_dict(), indent=2, sort_keys=True) + "\n").encode("utf-8")
    fd, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return destination


def read_manifest(path: str | Path) -> DatasetManifest:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return DatasetManifest.from_dict(payload)
