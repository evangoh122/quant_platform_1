===VERDICT START===
# VERDICT: nl1-round19 — DeepSeek (checker)
**Status:** CHANGES_REQUESTED
**Round:** 19

Range verified: `53d36a5..c8e3302` (MiMo round-19 build). Source read-only; every mutation performed in `/tmp/ds-*` copies created via `git archive HEAD | tar -x -C /tmp/<dir>`. Working tree untouched by this check.

Items 1–4 of the check request are closed (mutations killed). Item 5 is **not** closed: Codex's exact mutation (`GREATEST(dp.information_available_ts, adj.information_available_ts)` → `dp.information_available_ts`) still survives.

## Blocking findings

- [tests/analytics_nl/test_ddl.py:1084] `test_mutation_drop_adj_availability_from_greatest_fails` is vacuous — it does not catch the regression it claims to guard. Codex's exact item-5 mutation, `GREATEST(dp.information_available_ts, adj.information_available_ts) AS information_available_ts` → `dp.information_available_ts AS information_available_ts` (docs/NL1_PROPOSED_SERVING_VIEWS.md:173), yields **418 passed, 1 skipped** on the full suite — the regression is undetected. Two root causes:
  1. The added test applies the mutation to the *extracted* SQL itself and only asserts the mutation was applied (that GREATEST no longer holds both args). It never re-runs the availability-contract assertion on the mutated SQL, so it can never FAIL on a real DOC regression.
  2. Under the external mutation the test's guard `"ADJ.INFORMATION_AVAILABLE_TS" not in sql.upper()` (`test_ddl.py:1099`) no longer finds the block (adj.information_available_ts exists only inside the removed GREATEST), so the test **SKIPs** instead of failing.
  The `elif GREATEST ... AS INFORMATION_AVAILABLE_TS` branch added to `test_output_availability_is_window_max` (`test_ddl.py:957-965`) does not help: when GREATEST is removed entirely, `_find_greatest_args` finds no single-arg GREATEST in `returns_from_source`, so the `assert len(info_tokens) >= 2` (`test_ddl.py:987`) never fires. A late adjusted-return revision therefore still regresses without detection.
  → Required fix: assert the `returns_from_source` CTE in the adjusted equity-metrics block combines BOTH `dp.information_available_ts` AND `adj.information_available_ts` via GREATEST (or, at minimum, that the adjusted source's availability column contributes to the output availability), with a mutation that FAILS on `GREATEST(...) → dp.information_available_ts`.

## Non-blocking notes

- Item 4's ordering check in `analytics_nl/policy.py` (`cheap <= normal`) is gated behind `if not errors:` (`policy.py:~161`). A malformed policy with both a type/positivity error AND an ordering violation reports only the first class; still fail-closed (raises), but ordering violations are masked when other errors are present.
- Item 3's `_validate_registry` closes output scalar types to `{string, number, integer, date, coverage_status}`. The production registry still loads (fixture-based tests pass), but if any future output field uses a new type it will be rejected — acceptable fail-closed behaviour, worth documenting.
- The "drop adj → single-arg `GREATEST(dp.information_available_ts)`" variant IS caught by `test_output_availability_is_window_max` (`assert len(info_tokens) >= 2`, 1 failed). It is only Codex's "drop the GREATEST wrapper entirely" mutation that survives.

## Items confirmed closed (mutations killed)

| Item | Mutation | Result |
|---|---|---|
| 1 (High) | restore `if total_count > 0` in `policy.py:267` | 6 failed (`test_policy.py` zero-total / sample>total / negative) |
| 2 (High) | drop `ingest_ts` from fallback `GREATEST(derived_available_ts, ingest_ts)` | 2 failed (late-ingest shows Jan 2 not Jan 5) |
| 3 (Medium) | revert `registry.py` fail-closed validation (`git show 6248358:analytics_nl/registry.py`) | 10 failed (`test_registry.py::TestRegistryFailClosed`) |
| 4 (Medium) | revert `policy.py` bounds validation (`git show f7d80ad:analytics_nl/policy.py`) | 10 failed (`test_policy.py::TestPolicyBoundsValidation`) |
| 5 (Medium) | `GREATEST(dp…, adj…)` → `dp.information_available_ts` (Codex exact) | **SURVIVED — 418 passed, 1 skipped** |

## No production view semantic drift (beyond item 2)

`git diff 6248358^ 6248358 -- docs/NL1_PROPOSED_SERVING_VIEWS.md` changes only the two bronze **fallback** blocks (`serve_daily_prices_v1`, `serve_bounded_daily_bars_v1`): `information_available_ts` → `derived_available_ts` + `ingest_ts`, final select → `GREATEST(derived_available_ts, ingest_ts)`, plus two doc bullets. Primary (adjusted) paths unchanged; fallback output schema unchanged (no new column). The bronze `ingest_ts <= :as_of` predicate is preserved.

## Round 16–18 mutations still killed

- `test_mutation_bronze_without_ingest_ts`, `test_mutation_as_of_after_window`, `test_mutation_equity_metrics_as_of_after_window` → pass (guards intact).
- trailing-newline ticker/index/sector rejection (`test_contracts.py`) → 3 passed.
- IV 12/19,390 + absent-stat → INSUFFICIENT_DATA for all four operations (existing `TestInsufficientData` suite passes).

## Checks run

- `python3 -m pytest tests/analytics_nl -q` (repo @HEAD) → **419 passed** (14.8s).
- `PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps python3 -m pytest tests/analytics_nl -q` → **419 passed** (pyspark hidden).
- `python3 -m analytics_nl.export_schemas --check` → "All schemas match."
- Mutation dirs `/tmp/ds-nl1-r19`, `/tmp/ds-mut2`, `/tmp/ds-mut2b`, `/tmp/ds-mut3`, `/tmp/ds-mut4`, `/tmp/ds-mut5`, `/tmp/ds-mut5b`, `/tmp/ds-mut5c`, `/tmp/ds-old`: each a `git archive` copy with a single mutation → results above.
===VERDICT END===
