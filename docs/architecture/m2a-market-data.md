# M2a — Market-data foundation

## Purpose
Define a provider-neutral candle contract, dataset provenance record, and conservative quality checks before importing broker data or implementing strategy detectors.

## Implemented
- OHLC candles with symbol, timeframe, timezone-aware UTC timestamp, optional volume, and optional source label.
- Validation of finite OHLC values, internally consistent high/low, optional volume validity, mixed symbol/timeframe sequences, duplicate timestamps, and out-of-order rows.
- Optional gap reporting when a caller explicitly supplies an expected interval.
- Dataset manifest with source, timestamp timezone, date range, synthetic-data flag, notes, processing lineage, and schema version.
- ISO-8601 timestamp parser that rejects timezone-naive input and normalizes aware timestamps to UTC.

## Deliberate boundaries
- No broker/vendor adapter yet.
- No automatic sorting, deduplication, interpolation, or missing-candle repair.
- Gaps are informational because trading sessions, holidays, and broker calendars vary.
- No H4/H2/M15 alignment rule has been selected or silently assumed.
- No strategy detector, backtest, trading decision, or profitability claim.

## Acceptance
Run `python -m unittest discover -s tests -v` from the project root. Synthetic fixtures are plumbing tests only and are not market evidence.
