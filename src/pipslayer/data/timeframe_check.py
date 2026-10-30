"""Configurable, deliberately provisional candle-spacing diagnostics."""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import Iterable

from .candles import Candle, TIMEFRAME_MINUTES


@dataclass(frozen=True)
class TimeframeCheckPolicy:
    min_deltas: int = 20
    match_share: float = 0.70
    conflict_declared_max: float = 0.20
    conflict_other_min: float = 0.50
    provisional: bool = True

    def __post_init__(self) -> None:
        if self.provisional is not True:
            raise ValueError("M2e timeframe thresholds must remain provisional")
        if self.min_deltas < 10:
            raise ValueError("min_deltas must be at least 10")
        for name in ("match_share", "conflict_declared_max", "conflict_other_min"):
            value = getattr(self, name)
            if not 0 < value <= 1:
                raise ValueError(f"{name} must be in (0, 1]")
        if self.conflict_declared_max >= self.match_share:
            raise ValueError("conflict_declared_max must be less than match_share")

    @classmethod
    def from_json(cls, path: str | Path) -> "TimeframeCheckPolicy":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        allowed = {"min_deltas", "match_share", "conflict_declared_max", "conflict_other_min", "provisional"}
        unknown = set(payload) - allowed
        if unknown:
            raise ValueError("Unknown timeframe policy fields: " + ", ".join(sorted(unknown)))
        return cls(**payload)


def assess_timeframe_spacing(candles: Iterable[Candle], policy: TimeframeCheckPolicy | None = None) -> dict:
    policy = policy or TimeframeCheckPolicy()
    rows = list(candles)
    if not rows:
        return {"status": "insufficient_evidence", "delta_count": 0, "match_share": None, "dominant_other_spacing_minutes": None}
    expected = TIMEFRAME_MINUTES[rows[0].timeframe]
    deltas = []
    for prev, cur in zip(rows, rows[1:]):
        seconds = (cur.timestamp - prev.timestamp).total_seconds()
        if seconds > 0 and seconds % 60 == 0:
            deltas.append(int(seconds // 60))
    n = len(deltas)
    if n < policy.min_deltas:
        return {"status": "insufficient_evidence", "delta_count": n, "expected_minutes": expected, "match_share": None, "dominant_other_spacing_minutes": None}
    counts = Counter(deltas)
    matches = counts.get(expected, 0) / n
    other = [(minutes, count / n) for minutes, count in counts.items() if minutes != expected]
    dominant_minutes, dominant_share = max(other, key=lambda pair: pair[1], default=(None, 0.0))
    if matches >= policy.match_share:
        status = "matches"
    elif matches < policy.conflict_declared_max and dominant_share >= policy.conflict_other_min:
        status = "conflicts"
    else:
        status = "ambiguous"
    return {"status": status, "delta_count": n, "expected_minutes": expected, "match_share": matches,
            "dominant_other_spacing_minutes": dominant_minutes, "dominant_other_share": dominant_share}


def policy_record(policy: TimeframeCheckPolicy, source: str) -> dict:
    return {**asdict(policy), "policy_source": source, "provisional": True}
