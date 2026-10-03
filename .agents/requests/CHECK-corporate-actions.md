# CHECK: corporate actions / split adjustment (DeepSeek)

Branch `slice/corporate-actions`. Spec: `.agents/requests/BUILD-corporate-actions.md`. MiMo built:
- `notebooks/refresh_bronze_corporate_actions.py` (source-neutral split ingestion, yfinance adapter);
- `silver/08_silver_ohlcv_day_adjusted.sql`;
- the break masking;
- tests and docs.

612 tests pass. Read-only; scratch work in /tmp. Write `.agents/deepseek/VERDICT-corporate-actions.md`
(===VERDICT START/END===, Status).

Check, with proofs:
1. **Adjustment arithmetic.**
   - AMZN 20:1 (ex 2022-06-06): adjusted return ≈ the true return (about +2%), not −95%.
   - Reverse splits (e.g. 1:10): correct direction.
   - Multiple splits for one symbol compound.
   - Volume is adjusted inversely; dollar volume is invariant.
   - Hand-compute 3 cases.
2. **PIT.** `adj_*` levels are current-scale (they use future splits). Confirm they're documented as
   returns-only, that `return_1d` is safe, and that a price-level PIT helper (if specified) uses only
   splits with `ex_date ≤ t`. `bronze_corporate_actions.information_available_ts` = 09:30 New York on
   the ex-date.
3. **Break detector.**
   - An |overnight| ≥ 40% move not explained by a split (±3%) gets flagged. META 2022-06-09 (ticker
     reuse) is flagged.
   - Real large moves can be allow-listed.
   - A masked return is NULL, never 0.
   - Is it conservative enough not to mask genuine earnings moves silently? Is each flag logged and
     reviewable?
4. **Idempotency.** Bronze is append-only. Silver re-adjusts history when a new split arrives (a
   matched update is allowed): a rerun with identical inputs gives identical output, and no
   duplicates.
5. **Ingestion.** Rate-limited, resumable, dry-run. No network in tests (fixtures). The yfinance
   failure modes (empty, partial, symbol renames) are handled and logged.
6. **SQL** references only real columns (`bronze_ohlcv_day`: symbol, event_ts, event_date,
   event_year, open, high, low, close, volume, vwap, trade_count, timespan, source, source_file,
   ingest_ts).

Run `python3 -m pytest -q -p no:cacheprovider` and the full suite with `--ignore=tests/lakebase`,
both with pyspark hidden too.
