===VERDICT START===
# VERDICT: nl1-round15 — DeepSeek (checker)
**Status:** APPROVED
**Round:** 15

Range verified: `41c3e2c..5905f78` (round-15 strengthening commit `c07aa28` "feat(tests): strengthen availability window MAX check with frame matching"). Source read-only; all mutations performed in `/tmp/nl1r15-mut-{a,b1,b2,frame,c,d,e}` copies created via `git archive HEAD | tar -x` and discarded. Working tree clean at `5905f78`.

## Round-14 blocking finding — resolved

Round 14 (`.agents/deepseek/VERDICT-nl1-round14.md`) reported `test_output_availability_is_window_max` was vacuous against mutation (b): it only asserted `GREATEST(...)` had ≥2 availability tokens, so replacing `realized_vol_20d_info_ts`'s rolling `MAX(information_available_ts) OVER (...)` with the bare column passed the full suite (343 passed). `c07aa28` fixes this with two new assertions per info token: (1) the token must resolve to a CTE defined as `MAX(<availability_col>) OVER (... ROWS BETWEEN ... AND CURRENT ROW) AS <token>` (`_resolve_token_to_cte`), and (2) that window frame must match the companion metric's frame (`_extract_metric_window_frame`). Both mutation classes are now killed.

## Mutation proofs (this round)

| # | Mutation | Expected | Actual | Result |
|---|----------|----------|--------|--------|
| b1 | `realized_vol_20d_info_ts`: `MAX(information_available_ts) OVER (... ROWS BETWEEN 19 PRECEDING AND CURRENT ROW)` → bare `information_available_ts` (both adjusted + fallback blocks) | FAIL | `test_output_availability_is_window_max` **1 failed** ("availability token 'realized_vol_20d_info_ts' is not a window MAX") | caught |
| b2 | `drawdown_info_ts`: `MAX(information_available_ts) OVER (... ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)` → bare `information_available_ts` (both blocks) | FAIL | `test_output_availability_is_window_max` **1 failed** ("availability token 'drawdown_info_ts' is not a window MAX") | caught |
| frame | availability MAX frame only: `ROWS BETWEEN 19 PRECEDING` → `ROWS BETWEEN 9 PRECEDING` for `realized_vol_20d_info_ts`, metric `STDDEV_SAMP(...) * SQRT(252)` keeps 19 | FAIL | `test_output_availability_is_window_max` **1 failed** ("window frame does not match companion metric. Info frame: … ROWS BETWEEN 9 PRECEDING …, Metric frame: … ROWS BETWEEN 19 PRECEDING …") | caught |
| a (re-run) | `GREATEST(e.entity_info_ts, b.bench_max_info_ts)` → `GREATEST(e.entity_info_ts)` (docs:429) | FAIL | `test_output_availability_is_window_max` **1 failed** ("GREATEST must combine at least 2 availability timestamps, found 1") | caught |
| c (re-run) | drop `:start_date` bound (both entity & benchmark input CTEs → `event_date IS NOT NULL`) | FAIL | `test_start_date_bound_in_inputs` **1 failed** ("must filter by event_date >= :start_date") | caught |
| d (re-run) | bounded-bars `AS close_price` → `AS close_price_bogus` (both variants, section-scoped) | FAIL | `test_registry_output_fields_match_view_columns` **1 failed** ("output_field 'close_price' not found in view 'serve_bounded_daily_bars_v1'") | caught |
| e (re-run) | coverage enforcement restricted to `Operation.aggregate` only (`policy.py` coverage check) | FAIL | `test_iv_trend_coverage_check` / `test_iv_compare_coverage_check` / `test_iv_rank_coverage_check` **3 failed** | caught |

## No tests deleted/weakened

`git diff 41c3e2c..HEAD -- tests/` touches only `tests/analytics_nl/test_ddl.py` (+204 / −28). The 28 deleted lines are the prior vacuous implementation of `test_output_availability_is_window_max` (the `re.findall(... >= 2)` logic), replaced by the strictly-stronger token-resolution + frame-matching implementation. No `def test_*` was removed; no `assert`/`skip`/`xfail` weakened. `analytics_nl/policy.py` and `docs/` are unchanged in this range.

## Non-blocking notes

- The frame-matching (`_extract_metric_window_frame`, test_ddl.py:664) is substantive only for tokens whose companion metric follows the `*_info_ts → <base>` naming convention (`realized_vol_20d_info_ts → realized_vol_20d`, `drawdown_info_ts → drawdown`). For `entity_info_ts → cumulative_return` and `bench_max_info_ts → bench_cumulative_return` (relative-performance view, block 5) the naming convention fails and Strategy 2 returns the info frame itself, so the "frame matches metric" assertion is vacuous there. This is acceptable: those two metrics use `UNBOUNDED PRECEDING` frames where a 19→9-style mismatch is not a hazard, and the primary "is a window MAX" check (`_resolve_token_to_cte`) still covers all four tokens. Not blocking.
- The `_resolve_token_to_cte` / `_extract_window_frame` checks are regex string-match over the DDL markdown, not a semantic engine run (same class of limitation as items 3/5 noted in round 14). Correct for the PIT-safety contract this test guards.

## Checks run

- `python3 -m pytest tests/analytics_nl -q` (repo @5905f78) → **343 passed** (15.4s).
- `PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps python3 -m pytest tests/analytics_nl -q` → **343 passed** (15.7s; pyspark hidden, no pyspark import).
- `python3 -m analytics_nl.export_schemas --check` → "All schemas match."
- Mutation dirs `/tmp/nl1r15-mut-*`: each run `python3 -m pytest tests/analytics_nl -q` → results in table above (all `1 failed, 342 passed`, except `e` = `3 failed, 340 passed`).
- `git status --short` → clean (working tree unchanged by this check).
===VERDICT END===
