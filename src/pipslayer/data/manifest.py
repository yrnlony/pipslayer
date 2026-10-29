"""Dataset provenance metadata; intentionally independent of data vendors."""
from dataclasses import dataclass
from datetime import datetime, timedelta

from .candles import SUPPORTED_TIMEFRAMES

@dataclass(frozen=True)
class DatasetManifest:
    dataset_id: str
    symbol: str
    timeframe: str
    source_name: str
    timestamp_timezone: str
    start_time: datetime
    end_time: datetime
    synthetic: bool
    source_notes: str = ""
    processing_steps: tuple[str, ...] = ()
    schema_version: int = 1

    def __post_init__(self) -> None:
        for field_name in ("dataset_id", "symbol", "source_name", "timestamp_timezone"):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} must not be blank")
        if self.timeframe not in SUPPORTED_TIMEFRAMES:
            raise ValueError(f"Unsupported timeframe: {self.timeframe}")
        for name, value in (("start_time", self.start_time), ("end_time", self.end_time)):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{name} must be timezone-aware")
        if self.start_time > self.end_time:
            raise ValueError("start_time must be <= end_time")
        if self.schema_version < 1:
            raise ValueError("schema_version must be >= 1")
