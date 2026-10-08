# Massive incremental market-data plan

## Decision and scope

Massive market data is not CDC today. The Lakebase outbox in `db/migrations/004_analytics_outbox.sql` and `pipelines/lakebase_analytics.py` covers operational Lakebase rows only. Massive extraction is manual: the production-capable code is in `notebooks/refresh_bronze_equities.py`, `notebooks/refresh_bronze_options.py`, and `notebooks/refresh_bronze_corporate_actions.py`, with older reference implementations in `notebooks/01_ingest_market_data.py` and `notebooks/archive/00_project_setup.py`. The `etl/extract_polygon.py`, `etl/extract_stocks.py`, and `etl/extract_options.py` writers target retired DuckDB paths; the last two are IBKR, not Massive. They must not be scheduled.

Build one bounded batch pipeline, not streaming CDC. It discovers provider dates, re-reads a correction window, appends immutable Bronze observations, incrementally reconciles Silver/Gold, and records a durable manifest. Keep the new job `PAUSED` until the owner approves both its first backfill and activation. Never print, persist in manifests, or put into task parameters the S3 secret or REST `apiKey`; resolve `evangoh_capstone/massive_s3_access_key` and `evangoh_capstone/massive_s3_secret_key` at runtime. The secret key is also the REST key for splits and, if added, dividends.

The observed starting facts are `silver_ohlcv` through 2026-09-02 and `gold_model_features` through 2026-09-03. Every run must measure live maxima rather than treating those dates as configuration.

## Current-state map

“Natural key” below is the business identity used for deduplication and reconciliation; `ingest_ts` remains lineage, never part of that identity. The scope column distinguishes code that currently populated a table from a supported future lane.

| Massive dataset | Source/extractor today | Bronze target and natural key | Current downstream |
|---|---|---|---|
| U.S. stock SIP minute aggregates | S3 `us_stocks_sip/minute_aggs_v1`; `notebooks/refresh_bronze_equities.py` (logic derived from the archive) | `bronze_ohlcv`; `(symbol, event_ts, timespan)` with `timespan='minute'` | `silver_ohlcv` → `gold_ohlcv_features` → `gold_model_features`; minute bars also support execution/VWAP analysis |
| U.S. stock SIP daily aggregates | S3 `us_stocks_sip/day_aggs_v1`; `notebooks/refresh_bronze_equities.py` | `bronze_ohlcv_day`; `(symbol, event_ts, timespan)` (equivalently symbol/session date/day) | `silver_ohlcv_day_adjusted`; directly feeds `gold_tradable_universe` and `gold_regime_features`; adjusted daily data feeds UI/NL analytics |
| U.S. options OPRA daily aggregates | S3 `us_options_opra/day_aggs_v1`; `notebooks/refresh_bronze_options.py` | `bronze_options_day`; `(contract_symbol, event_ts, timespan)` | Direct volume input to `gold_options_features` (20-session window), then PIT AS-OF input to `gold_model_features` |
| Options-chain quote/IV/Greeks snapshots | Massive REST current options-chain snapshot; `notebooks/refresh_bronze_options.py` and legacy `notebooks/01_ingest_market_data.py` | `bronze_options_quotes`; `(option_symbol, participant_ts)`; provider timestamp preferred, otherwise one persisted run snapshot timestamp | `silver_options_quotes` → snapshot-only IV/Greeks fields in `gold_options_features` → `gold_model_features` |
| Options-chain last-trade snapshot | Legacy `notebooks/01_ingest_market_data.py` creates a trade row from the current chain snapshot; no active refresh lane | `bronze_options_trades`; `(option_symbol, participant_ts, sequence_id)` when sequence exists, otherwise `(option_symbol, participant_ts)` | `silver_options_trades`; not currently used by the Gold feature matrix |
| Split corporate actions | Massive REST `/v3/reference/splits`; `notebooks/refresh_bronze_corporate_actions.py` via `etl/corporate_actions.py` | `bronze_corporate_actions`; `(symbol, ex_date, source)` | `silver_ohlcv_day_adjusted` and `data_quality_breaks`; therefore affects adjusted daily history, UI prices, and return consumers |
| Index aggregates (for example `I:SPX`, `I:NDX`) | Legacy archive REST aggregate loop into `bronze_economic_metrics`; manual/reference-only today | `bronze_economic_metrics`; require `(metric_type, symbol, metric_name, event_ts, source)` after live-schema validation | No version-controlled Silver/Gold transform presently consumes these Massive index rows. `gold_regime_features` instead uses SPY/RSP/QQQ daily equity bars |
| Massive stock financials, forex and crypto metrics | Legacy archive REST paths into `bronze_economic_metrics`; manual/reference-only | Same table/key contract as index metrics, after schema validation | No current Silver/Gold consumer; exclude from the first scheduled job unless the owner explicitly retains this legacy scope |
| Dividends | No current extractor/table contract. Massive REST credentials are capable of the endpoint, but splits-only `bronze_corporate_actions` cannot represent dividends | None today; do not overload the split schema. A separate dividend schema/key such as `(symbol, ex_date, declaration_date, dividend_type, source)` needs its own approved design | No current downstream transform; out of M1–M5 until schema and PIT availability semantics are approved |
| Polygon/Massive ticker reference and stock snapshots | `etl/extract_polygon.py` only, through retired DuckDB tables (`polygon_tickers`, `polygon_snapshots`) | No active Delta Bronze contract | No current Silver/Gold path; explicitly not part of the scheduled job |

The existing full-market option minute prefix and `bronze_options_minute` archive path are also not consumed by current transforms. Do not silently add them to the recurring paid workload.

## Incremental Bronze contract

### Watermarks and planned pulls

Use Delta as the authority; no local checkpoint file is allowed. For each dataset/symbol (or contract family where a provider file is the unit), derive `max_event_date` from the target’s source event timestamp, not `ingest_ts`. Store the measured high watermark and the resulting plan in `massive_ingestion_manifest`, but recompute it from Bronze on each run so a lost manifest cannot skip data.

The manifest is one row per run/dataset/source object or REST request and contains: `run_id`, dataset, symbol/scope, source object or redacted endpoint name, planned start/end, observed target watermark, request/snapshot timestamp, status (`PLANNED`, `RUNNING`, `SUCCESS`, `FAILED`, `SKIPPED`, `CONFLICT`), candidate/new/corrected/rejected counts, payload/object checksum where available, started/completed timestamps, and a sanitized error class/message. Its natural key is `(run_id, dataset, source_object_or_request_id)`. Operational status rows may be MERGEd; Bronze market rows may not be updated or deleted.

Default planning rules:

- Flat files: `start = max(event_date) - correction_lookback + 1`, capped by explicit `--start-date`; `end = min(last completed/available US session, --end-date, start + max_days_per_run - 1)`. Defaults: seven calendar days for minute/daily equities and options daily, `max_days_per_run=5` for minute files and `20` for daily files.
- REST options snapshots: one capture per run after close; they are not historical. Do not loop dates or relabel a current response as an old snapshot.
- Splits: query each configured symbol using `execution_date.gte = watermark - 30 days` when supported, otherwise paginate and filter locally. Re-reading history is cheap enough to detect corrections. A dividend lane remains disabled until separately approved.
- Index/economic metrics: disabled by default. If approved, use a per-symbol event-date watermark and the same seven-day overlap.

`--dry-run` performs discovery and entitlement probes and prints a secret-free plan: dataset, symbol/file count, date span, estimated requests/bytes, candidates if parsed, already-successful objects, and guard breaches. It writes neither Bronze nor manifest. `--write` requires the same bounded plan. Hard fail before paid calls when `--max-days-per-run`, `--max-requests`, `--max-contracts`, or `--max-estimated-bytes` is exceeded; overrides require an explicit flag and owner approval.

### Calendar, lateness, corrections, and idempotency

Use an exchange calendar library with the XNYS calendar for session selection, early closes, weekends, and holidays. Provider object discovery remains authoritative: a missing weekend/holiday object is normal, while a missing expected session is reported and retried. All timestamps are UTC; session dates are America/New_York dates. A run after US close should target the last completed session and allow a configurable publication delay.

For each overlap file/request, parse with an explicit schema, reject null key/event times, normalize option rights, `dropDuplicates` on the natural key plus payload hash, and compare to existing rows. Preserve Bronze as an immutable observation log:

- An unseen natural key is appended (`MERGE ... WHEN NOT MATCHED THEN INSERT`, or an equivalent anti-join plus append).
- An identical existing key/payload is skipped.
- A changed payload for an existing natural key is appended as a correction observation with a new `ingest_ts`, payload checksum, and `correction_of_ingest_ts`/version lineage added by an approved additive schema migration. Every correction version gets its own `information_available_ts` (the `ingest_ts` of that correction observation). Bronze is never updated, deleted, overwritten, or `replaceWhere`d.
- Silver selects the latest valid observation by `(natural key ORDER BY ingest_ts DESC)` and MERGEs that canonical result. Until correction-lineage columns exist, changed same-key payloads are `CONFLICT` and fail closed rather than creating ambiguous duplicates.
- Historical features select the latest retained natural-key version with `information_available_ts <= prediction_ts`. This is the PIT selection rule; it must use the append-only Bronze replay as the history-preserving source, not latest-only Silver, because Silver overwrites the canonical row and loses prior versions.

This resolves the apparent conflict between correction handling and append-only Bronze: physical history is append-only; canonical Silver is mutable by keyed MERGE. Re-running the same run ID, source checksum, and snapshot timestamp produces zero new Bronze rows. A manifest is marked `SUCCESS` only after row-delta and key verification; partial writes remain retryable.

Rate-limit behavior is bounded exponential backoff with jitter for 429/5xx, `Retry-After` support, a request semaphore, and immediate sanitized failure for 401/403. Logs must redact query strings containing `apiKey` and must never serialize headers or secret values.

## Incremental Silver and Gold

`pipelines/run_silver_gold.py` currently substitutes the effectively full range `1900-01-01` to `2100-01-01`, so its MERGEs are idempotent but not incremental. Add explicit `--start-date`, `--end-date`, and affected-symbol inputs derived from the successful ingest manifest. The transforms must read a source lookback but write only the affected output interval.

| Transform | Incremental rule |
|---|---|
| `silver_ohlcv`, quarantine | Canonicalize and MERGE affected minute natural keys only. Include every re-pulled source partition so corrections replace the canonical row. |
| `silver_options_quotes`, `silver_options_trades` | MERGE only captured snapshot timestamps/contracts. Never forward-fill a missing snapshot. |
| `silver_ohlcv_day_adjusted`, `data_quality_breaks` | Daily-bar changes can MERGE affected dates. A newly discovered/corrected split requires recomputation of all prior dates for that symbol whose cumulative back-adjustment changes; bound by the symbol’s earliest retained daily date, not merely the overlap window. Preserve reviewed DQ decisions. |
| `gold_ohlcv_features` | Read from the beginning of each affected trading session (features are session-partitioned and use up to 30 rows); write from the earliest changed minute through session end. A late minute may change all later rows in that session. |
| `gold_options_features` | Read at least 19 prior trading observations per underlying for the 20-session volume z-score; MERGE affected feature dates. Quote-derived fields exist only for actual snapshot dates. |
| `gold_tradable_universe` | Read at least 252 prior sessions plus the five-session recency and 60-session ADV windows. Because ranks are cross-sectional, recompute all symbols for each affected `trade_date`, then delete stale membership rows and MERGE the complete date partition. |
| `gold_regime_features` | Read at least 251 prior sessions for SPY/RSP/QQQ; recompute from the earliest affected date through the current end because rolling windows and lagged returns propagate. |
| `gold_model_features` | Recompute each affected symbol/session after upstream completion; delete stale prediction timestamps for rebuilt sessions, then MERGE `(symbol, prediction_ts)`. Also rebuild sessions whose AS-OF options/SEC/COT choice changed. |
| `gold_trading_signals` | Not built by `run_silver_gold.py`. Optional scoring may read the refreshed matrix but must be read-only by default; publishing signals requires a separate explicit, approved mode. |

Point-in-time rules are invariants, not best effort: minute OHLCV is available no earlier than bar end; daily equity/options data is available only after the session close plus the configured publication buffer; quote/trade snapshots use the provider participant timestamp (or persisted retrieval timestamp); splits use their conservative `information_available_ts`; and no feature source may have `information_available_ts > prediction_ts`. `gold_model_features` must retain `ohlcv_available_ts`, `options_available_ts`, `sec_available_ts`, and `cot_available_ts`; populated features require a non-null matching availability timestamp. Run both `run_availability_invariant` and `run_matrix_invariant` after incremental builds. No forward/back-fill of IV, Greeks, or future corporate actions is allowed.

## Orchestration and operations

Define one Databricks job in `resources/jobs.yml`, `massive_market_refresh`, with `max_concurrent_runs: 1`, failure alerts, and these dependent tasks:

1. `plan_and_ingest_massive`: equities minute/day, options day/current snapshot, and splits; dry-run/write parameterized; emits manifest run ID and affected ranges.
2. `refresh_silver_gold`: consumes only successful manifest ranges and runs incremental transforms plus PIT/DQ checks.
3. `refresh_lakebase_analytics`: runs `pipelines/lakebase_analytics.py` after features succeed. This remains logically separate from Massive CDC but is chained for one operational completion signal.
4. `score_baseline_read_only` (optional and disabled by default): loads the new feature matrix, computes validation/scoring output to run artifacts only, and cannot write `gold_trading_signals` or place orders.

Schedule after US close in `America/New_York`, for example Quartz `0 30 19 ? * MON-FRI` (19:30 ET), to cover regular and early closes with provider delay. Use `pause_status: PAUSED` in every target. Set job/task timeout, retries only for transient failures, and notify the configured owner destination on final failure and on freshness SLA breach. Do not independently schedule the old `silver_gold_refresh` and `lakebase_analytics_refresh` once the chain is enabled; retain them paused or remove their schedules to prevent races.

First backfill, still paused/dry-run by default:

```bash
databricks bundle run massive_market_refresh \
  --params mode=dry-run,start_date=2026-09-03,end_date=$(date +%F),max_days_per_run=5
```

After reviewing each dry-run chunk, the owner can authorize the same command with `mode=write`. The orchestrator must advance in bounded resumable chunks until today rather than bypassing `max_days_per_run`. For reproducibility, production should pass an explicit end date resolved by the coordinator instead of relying on shell time. Options snapshots can only capture the execution-time state; the command must report the 2026-09-03-to-first-new-snapshot coverage gap rather than invent rows.

## App freshness and agent caching

The current API marks any nonempty Delta read `fresh` and puts only a row count in `Freshness.detail`; `FreshnessBadge` therefore cannot show actual update time. Extend the existing freshness contract rather than add a second badge:

- Market and signals queries return `data_max_event_ts`/`information_available_ts`, `last_successful_ingest_ts`, and `manifest_completed_at` for the relevant source/table. The API computes `fresh`/`stale` against market-session-aware SLAs and places a human-readable “data through …; pipeline completed …” detail in the existing envelope.
- `FreshnessBadge` renders the real “Updated …” time while retaining table/state and an exact timestamp tooltip. Empty and unavailable states remain explicit.
- The agent retrieval layer must not cache mutable market results indefinitely. Add a configurable `MARKET_DATA_CACHE_TTL_SECONDS` (default 300 seconds, bounded at 30–900), include the dataset watermark/manifest version in cache keys where practical, and invalidate affected symbols after a successful refresh. Role-cache TTL is unrelated and must not be reused. Public demo snapshots keep their static freshness label.
- Expose the manifest’s last successful completion and lag in system health so a successful job with stale provider data is distinguishable from a failed job.

## Build slices and review gates

Each slice is independently dispatched as **MiMo build → DeepSeek check → Codex review**. Every build request must require LF line endings, no edits to `.agents/dispatch.sh`, a commit, and a written verdict. Tests listed here must be added first and demonstrated failing against current `origin/main`; reviewers must repeat the named mutation and confirm the test fails for the intended reason.

### M1 — Incremental planner, manifest, and equities

Files: new `pipelines/massive_incremental.py` (or narrowly split helpers), `notebooks/refresh_bronze_equities.py`, an additive manifest migration/DDL, `tests/bronze/test_massive_incremental.py`, `tests/bronze/test_refresh_bronze_equities.py`, and data-contract documentation.

Required failing tests: Delta-derived per-symbol/file watermarks; XNYS holiday/early-close selection; overlap window; dry-run makes no writes; bounds stop oversized plans; identical rerun appends zero; partial retry appends only missing keys; secret redaction; manifest cannot become `SUCCESS` before verification.

Named mutations: ignore watermark and plan a full re-pull; use local checkpoint state; replace append/insert-only logic with overwrite or matched update; remove overlap; mark a failed file successful; log the REST query string; unbound `max_days_per_run`.

Acceptance:

```bash
pytest -q tests/bronze/test_massive_incremental.py tests/bronze/test_refresh_bronze_equities.py
python notebooks/refresh_bronze_equities.py --dry-run --start-date 2026-09-03 --end-date 2026-09-10 --max-days-per-run 5
databricks bundle validate
```

### M2 — Options snapshots/daily aggregates and corporate actions

Files: `notebooks/refresh_bronze_options.py`, `notebooks/refresh_bronze_corporate_actions.py`, `etl/corporate_actions.py` only if adapter changes are needed, additive correction lineage, `tests/bronze/test_refresh_bronze_options.py`, and `tests/bronze/test_corporate_actions.py`.

Required failing tests: OPRA natural-key dedup; correction conflict/version behavior; persisted snapshot timestamp makes retry idempotent; provider participant time wins; no historical date loop calls the current-snapshot endpoint; pagination; 429/backoff and 401/403 fail closed; split correction causes affected-history output; dividends remain disabled without schema approval.

Named mutations: key snapshots by calendar date; generate a new retry timestamp; stamp current quotes with requested historical dates; skip pagination; overwrite Bronze; use a future split before its availability; print `apiKey`.

Acceptance:

```bash
pytest -q tests/bronze/test_refresh_bronze_options.py tests/bronze/test_corporate_actions.py tests/test_extract_options.py
python notebooks/refresh_bronze_options.py --dry-run --start-date 2026-09-03 --end-date 2026-09-10
python notebooks/refresh_bronze_corporate_actions.py --mode dry-run --source massive
```

### M3 — Incremental Silver/Gold and PIT safety

Files: `pipelines/run_silver_gold.py`, affected SQL under `silver/` and `gold/`, `gold/pit_guard.py`, `tests/silver/test_silver_sql_semantics.py`, `tests/silver/test_ohlcv_day_adjusted.py`, `tests/gold/test_pit_leakage.py`, and new incremental-window tests.

Required failing tests: affected partitions only; late minute recomputes the rest of its session; 20/252-session lookbacks are present; a new split rebuilds prior adjusted history; cross-sectional universe partitions delete stale members; matrix rebuild removes stale prediction timestamps; every retained availability timestamp is at or before prediction time; the M3 original-before-prediction / correction-after-prediction regression fixture (an original observation before `prediction_ts` and a correction after `prediction_ts` must select the original for that prediction and the correction for later predictions).

Named mutations: remove lookback rows; MERGE only the newly arrived minute; restrict split rebuild to ex-date forward; omit stale-row delete; allow `information_available_ts > prediction_ts`; forward-fill IV; overwrite a full target.

Acceptance:

```bash
pytest -q tests/silver tests/gold tests/ml/test_pit_no_lookahead.py
python pipelines/run_silver_gold.py --start-date 2026-09-03 --end-date 2026-09-10 --check
```

### M4 — Chained paused job and operational guardrails

Files: `resources/jobs.yml`, `databricks.yml` only if variables are required, orchestration tests (extend `tests/test_bundle_sync.py` or add a focused job test), and runbook/CICD documentation.

Required failing tests: exact dependency chain; `America/New_York` schedule; `PAUSED` in every deployment target; `max_concurrent_runs: 1`; failure notifications configured; paid-call caps passed to ingest; scoring task absent/disabled or explicitly read-only; legacy jobs cannot race the chain.

Named mutations: unpause schedule by default; change timezone to UTC; remove a task dependency; permit concurrent runs; omit alerts; enable signal publishing; leave the old independent schedules active.

Acceptance:

```bash
pytest -q tests/test_bundle_sync.py tests/test_jobs_massive_incremental.py
databricks bundle validate
databricks bundle plan
```

### M5 — Real freshness and cache expiry

Files: `api/schemas.py`, `api/deps.py` or a focused freshness service, `api/routes/market.py`, `api/routes/signals.py`, `db/delta_adapter.py`, `frontend/src/api/types.ts`, `frontend/src/components/FreshnessBadge.tsx`, relevant API/frontend tests, and health diagnostics.

Required failing tests: nonempty old data is stale; freshness uses source/availability maximum rather than request time; badge displays exact last-updated time; cache expires and refresh watermark changes invalidate it; TTL bounds; empty/unavailable behavior remains stable.

Named mutations: hard-code `fresh` for nonempty reads; use `datetime.now()` as data freshness; cache forever; reuse role-cache TTL/state; omit watermark from invalidation; display manifest completion as if it were market event time.

Acceptance:

```bash
pytest -q tests/api/test_market.py tests/api/test_health_diagnostics.py tests/api/test_resilience.py
npm --prefix frontend test -- --run
npm --prefix frontend run build
```

## Owner approvals and rollout

The following are explicit stop gates, not defaults:

1. **First backfill:** approve the reviewed dry-run plan for 2026-09-03 through the execution date, including the known unrecoverable options-snapshot gap and bounded chunk sequence.
2. **Schedule activation:** approve changing the deployed chained job from `PAUSED` to active after one successful dry-run, one successful bounded write, PIT/DQ checks, and freshness verification. Source control should remain paused-by-default unless the owner explicitly changes that policy.
3. **Paid API volume:** approve any recurring REST snapshot volume, entitlement upgrade, index/economic-metric lane, dividends lane, options-minute lane, increased symbol universe, or override of request/day/byte caps. S3 flat-file retrieval should also surface estimated bytes before a large backfill.
4. **Schema evolution for corrections/dividends:** approve additive correction lineage and any dividend contract before those records are written.
5. **Signal publication:** approve a separate write mode before scoring output can enter `gold_trading_signals`; this plan’s optional scorer is read-only.

Roll out M1–M5 in order, keep all schedules paused, execute and inspect the complete backfill dry run, obtain approvals, write bounded chunks, validate Bronze counts/duplicates/manifests and Silver/Gold PIT invariants, verify UI timestamps, and only then activate the recurring job.
