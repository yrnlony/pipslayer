"""Staged dataset publication, journaling, and explicit recovery.

This is an interruption-recovery protocol, not a promise of power-loss durability.
All managed paths live beneath one output directory so replace operations stay on
one filesystem. Concurrent writers for the same stem are unsupported.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import uuid
from typing import Mapping


class FileOps:
    """Small filesystem seam for deterministic fault-injection tests."""
    def mkdir(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)

    def replace(self, source: Path, destination: Path) -> None:
        os.replace(source, destination)

    def write_bytes(self, path: Path, data: bytes, *, exclusive: bool = False) -> None:
        mode = "xb" if exclusive else "wb"
        with path.open(mode) as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())

    def fsync_file(self, path: Path) -> None:
        with path.open("rb") as stream:
            os.fsync(stream.fileno())

    def open_for_append(self, path: Path) -> None:
        if path.exists():
            with path.open("ab"):
                pass

    def unlink(self, path: Path) -> None:
        path.unlink(missing_ok=True)

    def rmtree(self, path: Path) -> None:
        shutil.rmtree(path, ignore_errors=False)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _journal_path(root: Path, stem: str) -> Path:
    return root / f".pipslayer-journal-{stem}.json"


def _live_names(stem: str) -> dict[str, str]:
    return {"normalized": f"{stem}.normalized.csv", "report": f"{stem}.quality-report.json", "manifest": f"{stem}.manifest.json"}


def publish_dataset(output_dir: str | Path, stem: str, payloads: Mapping[str, bytes], *, file_ops: FileOps | None = None) -> dict:
    """Publish normalized CSV, report, manifest. `payloads` keys: normalized/report/manifest."""
    ops = file_ops or FileOps()
    root = Path(output_dir).resolve()
    ops.mkdir(root)
    names = _live_names(stem)
    if set(payloads) != set(names):
        raise ValueError("payloads must contain normalized, report, and manifest")
    journal_path = _journal_path(root, stem)
    if journal_path.exists():
        raise RuntimeError(f"Pending output journal exists: {journal_path}; run recover-outputs first")

    live_paths = {key: root / name for key, name in names.items()}
    previous: dict[str, str] = {}
    manifest_path = live_paths["manifest"]
    if manifest_path.exists():
        # A prior accepted dataset must verify before replacement; do not overwrite ambiguity.
        if not live_paths["normalized"].is_file() or not live_paths["report"].is_file():
            raise RuntimeError("Existing live manifest has missing companion files; verify/recover before import")
        previous = {key: sha256_file(path) for key, path in live_paths.items()}
        try:
            old_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            old_report = json.loads(live_paths["report"].read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise RuntimeError("Existing live manifest/report is unreadable; refusing replacement") from exc
        if old_manifest.get("normalized_file_sha256") != previous["normalized"]:
            raise RuntimeError("Existing live dataset fails integrity verification; refusing replacement")
        if old_report.get("run_id") != old_manifest.get("run_id"):
            raise RuntimeError("Existing report/manifest run_id mismatch; refusing replacement")
        from .verify import verify_dataset
        old_verification = verify_dataset(manifest_path)
        if not old_verification["valid"]:
            raise RuntimeError("Existing live dataset fails verification; refusing replacement: " + ", ".join(old_verification["errors"]))
    else:
        # Orphan files without a commit marker are not safe to overwrite silently.
        orphans = [str(path) for key, path in live_paths.items() if key != "manifest" and path.exists()]
        if orphans:
            raise RuntimeError("Live outputs exist without a manifest; inspect/recover before import: " + ", ".join(orphans))

    run_id = json.loads(payloads["manifest"].decode("utf-8")).get("run_id")
    if not run_id:
        raise ValueError("new manifest payload must contain run_id")
    stage = root / f".pipslayer-staging-{run_id}"
    superseded = root / "superseded" / run_id
    if stage.exists():
        raise RuntimeError(f"Staging directory already exists: {stage}")
    ops.mkdir(stage)
    staged_paths = {key: stage / names[key] for key in names}
    new_hashes = {key: sha256_bytes(payloads[key]) for key in names}
    moved_old: list[str] = []
    published_new: list[str] = []
    journal = {
        "journal_version": 1, "run_id": run_id, "stem": stem, "intended_outcome": "accepted",
        "live_names": names, "previous_hashes": previous, "new_hashes": new_hashes,
        "staging_dir": str(stage), "superseded_dir": str(superseded),
        "supersede_order": ["manifest", "report", "normalized"],
        "publish_order": ["normalized", "report", "manifest"],
        "completed_supersede": [], "completed_publish": [],
    }
    try:
        for key, path in staged_paths.items():
            ops.write_bytes(path, payloads[key])
            if sha256_file(path) != new_hashes[key]:
                raise RuntimeError(f"Staged hash mismatch: {path}")
        for path in live_paths.values():
            ops.open_for_append(path)
        ops.write_bytes(journal_path, (json.dumps(journal, indent=2, sort_keys=True) + "\n").encode(), exclusive=True)
        if previous:
            ops.mkdir(superseded)
            for key in journal["supersede_order"]:
                source = live_paths[key]
                destination = superseded / names[key]
                if sha256_file(source) != previous[key]:
                    raise RuntimeError(f"Live file changed after preflight: {source}")
                ops.replace(source, destination)
                moved_old.append(key)
                journal["completed_supersede"].append(key)
                _rewrite_journal(ops, journal_path, journal)
        for key in journal["publish_order"]:
            ops.replace(staged_paths[key], live_paths[key])
            published_new.append(key)
            journal["completed_publish"].append(key)
            _rewrite_journal(ops, journal_path, journal)
        # Manifest is the commit marker; confirm all three expected bytes before cleanup.
        if any(sha256_file(live_paths[k]) != new_hashes[k] for k in names):
            raise RuntimeError("Published dataset failed post-publication hash verification")
        ops.rmtree(stage)
        ops.unlink(journal_path)
        return {"run_id": run_id, "unchanged": False, "superseded_dir": str(superseded) if previous else None}
    except Exception as original:
        # Roll back only files whose hashes match this run; never overwrite unknown bytes.
        try:
            _rollback(root, journal_path, journal, ops)
        except Exception as rollback_error:
            raise RuntimeError(
                f"PENDING-RECOVERY for stem {stem}: {original}; rollback also failed: {rollback_error}. "
                f"Run recover-outputs --output-dir {root} --stem {stem}"
            ) from original
        raise


def _rewrite_journal(ops: FileOps, path: Path, journal: dict) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    ops.write_bytes(temp, (json.dumps(journal, indent=2, sort_keys=True) + "\n").encode())
    ops.replace(temp, path)


def _rollback(root: Path, journal_path: Path, journal: dict, ops: FileOps) -> None:
    names = journal["live_names"]
    live = {key: root / name for key, name in names.items()}
    stage = Path(journal["staging_dir"])
    superseded = Path(journal["superseded_dir"])
    uncommitted = superseded / "uncommitted"
    uncommitted_created = False
    # Move any new candidate files out of live, but only when hashes prove ownership.
    for key in ("manifest", "report", "normalized"):
        path = live[key]
        if not path.exists():
            continue
        digest = sha256_file(path)
        if digest == journal["new_hashes"][key]:
            if not uncommitted_created:
                ops.mkdir(uncommitted)
                uncommitted_created = True
            ops.replace(path, uncommitted / names[key])
        elif journal["previous_hashes"].get(key) == digest:
            continue
        else:
            raise RuntimeError(f"Unknown file content blocks rollback: {path}")
    # Restore previous accepted set, normalized and report first, manifest last.
    for key in ("normalized", "report", "manifest"):
        expected = journal["previous_hashes"].get(key)
        if expected is None:
            continue
        destination = live[key]
        source = superseded / names[key]
        if destination.exists() and sha256_file(destination) == expected:
            continue
        if not source.exists() or sha256_file(source) != expected:
            raise RuntimeError(f"Previous file cannot be verified for restoration: {source}")
        ops.replace(source, destination)
    # Verify restored state before removing journal.
    if journal["previous_hashes"]:
        for key, expected in journal["previous_hashes"].items():
            if not live[key].exists() or sha256_file(live[key]) != expected:
                raise RuntimeError(f"Rollback verification failed for {live[key]}")
    ops.rmtree(stage) if stage.exists() else None
    ops.unlink(journal_path)


def recover_outputs(output_dir: str | Path, stem: str, *, file_ops: FileOps | None = None) -> dict:
    ops = file_ops or FileOps()
    root = Path(output_dir).resolve()
    journal_path = _journal_path(root, stem)
    if not journal_path.exists():
        # Idempotent no-op when there is nothing pending; list crash-left staging directories.
        orphans = sorted(str(p) for p in root.glob(".pipslayer-staging-*") if p.is_dir()) if root.exists() else []
        return {"status": "nothing-to-recover", "stem": stem, "orphan_staging_directories": orphans}
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    names = journal["live_names"]
    live = {key: root / name for key, name in names.items()}
    # A fully verified new manifest means commit completed; finalize only.
    manifest = live["manifest"]
    if manifest.exists() and sha256_file(manifest) == journal["new_hashes"]["manifest"]:
        if all(live[k].exists() and sha256_file(live[k]) == journal["new_hashes"][k] for k in names):
            stage = Path(journal["staging_dir"])
            if stage.exists():
                ops.rmtree(stage)
            ops.unlink(journal_path)
            return {"status": "finalized-committed", "run_id": journal["run_id"]}
    _rollback(root, journal_path, journal, ops)
    return {"status": "rolled-back", "run_id": journal["run_id"]}


def check_output_invariants(output_dir: str | Path, stem: str) -> dict:
    """Inspect publication invariants without mutating output files.

    Returns per-invariant booleans and diagnostics. Mid-run I2 states are allowed
    only when a journal makes the transaction detectable.
    """
    root = Path(output_dir).resolve()
    names = _live_names(stem)
    live = {key: root / name for key, name in names.items()}
    journal_path = _journal_path(root, stem)
    errors: dict[str, list[str]] = {f"I{i}": [] for i in range(1, 6)}
    journal = None
    if journal_path.exists():
        try:
            journal = json.loads(journal_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            errors["I4"].append(f"journal unreadable: {exc}")
    manifest = None
    if live["manifest"].exists():
        try:
            manifest = json.loads(live["manifest"].read_text(encoding="utf-8"))
            if not live["normalized"].is_file():
                errors["I1"].append("live manifest exists without normalized file")
            elif sha256_file(live["normalized"]) != manifest.get("normalized_file_sha256"):
                errors["I1"].append("normalized hash differs from live manifest")
            if live["report"].exists():
                report = json.loads(live["report"].read_text(encoding="utf-8"))
                if report.get("run_id") != manifest.get("run_id"):
                    errors["I1"].append("live report run_id differs from manifest")
        except (OSError, ValueError) as exc:
            errors["I1"].append(f"manifest/report unreadable: {exc}")
    if not journal:
        if live["manifest"].exists():
            from .verify import verify_dataset
            checked = verify_dataset(live["manifest"])
            if not checked["valid"]:
                errors["I2"].append("live accepted dataset does not verify: " + ", ".join(checked["errors"]))
        elif live["normalized"].exists() or live["report"].exists():
            errors["I2"].append("orphan live artifacts exist without manifest or journal")
    else:
        superseded = Path(journal["superseded_dir"])
        previous = journal.get("previous_hashes", {})
        for key, expected in previous.items():
            candidates = [live[key], superseded / names[key]]
            if not any(path.is_file() and sha256_file(path) == expected for path in candidates):
                errors["I3"].append(f"previous {key} artifact not found byte-identically in live or superseded")
        if not journal_path.exists():
            errors["I4"].append("journal absent during pending transaction")
    # I5 is enforced at mutation time; here report unknown hashes against journal expectations.
    if journal:
        expected_hashes = {**journal.get("previous_hashes", {}), **journal.get("new_hashes", {})}
        for key, path in live.items():
            if path.exists() and key in expected_hashes:
                digest = sha256_file(path)
                if digest not in {journal.get("previous_hashes", {}).get(key), journal.get("new_hashes", {}).get(key)}:
                    errors["I5"].append(f"unexpected live content for {key}")
    checks = {key: not values for key, values in errors.items()}
    return {"valid": all(checks.values()), "checks": checks, "errors": errors,
            "journal_present": journal_path.exists(), "live_files": {key: path.exists() for key, path in live.items()}}
