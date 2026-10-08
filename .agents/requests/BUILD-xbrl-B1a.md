# BUILD-xbrl-B1a — SEC Company Facts client + append-only bronze (Plan B, slice B1 part a)

You are MiMo. Branch `feat/xbrl-fundamentals` (worktree qp1-xbrl; stay on it, no new branches). LF endings, never touch
`.agents/dispatch.sh`, no Databricks calls, no network in tests. COMMIT per item. Binding spec:
`docs/ui_enhancement/PLAN-B-workbench-visuals-xbrl.md` sections 2.1, 2.2, 2.5 (items 1, 2, 10 partially). Owner request 2026-10-05:
bring XBRL fundamentals into the platform. This branch is based on PR #28 (`slice/rag-coverage`): REUSE its pieces, do not duplicate them —
`pipelines/sec_rag_ingest.py` `RateLimiter` (~682), `load_cik_overrides`/`build_cik_map` (~528/554), the EDGAR User-Agent resolver
(secret scope/key, same as the `sec_rag_ingest` job in resources/jobs.yml), config/sec_cik_overrides.yaml, and the canonical SEC universe.
If a helper needs to move to a shared module to be reused, move it and keep the old import working.

1. `pipelines/ingest_sec_companyfacts.py` (Spark entry point, args `--catalog --schema --tickers --run-id --dry-run` + the User-Agent
   secret args): fetch `https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json` per CIK on the driver with bounded concurrency,
   ≤10 req/s (target 8 with jitter), retries with backoff on 429/403/5xx honouring Retry-After, capped attempts, timeouts. Missing or
   placeholder User-Agent fails before any request. Never log response bodies or the contact email. Multi-CIK override tickers (XOM) fetch
   each CIK.
2. Flatten each payload into rows (one row per Company Facts unit entry) with Spark transformations; append to
   `bronze_sec_xbrl_facts` (columns exactly as Plan B 2.2) — Delta append only, never overwrite; create the table if absent.
   Preserve raw JSON for entries that fail typed parsing (value_decimal null). Skip writing when the same (cik, payload_hash) was already
   written in this run. Write a per-CIK manifest row (Plan B 2.1 fields) to `sec_companyfacts_ingest_log`.
3. `resources/jobs.yml`: a `sec_companyfacts_ingest` job (task before any silver/gold SEC XBRL task; params catalog/schema + secret scope/key
   like sec_rag_ingest). Update the bundle-sync / schema-contract tests if they enumerate jobs or tables.
4. Tests `tests/bronze/test_sec_companyfacts.py` (no network: fake HTTP session; Spark-free unit tests for flattening via plain dict→rows
   functions; Spark parts marked like the repo's other Spark tests): Plan B 2.5 item 1 (placeholder UA rejected, UA header sent,
   Retry-After honoured, rate cap — use a fake clock), item 2 (two changed payloads both appended; malformed fact preserved), same-payload
   skip within a run, manifest fields, XOM two-CIK fetch, no email in logs.
   Mutations to run and paste FAILED output for: accept a placeholder UA; remove the rate limiter; overwrite instead of append; drop
   malformed facts.
Acceptance: `python3 -m pytest tests/bronze/test_sec_companyfacts.py -q` and the offline suite
`python3 -m pytest -q -m "not spark and not lakebase and not databricks"` green. Verdict `.agents/mimo/VERDICT-xbrl-B1a.md`.
