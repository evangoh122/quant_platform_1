# BUILD-REQUEST: lakebase-agent-tools — ROUND 5 (approver authority)

**Branch:** `slice/lakebase-agent-tools` · **Builder:** DeepSeek · **Validators:** Claude, then Codex
**Gate:** BLOCKED by both validators. Read `.agents/claude/VERDICT-lakebase-agent-tools-round4.md`
and `.agents/codex/VERDICT-lakebase-agent-tools-round4.md`.

## The defect (proven on live Lakebase)

`_ensure_user` (`agent/tools_write.py:128`) upserts **any** `user_id` as role
`'trader'`, `_APPROVER_ROLES = ("trader",)`, and every agent-facing write tool
accepts an arbitrary `user_id`. One `add_to_watchlist(..., user_id="x")` mints
`x` as a valid approver. Reproduction: `.agents/claude/probe_approver_bypass.py`
(prints `BYPASS CONFIRMED`; it cleans up after itself).

## Fix — do all of these

1. **Separate existence from authority.** `_ensure_user` must provision new
   users with a **non-approving** role (`'viewer'`). `users.role` is
   unconstrained `TEXT` (`001_operational_schema.sql:18-23`), so no schema
   change is needed for the new value.
2. **Remediate existing rows.** Add forward-only migration
   `003_revoke_auto_provisioned_approvers.sql` that sets `role = 'viewer'` for
   every `role = 'trader'` row. Do not edit migrations 001 or 002.
3. **Out-of-band grant only.** Approver authority is granted only by an admin
   CLI script **outside** `agent/` (e.g. `scripts/grant_approver.py <user_id>`),
   documented in `docs/DEPLOYMENT.md` or the script's docstring. It must not be an
   agent tool, and no agent tool may change roles.
4. **No cross-user approval.** `record_approval` must reject when the approver is
   not the order's owner (structured reason `APPROVER_NOT_OWNER`). This is a
   single-user paper-trading tool: "explicit human approval" means a user
   confirming their own order.
5. **Runtime type check.** `record_approval` must reject anything that is not an
   actual `ApprovalContext` instance (it currently duck-types `.approver_id`).
6. **Honest docs.** Rewrite the claims Codex lists (`tools_write.py:14-17`,
   `105-112`, `285-293`, `326-328`) and the module docstring of
   `tests/lakebase/test_execution_boundary.py:3-8` so they claim only what is
   true: auto-provisioned identities cannot approve; cross-user approval is
   rejected; a same-process Python caller is **not** prevented.
   `002_approvals_accounts.sql:3-7` also says "non-bypassable": if
   `db/migrate.py` does not checksum applied migrations, fix that comment;
   if it does, leave it and add the correction to `db/migrations/CDC.md`.

## Required regression tests (offline-runnable where possible)

- **The exact exploit:** fabricated id → `add_to_watchlist` with it →
  `record_approval` returns `APPROVER_NOT_PERMITTED` → placement rejected →
  `submit_order.assert_not_called()`.
- Granted approver approving **another user's** order → `APPROVER_NOT_OWNER`, no broker call.
- Non-`ApprovalContext` object → rejected.
- Migration 003 downgrades a pre-existing `'trader'` row.
- Re-run `.agents/claude/probe_approver_bypass.py` and paste its output: it must
  no longer print `BYPASS CONFIRMED`.

## Constraints

- Do not touch `api/`, `frontend/`, `ml/`, `silver/`, `gold/`, `conftest.py`,
  `pytest.ini`, `requirements*.txt`. No regressions in earlier rounds.
- `python3 -m pytest tests/lakebase/ -q` must pass in full and offline. Paste both.
- **Commit your work** to this branch. Write `.agents/deepseek/VERDICT-lakebase-agent-tools-round5.md`.
