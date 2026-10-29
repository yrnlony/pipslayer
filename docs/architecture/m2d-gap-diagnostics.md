# M2d — timestamp-gap diagnostics

## Purpose
Provide a repeatable, non-destructive explanation of timestamp gaps in accepted market-data CSVs before any strategy detector or simulator is built.

## Input and output
- Input: CSV containing timezone-aware ISO-8601 `timestamp` values, typically M2c's normalized CSV.
- Caller must specify expected candle interval.
- Output: JSON report with row count, sequence issues, gap count, UTC boundaries, elapsed duration, exact interval-multiple flag, conditional missing-bar estimate, and a calendar hint.
- Source CSV is never rewritten, sorted, repaired, or filled.

## Classification policy
- `crosses_weekend_closure_candidate`: interval spans a Saturday or Sunday UTC date. Candidate only, not proof of expected closure.
- `long_gap_review_session_or_feed`: at least 12 elapsed hours without a weekend date in the span. Review session schedule and feed behavior.
- `weekday_gap_review_feed_or_session`: shorter gap that does not span a weekend date. Review; not automatically an error or a normal closure.
- Missing bars are estimated only if elapsed duration is an exact multiple of the caller-supplied interval. The estimate assumes continuous bars and is explicitly conditional.

## Non-goals and limitations
No broker-specific session calendar, holiday calendar, daylight-saving schedule, instrument-specific trading hours, automatic repair, interpolation, or strategy-performance inference. OHLC structural validation remains the responsibility of the existing canonical importer. The gap audit additionally flags duplicate and out-of-order timestamps.

## Acceptance criteria
- Handles an ordinary intraday gap and conditionally estimates missing bars.
- Marks weekend-spanning gaps as closure candidates, never as confirmed closures.
- Flags duplicate/out-of-order timestamps.
- Rejects missing or timezone-naive timestamps.
- Writes a JSON report without modifying the input data.
- Existing tests remain green.
