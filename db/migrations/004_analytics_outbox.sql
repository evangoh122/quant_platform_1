-- =============================================================================
-- 004_analytics_outbox.sql
-- Transactional outbox for CDC analytics pipeline.
--
-- Forward-only, re-runnable. Every statement is idempotent (CREATE TABLE IF
-- NOT EXISTS / CREATE OR REPLACE / DROP TRIGGER IF EXISTS … CREATE TRIGGER).
--
-- NOTE: PostgreSQL has no CREATE TRIGGER IF NOT EXISTS; re-applying uses
-- DROP TRIGGER IF EXISTS before each CREATE TRIGGER.
--
-- The outbox captures row-level changes on eight behavioural tables via
-- SECURITY DEFINER triggers. Each table has its own trigger function that
-- references ONLY that table's columns (no shared function that would fail
-- on tables lacking a column like watchlist_id). Payloads are built from
-- explicit field lists; to_jsonb(NEW) / SELECT * are never used. Sensitive
-- fields (note_text, input_summary, output_summary, display_name, credentials)
-- are excluded.
--
-- Trigger-generated events use dedupe_key = NULL so successive UPDATEs on the
-- same row each produce their own outbox row (Postgres UNIQUE allows multiple
-- NULLs). Snapshot seeds use 'snapshot:<table>:<pk>' for ON CONFLICT dedup.
-- =============================================================================

-- ── analytics_outbox ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS analytics_outbox (
    event_id       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_table   TEXT NOT NULL
                   CONSTRAINT analytics_outbox_source_chk
                   CHECK (source_table IN ('watchlists','signals','orders',
                          'executions','positions','agent_actions',
                          'research_notes','approvals')),
    source_pk      TEXT NOT NULL,
    operation      TEXT NOT NULL
                   CONSTRAINT analytics_outbox_op_chk
                   CHECK (operation IN ('insert','update','delete','snapshot')),
    before_payload JSONB,
    after_payload  JSONB,
    occurred_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    dedupe_key     TEXT,
    delivered_at   TIMESTAMPTZ,
    attempt_count  INTEGER NOT NULL DEFAULT 0,
    last_error     TEXT,
    CONSTRAINT analytics_outbox_dedupe_uq UNIQUE (dedupe_key)
);

CREATE INDEX IF NOT EXISTS idx_outbox_pending
    ON analytics_outbox (delivered_at, event_id)
    WHERE delivered_at IS NULL;

-- Lock down access: only the SECURITY DEFINER trigger function writes.
REVOKE ALL ON analytics_outbox FROM PUBLIC;

-- ── helper: safe search_path for all trigger functions ────────────────────────
-- (Each function SETs this individually via SECURITY DEFINER + SET search_path.)

-- =============================================================================
-- PER-TABLE TRIGGER FUNCTIONS
-- Each function references ONLY columns belonging to its source table.
-- Trigger-generated events use dedupe_key = NULL (UNIQUE allows multiple NULLs)
-- so successive UPDATEs on the same row each produce their own outbox row.
-- =============================================================================

-- ── watchlists ───────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION capture_outbox_watchlists()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO analytics_outbox
            (source_table, source_pk, operation, after_payload, occurred_at, dedupe_key)
        VALUES
            (TG_TABLE_NAME, NEW.watchlist_id, 'insert',
             jsonb_build_object(
                 'watchlist_id',     NEW.watchlist_id,
                 'user_id',          NEW.user_id,
                 'symbol',           NEW.symbol,
                 'created_at',       NEW.created_at,
                 'source_action_id', NEW.source_action_id
             ), now(), NULL);
    ELSIF TG_OP = 'UPDATE' THEN
        INSERT INTO analytics_outbox
            (source_table, source_pk, operation, before_payload, after_payload, occurred_at, dedupe_key)
        VALUES
            (TG_TABLE_NAME, NEW.watchlist_id, 'update',
             jsonb_build_object(
                 'watchlist_id',     OLD.watchlist_id,
                 'user_id',          OLD.user_id,
                 'symbol',           OLD.symbol,
                 'created_at',       OLD.created_at,
                 'source_action_id', OLD.source_action_id
             ),
             jsonb_build_object(
                 'watchlist_id',     NEW.watchlist_id,
                 'user_id',          NEW.user_id,
                 'symbol',           NEW.symbol,
                 'created_at',       NEW.created_at,
                 'source_action_id', NEW.source_action_id
             ), now(), NULL);
    ELSIF TG_OP = 'DELETE' THEN
        INSERT INTO analytics_outbox
            (source_table, source_pk, operation, before_payload, occurred_at, dedupe_key)
        VALUES
            (TG_TABLE_NAME, OLD.watchlist_id, 'delete',
             jsonb_build_object(
                 'watchlist_id',     OLD.watchlist_id,
                 'user_id',          OLD.user_id,
                 'symbol',           OLD.symbol,
                 'created_at',       OLD.created_at,
                 'source_action_id', OLD.source_action_id
             ), now(), NULL);
    END IF;
    RETURN COALESCE(NEW, OLD);
END;
$$;

REVOKE ALL ON FUNCTION capture_outbox_watchlists() FROM PUBLIC;

-- ── signals ──────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION capture_outbox_signals()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO analytics_outbox
            (source_table, source_pk, operation, after_payload, occurred_at, dedupe_key)
        VALUES
            (TG_TABLE_NAME, NEW.signal_id, 'insert',
             jsonb_build_object(
                 'signal_id',           NEW.signal_id,
                 'symbol',              NEW.symbol,
                 'prediction_ts',       NEW.prediction_ts,
                 'model_version',       NEW.model_version,
                 'direction',           NEW.direction,
                 'probability',         NEW.probability,
                 'feature_snapshot_id', NEW.feature_snapshot_id,
                 'status',              NEW.status
             ), now(), NULL);
    ELSIF TG_OP = 'UPDATE' THEN
        INSERT INTO analytics_outbox
            (source_table, source_pk, operation, before_payload, after_payload, occurred_at, dedupe_key)
        VALUES
            (TG_TABLE_NAME, NEW.signal_id, 'update',
             jsonb_build_object(
                 'signal_id',           OLD.signal_id,
                 'symbol',              OLD.symbol,
                 'prediction_ts',       OLD.prediction_ts,
                 'model_version',       OLD.model_version,
                 'direction',           OLD.direction,
                 'probability',         OLD.probability,
                 'feature_snapshot_id', OLD.feature_snapshot_id,
                 'status',              OLD.status
             ),
             jsonb_build_object(
                 'signal_id',           NEW.signal_id,
                 'symbol',              NEW.symbol,
                 'prediction_ts',       NEW.prediction_ts,
                 'model_version',       NEW.model_version,
                 'direction',           NEW.direction,
                 'probability',         NEW.probability,
                 'feature_snapshot_id', NEW.feature_snapshot_id,
                 'status',              NEW.status
             ), now(), NULL);
    ELSIF TG_OP = 'DELETE' THEN
        INSERT INTO analytics_outbox
            (source_table, source_pk, operation, before_payload, occurred_at, dedupe_key)
        VALUES
            (TG_TABLE_NAME, OLD.signal_id, 'delete',
             jsonb_build_object(
                 'signal_id',           OLD.signal_id,
                 'symbol',              OLD.symbol,
                 'prediction_ts',       OLD.prediction_ts,
                 'model_version',       OLD.model_version,
                 'direction',           OLD.direction,
                 'probability',         OLD.probability,
                 'feature_snapshot_id', OLD.feature_snapshot_id,
                 'status',              OLD.status
             ), now(), NULL);
    END IF;
    RETURN COALESCE(NEW, OLD);
END;
$$;

REVOKE ALL ON FUNCTION capture_outbox_signals() FROM PUBLIC;

-- ── orders ───────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION capture_outbox_orders()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO analytics_outbox
            (source_table, source_pk, operation, after_payload, occurred_at, dedupe_key)
        VALUES
            (TG_TABLE_NAME, NEW.order_id, 'insert',
             jsonb_build_object(
                 'order_id',        NEW.order_id,
                 'user_id',         NEW.user_id,
                 'signal_id',       COALESCE(NEW.signal_id, ''),
                 'symbol',          NEW.symbol,
                 'broker',          NEW.broker,
                 'broker_order_id', COALESCE(NEW.broker_order_id, ''),
                 'side',            NEW.side,
                 'quantity',        NEW.quantity::TEXT,
                 'notional',        NEW.notional::TEXT,
                 'order_type',      NEW.order_type,
                 'limit_price',     COALESCE(NEW.limit_price::TEXT, ''),
                 'status',          NEW.status,
                 'approved_by',     COALESCE(NEW.approved_by, ''),
                 'approved_at',     COALESCE(NEW.approved_at::TEXT, ''),
                 'submitted_at',    COALESCE(NEW.submitted_at::TEXT, ''),
                 'idempotency_key', NEW.idempotency_key,
                 'created_at',      NEW.created_at
             ), now(), NULL);
    ELSIF TG_OP = 'UPDATE' THEN
        INSERT INTO analytics_outbox
            (source_table, source_pk, operation, before_payload, after_payload, occurred_at, dedupe_key)
        VALUES
            (TG_TABLE_NAME, NEW.order_id, 'update',
             jsonb_build_object(
                 'order_id',        OLD.order_id,
                 'user_id',         OLD.user_id,
                 'signal_id',       COALESCE(OLD.signal_id, ''),
                 'symbol',          OLD.symbol,
                 'broker',          OLD.broker,
                 'broker_order_id', COALESCE(OLD.broker_order_id, ''),
                 'side',            OLD.side,
                 'quantity',        OLD.quantity::TEXT,
                 'notional',        OLD.notional::TEXT,
                 'order_type',      OLD.order_type,
                 'limit_price',     COALESCE(OLD.limit_price::TEXT, ''),
                 'status',          OLD.status,
                 'approved_by',     COALESCE(OLD.approved_by, ''),
                 'approved_at',     COALESCE(OLD.approved_at::TEXT, ''),
                 'submitted_at',    COALESCE(OLD.submitted_at::TEXT, ''),
                 'idempotency_key', OLD.idempotency_key,
                 'created_at',      OLD.created_at
             ),
             jsonb_build_object(
                 'order_id',        NEW.order_id,
                 'user_id',         NEW.user_id,
                 'signal_id',       COALESCE(NEW.signal_id, ''),
                 'symbol',          NEW.symbol,
                 'broker',          NEW.broker,
                 'broker_order_id', COALESCE(NEW.broker_order_id, ''),
                 'side',            NEW.side,
                 'quantity',        NEW.quantity::TEXT,
                 'notional',        NEW.notional::TEXT,
                 'order_type',      NEW.order_type,
                 'limit_price',     COALESCE(NEW.limit_price::TEXT, ''),
                 'status',          NEW.status,
                 'approved_by',     COALESCE(NEW.approved_by, ''),
                 'approved_at',     COALESCE(NEW.approved_at::TEXT, ''),
                 'submitted_at',    COALESCE(NEW.submitted_at::TEXT, ''),
                 'idempotency_key', NEW.idempotency_key,
                 'created_at',      NEW.created_at
             ), now(), NULL);
    ELSIF TG_OP = 'DELETE' THEN
        INSERT INTO analytics_outbox
            (source_table, source_pk, operation, before_payload, occurred_at, dedupe_key)
        VALUES
            (TG_TABLE_NAME, OLD.order_id, 'delete',
             jsonb_build_object(
                 'order_id',        OLD.order_id,
                 'user_id',         OLD.user_id,
                 'signal_id',       COALESCE(OLD.signal_id, ''),
                 'symbol',          OLD.symbol,
                 'broker',          OLD.broker,
                 'broker_order_id', COALESCE(OLD.broker_order_id, ''),
                 'side',            OLD.side,
                 'quantity',        OLD.quantity::TEXT,
                 'notional',        OLD.notional::TEXT,
                 'order_type',      OLD.order_type,
                 'limit_price',     COALESCE(OLD.limit_price::TEXT, ''),
                 'status',          OLD.status,
                 'approved_by',     COALESCE(OLD.approved_by, ''),
                 'approved_at',     COALESCE(OLD.approved_at::TEXT, ''),
                 'submitted_at',    COALESCE(OLD.submitted_at::TEXT, ''),
                 'idempotency_key', OLD.idempotency_key,
                 'created_at',      OLD.created_at
             ), now(), NULL);
    END IF;
    RETURN COALESCE(NEW, OLD);
END;
$$;

REVOKE ALL ON FUNCTION capture_outbox_orders() FROM PUBLIC;

-- ── executions ───────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION capture_outbox_executions()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO analytics_outbox
            (source_table, source_pk, operation, after_payload, occurred_at, dedupe_key)
        VALUES
            (TG_TABLE_NAME, NEW.execution_id, 'insert',
             jsonb_build_object(
                 'execution_id',        NEW.execution_id,
                 'order_id',            NEW.order_id,
                 'broker_execution_id', COALESCE(NEW.broker_execution_id, ''),
                 'fill_qty',            NEW.fill_qty::TEXT,
                 'fill_price',          NEW.fill_price::TEXT,
                 'commission',          NEW.commission::TEXT,
                 'executed_at',         NEW.executed_at
             ), now(), NULL);
    ELSIF TG_OP = 'UPDATE' THEN
        INSERT INTO analytics_outbox
            (source_table, source_pk, operation, before_payload, after_payload, occurred_at, dedupe_key)
        VALUES
            (TG_TABLE_NAME, NEW.execution_id, 'update',
             jsonb_build_object(
                 'execution_id',        OLD.execution_id,
                 'order_id',            OLD.order_id,
                 'broker_execution_id', COALESCE(OLD.broker_execution_id, ''),
                 'fill_qty',            OLD.fill_qty::TEXT,
                 'fill_price',          OLD.fill_price::TEXT,
                 'commission',          OLD.commission::TEXT,
                 'executed_at',         OLD.executed_at
             ),
             jsonb_build_object(
                 'execution_id',        NEW.execution_id,
                 'order_id',            NEW.order_id,
                 'broker_execution_id', COALESCE(NEW.broker_execution_id, ''),
                 'fill_qty',            NEW.fill_qty::TEXT,
                 'fill_price',          NEW.fill_price::TEXT,
                 'commission',          NEW.commission::TEXT,
                 'executed_at',         NEW.executed_at
             ), now(), NULL);
    ELSIF TG_OP = 'DELETE' THEN
        INSERT INTO analytics_outbox
            (source_table, source_pk, operation, before_payload, occurred_at, dedupe_key)
        VALUES
            (TG_TABLE_NAME, OLD.execution_id, 'delete',
             jsonb_build_object(
                 'execution_id',        OLD.execution_id,
                 'order_id',            OLD.order_id,
                 'broker_execution_id', COALESCE(OLD.broker_execution_id, ''),
                 'fill_qty',            OLD.fill_qty::TEXT,
                 'fill_price',          OLD.fill_price::TEXT,
                 'commission',          OLD.commission::TEXT,
                 'executed_at',         OLD.executed_at
             ), now(), NULL);
    END IF;
    RETURN COALESCE(NEW, OLD);
END;
$$;

REVOKE ALL ON FUNCTION capture_outbox_executions() FROM PUBLIC;

-- ── positions ────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION capture_outbox_positions()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO analytics_outbox
            (source_table, source_pk, operation, after_payload, occurred_at, dedupe_key)
        VALUES
            (TG_TABLE_NAME, NEW.account_id || '|' || NEW.symbol, 'insert',
             jsonb_build_object(
                 'account_id',     NEW.account_id,
                 'symbol',         NEW.symbol,
                 'quantity',       NEW.quantity::TEXT,
                 'avg_cost',       NEW.avg_cost::TEXT,
                 'market_price',   COALESCE(NEW.market_price::TEXT, ''),
                 'realized_pnl',   NEW.realized_pnl::TEXT,
                 'unrealized_pnl', NEW.unrealized_pnl::TEXT,
                 'updated_at',     NEW.updated_at
             ), now(), NULL);
    ELSIF TG_OP = 'UPDATE' THEN
        INSERT INTO analytics_outbox
            (source_table, source_pk, operation, before_payload, after_payload, occurred_at, dedupe_key)
        VALUES
            (TG_TABLE_NAME, NEW.account_id || '|' || NEW.symbol, 'update',
             jsonb_build_object(
                 'account_id',     OLD.account_id,
                 'symbol',         OLD.symbol,
                 'quantity',       OLD.quantity::TEXT,
                 'avg_cost',       OLD.avg_cost::TEXT,
                 'market_price',   COALESCE(OLD.market_price::TEXT, ''),
                 'realized_pnl',   OLD.realized_pnl::TEXT,
                 'unrealized_pnl', OLD.unrealized_pnl::TEXT,
                 'updated_at',     OLD.updated_at
             ),
             jsonb_build_object(
                 'account_id',     NEW.account_id,
                 'symbol',         NEW.symbol,
                 'quantity',       NEW.quantity::TEXT,
                 'avg_cost',       NEW.avg_cost::TEXT,
                 'market_price',   COALESCE(NEW.market_price::TEXT, ''),
                 'realized_pnl',   NEW.realized_pnl::TEXT,
                 'unrealized_pnl', NEW.unrealized_pnl::TEXT,
                 'updated_at',     NEW.updated_at
             ), now(), NULL);
    ELSIF TG_OP = 'DELETE' THEN
        INSERT INTO analytics_outbox
            (source_table, source_pk, operation, before_payload, occurred_at, dedupe_key)
        VALUES
            (TG_TABLE_NAME, OLD.account_id || '|' || OLD.symbol, 'delete',
             jsonb_build_object(
                 'account_id',     OLD.account_id,
                 'symbol',         OLD.symbol,
                 'quantity',       OLD.quantity::TEXT,
                 'avg_cost',       OLD.avg_cost::TEXT,
                 'market_price',   COALESCE(OLD.market_price::TEXT, ''),
                 'realized_pnl',   OLD.realized_pnl::TEXT,
                 'unrealized_pnl', OLD.unrealized_pnl::TEXT,
                 'updated_at',     OLD.updated_at
             ), now(), NULL);
    END IF;
    RETURN COALESCE(NEW, OLD);
END;
$$;

REVOKE ALL ON FUNCTION capture_outbox_positions() FROM PUBLIC;

-- ── agent_actions ────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION capture_outbox_agent_actions()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO analytics_outbox
            (source_table, source_pk, operation, after_payload, occurred_at, dedupe_key)
        VALUES
            (TG_TABLE_NAME, NEW.action_id, 'insert',
             jsonb_build_object(
                 'action_id',  NEW.action_id,
                 'user_id',    NEW.user_id,
                 'tool_name',  NEW.tool_name,
                 'action_type',NEW.action_type,
                 'status',     NEW.status,
                 'created_at', NEW.created_at
             ), now(), NULL);
    ELSIF TG_OP = 'UPDATE' THEN
        INSERT INTO analytics_outbox
            (source_table, source_pk, operation, before_payload, after_payload, occurred_at, dedupe_key)
        VALUES
            (TG_TABLE_NAME, NEW.action_id, 'update',
             jsonb_build_object(
                 'action_id',  OLD.action_id,
                 'user_id',    OLD.user_id,
                 'tool_name',  OLD.tool_name,
                 'action_type',OLD.action_type,
                 'status',     OLD.status,
                 'created_at', OLD.created_at
             ),
             jsonb_build_object(
                 'action_id',  NEW.action_id,
                 'user_id',    NEW.user_id,
                 'tool_name',  NEW.tool_name,
                 'action_type',NEW.action_type,
                 'status',     NEW.status,
                 'created_at', NEW.created_at
             ), now(), NULL);
    ELSIF TG_OP = 'DELETE' THEN
        INSERT INTO analytics_outbox
            (source_table, source_pk, operation, before_payload, occurred_at, dedupe_key)
        VALUES
            (TG_TABLE_NAME, OLD.action_id, 'delete',
             jsonb_build_object(
                 'action_id',  OLD.action_id,
                 'user_id',    OLD.user_id,
                 'tool_name',  OLD.tool_name,
                 'action_type',OLD.action_type,
                 'status',     OLD.status,
                 'created_at', OLD.created_at
             ), now(), NULL);
    END IF;
    RETURN COALESCE(NEW, OLD);
END;
$$;

REVOKE ALL ON FUNCTION capture_outbox_agent_actions() FROM PUBLIC;

-- ── research_notes ───────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION capture_outbox_research_notes()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO analytics_outbox
            (source_table, source_pk, operation, after_payload, occurred_at, dedupe_key)
        VALUES
            (TG_TABLE_NAME, NEW.note_id, 'insert',
             jsonb_build_object(
                 'note_id',    NEW.note_id,
                 'user_id',    NEW.user_id,
                 'symbol',     NEW.symbol,
                 'signal_id',  COALESCE(NEW.signal_id, ''),
                 'created_at', NEW.created_at,
                 'updated_at', NEW.updated_at
             ), now(), NULL);
    ELSIF TG_OP = 'UPDATE' THEN
        INSERT INTO analytics_outbox
            (source_table, source_pk, operation, before_payload, after_payload, occurred_at, dedupe_key)
        VALUES
            (TG_TABLE_NAME, NEW.note_id, 'update',
             jsonb_build_object(
                 'note_id',    OLD.note_id,
                 'user_id',    OLD.user_id,
                 'symbol',     OLD.symbol,
                 'signal_id',  COALESCE(OLD.signal_id, ''),
                 'created_at', OLD.created_at,
                 'updated_at', OLD.updated_at
             ),
             jsonb_build_object(
                 'note_id',    NEW.note_id,
                 'user_id',    NEW.user_id,
                 'symbol',     NEW.symbol,
                 'signal_id',  COALESCE(NEW.signal_id, ''),
                 'created_at', NEW.created_at,
                 'updated_at', NEW.updated_at
             ), now(), NULL);
    ELSIF TG_OP = 'DELETE' THEN
        INSERT INTO analytics_outbox
            (source_table, source_pk, operation, before_payload, occurred_at, dedupe_key)
        VALUES
            (TG_TABLE_NAME, OLD.note_id, 'delete',
             jsonb_build_object(
                 'note_id',    OLD.note_id,
                 'user_id',    OLD.user_id,
                 'symbol',     OLD.symbol,
                 'signal_id',  COALESCE(OLD.signal_id, ''),
                 'created_at', OLD.created_at,
                 'updated_at', OLD.updated_at
             ), now(), NULL);
    END IF;
    RETURN COALESCE(NEW, OLD);
END;
$$;

REVOKE ALL ON FUNCTION capture_outbox_research_notes() FROM PUBLIC;

-- ── approvals ────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION capture_outbox_approvals()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO analytics_outbox
            (source_table, source_pk, operation, after_payload, occurred_at, dedupe_key)
        VALUES
            (TG_TABLE_NAME, NEW.approval_id, 'insert',
             jsonb_build_object(
                 'approval_id', NEW.approval_id,
                 'order_id',    NEW.order_id,
                 'approver_id', NEW.approver_id,
                 'created_at',  NEW.created_at
             ), now(), NULL);
    ELSIF TG_OP = 'UPDATE' THEN
        INSERT INTO analytics_outbox
            (source_table, source_pk, operation, before_payload, after_payload, occurred_at, dedupe_key)
        VALUES
            (TG_TABLE_NAME, NEW.approval_id, 'update',
             jsonb_build_object(
                 'approval_id', OLD.approval_id,
                 'order_id',    OLD.order_id,
                 'approver_id', OLD.approver_id,
                 'created_at',  OLD.created_at
             ),
             jsonb_build_object(
                 'approval_id', NEW.approval_id,
                 'order_id',    NEW.order_id,
                 'approver_id', NEW.approver_id,
                 'created_at',  NEW.created_at
             ), now(), NULL);
    ELSIF TG_OP = 'DELETE' THEN
        INSERT INTO analytics_outbox
            (source_table, source_pk, operation, before_payload, occurred_at, dedupe_key)
        VALUES
            (TG_TABLE_NAME, OLD.approval_id, 'delete',
             jsonb_build_object(
                 'approval_id', OLD.approval_id,
                 'order_id',    OLD.order_id,
                 'approver_id', OLD.approver_id,
                 'created_at',  OLD.created_at
             ), now(), NULL);
    END IF;
    RETURN COALESCE(NEW, OLD);
END;
$$;

REVOKE ALL ON FUNCTION capture_outbox_approvals() FROM PUBLIC;

-- ── trigger attachments (one per source table) ───────────────────────────────
-- DROP IF EXISTS + CREATE ensures idempotent re-apply.

DROP TRIGGER IF EXISTS trg_outbox_watchlists ON watchlists;
CREATE TRIGGER trg_outbox_watchlists
    AFTER INSERT OR UPDATE OR DELETE ON watchlists
    FOR EACH ROW EXECUTE FUNCTION capture_outbox_watchlists();

DROP TRIGGER IF EXISTS trg_outbox_signals ON signals;
CREATE TRIGGER trg_outbox_signals
    AFTER INSERT OR UPDATE OR DELETE ON signals
    FOR EACH ROW EXECUTE FUNCTION capture_outbox_signals();

DROP TRIGGER IF EXISTS trg_outbox_orders ON orders;
CREATE TRIGGER trg_outbox_orders
    AFTER INSERT OR UPDATE OR DELETE ON orders
    FOR EACH ROW EXECUTE FUNCTION capture_outbox_orders();

DROP TRIGGER IF EXISTS trg_outbox_executions ON executions;
CREATE TRIGGER trg_outbox_executions
    AFTER INSERT OR UPDATE OR DELETE ON executions
    FOR EACH ROW EXECUTE FUNCTION capture_outbox_executions();

DROP TRIGGER IF EXISTS trg_outbox_positions ON positions;
CREATE TRIGGER trg_outbox_positions
    AFTER INSERT OR UPDATE OR DELETE ON positions
    FOR EACH ROW EXECUTE FUNCTION capture_outbox_positions();

DROP TRIGGER IF EXISTS trg_outbox_agent_actions ON agent_actions;
CREATE TRIGGER trg_outbox_agent_actions
    AFTER INSERT OR UPDATE OR DELETE ON agent_actions
    FOR EACH ROW EXECUTE FUNCTION capture_outbox_agent_actions();

DROP TRIGGER IF EXISTS trg_outbox_research_notes ON research_notes;
CREATE TRIGGER trg_outbox_research_notes
    AFTER INSERT OR UPDATE OR DELETE ON research_notes
    FOR EACH ROW EXECUTE FUNCTION capture_outbox_research_notes();

DROP TRIGGER IF EXISTS trg_outbox_approvals ON approvals;
CREATE TRIGGER trg_outbox_approvals
    AFTER INSERT OR UPDATE OR DELETE ON approvals
    FOR EACH ROW EXECUTE FUNCTION capture_outbox_approvals();

-- ── idempotent snapshot seed for existing source rows ────────────────────────
-- Uses dedupe_key for ON CONFLICT so re-applying is safe.

INSERT INTO analytics_outbox (source_table, source_pk, operation, after_payload, dedupe_key)
SELECT 'watchlists', watchlist_id, 'snapshot',
       jsonb_build_object(
           'watchlist_id',     watchlist_id,
           'user_id',          user_id,
           'symbol',           symbol,
           'created_at',       created_at,
           'source_action_id', source_action_id
       ),
       'snapshot:watchlists:' || watchlist_id
FROM watchlists
ON CONFLICT (dedupe_key) DO NOTHING;

INSERT INTO analytics_outbox (source_table, source_pk, operation, after_payload, dedupe_key)
SELECT 'signals', signal_id, 'snapshot',
       jsonb_build_object(
           'signal_id',           signal_id,
           'symbol',              symbol,
           'prediction_ts',       prediction_ts,
           'model_version',       model_version,
           'direction',           direction,
           'probability',         probability::TEXT,
           'feature_snapshot_id', feature_snapshot_id,
           'status',              status
       ),
       'snapshot:signals:' || signal_id
FROM signals
ON CONFLICT (dedupe_key) DO NOTHING;

INSERT INTO analytics_outbox (source_table, source_pk, operation, after_payload, dedupe_key)
SELECT 'orders', order_id, 'snapshot',
       jsonb_build_object(
           'order_id',        order_id,
           'user_id',         user_id,
           'signal_id',       COALESCE(signal_id, ''),
           'symbol',          symbol,
           'broker',          broker,
           'broker_order_id', COALESCE(broker_order_id, ''),
           'side',            side,
           'quantity',        quantity::TEXT,
           'notional',        notional::TEXT,
           'order_type',      order_type,
           'limit_price',     COALESCE(limit_price::TEXT, ''),
           'status',          status,
           'approved_by',     COALESCE(approved_by, ''),
           'approved_at',     COALESCE(approved_at::TEXT, ''),
           'submitted_at',    COALESCE(submitted_at::TEXT, ''),
           'idempotency_key', idempotency_key,
           'created_at',      created_at
       ),
       'snapshot:orders:' || order_id
FROM orders
ON CONFLICT (dedupe_key) DO NOTHING;

INSERT INTO analytics_outbox (source_table, source_pk, operation, after_payload, dedupe_key)
SELECT 'executions', execution_id, 'snapshot',
       jsonb_build_object(
           'execution_id',        execution_id,
           'order_id',            order_id,
           'broker_execution_id', COALESCE(broker_execution_id, ''),
           'fill_qty',            fill_qty::TEXT,
           'fill_price',          fill_price::TEXT,
           'commission',          commission::TEXT,
           'executed_at',         executed_at
       ),
       'snapshot:executions:' || execution_id
FROM executions
ON CONFLICT (dedupe_key) DO NOTHING;

INSERT INTO analytics_outbox (source_table, source_pk, operation, after_payload, dedupe_key)
SELECT 'positions', account_id || '|' || symbol, 'snapshot',
       jsonb_build_object(
           'account_id',     account_id,
           'symbol',         symbol,
           'quantity',       quantity::TEXT,
           'avg_cost',       avg_cost::TEXT,
           'market_price',   COALESCE(market_price::TEXT, ''),
           'realized_pnl',   realized_pnl::TEXT,
           'unrealized_pnl', unrealized_pnl::TEXT,
           'updated_at',     updated_at
       ),
       'snapshot:positions:' || account_id || '|' || symbol
FROM positions
ON CONFLICT (dedupe_key) DO NOTHING;

INSERT INTO analytics_outbox (source_table, source_pk, operation, after_payload, dedupe_key)
SELECT 'agent_actions', action_id, 'snapshot',
       jsonb_build_object(
           'action_id',  action_id,
           'user_id',    user_id,
           'tool_name',  tool_name,
           'action_type',action_type,
           'status',     status,
           'created_at', created_at
       ),
       'snapshot:agent_actions:' || action_id
FROM agent_actions
ON CONFLICT (dedupe_key) DO NOTHING;

INSERT INTO analytics_outbox (source_table, source_pk, operation, after_payload, dedupe_key)
SELECT 'research_notes', note_id, 'snapshot',
       jsonb_build_object(
           'note_id',    note_id,
           'user_id',    user_id,
           'symbol',     symbol,
           'signal_id',  COALESCE(signal_id, ''),
           'created_at', created_at,
           'updated_at', updated_at
       ),
       'snapshot:research_notes:' || note_id
FROM research_notes
ON CONFLICT (dedupe_key) DO NOTHING;

INSERT INTO analytics_outbox (source_table, source_pk, operation, after_payload, dedupe_key)
SELECT 'approvals', approval_id, 'snapshot',
       jsonb_build_object(
           'approval_id', approval_id,
           'order_id',    order_id,
           'approver_id', approver_id,
           'created_at',  created_at
       ),
       'snapshot:approvals:' || approval_id
FROM approvals
ON CONFLICT (dedupe_key) DO NOTHING;