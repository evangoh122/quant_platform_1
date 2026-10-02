-- =============================================================================
-- 003_revoke_auto_provisioned_approvers.sql
-- Round-5 remediation: revoke approval authority from auto-provisioned users.
--
-- Before this migration, `agent/tools_write._ensure_user` upserted any
-- previously-unseen `user_id` with `role = 'trader'`, and `_APPROVER_ROLES` was
-- `('trader',)`. Any identity ever passed to a write tool therefore became a
-- valid approver. `_ensure_user` now provisions new identities as `'viewer'`,
-- and `'trader'` is granted only out-of-band via `scripts/grant_approver.py`.
--
-- This migration downgrades every pre-existing `'trader'` row to `'viewer'` so
-- that no auto-provisioned identity retains approval authority. Operators that
-- have already vetted a principal must re-grant it with the admin CLI.
--
-- Forward-only and re-runnable: after the first run there are no `'trader'`
-- rows to update, so re-applying is a no-op.
-- =============================================================================

UPDATE users SET role = 'viewer' WHERE role = 'trader';
