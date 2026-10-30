# Pipslayer build report

## Baseline M2d

The supplied M2d snapshot passed 38 tests before M2e changes in the implementation environment.

## M2e — data integrity and reproducible publication

Implemented in the available working snapshot. This report records only results actually observed in the current container; Windows/PowerShell and a real MT5 terminal were not available for verification.

- Version: `0.5.0`.
- Added versioned canonical candle hashing and a pinned golden digest.
- Added schema-v2 manifests with timestamp semantics fixed to `unverified`.
- Added provisional timeframe diagnostics (default `report-only`) and last-bar assessment (default `flag`).
- Added journaled accepted-dataset publication, separate rejection reports, explicit recovery, and normalized-data verification.
- Added atomic MT5 raw CSV replacement and a non-conclusive MT5 clock diagnostic.
- Added exhaustive single-operation fault and simulated-crash sweeps plus double-fault recovery tests.

Command run in the implementation environment:

```text
PYTHONPATH=src python -m unittest discover -s tests -v
Ran 66 tests ... OK
```

The precise run time varies by environment. The canonical golden test was executed with Python 3.13.5 in this container. Python 3.11 and Windows filesystem-lock behavior still require local verification. No live MT5 terminal or broker data was used. These checks do not validate strategy performance or profitability.
