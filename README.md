# Pipslayer — M1a + M1b + M2a + M2b + M2c + M2d

Pipslayer is an evolution-first trading research platform. Starting with XAUUSD and MSNR (Market Structure and Support/Resistance), it aims to build reproducible experiments, tick-based simulation, rigorous validation, persistent research knowledge, and AI-assisted strategy discovery. Evidence-driven and human-controlled.

Pipslayer is a research system for testing trading hypotheses with reproducible evidence. It is not a live-trading bot and makes no profitability claim.

## Included
- Strategy-independent Python package and MSNR candidate registry.
- Versioned research metadata, configurations, and owner decision log.
- Provider-neutral candle schema and dataset provenance manifest.
- Conservative OHLC/time-order/duplicate/mixed-series validation and optional gap reporting.
- Canonical CSV import, UTC normalization, dataset hashing, JSON quality reports, and normalized dataset/manifest outputs for accepted files.
- Synthetic infrastructure fixture and automated tests.
- Optional read-only MetaTrader 5 historical-candle adapter (M2c); no trading or order-placement calls.
- Non-destructive timestamp-gap diagnostics with cautious calendar hints (M2d).

## Not included
No timezone guessing for naive timestamps, automatic candle repair, timeframe alignment policy, strategy detectors, simulator, experiment engine, AI brain, or live execution. The MT5 adapter is optional and read-only.

## Run from this folder (PowerShell)
```powershell
$env:PYTHONPATH = "src"
py -m unittest discover -s tests -v
py -m pipslayer.cli list-candidates
```

## Audit the bundled example CSV
```powershell
$env:PYTHONPATH = "src"
py -m pipslayer.cli import-csv .\fixtures\infrastructure\canonical_xauusd_m15_example.csv --output-dir .\data\audit-example --symbol XAUUSD --timeframe M15 --source-name synthetic-example --source-notes "Bundled synthetic fixture" --expected-interval-minutes 15 --synthetic
```

The example is synthetic. For your own historical data, use a CSV with `timestamp,open,high,low,close` headers and optional `volume`. Every timestamp must include an explicit timezone/UTC offset. The CLI writes a quality report for rejected data, but only writes normalized data and a manifest when structural validation passes.

Candidate registry entries are hypotheses/metadata, not executable rules. Statuses describe lifecycle/review state, not performance. Structural data acceptance is not proof of feed completeness or strategy profitability.

## Optional read-only MetaTrader 5 bridge (M2c)

The optional MT5 adapter reads historical rates from a locally installed, running and logged-in MetaTrader 5 terminal. It does not place, modify, or close trades. The terminal should be logged in to the intended broker account (for this setup, Headway) and the exact symbol name must match Market Watch (for example, `XAUUSD`, `XAUUSD.a`, or another broker-specific name).

Install the optional package in the same Python environment used to run Pipslayer:

```powershell
py -m pip install -r requirements-mt5.txt
```

Then fetch a date range. Use explicit timezone-aware ISO timestamps; `Z` means UTC:

```powershell
$env:PYTHONPATH = "src"
py -m pipslayer.cli fetch-mt5 --symbol XAUUSD --timeframe M15 --start 2026-01-01T00:00:00Z --end 2026-02-01T00:00:00Z --output-dir .\data\mt5-headway-xauusd-m15 --source-name Headway-MT5 --expected-interval-minutes 15
```

The command writes a raw export, then runs Pipslayer's existing CSV audit and emits normalized data, a dataset manifest, and a quality report under the output directory. It reports gaps only
## Dataset integrity and reproducibility (M2e)

M2e strengthens dataset identity, provenance, validation, and safe publication.

### What's new

- Versioned canonical dataset hashing using `candle-canon-v1`.
- Separate hashes for source files, canonical dataset content, and normalized output files.
- Manifest schema v2 with expanded provenance and integrity metadata.
- Dataset verification.
- Configurable timeframe diagnostics, defaulting to report-only.
- Last-candle completeness assessment, defaulting to flagging rather than excluding.
- Read-only MT5 clock diagnostics that do not automatically decide timestamp correctness.
- Safer output publication and recovery procedures.
- Protection of previously accepted datasets when a replacement import is rejected.
- Safer replacement of MT5 raw exports.

### Verify a dataset

```powershell
$env:PYTHONPATH = "src"
py -m pipslayer.cli verify-dataset --help
```

Use the displayed arguments to verify a dataset and its manifest.

### Recover interrupted output publication

```powershell
py -m pipslayer.cli recover-outputs --help
```

This command provides the recovery interface for interrupted publication operations.

### Check MT5 clock observations

```powershell
py -m pipslayer.cli mt5-clock-check --help
```

This performs read-only clock diagnostics. Its observations are non-conclusive and do not establish broker timestamp correctness.

### Important limitations

Timeframe diagnostics are provisional. They do not establish that a broker's feed is complete or correctly timestamped.

Last-candle assessment is a warning mechanism, not proof that a candle is complete.

A valid canonical hash establishes dataset identity under the specified canonicalization rules. It does not establish market-data accuracy or trading profitability.

See `docs/architecture/dataset-canonicalization-v1.md` and `docs/architecture/m2e-data-integrity.md` for technical details.