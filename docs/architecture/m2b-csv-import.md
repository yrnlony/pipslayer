# M2b — Canonical CSV import and quality report

## Purpose

M2b makes the M2a candle contract usable on local CSV files. It is provider-neutral: it does not connect to a broker or decide which historical-data provider is authoritative.

## Canonical input format

Required headers (case-insensitive):

- `timestamp` — ISO-8601 timestamp with explicit timezone/UTC offset, such as `2026-10-01T09:15:00Z` or `2026-10-01T12:15:00+03:00`
- `open`, `high`, `low`, `close` — finite numeric OHLC values

Optional header: `volume`. A blank volume is represented as unavailable. The instrument and timeframe are supplied as explicit CLI arguments rather than guessed from a filename.

## Run an import/audit

From the project root in PowerShell:

```powershell
$env:PYTHONPATH = "src"
py -m pipslayer.cli import-csv .\fixtures\infrastructure\canonical_xauusd_m15_example.csv --output-dir .\data\audit-example --symbol XAUUSD --timeframe M15 --source-name synthetic-example --source-notes "Bundled synthetic fixture" --expected-interval-minutes 15 --synthetic
```

The example data is synthetic and must not be used to claim trading performance.

## Outputs

- `*.quality-report.json` is written whether the dataset is accepted or rejected.
- `*.normalized.csv` and `*.manifest.json` are written only when all rows parse and the sequence passes structural validation.
- The manifest includes the input SHA-256, date range, symbol, timeframe, source label, row count, and processing steps.

## Conservative acceptance rules

- No silent row dropping, sorting, filling, or price repair.
- Naive timestamps are rejected; the importer does not guess a broker timezone.
- Duplicate timestamps, out-of-order rows, malformed rows, invalid OHLC, and mixed candle series block normalized output.
- Gaps are reported only if `--expected-interval-minutes` is supplied. Gaps remain informational because session calendars and feed behavior vary.
- Acceptance means the file passed these structural checks. It does not prove that the feed is complete, the broker's candle boundaries are correct, or any strategy is profitable.

## Deferred

Broker-specific export adapters, timezone mapping for naive exports, session calendars, gap policy, timeframe aggregation/alignment, missing-candle repair, detectors, simulation, and AI research orchestration remain out of scope.
