"""Generate point-in-time H4 pre-contact evidence for Pipslayer."""

from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipslayer.data.reader import load_canonical_csv
from pipslayer.strategies.msnr.level_significance import (
    build_level_catalogue,
)
from pipslayer.strategies.msnr.precontact_evidence import (
    build_precontact_evidence,
)


DATA_DIR = (
    ROOT
    / "data/mt5-headway-xauusd-h4-2026-05-to-2026-11"
    / "audit"
)

CSV_PATH = DATA_DIR / "XAUUSD_H4_mt5_raw.normalized.csv"
MANIFEST_PATH = DATA_DIR / "XAUUSD_H4_mt5_raw.manifest.json"

REPORT_DIR = ROOT / "reports"

RECOGNITION_PATH = REPORT_DIR / "xauusd-h4-av-gap-context.json"
INTERACTIONS_PATH = REPORT_DIR / "xauusd-h4-level-interactions.json"
REACTIONS_PATH = REPORT_DIR / "xauusd-h4-level-reactions.json"
OUTPUT_PATH = REPORT_DIR / "xauusd-h4-precontact-evidence-gap-aware.json"


def read_json(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"Required report not found: {path}")

    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def main() -> None:
    manifest = read_json(MANIFEST_PATH)

    expected_dataset_id = "XAUUSD-H4-c1-c0b7e6744552e96c"

    if manifest.get("dataset_id") != expected_dataset_id:
        raise ValueError("H4 manifest dataset ID mismatch")

    if manifest.get("symbol") != "XAUUSD":
        raise ValueError("Unexpected H4 manifest symbol")

    if manifest.get("timeframe") != "H4":
        raise ValueError("Unexpected H4 manifest timeframe")

    if manifest.get("synthetic") is not False:
        raise ValueError("Expected a non-synthetic H4 dataset")

    actual_hash = sha256_file(CSV_PATH)
    expected_hash = manifest.get("normalized_file_sha256")

    if actual_hash.lower() != str(expected_hash).lower():
        raise ValueError("Normalized H4 CSV hash does not match manifest")

    candles = load_canonical_csv(CSV_PATH)

    if len(candles) != manifest.get("row_count"):
        raise ValueError("CSV row count does not match manifest")

    last_bar = manifest.get("last_bar", {})

    if last_bar.get("status") != "possibly_incomplete":
        raise ValueError("Manifest does not identify the expected incomplete bar")

    if last_bar.get("policy") != "flag":
        raise ValueError("Unexpected final-bar policy")

    incomplete_timestamp = last_bar.get("last_bar_open")

    if not incomplete_timestamp:
        raise ValueError("Manifest is missing last_bar_open")

    final_candle = candles[-1]

    if final_candle.timestamp.isoformat().replace("+00:00", "Z") != (
        incomplete_timestamp
    ):
        raise ValueError("Final CSV candle does not match manifest last bar")

    data_as_of = datetime.fromisoformat(
        last_bar["data_as_of"].replace("Z", "+00:00")
    )

    if final_candle.timestamp + timedelta(hours=4) <= data_as_of:
        raise ValueError("Manifest final candle is not actually incomplete")

    # Exclude only the manifest-identified incomplete final candle.
    complete_candles = candles[:-1]

    if len(complete_candles) != 815:
        raise ValueError(
            f"Expected 815 completed H4 candles, got {len(complete_candles)}"
        )

    recognition = read_json(RECOGNITION_PATH)
    interactions = read_json(INTERACTIONS_PATH)
    reactions = read_json(REACTIONS_PATH)

    for name, report in (
        ("recognition", recognition),
        ("interactions", interactions),
        ("reactions", reactions),
    ):
        if report.get("dataset_id") != expected_dataset_id:
            raise ValueError(f"{name} report dataset ID mismatch")

    catalogue = build_level_catalogue(
        recognition,
        symbol="XAUUSD",
    )

    if len(catalogue["levels"]) != 425:
        raise ValueError("Expected 425 H4 catalogue levels")

    if len(interactions.get("episodes", [])) != 3726:
        raise ValueError("Expected 3,726 interaction episodes")

    if len(reactions.get("reactions", [])) != 3726:
        raise ValueError("Expected 3,726 reaction records")

    evidence = build_precontact_evidence(
        complete_candles,
        catalogue,
        interactions,
        reactions,
    )

    if evidence.get("snapshot_count") != 3726:
        raise ValueError(
            "Expected exactly one snapshot per interaction episode"
        )

    if OUTPUT_PATH.exists():
        raise FileExistsError(
            f"Output already exists; inspect it before replacing: {OUTPUT_PATH}"
        )

    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    with OUTPUT_PATH.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(
            evidence,
            stream,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        stream.write("\n")

    print("H4 PRE-CONTACT EVIDENCE GENERATED")
    print(f"Dataset: {expected_dataset_id}")
    print(f"Canonical CSV rows: {len(candles)}")
    print(f"Completed H4 candles: {len(complete_candles)}")
    print(f"Excluded incomplete candles: 1")
    print(f"Catalogue levels: {len(catalogue['levels'])}")
    print(f"Interaction episodes: {len(interactions['episodes'])}")
    print(f"Reaction records: {len(reactions['reactions'])}")
    print(f"Snapshots: {evidence['snapshot_count']}")
    print(f"Output: {OUTPUT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

