> **IMPLEMENT NOW, end to end.** Do not stop to ask "Shall I proceed?". Commit after each stage so a timeout never loses work. NEVER delete or weaken existing tests. No network calls in tests (yfinance via fixtures only).

# BUILD: corporate-actions lane

## 0. Purpose, branch, and non-negotiable scope

Build this lane on `slice/corporate-actions`, based on `origin/main`. The live fact to correct is that `bootcamp_students.evangoh_capstone.bronze_ohlcv_day` contains unadjusted Massive/Polygon daily bars. Claude measured 237 `(symbol, event_date)` observations from 2022 through 2026 among symbols that have ever appeared in `gold_tradable_universe` where `abs(close / previous_close - 1) >= 0.40`. Most are splits (for example AMZN, GOOG/GOOGL, SHOP, TSLA, COHR, PANW, FTNT, DXCM and reverse-split leveraged ETFs); `META` on 2022-06-09 is ticker reuse, not a split.

This lane owns corporate-action ingestion, adjusted daily Silver data, break classification/masking, tests, orchestration, documentation, and a live verification report. It **does not** edit either downstream consumer branch. In particular, do not copy or edit `strategies/` or `analytics_nl/` here; section 8 defines the interfaces their later lanes must consume.

Do not modify `.agents/dispatch.sh`. Use LF line endings. Tests must be offline and must never call yfinance. Do not add dependencies: yfinance is already in `requirements.txt` and has reference code at `etl/extract_yfinance.py:1-95` (`yf.Ticker(...).history(..., auto_adjust=False)`, retry and delay conventions). Do not resurrect its retired DuckDB writer.

Dividends are explicitly deferred in v1. The required Bronze schema has no dividend amount/currency fields, and dividends do not explain the observed split-scale discontinuities. Design the adapter so a later `CorporateAction` variant can add dividends, but do not put dividend records into a split-only schema or use yfinance `Adj Close`.

## 1. Required files and staged commits

MiMo may create/edit only these production/test/docs files for this lane (plus its required verdict):

1. `etl/corporate_actions.py` — source-neutral dataclass/protocol, yfinance adapter, normalization, retry/rate-limit helpers. It must be importable without Spark and must have no network/import-time side effects.
2. `notebooks/refresh_bronze_corporate_actions.py` — Databricks notebook entry point, dry-run/write/resume logic, table creation if absent, append-only anti-join, JSON report.
3. `silver/08_silver_ohlcv_day_adjusted.sql` — deterministic daily deduplication, split factor, adjusted OHLC/VWAP/volume, break classification and masked return. It may contain idempotent `CREATE TABLE IF NOT EXISTS` and `MERGE` statements split by semicolons, matching `pipelines/run_silver_gold.py:125-155`.
4. `pipelines/run_silver_gold.py` — register the corporate-actions step after existing Silver inputs and before any daily Gold consumer; add both new Silver tables to counts/checks/target handling without changing unrelated transforms.
5. `resources/jobs.yml` — add a manually runnable, unscheduled corporate-action refresh notebook task, or add it as a predecessor of the Silver/Gold refresh only if the existing bundle syntax supports that cleanly. Default parameters must be `mode=dry-run`, a bounded per-symbol delay, and a resumable symbol range/checkpoint.
6. `tests/bronze/test_corporate_actions.py` — pure adapter/normalization/idempotency tests with fixtures/fakes.
7. `tests/silver/test_ohlcv_day_adjusted.py` — offline arithmetic, PIT helper/reference, and break-detector tests. Follow the repo's pure-test pattern; a local pandas/Python reference implementation is acceptable and preferred to requiring Spark.
8. `docs/DATA_SCHEMAS.md` — add exact schemas and PIT/quality semantics.
9. `docs/CORPORATE_ACTIONS_RUNBOOK.md` — exact commands/queries from section 9 and a result template.
10. `.agents/mimo/VERDICT-corporate-actions.md` — self-report required by the owner workflow.

Commit in these stages, each passing the relevant offline tests before proceeding:

1. `feat(corpact): add source-neutral split ingestion`
2. `feat(corpact): build adjusted daily silver data and breaks`
3. `test(corpact): cover adjustments pit and break masking`
4. `docs(corpact): add schemas and live runbook`

Do not rewrite or squash unrelated history. Report the commit SHAs in the MiMo verdict.

## 2. Corporate-action source adapter

At `etl/corporate_actions.py:1` define an immutable normalized record (dataclass or equivalent) and a source protocol such as:

```python
CorporateActionSplit(
    symbol: str,
    ex_date: datetime.date,
    split_ratio: float,                  # new shares / old shares
    source: str,
    fetched_ts: datetime.datetime,       # naive UTC, consistent with repo Spark timestamps
    information_available_ts: datetime.datetime,
)

class CorporateActionsSource(Protocol):
    def fetch_splits(self, symbol: str) -> list[CorporateActionSplit]: ...
```

Implement `YFinanceCorporateActionsSource` behind that protocol. Fetch unadjusted action history from `yf.Ticker(symbol)` (`get_splits()` if supported by the pinned dependency, otherwise the `Stock Splits` values from `history(period="max", actions=True, auto_adjust=False)`). Never infer a split from price data and never consume yfinance adjusted prices. Normalize provider timestamps to an exchange-local `ex_date`, then discard timezone. Accept only finite, positive, non-one ratios; preserve fractional reverse-split ratios exactly as `DOUBLE`. Use source value `yfinance`.

`information_available_ts` is the ex-date market open, conservatively: 09:30:00 `America/New_York` converted to naive UTC, including DST. This field is an availability boundary, not the fetch time. Tests must cover EST and EDT dates. `fetched_ts` is one captured UTC timestamp per fetch attempt so reruns do not affect the natural key.

The adapter constructor must accept injectable ticker factory, clock, sleeper, delay and retry policy. Production defaults: at most one symbol request every 0.5 seconds (configurable upward), exponential bounded retry for transient failures, no retry for clearly permanent empty/not-found responses, and continue/checkpoint after a symbol failure. Unit tests pass fakes and a no-op sleeper. Do not import Spark, `dbutils`, or establish a connection in this module.

The abstraction is mandatory so a future `PolygonCorporateActionsSource` can implement the same protocol without changes to normalization or Bronze writing. Do not implement Polygon while its key is broken.

## 3. `bronze_corporate_actions`: universe, schema, append-only idempotency

At `notebooks/refresh_bronze_corporate_actions.py:1`, follow the import-safe layout and JSON reporting style of `notebooks/refresh_bronze_equities.py:1-22,220-231,276-551`: pure helpers at module scope, all Spark/dbutils/network setup inside `main()`, and `if __name__ == "__main__": main()`.

The symbol set is determined live, not from `config/universe.yaml`:

```sql
SELECT DISTINCT UPPER(TRIM(symbol)) AS symbol
FROM bootcamp_students.evangoh_capstone.gold_tradable_universe
WHERE symbol IS NOT NULL
UNION SELECT 'SPY'
UNION SELECT 'RSP'
UNION SELECT 'QQQ'
```

Assert/report the measured distinct universe count before factor additions (Claude observed 557) and the final distinct count. Do not hard-fail merely because the universe evolves away from 557; hard-fail only for an empty/invalid universe. The three factor instruments must be present even if they already occur in Gold.

Create/read this Delta table:

| column | type | null | semantics |
|---|---|---:|---|
| `symbol` | STRING | no | normalized uppercase ticker |
| `ex_date` | DATE | no | first session trading on the new share basis |
| `split_ratio` | DOUBLE | no | new shares / old shares; 20.0 for AMZN 20:1, 0.1 for 1:10 reverse split |
| `source` | STRING | no | `yfinance` in v1 |
| `fetched_ts` | TIMESTAMP | no | UTC fetch observation time |
| `information_available_ts` | TIMESTAMP | no | 09:30 America/New_York on `ex_date`, stored UTC |

The immutable event identity is `(symbol, ex_date, source)`. Bronze is append-only: no update, delete, overwrite, `replaceWhere`, or matched-update. For each fetched/checkpointed batch, validate fields, `dropDuplicates` on that key, then left-anti-join against the target key before append. A rerun of the exact fixture must append zero rows even though its new `fetched_ts` differs. A provider correction with the same natural key must be surfaced as a conflict in the report and must not silently mutate history; a human can authorize a later correction design.

Parameters/widgets:

- `mode`: `dry-run` (default) or `write`; reject all other values.
- `source`: only `yfinance` for now, selected through the adapter factory.
- `symbol_start` / `symbol_end`: optional inclusive lexical bounds for manual sharding/resume.
- `checkpoint_table`: operational table name with a safe fixed default such as `corporate_actions_ingestion_log`; never interpolate an arbitrary unchecked identifier.
- `delay_seconds`: default `0.5`, minimum `0.5` in production; tests exercise only pure parsing.
- `max_retries`: bounded default 2.

The operational log may be updated/appended and is not Bronze. Key attempts by `(run_id, symbol, source)` and record `RUNNING/SUCCESS/EMPTY/FAILED`, attempts, started/completed timestamps, row/conflict counts, and sanitized error text. Resume skips `SUCCESS` and `EMPTY` symbols for the same explicitly supplied/resumed run ID; a fresh run refetches them so newly announced history can be discovered. Mark `SUCCESS` only after post-append key verification. A failed symbol remains retryable, and one failure must not lose completed symbols.

Dry-run performs the actual reads, normalization, validation, deduplication and anti-join/counting but writes **neither Bronze nor the operational log**. Both modes print and notebook-exit a machine-readable JSON summary with: mode/run ID, source, universe counts, symbol bounds, attempted/success/empty/failed/resumed symbol counts, candidate/deduped/existing/new/conflict/action counts, pre/post Bronze counts, failures by symbol, duration and effective request rate. Never print credentials.

## 4. Adjusted daily contract and exact arithmetic

At `silver/08_silver_ohlcv_day_adjusted.sql:1`, create/populate both `silver_ohlcv_day_adjusted` and `data_quality_breaks`. Source daily bars from `bronze_ohlcv_day`, restricted to symbols in the live corporate-action universe. Deduplicate `(symbol, event_date)` deterministically with `ROW_NUMBER`, preferring latest `ingest_ts` and then stable source/source-file ordering. Reject null/nonpositive OHLC values, negative volume, and impossible OHLC ranges from the adjusted output (count them in checks; do not silently convert them to zero).

For a bar date `d`, define:

```text
cumulative_split_ratio(d) = PRODUCT(split_ratio_s for all splits s where s.ex_date > d)
price_adjustment_factor(d) = 1 / cumulative_split_ratio(d)
adj_open   = open  * price_adjustment_factor
adj_high   = high  * price_adjustment_factor
adj_low    = low   * price_adjustment_factor
adj_close  = close * price_adjustment_factor
adj_vwap   = vwap  * price_adjustment_factor  (NULL stays NULL)
adj_volume = volume / price_adjustment_factor = volume * cumulative_split_ratio
```

An ex-date bar is already on the new share basis, so its split is **not** included for that bar (`ex_date > event_date`, not `>=`). Multiple splits multiply. With no later split, both factors are 1. Use log-sum-exp (`EXP(SUM(LN(split_ratio)))`) or an equivalently stable product; never use floating exponent tricks. The final values must be positive/finite where raw values are valid. `adj_volume` is `DOUBLE` because fractional reverse-split factors need not yield an integer; do not round.

Required output columns:

| column | type | note |
|---|---|---|
| `symbol` | STRING | key part |
| `event_date` | DATE | key part; downstream may alias to `trade_date` |
| `event_ts` | TIMESTAMP | source daily timestamp |
| `open`, `high`, `low`, `close`, `volume`, `vwap`, `trade_count` | source types | raw audit columns |
| `cumulative_split_ratio` | DOUBLE | product above |
| `price_adjustment_factor` | DOUBLE | reciprocal above |
| `adj_open`, `adj_high`, `adj_low`, `adj_close`, `adj_vwap` | DOUBLE | globally/current-scale back-adjusted levels |
| `adj_volume` | DOUBLE | split-adjusted share volume |
| `raw_overnight_return` | DOUBLE | `close / LAG(close) - 1` |
| `adjusted_return_1d_unmasked` | DOUBLE | `adj_close / LAG(adj_close) - 1` |
| `return_1d` | DOUBLE nullable | canonical return; NULL when the date has an active DQ break |
| `is_data_quality_break` | BOOLEAN | active unresolved/confirmed break mask |
| `information_available_ts` | TIMESTAMP | 16:30 America/New_York on the bar date, converted to UTC |
| `processed_ts` | TIMESTAMP | build lineage |

Populate idempotently with a stable `(symbol,event_date)` key. It is acceptable for Silver to use a matched update because a newly ingested future split necessarily changes older current-scale adjusted levels. A rerun with identical inputs must not duplicate rows. Ensure stale historical factors are updated when a later split arrives; an insert-only incremental window is incorrect.

### Point-in-time decision

The stored `adj_*` columns are **global/current-scale back-adjusted display levels** and knowingly use future split events to rescale past levels. They are approved for computing returns because:

- within a split-free interval, the same factor cancels from the ratio; and
- across an ex-date, the prior bar includes that split and the ex-date bar does not, removing the mechanical jump.

They are **not approved as model price-level features** at a historical observation time. Any feature using a level (threshold, dollar price, distance to a fixed level, raw adjusted price in a model, etc.) must compute an as-of-`t` adjusted history using only splits whose `information_available_ts <= t` (equivalently, for end-of-day features, `row_date < ex_date <= DATE(t)`):

```text
pit_factor(row_date, t) = 1 / PRODUCT(split_ratio_s
                                      where row_date < s.ex_date
                                        and s.information_available_ts <= t)
pit_adjusted_price(row_date, t) = raw_price(row_date) * pit_factor(row_date, t)
```

Do not add a misleading single `pit_adj_close` column without an as-of dimension. Document and test the two-dimensional helper/reference calculation. The canonical `return_1d` from the global adjusted series is PIT-safe at that day's close because only the split effective that morning is needed to repair that day's ratio; no future split changes that ratio.

## 5. Conservative break detector, review states, and masking

Run detection over the 2022-01-01 through the current data maximum at minimum, and support all history. A candidate is a deduplicated consecutive observed bar pair for the same symbol with both closes positive and:

```text
abs(raw_gross_return - 1) >= 0.40
raw_gross_return = close_d / close_previous_observed_bar
```

Weekends/holidays are normal because comparison is to the previous observed bar. Do not compare across a symbol-history identity boundary if one is already explicitly known; in v1, META has no such mapping and must be caught as a candidate.

A candidate is mechanically explained by splits on `d` only if there is at least one Bronze split with `ex_date = d` and:

```text
day_split_ratio = PRODUCT(all unique split_ratio events on d)
post_split_gross_return = raw_gross_return * day_split_ratio
split_error = abs(post_split_gross_return - 1.0)
split_error <= 0.03
```

Thus AMZN's roughly 0.051 raw gross return times 20 is near 1 and is explained. The tolerance is an absolute three-percentage-point organic move after removing the mechanical ratio; do not use `abs(adjusted_return) >= 40%` as an automatic deletion rule. A ≥40% real move can happen. Candidates without a matching split or outside the 3% tolerance enter `data_quality_breaks` for review and are conservatively masked pending review, rather than silently dropped or zero-filled.

Required `data_quality_breaks` columns:

| column | type | semantics |
|---|---|---|
| `symbol`, `event_date` | STRING, DATE | stable key |
| `previous_event_date` | DATE | compared bar |
| `previous_close`, `close` | DOUBLE | evidence |
| `raw_overnight_return` | DOUBLE | evidence |
| `matched_split_ratio` | DOUBLE nullable | same-day product, if any |
| `post_split_gross_return`, `split_error` | DOUBLE nullable | explanation evidence |
| `classification` | STRING | `SPLIT_EXPLAINED`, `UNEXPLAINED_PENDING`, `CONFIRMED_DATA_BREAK`, or `ALLOW_REAL_MOVE` |
| `reason` | STRING | e.g. `ticker_reuse`, `verified_earnings_move`; no secrets/freeform SQL |
| `is_masked` | BOOLEAN | true only for pending/confirmed |
| `reviewed_by`, `reviewed_ts` | STRING, TIMESTAMP nullable | audit fields |
| `detected_ts`, `processed_ts` | TIMESTAMP | lineage |

Preserve manual review decisions on rerun: transformation logic may refresh computed evidence/classification for unreviewed rows but must never overwrite a reviewed `ALLOW_REAL_MOVE` or `CONFIRMED_DATA_BREAK`. Implement the allow-list as reviewed rows in this table (or a separate small append-only review table joined by the stable key), not a Python/SQL hardcoded list. `ALLOW_REAL_MOVE` makes `is_masked=false` and restores the adjusted return. `CONFIRMED_DATA_BREAK`, including META 2022-06-09 ticker reuse, remains masked. `UNEXPLAINED_PENDING` is also masked fail-closed until reviewed. `SPLIT_EXPLAINED` is retained for reconciliation but never masked.

Mask only the return whose endpoint is the candidate date: `return_1d = NULL`, never `0`. Do not null adjacent prices or automatically mask the following day's return. Log/report every active mask. Keep `adjusted_return_1d_unmasked` and evidence for audit, but downstream sanctioned consumers must select canonical `return_1d` or reproduce its mask.

The live report must reconcile **exactly 237 baseline candidates** for the same Claude scope (ever-in-Gold symbols, 2022 onward, factor instruments included only if they are part of that declared scope). Report:

```text
baseline_candidates = split_explained + unexplained_pending
                      + confirmed_data_break + allow_real_move
```

Do not invent the split-explained/flagged counts in code or documentation. Compute and print them from live data, list the unexplained keys, and fail the baseline verification if the total is not 237 until the cause (scope/date/data drift) is explicitly reported. Separately report current/full-history counts so future reruns can evolve without hardcoding 237 forever.

## 6. Offline tests that must fail before this lane exists

No test may use network, Databricks credentials, `dbutils`, or a live Spark catalog. Use yfinance-shaped pandas fixtures and fake adapters/clocks/sleepers. At minimum:

1. Adapter normalization: forward 20:1 yields `20.0`; reverse 1:10 yields `0.1`; zero/one/negative/NaN action values are rejected; timestamps map to the correct exchange `ex_date` and 09:30 ET availability in both DST regimes.
2. Source isolation: fake source satisfies the protocol; importing modules makes no calls; yfinance exceptions retry with the injected sleeper and eventually checkpoint failure.
3. Bronze idempotency: duplicate fixture rows and a second fetch with a different `fetched_ts` produce one natural key/zero new rows; a same-key/different-ratio correction is a reported conflict.
4. AMZN 20:1: fixture values approximately `prev close=2447`, `ex-date close=124.79` (or other sourced fixture with the same mechanics). The prior adjusted close is divided by 20, ex-date price factor is 1, and adjusted return is approximately +2%, never approximately -95%.
5. Reverse split: a 1:10 action (`split_ratio=0.1`) multiplies prior price by 10 and prior volume by 0.1; ex-date factor remains 1.
6. Multiple splits: products apply in chronological/future order, including a forward plus reverse split; verify OHLC/VWAP share the factor, volume uses its reciprocal, and no-split rows use 1.
7. Split-day truth: construct `old_close`, organic return `g`, and ratio `r`, with raw ex-date close `old_close * g / r`; assert adjusted return equals `g - 1` to tight floating tolerance for forward and reverse splits.
8. PIT rule: adding a split after as-of `t` changes the global historical `adj_close` but does not change `pit_adjusted_price(row_date,t)`; a split with availability at/before `t` does change the PIT history; ex-date morning availability is respected.
9. Breaks: AMZN is `SPLIT_EXPLAINED`; META fixture (`META`, 2022-06-09, approximately +1395%, no split) is `UNEXPLAINED_PENDING`, logged and `return_1d is NaN`; an allow-listed genuine ≥40% move is `ALLOW_REAL_MOVE` and keeps its actual return; never assert/fill zero.
10. Tolerance boundaries: exactly 3% after split correction is explained, just beyond is flagged; a same-date split with a huge residual move is flagged.
11. Review persistence: rerunning computed data does not overwrite reviewed allow/confirmed states.
12. SQL/static contract: tests read the SQL and assert strict `ex_date > event_date`, canonical masked `return_1d`, required columns/table names, and no Bronze update/delete/overwrite. Avoid brittle assertions about whitespace.

Before implementation, demonstrate these new tests fail against the current checkout because the modules/files/contracts do not exist (a focused collection/import failure is acceptable for the pre-build proof). After implementation run:

```bash
python -m pytest -q tests/bronze/test_corporate_actions.py tests/silver/test_ohlcv_day_adjusted.py
python -m pytest -q
git diff --check
```

Record exact commands, pass/fail totals and the pre-build failure evidence in `.agents/mimo/VERDICT-corporate-actions.md`.

## 7. Orchestration and table checks

At `pipelines/run_silver_gold.py:39-64`, add the adjusted daily step in dependency order and both `silver_ohlcv_day_adjusted` and `data_quality_breaks` to managed counts/checks. Do not make the existing minute `silver_ohlcv` depend on daily actions. The adjusted build must run after `bronze_corporate_actions` has been refreshed and before any future daily Gold/serving views consume it.

Add checks that fail or clearly return nonzero for:

- duplicate `(symbol,ex_date,source)` Bronze action keys;
- duplicate `(symbol,event_date)` adjusted keys and break keys;
- nonpositive/nonfinite ratios/factors/adjusted prices;
- `price_adjustment_factor * cumulative_split_ratio` materially different from 1;
- explained rows whose `split_error > 0.03` or active masked rows whose canonical `return_1d IS NOT NULL`;
- canonical returns equal to zero solely because a break was masked (mask must be NULL);
- the AMZN 2022-06-06 sanity query not returning an adjusted move near +2% (use a documented tolerance, e.g. -1% to +5%, while printing the actual value);
- live baseline reconciliation not summing to its candidate count.

Avoid `TRUNCATE` semantics that would erase manual break reviews. If the existing `--truncate` path includes these tables, explicitly exclude/rebuild computed Silver safely while preserving review state, and document that behavior.

## 8. Downstream interfaces only — changes land in later lanes

### Strategy lane after this merges

Current code on `origin/slice/strategy-residual-reversion`, `strategies/run_residual_reversion.py:68-90`, selects raw `close` from `bronze_ohlcv_day`; `build_wide` at lines 101-102 expects a column named `close`. The later strategy change is intentionally minimal:

```sql
SELECT symbol, event_date, adj_close AS close
FROM ${FQN}.silver_ohlcv_day_adjusted
WHERE symbol IN (... Gold universe plus SPY/RSP/QQQ ...)
  AND adj_close IS NOT NULL AND adj_close > 0
```

It must also fetch active breaks (`is_masked=true`) or, preferably, fetch canonical `return_1d` directly and ensure the strategy return frame uses it. If retaining `compute_daily_returns(adj_close)`, explicitly set those `(event_date,symbol)` cells to `NaN` after `pct_change(fill_method=None)` and log count/keys. Never set them to 0. Add a strategy test proving META is NaN and does not enter factors/P&L, while AMZN's split-day return is normal. Preserve SPY/RSP/QQQ and universe masking behavior at `run_residual_reversion.py:132-177`. Regenerate r9 under a new result revision; do not relabel contaminated r9.

### NL1 lane after this merges

On `origin/slice/nl-contracts`, the registry already names logical serving views and `adj_close`; the physical error is in proposed DDL: `docs/NL1_PROPOSED_SERVING_VIEWS.md:36-70,74-145,218-253` reads/assumes `bronze_ohlcv_day`. The later NL lane must point `serve_daily_prices_v1`, `serve_bounded_daily_bars_v1`, and the base of `serve_daily_equity_metrics_v1` at `silver_ohlcv_day_adjusted`; alias `event_date AS trade_date`; expose `adj_close`; use canonical masked `return_1d` rather than independently recomputing an unmasked `LAG`; and propagate NULL into rolling return-derived metrics according to their existing minimum-observation policy. The logical names in `analytics_nl/data/semantic_registry_v1.yaml:9-15` need not change unless the NL owner versions the serving views, but descriptions/tests must state adjusted, break-masked semantics. Price-level outputs are current-scale display values, not PIT model features; disclose this in NL metadata. No NL files are edited in this corporate-actions lane.

## 9. Live runbook for Claude

Write `docs/CORPORATE_ACTIONS_RUNBOOK.md` with copy/paste-ready commands appropriate to this repo/Databricks bundle and these gates:

1. **Deploy/check identity.** Confirm catalog/schema/profile, current branch/commit, target table schemas, and the live symbol query. Print the pre-run Bronze row/key counts. Never echo tokens.
2. **Dry-run.** Run the refresh with `mode=dry-run`, yfinance source, full lexical range and delay ≥0.5 seconds. Save JSON. Require zero writes, no schema errors, and explicitly review failed/empty/conflict symbols. Resume dry-run shards if needed.
3. **Fetch/write.** Run `mode=write` with a named run ID; resume the same run after interruption. Require all nonempty symbols success, post-count delta equal new rows, and zero duplicate natural keys. Rerun once and prove zero appended rows.
4. **Build Silver.** Run only the adjusted daily step (or documented orchestrator command), preserving reviewed DQ states. Run table checks and duplicate/factor invariants.
5. **AMZN verification.** Query raw prior close, raw ex-date close, same-day split ratio, factors, adjusted closes and canonical return for 2022-06-03/2022-06-06. Require AMZN 2022-06-06 adjusted/canonical return to print approximately +2% (accept the documented -1% to +5% guard), not approximately -95%, and `is_data_quality_break=false`.
6. **Known examples.** Print classification/evidence for GOOG, GOOGL, SHOP, TSLA, COHR, PANW, FTNT, DXCM and representative SQQQ/SOXS/FNGU reverse splits. Print META 2022-06-09 as non-split, masked, and pending/confirmed ticker reuse.
7. **Reconcile 237.** Recreate Claude's exact 2022-2026 ever-in-Gold ≥40% scope; group by classification and masking; assert the categories sum to 237; output `split_explained` and `flagged = unexplained_pending + confirmed_data_break` plus allow-real-move count. List every flagged key and evidence. If the total differs, stop consumer rollout and report scope/date/source drift rather than changing the constant.
8. **Review real moves.** A human verifies flagged events externally and records either `ALLOW_REAL_MOVE` with reason/reviewer/timestamp or `CONFIRMED_DATA_BREAK`. Rebuild and prove allowed returns are restored and confirmed/pending remain NULL.
9. **Consumer gate.** Do not run strategy r10 or deploy NL serving DDL until this lane is merged and the separate consumer changes in section 8 pass their tests.

The runbook must include a dated result block Claude can fill with: source/run ID, symbols attempted/succeeded/failed, Bronze new/conflicts, candidate total, split-explained, pending, confirmed, allow-listed, masked total, AMZN raw/adjusted return, META status, duplicate counts, and query timestamp. MiMo must not fabricate live values if it cannot access Databricks/yfinance.

## 10. Acceptance criteria

This lane is ready for DeepSeek only when all are true:

1. Bronze contains normalized split history for the live ever-in-Gold universe plus SPY/RSP/QQQ via the swappable adapter, with append-only natural-key idempotency, dry-run, throttling, retry, checkpoint/resume and conflict reporting.
2. Silver correctly adjusts OHLC/VWAP and inverse-adjusts volume for forward, reverse and multiple splits; factors are explicit and idempotently refreshed when future actions arrive.
3. The global-level versus PIT-level distinction is documented and enforced by tests; no false claim calls global historical price levels PIT-safe.
4. Every ≥40% candidate is classified conservatively using same-date split correction and 3% tolerance; pending/confirmed breaks produce NULL canonical returns; reviewed real moves are retained.
5. The live report computes, rather than assumes, how many of Claude's 237 are split-explained versus flagged. AMZN is repaired and META is flagged/masked.
6. Both future consumer interfaces are documented exactly, but no strategy/NL branch file is changed here.
7. Focused and full offline test suites pass, `git diff --check` is clean, commits are staged, and the MiMo verdict exists.

## 11. DeepSeek must check

DeepSeek's verdict must explicitly return `APPROVED` or `CHANGES_REQUESTED` with file:line evidence for each item:

1. No yfinance/network call occurs in tests or at import; adapter is genuinely source-neutral and does not use `Adj Close`.
2. Split ratio orientation is new/old everywhere; strict `ex_date > event_date`, price divide/volume multiply math handles forward, reverse and multiple splits.
3. Bronze writes are append-only and key on `(symbol,ex_date,source)` excluding `fetched_ts`; retries/resume cannot duplicate or silently overwrite corrections.
4. `information_available_ts` is ex-date 09:30 ET with DST; daily return availability is no earlier than 16:30 ET.
5. PIT explanation/test is mathematically correct: global back-adjusted levels are not used as historical model-level features, while ratios are safe.
6. Break matching uses `abs((close/prev_close)*ratio - 1) <= 0.03`, not a blind ≥40% drop; META is not misclassified as a split; pending/confirmed returns are NULL, never zero; allow-list reviews persist.
7. Window order is correct: `LAG` is computed before filtering candidate rows/date ranges, so the first in-range return has its true prior observation.
8. Live reconciliation is scoped identically to the 237 baseline and reports actual explained/flagged counts without hardcoding their split; AMZN sanity and reverse-split examples are in the runbook.
9. Orchestrator dependency order is correct and truncate/rebuild cannot erase manual reviews.
10. No files outside section 1 (especially `.agents/dispatch.sh`, strategy, or NL files) changed; LF, staged commits, focused/full pytest and `git diff --check` evidence are present.

After completing the staged implementation, MiMo must write `.agents/mimo/VERDICT-corporate-actions.md` with changed files, design decisions, pre-build failing-test proof, test outputs, commit SHAs, any unavailable live checks, and an explicit self-verdict. Do not open a PR; DeepSeek, Codex, and Claude reviews come first.
