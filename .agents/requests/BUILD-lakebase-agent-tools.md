# BUILD-REQUEST: lakebase-agent-tools

**Round:** 1
**Branch:** `slice/lakebase-agent-tools` (create it; never commit to `main`)
**Rubric requirements covered:** Lakebase operational data model; Agent write
actions; Agent retrieval tools; deterministic guardrails. (Rubric sections D, E,
7.2, 7.3, 7.4, and the "Lakebase data model" / "Agent write action" rows of the
section-13 acceptance table.)

---

## Context you need

The repo is a Databricks capstone: a mid-frequency quant trading research and
paper-execution platform. Read `README.md` and `MERGE_PLAN.md` for background.
The full proposal/rubric is not in the repo; the requirements you must satisfy
are restated below in full, so build to *this* document.

### Live infrastructure (already provisioned and verified working)

- **Unity Catalog schema** holding 27 Delta tables: `bootcamp_students.evangoh_capstone`.
  Relevant Gold tables that already exist: `gold_trading_signals`,
  `gold_ohlcv_features`, `gold_options_features`, `gold_cot_features`,
  `gold_model_features`, and `silver_sec_sections`.
- **Lakebase (Postgres 16.15)** instance `evangoh-capstone-lakebase`,
  state AVAILABLE, database `databricks_postgres`, schema `public` is empty.
  - host: `ep-steep-truth-d1ex36nr.database.us-west-2.cloud.databricks.com`
  - port: `5432`, sslmode: `require`, user: `evangohsg@gmail.com`
  - **Password is a short-lived OAuth token, NOT a static secret.** Mint it with:
    ```
    databricks api post /api/2.0/database/credentials \
      --json '{"request_id":"<uuid4>","instance_names":["evangoh-capstone-lakebase"]}'
    ```
    and read `.token` from the JSON. It expires in ~1 hour, so the adapter must
    mint on demand and refresh on expiry — never cache it to disk, never commit it.
  - `psycopg` 3.3.6 is installed and a connection has been verified.

---

## Scope — what to build

### 1. Lakebase schema + migrations

Create forward-only, re-runnable migrations under `db/migrations/` (e.g.
`001_operational_schema.sql`) and a small runner. Eight tables, exactly these
names, with the fields the rubric specifies:

| Table | Required fields |
| :-- | :-- |
| `users` | `user_id` PK, `display_name`, `role`, `created_at` |
| `watchlists` | `watchlist_id` PK, `user_id` FK→users, `symbol`, `created_at`, `source_action_id` |
| `signals` | `signal_id` PK, `symbol`, `prediction_ts`, `model_version`, `direction`, `probability`, `feature_snapshot_id`, `status` |
| `orders` | `order_id` PK, `user_id` FK, `signal_id` FK nullable, `broker`, `broker_order_id`, `side`, `quantity`, `notional`, `order_type`, `limit_price`, `status`, `approved_by`, `approved_at`, `submitted_at`, `idempotency_key` UNIQUE |
| `executions` | `execution_id` PK, `order_id` FK→orders, `broker_execution_id`, `fill_qty`, `fill_price`, `commission`, `executed_at` |
| `positions` | composite PK (`account_id`,`symbol`), `quantity`, `avg_cost`, `market_price`, `realized_pnl`, `unrealized_pnl`, `updated_at` |
| `agent_actions` | `action_id` PK, `user_id` FK, `tool_name`, `action_type`, `input_summary`, `output_summary`, `status`, `created_at` |
| `research_notes` | `note_id` PK, `user_id` FK, `symbol`, `signal_id` FK nullable, `note_text`, `created_at`, `updated_at` |

Requirements:
- Explicit PKs; FKs with deliberate `ON DELETE` behaviour; `NOT NULL` wherever
  the field is logically required; `CHECK` constraints on enums
  (`orders.status`, `orders.side`, `signals.direction`).
- `orders.status` must at minimum support: `PENDING_APPROVAL`, `APPROVED`,
  `SUBMITTED`, `FILLED`, `PARTIALLY_FILLED`, `CANCELLED`, `REJECTED`, `FAILED`.
- Indexes to support the actual read patterns (see §3 latency budgets).
- **Enable Postgres logical replication / change capture** on the seven tables
  whose changes are behavioural: `watchlists`, `signals`, `orders`, `executions`,
  `positions`, `agent_actions`, `research_notes`. The next slice consumes this,
  so set `REPLICA IDENTITY FULL` where needed and document what a CDC consumer
  must subscribe to. Do not build the consumer in this slice.

### 2. Lakebase adapter

`db/lakebase.py` — connection + transaction layer:
- Mints the OAuth token on demand, refreshes before expiry.
- Explicit connection pooling (`psycopg_pool`), configured, not defaulted.
- Context-managed transactions; no autocommit for multi-statement writes.
- **Parameterized queries only.** A single f-string-interpolated SQL value is a
  blocking defect.

### 3. Replace the fake agent write tools

`agent/tools_write.py` currently contains six stubs that return a fresh UUID and
touch no database at all. Replace every one with a real transactional write:

| Tool | Real behaviour required |
| :-- | :-- |
| `add_to_watchlist` | INSERT into `watchlists`, idempotent per (user, symbol) |
| `save_research_note` | INSERT into `research_notes` |
| `create_order_intent` | INSERT `orders` with status `PENDING_APPROVAL`; **no broker call** |
| `approve_and_place_paper_order` | re-run risk checks, require explicit human approval, then call the execution bridge; record `broker_order_id` + status |
| `cancel_paper_order` | request cancel via bridge, update state |
| `record_agent_action` | INSERT into `agent_actions` — called for *every* tool call |

Also fix `agent/tools_retrieval.py`: `search_sec_filings`, `get_options_features`
and `get_cot_positioning` f-string-interpolate `symbol` straight into SQL filter
strings. That is an injection hole and the rubric explicitly forbids giving the
agent unrestricted SQL. Parameterize or allow-list. Wire
`get_portfolio_positions`, `get_open_orders` and `get_watchlist` to Lakebase —
they currently `return []`.

**Latency budgets** (state them in code and prove them): agent read tools
p95 < 500 ms; write tools p95 < 800 ms. Every query over an operational table
must use an index — prove it with `EXPLAIN`.

### 4. Deterministic risk service

`agent/guardrails.py` is 44 lines and insufficient. Build a deterministic risk
service that the LLM cannot bypass. Every order must pass, with a structured
machine-readable reason on failure and **no broker call** when any check fails:

- symbol on allow-list
- paper-account-mode assertion
- positive quantity/notional
- max notional per order
- max position concentration
- sufficient buying power
- duplicate / conflicting open order detection
- market-session status
- stale-signal threshold (reject if the signal backing the order is too old)
- idempotency key present and unique

Explicit human approval is required for every new paper order. The LLM must not
be able to call the broker directly, and no credential or session material may
reach the LLM or a browser.

### 5. Tests

Tests under `tests/lakebase/`. They must actually run and actually assert:
- Migration applies cleanly to an empty database and is re-runnable.
- Every write tool round-trips: write, then read back and assert the row.
- Every risk check rejects when it should — one test per check, asserting the
  structured reason and asserting **no broker call** occurred (mock the bridge
  and assert not-called).
- Injection regression: a symbol like `'; DROP TABLE users; --` must not execute.
- Idempotency: calling `create_order_intent` twice with one key yields one row.

Mark tests needing live Lakebase with `@pytest.mark.lakebase` so they can be
deselected. The suite must be runnable without network for the pure-logic tests.

---

## Non-goals for this slice — do not build

- CDF **consumer** / `analytics_*` Delta tables (next slice; just make the
  source side capturable).
- React frontend, FastAPI routes, Databricks App packaging.
- ML models, MLflow, the A/B/C/D ablation.
- Structured Streaming pipelines.
- Real IBKR connectivity. `execution/bridge.py` stays an interface you call;
  mock it in tests. Do not place real broker orders.

## Acceptance criteria

1. Migration runs against the live Lakebase and all 8 tables exist with
   constraints and indexes.
2. `rg -n "f\"" agent/ db/ | grep -i select` returns nothing meaningful —
   no f-string SQL.
3. No stub remains in `agent/tools_write.py`; every function performs real I/O.
4. `pytest tests/ -q` passes. Paste the command and the real output in your
   verdict. A claim of passing tests without pasted output is itself a blocking
   finding.
5. No secret, token, or credential is committed. `.env.example` may document
   variable *names* only.
6. Branch `slice/lakebase-agent-tools` exists with your commits. `main` untouched.

## When finished

Write your verdict to your lane file per `.agents/PROTOCOL.md`.
