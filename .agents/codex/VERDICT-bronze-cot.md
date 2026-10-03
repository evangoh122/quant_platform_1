# VERDICT: bronze-cot — Codex

CHANGES_REQUESTED

1. The write path is not strictly append-only. If a target table is absent, it creates it using `.mode("overwrite")`, explicitly violating the Bronze constraint forbidding overwrite operations: [refresh_bronze_cot.py:455](/home/jianj/code/qp1-b-cot/notebooks/refresh_bronze_cot.py:455), [refresh_bronze_cot.py:460](/home/jianj/code/qp1-b-cot/notebooks/refresh_bronze_cot.py:460). Existing tables do use incoming-key deduplication, a target-key left anti-join, and append mode at lines 303–320 and 463–464.

2. Successful writes are not actually verified. After the append, the code only reads count/max statistics and unconditionally sets `status = "OK"`; it never asserts that `post_count - pre_count == new_count`, that all expected keys landed, or that duplicate keys remain absent: [refresh_bronze_cot.py:455](/home/jianj/code/qp1-b-cot/notebooks/refresh_bronze_cot.py:455), [refresh_bronze_cot.py:466](/home/jianj/code/qp1-b-cot/notebooks/refresh_bronze_cot.py:466), [refresh_bronze_cot.py:470](/home/jianj/code/qp1-b-cot/notebooks/refresh_bronze_cot.py:470). Thus the implementation does not satisfy the required “verification passed before success” contract. Exceptions are otherwise converted to `FAILED`, and `main()` exits nonzero when either dataset fails at lines 472–475 and 575–579.

3. The focused tests do not exercise the production parsing/key implementation. Contract-code tests are tautologies or locally reimplement the lookup rather than calling `validate_contract_code_column`: [test_refresh_bronze_cot.py:153](/home/jianj/code/qp1-b-cot/tests/bronze/test_refresh_bronze_cot.py:153). Natural-key and anti-join tests construct independent Python/Pandas logic instead of calling `anti_join_new_rows` or `detect_revision_conflicts`: [test_refresh_bronze_cot.py:182](/home/jianj/code/qp1-b-cot/tests/bronze/test_refresh_bronze_cot.py:182), [test_refresh_bronze_cot.py:256](/home/jianj/code/qp1-b-cot/tests/bronze/test_refresh_bronze_cot.py:256). The real `to_bronze` parsing and write verification path is untested.

4. Default window handling has an off-by-one inconsistency: `main()` sets `start_date = max(report_date) + 1 day`, but filtering then requires `report_date > start_date`. A report exactly one day after the current maximum would be skipped: [refresh_bronze_cot.py:407](/home/jianj/code/qp1-b-cot/notebooks/refresh_bronze_cot.py:407), [refresh_bronze_cot.py:531](/home/jianj/code/qp1-b-cot/notebooks/refresh_bronze_cot.py:531). Weekly COT cadence masked this during the reported live run, but the generic incremental contract is incorrect.

Other checks:

- The specified key `(source_dataset, CFTC_Contract_Market_Code, report_date)` is used consistently at lines 303–320. Per the lane specification and supplied live duplicate result, it is complete for these TFF datasets; no display-name fallback is used.
- `release_ts` is derived from the report date plus six days at 15:30 New York, producing the conservative Monday fallback rather than treating Tuesday `report_date` as availability: [refresh_bronze_cot.py:204](/home/jianj/code/qp1-b-cot/notebooks/refresh_bronze_cot.py:204), [refresh_bronze_cot.py:211](/home/jianj/code/qp1-b-cot/notebooks/refresh_bronze_cot.py:211).
- CFTC download requires no credentials. This lane contains no secret reads or secret printing.
- Requested test command passed: `32 passed in 0.98s`.

