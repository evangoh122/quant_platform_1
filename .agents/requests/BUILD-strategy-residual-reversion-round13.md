# BUILD residual reversion round 13 (builder: MiMo) — CodeRabbit PR #16 comments

IMPLEMENT NOW. Do not ask "Shall I proceed?". Stay on branch slice/strategy-residual-reversion (main incl. #25 already merged in). Descriptive commits.
NEVER delete or weaken tests (source-inspection tests replaced by behavioural ones may be removed — list them). Each fix needs a test that FAILS on the
old code; prove it in a copy made with `git archive HEAD | tar -x -C /tmp/<dir>` and paste the output.

1. strategies/run_residual_reversion.py ~98 (fetch_data): the WHERE clause filters raw `close` while the adjusted path selects `adj_close AS close`.
   Apply `IS NOT NULL AND > 0` to the SELECTED price column (adj_close on the adjusted path, close otherwise), keeping `close` as the output alias.
2. ~565-568 `_render`: the report generator must itself emit the disclosures Claude added by hand to strategies/results/residual_reversion_r10.md
   (read that file): the corrected "What changed vs r9" section, masked-day P&L caveat, understated trial-count (DSR) caveat, no untouched holdout,
   and the conclusion (computed from n_trials, n_dates, the baseline metrics, _sharpe and oos_net — not hard-coded numbers). Regenerating must
   reproduce them. Test: render from a synthetic result and assert each disclosure appears.
3. tests/strategies/test_run_residual_reversion.py ~313-351 test_masked_break_no_signal_triggered: put the TESTX ×15 jump AFTER the 60-day residual
   window is warmed up, keep TESTX flat before it, use log-return np.log(15.0); run build_signals with and without masked_breaks and assert the
   UNMASKED control opens a position on the jump day while the masked run stays flat. Mutation: ignore the mask → FAILS.
4. Nit (~245-268): replace the source-inspection assertions in test_adjusted_table_maps_adj_close_as_close and test_bronze_path_logs_warning with
   behavioural tests: stub `_fetch` to capture the generated SQL for each price_table (assert adj_close mapping AND the filter column from item 1) and
   use pytest.warns for the bronze warning.
Acceptance: python3 -m pytest -q tests/strategies tests/ml all pass. .agents/mimo/VERDICT-strategy-residual-reversion-round13.md. Commit everything.
