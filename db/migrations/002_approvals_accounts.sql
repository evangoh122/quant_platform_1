-- =============================================================================
-- 002_approvals_accounts.sql
-- Round-2 additions to support a non-bypassable execution boundary:
--
--   * approvals — a durable, trusted human-approval record. Placement reads the
--     record back; it never accepts a caller-supplied boolean asserting that "a
--     human approved this".
--   * accounts   — the trusted source for buying power. Placement no longer
--     fabricates a $100k constant.
--   * orders.status gains SUBMITTING so the broker call can be moved outside
--     the open transaction: intent is committed first, the broker is called,
--     then the result is recorded — keeping the retry path idempotent.
--
-- Forward-only and re-runnable. This file extends 001; it does not rewrite it.
-- =============================================================================

-- ── approvals (trusted human-approval record) ────────────────────────────────
CREATE TABLE IF NOT EXISTS approvals (
    approval_id  TEXT PRIMARY KEY,
    order_id     TEXT NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
    approver_id  TEXT NOT NULL REFERENCES users(user_id) ON DELETE RESTRICT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- One approval per order; a re-approval overwrites in place (idempotent).
    CONSTRAINT approvals_order_uq UNIQUE (order_id)
);

CREATE INDEX IF NOT EXISTS idx_approvals_order ON approvals (order_id);

-- ── accounts (trusted account source for buying power) ───────────────────────
CREATE TABLE IF NOT EXISTS accounts (
    account_id   TEXT PRIMARY KEY,
    buying_power NUMERIC(18, 2) NOT NULL,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT accounts_buying_power_nonneg CHECK (buying_power >= 0)
);

-- ── extend orders.status with SUBMITTING (in-flight submission intent) ───────
ALTER TABLE orders DROP CONSTRAINT IF EXISTS orders_status_chk;
ALTER TABLE orders ADD CONSTRAINT orders_status_chk
    CHECK (status IN ('PENDING_APPROVAL', 'APPROVED', 'SUBMITTING', 'SUBMITTED',
                      'FILLED', 'PARTIALLY_FILLED', 'CANCELLED', 'REJECTED',
                      'FAILED'));

-- ── CDC source-side config for the new behavioural table ─────────────────────
-- approvals changes over time and is behavioural; accounts is config-like and
-- excluded from the behavioural CDC set, mirroring how `users` is excluded.
ALTER TABLE approvals REPLICA IDENTITY FULL;
