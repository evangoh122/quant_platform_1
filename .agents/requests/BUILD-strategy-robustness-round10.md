# BUILD: strategy robustness round 10, checkpoint correctness (MiMo)

> **IMPLEMENT NOW.** No confirmation questions. Commit when done. NEVER delete or weaken existing
> tests.

Checker verdict (Claude, DeepSeek out of credit): `.agents/deepseek/VERDICT-strategy-robustness-perf2.md`.
The equivalence, pool determinism and resume ordering are verified. Two NEW blocking defects:

1. **The cache round-trip loses the date indexes** (`strategies/run_residual_reversion.py:~584-627`,
   used at `~736-737`). `net`/`gross`/`turnover` come back with a RangeIndex, and the frames with
   string indexes. After a resume, `net.reindex(dates)` is all-NaN, so the drop-top-3 section is
   silently empty.
   - Persist with a type-preserving format: pickle per variant, or parquet plus a JSON sidecar of
     dtypes and index types.
   - Test: put a REAL `_run_variant` result through the actual `_save_cache`/`_load_cache` code.
     Every Series/DataFrame round-trips with an equal index (dtype included) and equal values.
   - End-to-end: a run that resumes fully from cache produces a report IDENTICAL to a fresh run.
     Call the real `main()` path on a tiny synthetic panel.
2. **CLI overrides aren't in the fingerprint** (`~:637`). Include the EFFECTIVE `book_capital`,
   `factor_model` and `pca_components` (after CLI overrides).
   Test: rerunning with a different `--book-capital` recomputes.

Also, from the non-blocking notes:
- Make the data fingerprint a hash of the full panel values: `close` AND `dollar_volume` for all
  symbols and dates, e.g. `pd.util.hash_pandas_object(...).values` hashed with sha256.
- Expand the determinism test to all result fields, at workers 1/2/4.
- Report "Executed trials (computed this run): N / cached: M / total counted: K".

Run:
- `python3 -m pytest -q tests/strategies tests/ml`;
- the same suite with pyspark hidden.

LF line endings only. Don't touch `.agents/dispatch.sh`. Write
`.agents/mimo/VERDICT-strategy-robustness-round10.md`.
