===VERDICT START===
# VERDICT: strategy-residual-reversion-round12 — DeepSeek
**Status:** APPROVED
**Round:** 12

Read-only check of commits `db6393c..HEAD` (build commit `5527817`) against
`BUILD-strategy-residual-reversion-round12.md` and
`CHECK-strategy-residual-reversion-round12.md`. Traced `main → fetch_data /
fetch_masked_breaks → build_signals → run_one → run_backtest`, audited the silver
`08_silver_ohlcv_day_adjusted.sql` DDL (`slice/corporate-actions`) for mask-source
and date alignment, re-ran the required suites (normal + nodbc shim), and performed the
mask-ignore mutation in a `git archive` copy. Nothing committed or pushed.

## Blocking findings

None.

## Item-by-item

### 1. Price source config + CLI — PASS
- `fetch_data(w, price_table="silver_ohlcv_day_adjusted")` (`strategies/run_residual_reversion.py:68`)
  selects `adj_close AS close` for the adjusted table (`:80`) and `close` for any other table with a
  loud `warnings.warn(..., stacklevel=2)` (`:82-89`) containing "UNADJUSTED".
- CLI flag `--price-table` added (`:391`, default `silver_ohlcv_day_adjusted`), threaded through
  `main → fetch_data` (`:399`) and into the report header via `_render(..., price_table=..., n_masked_breaks=...)`
  (`:493-496`). Header shows `(split-adjusted)` or `(**UNADJUSTED — splits contaminate results**)`.
- `strategies/config.yaml:9` adds `global.price_table: silver_ohlcv_day_adjusted`.

### 2. Masked breaks — PASS (no off-by-one)
- Mask source is `data_quality_breaks WHERE is_masked = true` (`fetch_masked_breaks`,
  `run_residual_reversion.py:114-127`), returning `set[(symbol, event_date)]`.
- **Source completeness / alignment:** confirmed against the silver DDL. `silver_ohlcv_day_adjusted.return_1d`
  is `NULL` exactly when a `data_quality_breaks` row has `is_masked=TRUE` on the same `event_date`
  (DDL step 10, join on `br.symbol = a.symbol AND br.event_date = a.event_date AND br.is_masked = TRUE`).
  `event_date` is the break day itself, and the strategy recomputes `return[t] = close[t]/close[t-1]-1`,
  so masking `event_date` (not `event_date+1`) is correct — no off-by-one.
- Both frames are masked: `tradeable_returns` (signals, `:193-196`) and `valuation_returns` (P&L,
  `:210-214`) get `np.nan` on `(symbol, dt)` where `dt` is in the frame index. The strategy does NOT use
  silver's `return_1d` column at all — it recomputes returns from `adj_close`, so identifying break days
  via `is_masked` and setting the recomputed return to NaN is the correct approach.

### 3. r9 SUPERSEDED / r10 placeholder — PASS
- `strategies/results/residual_reversion_r9.md:1` now begins `# SUPERSEDED — Residual mean-reversion — round 9`,
  with an explanatory note (`:3-5`) that it used unadjusted `bronze_ohlcv_day`.
- `strategies/results/residual_reversion_r10.md` is a `**PLACEHOLDER**` (`:3`) with no results table; it
  states the price source and the two r12 fixes but claims no numbers. Nothing claims r10 results.

### 4. Round-11 regression (exit-day P&L) not reintroduced — PASS
- `valuation_returns = returns[tradeable].copy()` (`:210`) is **not** masked to the PIT universe, so a held
  name that leaves the universe on day t keeps its real exit-day return — the round-11 fix. Only break days
  are then set to NaN (intended: positions held across a masked day earn 0, stated in the report
  limitations `:565-568` and `_render`).
- `test_signals_unchanged_by_valuation_returns_fix` (`tests/strategies/test_run_residual_reversion.py:186`)
  still asserts `valuation_returns["A"]` is valid on the universe drop day (`:222`) while `returns["A"]` is
  NaN (`:228`); `test_exit_day_pnl_includes_held_name_return` (`:69`) pins the exact exit-day P&L. Both pass.

### Mutation result (mask ignored)
Performed in `git archive HEAD | tar -x -C /tmp/check12-mutation`, then removed both `if masked_breaks:`
loops in `build_signals`. Result:
- `test_masked_break_yields_nan_return` → **FAILED** (return finite, expected NaN)
- `test_mutation_ignore_mask_fails` → **FAILED** (with-mask assert `pd.isna(...)` got `np.float64(0.0107…)`)
- `test_masked_break_no_signal_triggered` → **PASSED** (see non-blocking note 1 — non-discriminating)

The mask is load-bearing: ignoring it fails 2 tests.

## Non-blocking notes

1. `test_masked_break_no_signal_triggered` (`tests/strategies/test_run_residual_reversion.py:313`) does
   **not** actually prove "a masked jump triggers no trade". The ×7.4 jump is placed at `dates[100]`, where
   the trailing σ window `[41..100]` still contains the β warm-up region `[41..59]` (NaN residuals), giving
   only 41 valid residuals < `min_obs=48` → σ NaN → s-score NaN → position 0 **regardless of the mask**.
   Confirmed: the test still passes with the mask removed. Recommend moving the jump to `dates[150]` (or
   `periods=300`) so σ has full history and the jump would genuinely produce |s|>2.5 if unmasked. The
   load-bearing coverage is currently carried by `test_masked_break_yields_nan_return` + the mutation test.
2. `fetch_data` WHERE clause (`run_residual_reversion.py:98`) filters `close IS NOT NULL AND close > 0` on
   the table's **raw** `close`, not `adj_close`, while the SELECT aliases `adj_close AS close`. Equivalent in
   practice (DDL makes `adj_close = close × positive factor`), but the filter should target `adj_close` for
   the adjusted path to stay correct if `adj_close` ever goes NULL for a row with valid raw close.
3. `strategies/config.yaml:9` `price_table` is documentation-only — no loader reads it; the effective default
   is the argparse constant `silver_ohlcv_day_adjusted` (`:391`), and catalog/schema come from env vars. This
   matches the existing aspirational-config pattern but is worth a comment.
4. `test_adjusted_table_maps_adj_close_as_close` (`:247`) and `test_bronze_path_logs_warning` (`:258`) inspect
   `fetch_data` source via `inspect.getsource` rather than generating SQL. Acceptable given no Databricks
   access, but weaker than the "generated SQL per table" acceptance wording.
5. `_render`/`CHANGELOG` routing: the rerun output is `residual_reversion_r10.md`, so `parse_round_from_output`
   yields round 10 and `_render` would emit `CHANGELOG[10]` ("Exit-day P&L…"), not the round-12 entries.
   Claude should pass `--round 12` (or otherwise confirm) so the auto-rendered "What changed" table lists the
   split-adjusted + masked-break fixes, matching the placeholder. Strategy correctness is unaffected.
6. `test_run_residual_reversion.py` ends without a trailing newline; the request's "×15" is rendered as a
   ~639% log-return (×7.4) jump — magnitude immaterial to the masking invariant.

## Checks run

- `python3 -m pytest -q tests/strategies tests/ml` (repo root) → **94 passed**, 34 warnings (0 failures)
- same suite with `PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nodbc`
  → **94 passed**, 34 warnings
- `python3 -m pytest -q tests/strategies/test_run_residual_reversion.py` → 5 new r12 tests
  (`test_adjusted_table_maps_adj_close_as_close`, `test_bronze_path_logs_warning`,
  `test_masked_break_yields_nan_return`, `test_masked_break_no_signal_triggered`,
  `test_mutation_ignore_mask_fails`); no prior test deleted or weakened (159 additions, 0 deletions in
  `tests/strategies/test_run_residual_reversion.py`)
- Mutation: `git archive HEAD | tar -x -C /tmp/check12-mutation`, removed mask loops → 2 tests FAIL
  (pasted above)
- `git show slice/corporate-actions:silver/08_silver_ohlcv_day_adjusted.sql` → confirmed `return_1d`
  masking and `adj_close` derivation align with `data_quality_breaks.event_date` (no off-by-one)
===VERDICT END===
