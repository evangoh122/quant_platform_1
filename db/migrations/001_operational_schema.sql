-- =============================================================================
-- 001_operational_schema.sql
-- Lakebase (Postgres 16.15) operational data model.
--
-- Forward-only, re-runnable. Every statement is idempotent (CREATE TABLE IF
-- NOT EXISTS / ALTER ... IF NOT EXISTS where supported / plain ALTER no-ops) so
-- re-applying this file is safe. The runner (db/migrate.py) additionally tracks
-- applied migrations in schema_migrations to keep ordering deterministic.
--
-- CDC note: wal_level=logical is already enabled on this Lakebase instance.
-- CREATE PUBLICATION is administratively disabled here, so the publication/slot
-- must be created by the Databricks Lakebase CDC layer (next slice). We set
-- REPLICA IDENTITY FULL on the seven behavioural tables so every UPDATE/DELETE
-- emits a complete before/after row image. See CDC.md.
-- =============================================================================

-- ── users ────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    user_id      TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    role         TEXT NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── watchlists ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS watchlists (
    watchlist_id     TEXT PRIMARY KEY,
    user_id          TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    symbol           TEXT NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_action_id TEXT,
    -- idempotent per (user, symbol): a user cannot watch the same symbol twice.
    CONSTRAINT watchlists_user_symbol_uq UNIQUE (user_id, symbol)
);

-- ── signals ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS signals (
    signal_id           TEXT PRIMARY KEY,
    symbol              TEXT NOT NULL,
    prediction_ts       TIMESTAMPTZ NOT NULL,
    model_version       TEXT NOT NULL,
    direction           TEXT NOT NULL
                        CONSTRAINT signals_direction_chk
                        CHECK (direction IN ('LONG', 'SHORT', 'FLAT')),
    probability         DOUBLE PRECISION NOT NULL
                        CONSTRAINT signals_probability_chk
                        CHECK (probability >= 0 AND probability <= 1),
    feature_snapshot_id TEXT,
    status              TEXT NOT NULL DEFAULT 'ACTIVE'
);

CREATE INDEX IF NOT EXISTS idx_signals_symbol_prediction
    ON signals (symbol, prediction_ts DESC);

-- ── orders ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS orders (
    order_id        TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL REFERENCES users(user_id) ON DELETE RESTRICT,
    signal_id       TEXT REFERENCES signals(signal_id) ON DELETE SET NULL,
    symbol          TEXT NOT NULL,
    broker          TEXT NOT NULL,
    broker_order_id TEXT,
    side            TEXT NOT NULL
                    CONSTRAINT orders_side_chk CHECK (side IN ('BUY', 'SELL')),
    quantity        NUMERIC(18, 8) NOT NULL,
    notional        NUMERIC(18, 2) NOT NULL,
    order_type      TEXT NOT NULL
                    CONSTRAINT orders_type_chk CHECK (order_type IN ('MARKET', 'LIMIT')),
    limit_price     NUMERIC(18, 8),
    status          TEXT NOT NULL DEFAULT 'PENDING_APPROVAL'
                    CONSTRAINT orders_status_chk
                    CHECK (status IN ('PENDING_APPROVAL', 'APPROVED', 'SUBMITTED',
                                      'FILLED', 'PARTIALLY_FILLED', 'CANCELLED',
                                      'REJECTED', 'FAILED')),
    approved_by     TEXT,
    approved_at     TIMESTAMPTZ,
    submitted_at    TIMESTAMPTZ,
    idempotency_key TEXT NOT NULL UNIQUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- open-order reads (get_open_orders) and duplicate/conflicting-order detection.
CREATE INDEX IF NOT EXISTS idx_orders_user_status
    ON orders (user_id, status);
CREATE INDEX IF NOT EXISTS idx_orders_user_symbol_side_status
    ON orders (user_id, symbol, side, status);
CREATE INDEX IF NOT EXISTS idx_orders_signal
    ON orders (signal_id) WHERE signal_id IS NOT NULL;

-- ── executions ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS executions (
    execution_id         TEXT PRIMARY KEY,
    order_id             TEXT NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
    broker_execution_id  TEXT,
    fill_qty             NUMERIC(18, 8) NOT NULL,
    fill_price           NUMERIC(18, 8) NOT NULL,
    commission           NUMERIC(18, 6) NOT NULL DEFAULT 0,
    executed_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_executions_order ON executions (order_id);

-- ── positions ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS positions (
    account_id      TEXT NOT NULL,
    symbol          TEXT NOT NULL,
    quantity        NUMERIC(18, 8) NOT NULL,
    avg_cost        NUMERIC(18, 8) NOT NULL,
    market_price    NUMERIC(18, 8),
    realized_pnl    NUMERIC(18, 2) NOT NULL DEFAULT 0,
    unrealized_pnl  NUMERIC(18, 2) NOT NULL DEFAULT 0,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (account_id, symbol)
);

-- ── agent_actions (audit trail for every tool call) ─────────────────────────
CREATE TABLE IF NOT EXISTS agent_actions (
    action_id      TEXT PRIMARY KEY,
    user_id        TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    tool_name      TEXT NOT NULL,
    action_type    TEXT NOT NULL,
    input_summary  TEXT NOT NULL,
    output_summary TEXT NOT NULL,
    status         TEXT NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_agent_actions_user_ts
    ON agent_actions (user_id, created_at DESC);

-- ── research_notes ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS research_notes (
    note_id     TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    symbol      TEXT NOT NULL,
    signal_id   TEXT REFERENCES signals(signal_id) ON DELETE SET NULL,
    note_text   TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_research_notes_user_symbol
    ON research_notes (user_id, symbol);
CREATE INDEX IF NOT EXISTS idx_research_notes_signal
    ON research_notes (signal_id) WHERE signal_id IS NOT NULL;

-- ── change-capture source-side configuration ────────────────────────────────
-- Full row images for the seven behavioural tables so the CDC consumer can
-- reconstruct complete before/after state on UPDATE and DELETE.
ALTER TABLE watchlists     REPLICA IDENTITY FULL;
ALTER TABLE signals        REPLICA IDENTITY FULL;
ALTER TABLE orders         REPLICA IDENTITY FULL;
ALTER TABLE executions     REPLICA IDENTITY FULL;
ALTER TABLE positions      REPLICA IDENTITY FULL;
ALTER TABLE agent_actions  REPLICA IDENTITY FULL;
ALTER TABLE research_notes REPLICA IDENTITY FULL;
