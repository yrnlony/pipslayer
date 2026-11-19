"""Point-in-time contract for MSNR A/V structure recognition (research only)."""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, Literal, Protocol, Sequence, runtime_checkable

from pipslayer.data.candles import (
    SUPPORTED_TIMEFRAMES,
    TIMEFRAME_MINUTES,
    Candle,
)

AVKind = Literal["A", "V"]
_KINDS = frozenset({"A", "V"})


def _require_utc(value: object, name: str) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
    ):
        raise ValueError(f"{name} must be a timezone-aware UTC datetime")


def candle_close_time(candle: Candle) -> datetime:
    """Close time of a candle whose timestamp is its open time."""
    return candle.timestamp + timedelta(
        minutes=TIMEFRAME_MINUTES[candle.timeframe]
    )


@dataclass(frozen=True)
class AVStructure:
    """One recognised A (closing-price peak) or V (closing-price valley)."""

    kind: AVKind
    symbol: str
    timeframe: str
    price: float
    anchor_timestamp: datetime
    formed_at: datetime
    recognised_at: datetime
    method: str
    contributing_timestamps: tuple[datetime, ...]
    method_parameters: tuple[tuple[str, str], ...] = ()
    confirmed_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.kind not in _KINDS:
            raise ValueError("kind must be 'A' or 'V'")

        if not self.symbol.strip() or not self.method.strip():
            raise ValueError("symbol and method must not be blank")

        if self.timeframe not in SUPPORTED_TIMEFRAMES:
            raise ValueError(f"Unsupported timeframe: {self.timeframe}")

        if not math.isfinite(float(self.price)):
            raise ValueError("price must be finite")

        _require_utc(self.anchor_timestamp, "anchor_timestamp")
        _require_utc(self.formed_at, "formed_at")
        _require_utc(self.recognised_at, "recognised_at")

        if not self.contributing_timestamps:
            raise ValueError("contributing_timestamps must not be empty")

        for stamp in self.contributing_timestamps:
            _require_utc(stamp, "contributing_timestamps")

        if len(set(self.contributing_timestamps)) != len(
            self.contributing_timestamps
        ):
            raise ValueError("contributing_timestamps must be unique")

        if tuple(sorted(self.contributing_timestamps)) != (
            self.contributing_timestamps
        ):
            raise ValueError(
                "contributing_timestamps must be chronological"
            )

        if self.anchor_timestamp not in self.contributing_timestamps:
            raise ValueError(
                "anchor_timestamp must be one of contributing_timestamps"
            )

        expected_formed_at = self.anchor_timestamp + timedelta(
            minutes=TIMEFRAME_MINUTES[self.timeframe]
        )
        if self.formed_at != expected_formed_at:
            raise ValueError(
                "formed_at must equal the anchor candle's close time"
            )

        if self.recognised_at < self.formed_at:
            raise ValueError("recognised_at must not precede formed_at")

        parameter_keys = []
        for parameter in self.method_parameters:
            if (
                not isinstance(parameter, tuple)
                or len(parameter) != 2
                or not all(isinstance(value, str) for value in parameter)
            ):
                raise ValueError(
                    "method_parameters must contain string key/value pairs"
                )

            key, _ = parameter
            if not key.strip():
                raise ValueError("method parameter keys must not be blank")
            parameter_keys.append(key)

        if len(set(parameter_keys)) != len(parameter_keys):
            raise ValueError("method parameter keys must be unique")

        if self.confirmed_at is not None:
            _require_utc(self.confirmed_at, "confirmed_at")
            if self.confirmed_at < self.recognised_at:
                raise ValueError(
                    "confirmed_at must not precede recognised_at"
                )

    @property
    def structure_id(self) -> str:
        """Same structural event and method configuration produce the same ID."""
        params = ",".join(
            f"{key}={value}"
            for key, value in sorted(self.method_parameters)
        )

        raw = "|".join(
            (
                self.kind,
                self.symbol,
                self.timeframe,
                self.method,
                params,
                self.anchor_timestamp.isoformat(),
            )
        )

        return "av-" + hashlib.sha256(
            raw.encode("utf-8")
        ).hexdigest()[:16]


@dataclass(frozen=True)
class RecognitionNote:
    """An observed case that a recognition method did not turn into a structure."""

    code: str
    kind: AVKind | None
    first_timestamp: datetime
    last_timestamp: datetime
    recognised_at: datetime
    detail: str

    def __post_init__(self) -> None:
        if self.kind is not None and self.kind not in _KINDS:
            raise ValueError("kind must be 'A', 'V', or None")

        if not self.code.strip():
            raise ValueError("code must not be blank")

        for name in (
            "first_timestamp",
            "last_timestamp",
            "recognised_at",
        ):
            _require_utc(getattr(self, name), name)

        if self.first_timestamp > self.last_timestamp:
            raise ValueError(
                "first_timestamp must not follow last_timestamp"
            )

        if self.recognised_at < self.last_timestamp:
            raise ValueError(
                "recognised_at must not precede the last observed timestamp"
            )


@dataclass(frozen=True)
class AVRecognitionResult:
    structures: tuple[AVStructure, ...] = ()
    notes: tuple[RecognitionNote, ...] = ()

    def __post_init__(self) -> None:
        seen: dict[str, AVStructure] = {}

        for structure in self.structures:
            identity = structure.structure_id

            if identity in seen:
                previous = seen[identity]

                if previous != structure:
                    raise ValueError(
                        "Conflicting structures share structure_id "
                        f"{identity}"
                    )

                raise ValueError(
                    f"Duplicate structure_id in result: {identity}"
                )

            seen[identity] = structure


@runtime_checkable
class AVRecogniser(Protocol):
    """Interface and behavioural obligations for an A/V recognition method.

    Obligations are verified by tests, not enforced by the Protocol:

    1. Use only supplied, closed, strictly time-ordered candles.
    2. Never sort, repair or fill supplied candles.
    3. Be prefix-invariant: future candles must never change earlier output.
    4. Set confirmed_at to None.
    5. Report excluded cases as notes rather than silently dropping them.
    """

    @property
    def method_id(self) -> str: ...

    def recognise(
        self, candles: Sequence[Candle]
    ) -> AVRecognitionResult: ...


def structures_known_at(
    structures: Iterable[AVStructure],
    as_of: datetime,
) -> tuple[AVStructure, ...]:
    """Return only structures recognised at or before the requested time."""
    _require_utc(as_of, "as_of")

    return tuple(
        structure
        for structure in structures
        if structure.recognised_at <= as_of
    )