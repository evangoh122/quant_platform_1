# VERDICT: strategy-residual-reversion-round13 — MiMo
**Status:** APPROVED
**Round:** 13

## Blocking findings
- None

## Non-blocking notes
- Item 1 (filter-column fix): `fetch_data` WHERE clause now uses `{filter_col}` (`adj_close` on the adjusted path, `close` otherwise) instead of hardcoded `close`. The behavioural test stubs `_fetch` and asserts the generated SQL contains the correct filter column.
- Item 2 (disclosures): `_render` now emits all four required disclosures from residual_reversion_r10.md: masked-day P&L caveat, DSR trial-count caveat (with computed DSR value), no-untouched-holdout (with n_dates), and conclusion (computed from `bm['net_sharpe']`, `_sharpe(oos_net)`, `_deflated_sharpe(oos_net, n_trials)`). CHANGELOG updated with round 13 entry.
- Item 3 (masked-break test): Jump moved from day 100 (inside warmup) to day 120 (after 60-day window). Uses `np.log(15.0)` for x15 log-return. Unmasked control assertion added — proves the mask is load-bearing by verifying the unmasked control opens a position on the jump day while the masked run stays flat.
- Item 4 (behavioural tests): Source-inspection tests (`inspect.getsource`) replaced with behavioural tests that stub `_fetch` to capture generated SQL and assert column mapping + filter correctness. Bronze path uses `pytest.warns` for the unadjusted-price warning.
- Two of four new tests FAIL on old code (archived HEAD): `test_adjusted_path_generates_correct_sql` (old filters on `close`, not `adj_close`) and `test_render_emits_required_disclosures` (old missing disclosures). Mutation proof confirmed.

## Checks run
- `wsl python3 -m pytest -q tests/strategies tests/ml` → 95 passed (0 failed)
- Old-code archive (`git archive HEAD | tar -x -C /tmp/rr-old`) with new tests: 2 FAILED, 2 passed
- `git diff --stat` → 2 files changed, 154 insertions, 23 deletions