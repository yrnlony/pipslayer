# M2c — Read-only MetaTrader 5 bridge

## Scope

M2c adds an optional Windows Python adapter that reads historical rates through the MetaTrader5 Python package. It is a data transport integration only, not a strategy detector or trading integration.

## Safety and boundaries

- No order-send, modify, close, position, or account-trading calls are implemented.
- User must start MT5 and log in to the intended account manually.
- Symbol name is explicit and must match the terminal's broker-specific Market Watch symbol.
- Date inputs must include a timezone; the adapter converts them to UTC before calling the MT5 API.
- MT5 rate timestamps are interpreted as UTC epoch seconds.
- Original raw export is preserved; Pipslayer's existing CSV importer validates and writes normalized data only if structural validation passes.
- `tick_volume` is mapped to the canonical `volume` column and clearly documented as tick activity, not exchange-wide traded volume.
- Optional gap reporting does not model weekends, holidays, or broker sessions.

## Deferred

No timeframe resampling/alignment policy, current-bar filtering, strategy detector, simulator, experiment engine, AI brain, or order execution is included. The fetched range must be reviewed for completeness and broker-specific timestamp behavior before research use.
