-- =============================================================================
-- 004_analytics_outbox.sql
-- Transactional outbox for CDC analytics pipeline.
--
-- Forward-only, re-runnable. Every statement is idempotent (CREATE TABLE IF
-- NOT EXISTS / CREATE OR REPLACE / CREATE TRIGGER IF NOT EXISTS).
--
-- The outbox captures row-level changes on eight behavioural tables via
-- SECURITY DEFINER triggers. Payloads are built from explicit field lists;
-- to_jsonb(NEW) / SELECT * are never used. Sensitive fields (note_text,
-- input_summary, output_summary, display_name, credentials) are excluded.
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

-- ── trigger function (SECURITY DEFINER, safe search_path) ────────────────────
CREATE OR REPLACE FUNCTION capture_outbox_event()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    _op     TEXT;
    _before JSONB;
    _after  JSONB;
    _pk     TEXT;
BEGIN
    IF TG_OP = 'INSERT' THEN
        _op := 'insert';
        _pk := NEW.watchlist_id;
        _after := jsonb_build_object(
            'watchlist_id',     NEW.watchlist_id,
            'user_id',          NEW.user_id,
            'symbol',           NEW.symbol,
            'created_at',       NEW.created_at,
            'source_action_id', NEW.source_action_id
        );
    ELSIF TG_OP = 'UPDATE' THEN
        _op := 'update';
        _pk := NEW.watchlist_id;
        _before := jsonb_build_object(
            'watchlist_id',     OLD.watchlist_id,
            'user_id',          OLD.user_id,
            'symbol',           OLD.symbol,
            'created_at',       OLD.created_at,
            'source_action_id', OLD.source_action_id
        );
        _after := jsonb_build_object(
            'watchlist_id',     NEW.watchlist_id,
            'user_id',          NEW.user_id,
            'symbol',           NEW.symbol,
            'created_at',       NEW.created_at,
            'source_action_id', NEW.source_action_id
        );
    ELSIF TG_OP = 'DELETE' THEN
        _op := 'delete';
        _pk := OLD.watchlist_id;
        _before := jsonb_build_object(
            'watchlist_id',     OLD.watchlist_id,
            'user_id',          OLD.user_id,
            'symbol',           OLD.symbol,
            'created_at',       OLD.created_at,
            'source_action_id', OLD.source_action_id
        );
    END IF;

    IF TG_TABLE_NAME = 'signals' THEN
        IF TG_OP = 'INSERT' THEN
            _pk := NEW.signal_id;
            _after := jsonb_build_object(
                'signal_id',           NEW.signal_id,
                'symbol',              NEW.symbol,
                'prediction_ts',       NEW.prediction_ts,
                'model_version',       NEW.model_version,
                'direction',           NEW.direction,
                'probability',         NEW.probability,
                'feature_snapshot_id', NEW.feature_snapshot_id,
                'status',              NEW.status
            );
        ELSIF TG_OP = 'UPDATE' THEN
            _pk := NEW.signal_id;
            _before := jsonb_build_object(
                'signal_id',           OLD.signal_id,
                'symbol',              OLD.symbol,
                'prediction_ts',       OLD.prediction_ts,
                'model_version',       OLD.model_version,
                'direction',           OLD.direction,
                'probability',         OLD.probability,
                'feature_snapshot_id', OLD.feature_snapshot_id,
                'status',              OLD.status
            );
            _after := jsonb_build_object(
                'signal_id',           NEW.signal_id,
                'symbol',              NEW.symbol,
                'prediction_ts',       NEW.prediction_ts,
                'model_version',       NEW.model_version,
                'direction',           NEW.direction,
                'probability',         NEW.probability,
                'feature_snapshot_id', NEW.feature_snapshot_id,
                'status',              NEW.status
            );
        ELSIF TG_OP = 'DELETE' THEN
            _pk := OLD.signal_id;
            _before := jsonb_build_object(
                'signal_id',           OLD.signal_id,
                'symbol',              OLD.symbol,
                'prediction_ts',       OLD.prediction_ts,
                'model_version',       OLD.model_version,
                'direction',           OLD.direction,
                'probability',         OLD.probability,
                'feature_snapshot_id', OLD.feature_snapshot_id,
                'status',              OLD.status
            );
        END IF;

    ELSIF TG_TABLE_NAME = 'orders' THEN
        IF TG_OP = 'INSERT' THEN
            _pk := NEW.order_id;
            _after := jsonb_build_object(
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
            );
        ELSIF TG_OP = 'UPDATE' THEN
            _pk := NEW.order_id;
            _before := jsonb_build_object(
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
            );
            _after := jsonb_build_object(
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
            );
        ELSIF TG_OP = 'DELETE' THEN
            _pk := OLD.order_id;
            _before := jsonb_build_object(
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
            );
        END IF;

    ELSIF TG_TABLE_NAME = 'executions' THEN
        IF TG_OP = 'INSERT' THEN
            _pk := NEW.execution_id;
            _after := jsonb_build_object(
                'execution_id',        NEW.execution_id,
                'order_id',            NEW.order_id,
                'broker_execution_id', COALESCE(NEW.broker_execution_id, ''),
                'fill_qty',            NEW.fill_qty::TEXT,
                'fill_price',          NEW.fill_price::TEXT,
                'commission',          NEW.commission::TEXT,
                'executed_at',         NEW.executed_at
            );
        ELSIF TG_OP = 'UPDATE' THEN
            _pk := NEW.execution_id;
            _before := jsonb_build_object(
                'execution_id',        OLD.execution_id,
                'order_id',            OLD.order_id,
                'broker_execution_id', COALESCE(OLD.broker_execution_id, ''),
                'fill_qty',            OLD.fill_qty::TEXT,
                'fill_price',          OLD.fill_price::TEXT,
                'commission',          OLD.commission::TEXT,
                'executed_at',         OLD.executed_at
            );
            _after := jsonb_build_object(
                'execution_id',        NEW.execution_id,
                'order_id',            NEW.order_id,
                'broker_execution_id', COALESCE(NEW.broker_execution_id, ''),
                'fill_qty',            NEW.fill_qty::TEXT,
                'fill_price',          NEW.fill_price::TEXT,
                'commission',          NEW.commission::TEXT,
                'executed_at',         NEW.executed_at
            );
        ELSIF TG_OP = 'DELETE' THEN
            _pk := OLD.execution_id;
            _before := jsonb_build_object(
                'execution_id',        OLD.execution_id,
                'order_id',            OLD.order_id,
                'broker_execution_id', COALESCE(OLD.broker_execution_id, ''),
                'fill_qty',            OLD.fill_qty::TEXT,
                'fill_price',          OLD.fill_price::TEXT,
                'commission',          OLD.commission::TEXT,
                'executed_at',         OLD.executed_at
            );
        END IF;

    ELSIF TG_TABLE_NAME = 'positions' THEN
        IF TG_OP = 'INSERT' THEN
            _pk := NEW.account_id || '|' || NEW.symbol;
            _after := jsonb_build_object(
                'account_id',     NEW.account_id,
                'symbol',         NEW.symbol,
                'quantity',       NEW.quantity::TEXT,
                'avg_cost',       NEW.avg_cost::TEXT,
                'market_price',   COALESCE(NEW.market_price::TEXT, ''),
                'realized_pnl',   NEW.realized_pnl::TEXT,
                'unrealized_pnl', NEW.unrealized_pnl::TEXT,
                'updated_at',     NEW.updated_at
            );
        ELSIF TG_OP = 'UPDATE' THEN
            _pk := NEW.account_id || '|' || NEW.symbol;
            _before := jsonb_build_object(
                'account_id',     OLD.account_id,
                'symbol',         OLD.symbol,
                'quantity',       OLD.quantity::TEXT,
                'avg_cost',       OLD.avg_cost::TEXT,
                'market_price',   COALESCE(OLD.market_price::TEXT, ''),
                'realized_pnl',   OLD.realized_pnl::TEXT,
                'unrealized_pnl', OLD.unrealized_pnl::TEXT,
                'updated_at',     OLD.updated_at
            );
            _after := jsonb_build_object(
                'account_id',     NEW.account_id,
                'symbol',         NEW.symbol,
                'quantity',       NEW.quantity::TEXT,
                'avg_cost',       NEW.avg_cost::TEXT,
                'market_price',   COALESCE(NEW.market_price::TEXT, ''),
                'realized_pnl',   NEW.realized_pnl::TEXT,
                'unrealized_pnl', NEW.unrealized_pnl::TEXT,
                'updated_at',     NEW.updated_at
            );
        ELSIF TG_OP = 'DELETE' THEN
            _pk := OLD.account_id || '|' || OLD.symbol;
            _before := jsonb_build_object(
                'account_id',     OLD.account_id,
                'symbol',         OLD.symbol,
                'quantity',       OLD.quantity::TEXT,
                'avg_cost',       OLD.avg_cost::TEXT,
                'market_price',   COALESCE(OLD.market_price::TEXT, ''),
                'realized_pnl',   OLD.realized_pnl::TEXT,
                'unrealized_pnl', OLD.unrealized_pnl::TEXT,
                'updated_at',     OLD.updated_at
            );
        END IF;

    ELSIF TG_TABLE_NAME = 'agent_actions' THEN
        IF TG_OP = 'INSERT' THEN
            _pk := NEW.action_id;
            _after := jsonb_build_object(
                'action_id',  NEW.action_id,
                'user_id',    NEW.user_id,
                'tool_name',  NEW.tool_name,
                'action_type',NEW.action_type,
                'status',     NEW.status,
                'created_at', NEW.created_at
            );
        ELSIF TG_OP = 'UPDATE' THEN
            _pk := NEW.action_id;
            _before := jsonb_build_object(
                'action_id',  OLD.action_id,
                'user_id',    OLD.user_id,
                'tool_name',  OLD.tool_name,
                'action_type',OLD.action_type,
                'status',     OLD.status,
                'created_at', OLD.created_at
            );
            _after := jsonb_build_object(
                'action_id',  NEW.action_id,
                'user_id',    NEW.user_id,
                'tool_name',  NEW.tool_name,
                'action_type',NEW.action_type,
                'status',     NEW.status,
                'created_at', NEW.created_at
            );
        ELSIF TG_OP = 'DELETE' THEN
            _pk := OLD.action_id;
            _before := jsonb_build_object(
                'action_id',  OLD.action_id,
                'user_id',    OLD.user_id,
                'tool_name',  OLD.tool_name,
                'action_type',OLD.action_type,
                'status',     OLD.status,
                'created_at', OLD.created_at
            );
        END IF;

    ELSIF TG_TABLE_NAME = 'research_notes' THEN
        IF TG_OP = 'INSERT' THEN
            _pk := NEW.note_id;
            _after := jsonb_build_object(
                'note_id',    NEW.note_id,
                'user_id',    NEW.user_id,
                'symbol',     NEW.symbol,
                'signal_id',  COALESCE(NEW.signal_id, ''),
                'created_at', NEW.created_at,
                'updated_at', NEW.updated_at
            );
        ELSIF TG_OP = 'UPDATE' THEN
            _pk := NEW.note_id;
            _before := jsonb_build_object(
                'note_id',    OLD.note_id,
                'user_id',    OLD.user_id,
                'symbol',     OLD.symbol,
                'signal_id',  COALESCE(OLD.signal_id, ''),
                'created_at', OLD.created_at,
                'updated_at', OLD.updated_at
            );
            _after := jsonb_build_object(
                'note_id',    NEW.note_id,
                'user_id',    NEW.user_id,
                'symbol',     NEW.symbol,
                'signal_id',  COALESCE(NEW.signal_id, ''),
                'created_at', NEW.created_at,
                'updated_at', NEW.updated_at
            );
        ELSIF TG_OP = 'DELETE' THEN
            _pk := OLD.note_id;
            _before := jsonb_build_object(
                'note_id',    OLD.note_id,
                'user_id',    OLD.user_id,
                'symbol',     OLD.symbol,
                'signal_id',  COALESCE(OLD.signal_id, ''),
                'created_at', OLD.created_at,
                'updated_at', OLD.updated_at
            );
        END IF;

    ELSIF TG_TABLE_NAME = 'approvals' THEN
        IF TG_OP = 'INSERT' THEN
            _pk := NEW.approval_id;
            _after := jsonb_build_object(
                'approval_id', NEW.approval_id,
                'order_id',    NEW.order_id,
                'approver_id', NEW.approver_id,
                'created_at',  NEW.created_at
            );
        ELSIF TG_OP = 'UPDATE' THEN
            _pk := NEW.approval_id;
            _before := jsonb_build_object(
                'approval_id', OLD.approval_id,
                'order_id',    OLD.order_id,
                'approver_id', OLD.approver_id,
                'created_at',  OLD.created_at
            );
            _after := jsonb_build_object(
                'approval_id', NEW.approval_id,
                'order_id',    NEW.order_id,
                'approver_id', NEW.approver_id,
                'created_at',  NEW.created_at
            );
        ELSIF TG_OP = 'DELETE' THEN
            _pk := OLD.approval_id;
            _before := jsonb_build_object(
                'approval_id', OLD.approval_id,
                'order_id',    OLD.order_id,
                'approver_id', OLD.approver_id,
                'created_at',  OLD.created_at
            );
        END IF;
    END IF;

    INSERT INTO analytics_outbox
        (source_table, source_pk, operation, before_payload, after_payload,
         occurred_at, dedupe_key)
    VALUES
        (TG_TABLE_NAME, _pk, _op, _before, _after, now(),
         _op || ':' || TG_TABLE_NAME || ':' || _pk);

    RETURN COALESCE(NEW, OLD);
END;
$$;

-- Restrict trigger function execution to owner only.
REVOKE ALL ON FUNCTION capture_outbox_event() FROM PUBLIC;

-- ── trigger attachments (one per source table) ───────────────────────────────
CREATE TRIGGER trg_outbox_watchlists
    AFTER INSERT OR UPDATE OR DELETE ON watchlists
    FOR EACH ROW EXECUTE FUNCTION capture_outbox_event();

CREATE TRIGGER trg_outbox_signals
    AFTER INSERT OR UPDATE OR DELETE ON signals
    FOR EACH ROW EXECUTE FUNCTION capture_outbox_event();

CREATE TRIGGER trg_outbox_orders
    AFTER INSERT OR UPDATE OR DELETE ON orders
    FOR EACH ROW EXECUTE FUNCTION capture_outbox_event();

CREATE TRIGGER trg_outbox_executions
    AFTER INSERT OR UPDATE OR DELETE ON executions
    FOR EACH ROW EXECUTE FUNCTION capture_outbox_event();

CREATE TRIGGER trg_outbox_positions
    AFTER INSERT OR UPDATE OR DELETE ON positions
    FOR EACH ROW EXECUTE FUNCTION capture_outbox_event();

CREATE TRIGGER trg_outbox_agent_actions
    AFTER INSERT OR UPDATE OR DELETE ON agent_actions
    FOR EACH ROW EXECUTE FUNCTION capture_outbox_event();

CREATE TRIGGER trg_outbox_research_notes
    AFTER INSERT OR UPDATE OR DELETE ON research_notes
    FOR EACH ROW EXECUTE FUNCTION capture_outbox_event();

CREATE TRIGGER trg_outbox_approvals
    AFTER INSERT OR UPDATE OR DELETE ON approvals
    FOR EACH ROW EXECUTE FUNCTION capture_outbox_event();

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