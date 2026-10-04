# CHECK: residual reversion round 12 (checker: DeepSeek)

Read-only. Mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>` (never run git in a cp -r of this worktree).
Write .agents/deepseek/VERDICT-strategy-residual-reversion-round12.md between ===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or
"Status: CHANGES_REQUESTED", findings with file:line, counts, mutation results.
Build request: .agents/requests/BUILD-strategy-residual-reversion-round12.md. Commits db6393c..HEAD.
1. price_table config/CLI, default silver_ohlcv_day_adjusted, adjusted path selects adj_close AS close; bronze path logs a loud unadjusted WARNING;
   the source appears in the report header. Test: generated SQL per table.
2. Masked breaks: returns on masked (symbol, event_date) are NaN for BOTH signals and valuation; a synthetic ×15 masked jump triggers no trade and no
   P&L. Mutation: ignore the mask → FAILS. Check the mask source (silver return_1d NULL and/or data_quality_breaks.is_masked) is fetched correctly and
   aligned on dates (no off-by-one).
3. r9 marked SUPERSEDED; r10 is a placeholder (Claude runs the live rerun) — make sure nothing claims r10 results yet.
4. Earlier fixes (rounds 9–11: pandas 3 read-only arrays, single forward-filled ADV frame for cap and costs, valuation_returns unmasked vs masked
   signals) still hold — note: round 12's masking must not reintroduce the round-11 bug where exit-day P&L was dropped by masked returns. Check it.
No tests deleted/weakened. Run python3 -m pytest -q tests/strategies tests/ml; also with PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nodbc.
