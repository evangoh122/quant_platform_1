-- =============================================================================
-- 005_agent_runtime.sql
-- Agent runtime additions:
--
--   * research_notes.idempotency_key — nullable unique key for idempotent
--     save_research_note replays. NULL means "no key" (existing rows remain
--     valid). A non-null key enforces exactly-one note per key.
--
--   * agent_actions gains trace_id, step, decision, and reason columns for
--     agent audit records. Existing rows remain valid (new columns nullable).
--
-- Forward-only and re-runnable. This file extends 004; it does not rewrite it.
-- =============================================================================

-- ── research_notes: idempotency key ──────────────────────────────────────────
ALTER TABLE research_notes
    ADD COLUMN IF NOT EXISTS idempotency_key TEXT;

-- Nullable unique: NULLs are distinct (existing rows stay valid), non-null
-- values enforce exactly-once semantics.
CREATE UNIQUE INDEX IF NOT EXISTS idx_research_notes_idempotency_key
    ON research_notes (idempotency_key)
    WHERE idempotency_key IS NOT NULL;

-- ── agent_actions: agent audit fields ────────────────────────────────────────
ALTER TABLE agent_actions
    ADD COLUMN IF NOT EXISTS trace_id TEXT;

ALTER TABLE agent_actions
    ADD COLUMN IF NOT EXISTS step INTEGER;

ALTER TABLE agent_actions
    ADD COLUMN IF NOT EXISTS decision TEXT;

ALTER TABLE agent_actions
    ADD COLUMN IF NOT EXISTS reason TEXT;

CREATE INDEX IF NOT EXISTS idx_agent_actions_trace
    ON agent_actions (trace_id)
    WHERE trace_id IS NOT NULL;