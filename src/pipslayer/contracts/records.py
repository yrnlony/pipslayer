"""Provider-neutral metadata records; no trading logic."""
from dataclasses import dataclass, field
from typing import Any

ALLOWED_STATUSES = {
    "draft", "owner_review", "approved_definition", "implemented",
    "retired", "flag_for_review", "rejected_foreign"
}

@dataclass(frozen=True)
class LineageRef:
    parent_id: str
    relationship: str

@dataclass(frozen=True)
class CandidateRecord:
    candidate_id: str
    strategy_id: str
    name: str
    category: str
    version: int
    status: str
    definition_summary: str
    unresolved: tuple[str, ...] = ()
    lineage: tuple[LineageRef, ...] = ()
    tags: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.candidate_id.strip() or not self.strategy_id.strip() or not self.name.strip():
            raise ValueError("candidate_id, strategy_id, and name must not be blank")
        if self.version < 1:
            raise ValueError("version must be >= 1")
        if self.status not in ALLOWED_STATUSES:
            raise ValueError(f"Unsupported status: {self.status}")
