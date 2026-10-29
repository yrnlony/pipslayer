# Scaffold test report

Command: `python -m unittest discover -s tests -v`
Exit code: `0`

```text

Spreadsheet runtime warmup failed during python startup
Traceback (most recent call last):
  File "/tmp/tmp.QlpUkOUI9D/artifact_tool_v2-2.8.66/artifact_tool/patches/warm_spreadsheet_runtime_on_startup.py", line 26, in warm_spreadsheet_runtime_on_startup
  File "/tmp/tmp.QlpUkOUI9D/artifact_tool_v2-2.8.66/artifact_tool/spreadsheet_warmup.py", line 785, in warm_spreadsheet_runtime
  File "/tmp/tmp.QlpUkOUI9D/artifact_tool_v2-2.8.66/artifact_tool/spreadsheet_warmup.py", line 718, in _warm_feature_flows
  File "/tmp/tmp.QlpUkOUI9D/artifact_tool_v2-2.8.66/artifact_tool/spreadsheet_warmup.py", line 509, in _warm_drawing_and_image_flows
  File "/tmp/tmp.QlpUkOUI9D/artifact_tool_v2-2.8.66/artifact_tool/generated/interface/models.py", line 32861, in bring_to_front
  File "/tmp/tmp.QlpUkOUI9D/artifact_tool_v2-2.8.66/artifact_tool/rpc/remote.py", line 764, in __call__
  File "/tmp/tmp.QlpUkOUI9D/artifact_tool_v2-2.8.66/artifact_tool/rpc/client.py", line 175, in call
artifact_tool.rpc.client.RemoteError: Element ordering requires an owning element collection.
test_approved_configurations (test_configurations.ConfigurationTests.test_approved_configurations) ... ok
test_core_does_not_import_msnr (test_isolation.IsolationTests.test_core_does_not_import_msnr) ... ok
test_unknown_status_rejected (test_records.RecordTests.test_unknown_status_rejected) ... ok
test_valid_record (test_records.RecordTests.test_valid_record) ... ok
test_zero_version_rejected (test_records.RecordTests.test_zero_version_rejected) ... ok
test_all_non_executable (test_registry.RegistryTests.test_all_non_executable) ... ok
test_duplicate_rejected (test_registry.RegistryTests.test_duplicate_rejected) ... ok
test_review_statuses (test_registry.RegistryTests.test_review_statuses) ... ok
test_unique_candidate_ids (test_registry.RegistryTests.test_unique_candidate_ids) ... ok

----------------------------------------------------------------------
Ran 9 tests in 0.004s

OK
```

These tests validate scaffold metadata and architecture boundaries only. They do not test trading logic, data fidelity, or profitability.

## M2b — Canonical CSV importer and quality report

Command: `PYTHONPATH=src python -m unittest discover -s tests -v`
Exit code: `0`; 27 tests passed.

Additional checks completed:

- `python -m pipslayer.cli list-candidates` completed successfully.
- The bundled synthetic XAUUSD M15 CSV imported successfully into a normalized CSV, JSON manifest, and JSON quality report.
- Invalid row values, naive timestamps, duplicates, and out-of-order rows block normalized output; gap reporting remains opt-in.

These tests validate importer behavior and conservative structural checks. They do not establish that a provider's historical feed is complete or that any trading strategy is profitable.


## M2d — timestamp-gap diagnostics

Added a non-destructive `audit-gaps` CLI command. It reports gap boundaries, elapsed durations, conditional missing-bar estimates, UTC weekend-crossing hints, and duplicate/out-of-order timestamps. It does not infer a broker session calendar, fill candles, or modify the dataset. Local regression suite: 38 tests passed.
