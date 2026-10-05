# PLAN request (Codex, planner): keep Massive market data current (incremental ingest + incremental silver/gold + schedule)

Owner (2026-10-06): "do you open CDC for new data from Massive so that it is reflected?" Today it is not: the Massive extractors
(etl/extract_polygon.py, etl/extract_stocks.py, etl/extract_options.py; see also pipelines/refresh_bronze_* if present and tests/bronze/test_refresh_bronze_*)
run manually; resources/jobs.yml has no Massive job; `silver_gold_refresh` (02:00) and `lakebase_analytics_refresh` are PAUSED; live data ends
silver_ohlcv 2026-09-02, gold_model_features 2026-09-03. The existing "CDC" (db/migrations/004_analytics_outbox.sql → pipelines/lakebase_analytics.py)
covers Lakebase operational tables only.
Read the repo on origin/main (git show origin/main:<path> if needed): etl/, pipelines/, silver/, gold/, resources/jobs.yml, databricks.yml, config/,
docs/ (data contracts, CICD, runbooks), memory of rules in AGENTS.md. Massive auth: S3 flat files + REST apiKey (the S3 secret key works as the
REST apiKey for splits/dividends); never print secrets.
Write docs/data/PLAN-massive-incremental.md with:
1. Current-state map: every Massive dataset we ingest (stocks minute/day, options day/quotes, indices, corporate actions…), its bronze table, how
   it is extracted, its natural key, and the downstream silver/gold tables.
2. Incremental ingest design: per-dataset watermark (max ingested event date per symbol, from Delta, not local state), late/corrected data
   handling (re-pull a trailing window, MERGE on natural key + keep ingest_ts, append-only bronze semantics preserved), market calendar/holidays,
   rate limits/cost guard (max days per run, dry-run that prints the planned pulls), idempotent re-runs, manifest table.
3. Incremental silver/gold: which transforms can MERGE only new partitions vs which must recompute windows (rolling features need a lookback),
   point-in-time rules (feature availability timestamps), and how gold_model_features/gold_trading_signals inputs stay PIT-safe.
4. Orchestration: one chained Databricks job (Massive ingest → silver/gold → analytics → optional baseline signals scoring in read-only mode),
   schedule after US close in America/New_York, alerts on failure, PAUSED until the owner approves; backfill command for 2026-09-03 → today.
5. App freshness: how the UI shows real last-updated times (existing FreshnessBadge/freshness API) and agent cache TTL.
6. Build slices M1..Mn (each one MiMo build + DeepSeek check + Codex review): files, tests that must fail on the current code, named mutations
   (e.g. watermark ignored → full re-pull; overwrite instead of MERGE; future-dated rows leak into features; schedule unpaused by default),
   acceptance commands. Explicitly list what needs owner approval: first backfill, unpausing schedules, any paid-API volume.
Do not write application code. Print a short summary.
