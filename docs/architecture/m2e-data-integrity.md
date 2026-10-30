# M2e — Data integrity and reproducible dataset publication

## Scope

M2e hardens the existing CSV/MT5 market-data boundary. It does not implement trading rules, MSNR detection, simulation, strategy evolution, or execution.

## Import outcome

- Accepted imports publish normalized CSV, quality report, and manifest using a staged publication protocol.
- The manifest is the commit marker and is published last.
- Rejected imports write a run-specific report under `rejections/<run_id>/`; they never displace a previously accepted live dataset.
- Byte-identical normalized re-imports are reported as unchanged when the live dataset verifies.
- A pending journal blocks imports for that stem. Run `recover-outputs` explicitly.

## Publication and recovery

The journal records the run ID, expected hashes, old and new artifact names, staging and superseded paths, and ordered operations. Previous files move into `superseded/<run_id>/` before an accepted replacement is published. Recovery verifies hashes before any move. It restores the previous accepted dataset or finalizes a completely published new dataset. Unknown file contents stop recovery instead of being overwritten.

This is best-effort recovery from exceptions and process interruption, not a guarantee against arbitrary power loss, storage-device failure, or concurrent writers. Windows file-lock behavior must be checked locally.

## Timeframe checks

Timeframe-spacing thresholds are provisional and configurable. The default is `report-only`; `enforce` rejects only a clear conflict under the selected policy. The defaults have not been established against the owner's real Headway data. See `fixtures/infrastructure/timeframe-policy-provisional.json`.

## Last candle

The default `flag` policy preserves the final candle and records whether it may be incomplete. `exclude-if-possibly-incomplete` is opt-in and affects the retained dataset only when a reference timestamp indicates that the last bar may still be forming. Raw source data is never modified.

## Timestamp semantics

Timestamp values are normalized to UTC representation, but that does not establish the broker's clock or candle boundaries. `timestamp_semantics.verification_status` remains `unverified`. The MT5 clock diagnostic is observational, has `decision: null`, and cannot update manifest verification status.

## Commands

```powershell
$env:PYTHONPATH = "src"
py -m pipslayer.cli import-csv .\fixtures\infrastructure\canonical_xauusd_m15_example.csv --output-dir .\data\m2e-check --symbol XAUUSD --timeframe M15 --source-name synthetic-example --synthetic --timeframe-check report-only
py -m pipslayer.cli verify-dataset .\data\m2e-check\canonical_xauusd_m15_example.manifest.json
py -m pipslayer.cli recover-outputs --output-dir .\data\m2e-check --stem canonical_xauusd_m15_example
py -m pipslayer.cli mt5-clock-check --symbol XAUUSD --output-json .\data\mt5-clock-check.json
py -m unittest discover -s tests -v
```

For CSV last-bar assessment, supply `--data-as-of` with an explicit timezone offset. For a policy override, supply `--timeframe-policy .\fixtures\infrastructure\timeframe-policy-provisional.json`. The MT5 diagnostic requires a configured terminal and may alter Market Watch selection through `symbol_select`; it does not place orders.
