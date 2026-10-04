===VERDICT START===
# VERDICT: strategy-residual-reversion-round13 — DeepSeek
**Status:** APPROVED
**Round:** 13

Read-only check of build commit `d40a168` ("fix(r13): ...") against
`BUILD-strategy-residual-reversion-round13.md` (CodeRabbit PR #16 comments) and
`CHECK-strategy-residual-reversion-round13.md`. Re-ran the required suites and,
for each of the 4 items, performed the prescribed mutation in a `git archive HEAD`
copy (`/tmp/rr-mut*`) to confirm the corresponding test is load-bearing. Nothing
committed or pushed; repo working tree remains clean.

## Blocking findings

None.

## Item-by-item (mutation-verified)

### 1. fetch_data filters the SELECTED price column — PASS
`strategies/run_residual_reversion.py:78-100` sets `filter_col = "adj_close"` on the
adjusted path and `"close"` otherwise, and the WHERE clause is now
`AND {filter_col} IS NOT NULL AND {filter_col} > 0` (`:100`), with `close` kept as the
output alias (`adj_close AS close`). This resolves the round-12 non-blocking note 2.
**Mutation (filter raw `close` again):** `sed` reverted line 100 to
`AND close IS NOT NULL AND close > 0` →
`test_adjusted_path_generates_correct_sql` **FAILED**
("adjusted path must filter on `adj_close`, not raw `close`"). Load-bearing. PASS.

### 2. `_render` emits the r10 disclosures from inputs — PASS
`_render` (`:583-598`) now emits, computed from its arguments: masked-day P&L caveat,
DSR trial-count caveat (`n_trials={n_trials}` + `_deflated_sharpe(oos_net, n_trials)`),
no-untouched-holdout (`n_dates`), and a conclusion built from `bm['net_sharpe']`,
`_sharpe(oos_net)`, and `_deflated_sharpe(...)` — no hard-coded numbers.
Regenerating from a synthetic result reproduced the `strategies/results/residual_reversion_r10.md`
Limitations structure (5 bullets, same order/headings); the computed fields tracked the
inputs (e.g. `net Sharpe {bm['net_sharpe']:.3f}` → "0.118", `All {n_dates} days` → "939 days").
**Mutation (drop one disclosure):** deleted the masked-day-P&L caveat lines →
`test_render_emits_required_disclosures` **FAILED** ("missing masked-day P&L caveat"). Load-bearing. PASS.

### 3. Masked-break test with unmasked control — PASS
`test_masked_break_no_signal_triggered` (`tests/strategies/test_run_residual_reversion.py:404`)
moves the TESTX ×15 jump to day 120 (after the 60-day warmup; round-12 non-blocking note 1),
uses log-return `np.log(15.0)`, keeps TESTX flat before the jump, and asserts the masked run
stays flat **and** the unmasked control opens a position on the jump day (`:445-452`).
**Mutation (ignore the mask):** `if masked_breaks:` → `if False and masked_breaks:` →
test **FAILED** ("masked break day must not trigger a trade, got position -1.0"). Load-bearing. PASS.

### 4. Behavioural fetch_data tests — PASS
Source-inspection tests (`inspect.getsource`) replaced with `_StubFetch`-based behavioural
tests: `test_adjusted_path_generates_correct_sql` (asserts `adj_close AS close` + filter column)
and `test_bronze_path_generates_correct_sql_and_warns` (asserts raw-`close` filter, no `adj_close`
reference, and `pytest.warns` for UNADJUSTED).
**Mutation (hardcode bronze):** `is_adjusted = False` →
`test_adjusted_path_generates_correct_sql` **FAILED** ("must select `adj_close AS close`").
**Mutation (strip warning text):** `test_bronze_path_generates_correct_sql_and_warns` **FAILED**
("bronze path must warn about unadjusted prices"). Both load-bearing. PASS.

## No tests deleted/weakened
- The two replaced source-inspection tests (`test_adjusted_table_maps_adj_close_as_close`,
  `test_bronze_path_logs_warning`) are the only removals — explicitly permitted by the build
  request ("source-inspection tests replaced by behavioural ones"). All other tests intact.
- `test_masked_break_no_signal_triggered` was strengthened (jump moved out of warmup + unmasked
  control added), not weakened.

## Checks run
- `python3 -m pytest -q tests/strategies tests/ml` (repo root) → **95 passed**, 35 warnings (0 failures)
- Mutation 1 (raw-close filter) → `test_adjusted_path_generates_correct_sql` FAILED (expected)
- Mutation 2 (drop disclosure) → `test_render_emits_required_disclosures` FAILED (expected)
- Mutation 3 (ignore mask) → `test_masked_break_no_signal_triggered` FAILED (expected)
- Mutation 4a (hardcode bronze) → `test_adjusted_path_generates_correct_sql` FAILED (expected)
- Mutation 4b (strip warning) → `test_bronze_path_generates_correct_sql_and_warns` FAILED (expected)
- `git status` → clean; no secrets in diff (`_render`/`fetch_data`/tests only)

## Non-blocking notes
- The `_StubFetch` tests monkeypatch `mod._fetch` and restore it via a `finally` that reads
  `mod.__dict__.get("_fetch_orig", mod._fetch)`; `_fetch_orig` is never actually set, so the
  restore is a no-op that re-assigns the stub to itself. Harmless in isolation, but if another
  test needed the real `_fetch` after these, the module attribute would stay stubbed. Cosmetic.
- `test_render_emits_required_disclosures` uses `oos_net = [0.001,0.002,0.003]`, whose DSR/OOS
  compute to 1.000 / ~38.9 — fine for asserting the disclosure *text and structure* (values are
  interpolated, not compared), but the concrete r10 numbers are not re-asserted here.
===VERDICT END===
