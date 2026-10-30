# Dataset canonicalization v1

Status: M2e implementation contract. This defines logical candle dataset identity; it does not verify source-data accuracy or broker clock semantics.

## Canonical bytes

- Encoding: UTF-8, no BOM, LF line endings, final newline.
- Header: `pipslayer-candles-canon-1|<SYMBOL>|<TIMEFRAME>`.
- Symbol: surrounding whitespace stripped, case preserved; blank symbols and symbols containing `|`, CR, LF, or Unicode control-category characters are rejected.
- Timeframe: uppercase and must be in Pipslayer's supported timeframe set.
- Row: `<timestamp>|<open>|<high>|<low>|<close>|<volume>`.
- Timestamp: UTC `YYYY-MM-DDTHH:MM:SSZ`; if microseconds are nonzero, exactly six fractional digits precede `Z`.
- Numbers: parse to IEEE-754 binary64 and format using Python `repr`. Negative zero becomes `0.0`. Non-finite values and values whose `repr` uses exponent notation are rejected with a row/field diagnostic. Empty volume is distinct from numeric zero.
- Ordering: rows are hashed in input order; the importer does not sort them.
- Digest: SHA-256 of the canonical byte stream. Dataset IDs use `SYMBOL-TIMEFRAME-c1-` plus the first 16 hex digits. The full digest is stored in the manifest.

The canonical hash covers parsed numeric values rather than the original decimal strings. For example, `100`, `100.0`, and `100.00` map to the same binary64 value and canonical representation. Source-file and normalized-file hashes are separate and retain their own purposes.

## Versioning and tests

`candle-canon-v1` is immutable. Any change to these rules requires a new version and must not reinterpret old IDs. The fixed golden digest in `tests/test_m2e_integrity.py` is authoritative alongside this specification. The runtime formatting self-test is an additional guard, not a replacement for the golden test.

The current golden fixture is `fixtures/infrastructure/canonical_xauusd_m15_example.csv`. Its canonical SHA-256 is `2c65a7112990c5f7fa6b41202bd915da0838742ce03774484dbcc49c87e71d67`.

## Limitations

Canonical identity does not prove that prices are genuine, timestamps reflect the broker's actual clock, the dataset is complete, or a strategy generalizes. M2e timestamp semantics remain `unverified`.
