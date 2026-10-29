# Pipslayer — M1a + M1b + M2a + M2b + M2c + M2d

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

The command writes a raw export, then runs Pipslayer's existing CSV audit and emits normalized data, a dataset manifest, and a quality report under the output directory. It reports gaps only when an interval is supplied; the diagnostic does not understand broker holidays, weekends, or session calendars. MT5's `tick_volume` is stored in the canonical `volume` column and is **not** centralized traded volume. Keep raw exports unchanged for traceability.

If the terminal is not the default installation, add `--terminal-path "C:\\path\\to\\terminal64.exe"`. If the symbol is unavailable, inspect Market Watch and use its exact name. No live-trading or order-placement capability is included in this bridge.

## M2d — non-destructive timestamp-gap diagnostics

M2d adds `audit-gaps` for a CSV with a `timestamp` column. It reports elapsed time between consecutive candles, an estimated missing-bar count only when the interval is an exact multiple, sequence issues, and cautious UTC calendar hints. It does **not** assume Headway's trading calendar, determine that a gap is safe, fill bars, sort rows, or modify the input.

Run this against the accepted normalized M15 dataset fetched in M2c:

```powershell
$env:PYTHONPATH = "src"
py -m pipslayer.cli audit-gaps .\data\mt5-headway-xauusd-m15\audit\XAUUSD_M15_mt5_raw.normalized.csv --expected-interval-minutes 15 --output-json .\data\mt5-headway-xauusd-m15\audit\gap-diagnostics.json
```

Open `gap-diagnostics.json` and review each entry's `previous_timestamp_utc`, `next_timestamp_utc`, `elapsed`, `estimated_missing_bars_if_continuous`, and `calendar_hint_not_a_verdict`. `crosses_weekend_closure_candidate` is only a clue; broker hours, holidays, and feed-specific behavior are not encoded. All gaps require review before they can be excluded from or used in strategy research. This diagnostic returns a non-zero exit code if duplicate or out-of-order timestamps are detected.

Run the regression suite after updating:

```powershell
py -m unittest discover -s tests -v
```
