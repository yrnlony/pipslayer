"""Load and validate MSNR candidate metadata."""
import json
from pathlib import Path
from pipslayer.contracts.records import CandidateRecord, LineageRef

REGISTRY_PATH = Path(__file__).with_name("registry.json")

def load_registry(path=None):
    raw = json.loads((path or REGISTRY_PATH).read_text(encoding="utf-8"))
    records = [CandidateRecord(
        candidate_id=x["candidate_id"], strategy_id=x["strategy_id"], name=x["name"],
        category=x["category"], version=x["version"], status=x["status"],
        definition_summary=x["definition_summary"], unresolved=tuple(x.get("unresolved", [])),
        lineage=tuple(LineageRef(**r) for r in x.get("lineage", [])),
        tags=tuple(x.get("tags", [])), metadata=x.get("metadata", {})
    ) for x in raw]
    validate_registry(records)
    return records

def validate_registry(records):
    seen = set()
    for record in records:
        if record.candidate_id in seen:
            raise ValueError(f"duplicate candidate_id: {record.candidate_id}")
        seen.add(record.candidate_id)
        if record.strategy_id != "MSNR":
            raise ValueError(f"unexpected strategy_id in MSNR registry: {record.strategy_id}")
        if record.metadata.get("executable") is True:
            raise ValueError(f"M1 entries must not be executable: {record.candidate_id}")
