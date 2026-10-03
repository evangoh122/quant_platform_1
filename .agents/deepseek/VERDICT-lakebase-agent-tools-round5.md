# VERDICT: lakebase-agent-tools ROUND 5 — DeepSeek
**Status:** APPROVED
**Round:** 5

All six requested items done. Committed as `3490d3d`
(`feat(lakebase): round-5 — separate approver authority from identity, revoke
auto-provisioned approvers`). No earlier-round behaviour weakened; no files in
the forbidden set (`api/`, `frontend/`, `ml/`, `silver/`, `gold/`,
`conftest.py`, `pytest.ini`, `requirements*.txt`) touched.

## Per-item resolution

### Item 1 — separate existence from authority: DONE
`_ensure_user` (`agent/tools_write.py:134`) now provisions previously-unseen
identities with role `'viewer'` instead of `'trader'`. `_APPROVER_ROLES` stays
`("trader",)`, so an auto-provisioned identity can no longer approve. No schema
change needed (`users.role` is unconstrained `TEXT`).

### Item 2 — remediate existing rows: DONE
New forward-only migration `db/migrations/003_revoke_auto_provisioned_approvers.sql`
runs `UPDATE users SET role = 'viewer' WHERE role = 'trader'`. Re-runnable
(no-op after first run). Migrations 001 and 002 are otherwise untouched.

### Item 3 — out-of-band grant only: DONE
`scripts/grant_approver.py <user_id>` is the sole path to `'trader'`, lives
outside `agent/`, and is not an agent tool. Documented in its own docstring and
in `docs/DEPLOYMENT.md`. No module under `agent/` inserts or updates
`users.role` (verified by grep).

### Item 4 — no cross-user approval: DONE
`record_approval` now rejects a non-owner approver with
`reason == "APPROVER_NOT_OWNER"` (`agent/tools_write.py:384`) after the role
check, so the fabricated-id exploit still surfaces as `APPROVER_NOT_PERMITTED`.

### Item 5 — runtime type check: DONE
`record_approval` rejects anything that is not an `ApprovalContext` instance
with `reason == "INVALID_APPROVAL_CONTEXT"` *before* any database work
(`agent/tools_write.py:310`). The old duck-typed `.approver_id` access is gone
from the early path.

### Item 6 — honest docs: DONE
Rewrote the claims Codex listed: module docstring, `ApprovalContext` docstring,
`record_approval` docstring, the `_APPROVER_ROLES` and `_ensure_user` comments
(`agent/tools_write.py`), and the `test_execution_boundary.py` module docstring
(now states it proves each covered placement invocation fails closed, and does
**not** prove a boundary a same-process caller cannot bypass). `db/migrate.py`
does not checksum applied migrations, so the `002_approvals_accounts.sql:3-7`
"non-bypassable" comment was corrected in place (as the request specifies);
`CDC.md` left unchanged.

## Required regression tests

- **Exact exploit** — `test_auto_provisioned_id_cannot_approve`
  (`tests/lakebase/test_tools_write.py`): fabricated id → `add_to_watchlist` →
  `record_approval` returns `APPROVER_NOT_PERMITTED` → placement rejected →
  `submit_order.assert_not_called()`.
- **Cross-user approval** — `test_granted_approver_cannot_approve_other_users_order`:
  vetted `'trader'` approves another user's order → `APPROVER_NOT_OWNER`, no
  broker call.
- **Non-`ApprovalContext`** — `test_record_approval_rejects_non_context_object`
  (offline) and the renamed signature-only
  `test_record_approval_signature_requires_context_object`.
- **Migration 003** — `test_migration_003_downgrades_preexisting_trader`
  (`tests/lakebase/test_migrations.py`): 001+002 → seed `'trader'` → 003 →
  role becomes `'viewer'`, in a scratch schema.
- **Probe** — `.agents/claude/probe_approver_bypass.py` no longer prints
  `BYPASS CONFIRMED` (output pasted below).

## Blocking findings

None.

## Non-blocking notes

- Existing live tests that placed orders now seed the owner with `role='trader'`
  first (`_place_order`, `test_duplicate_idempotency_key_replay_no_broker_call`,
  `test_record_approval_roundtrip`), since auto-provisioning no longer grants
  authority. This reflects the new, intended contract.
- `003` is a blanket revoke of `'trader'` → `'viewer'` on the shared DB when
  migrations are applied; operators must re-grant vetted principals via
  `scripts/grant_approver.py` (documented in `docs/DEPLOYMENT.md`).
- A same-process Python caller can still import the private seams; this is
  explicitly documented and unchanged by design.

## Checks run

- `python3 -m py_compile agent/tools_write.py scripts/grant_approver.py tests/lakebase/test_execution_boundary.py tests/lakebase/test_tools_write.py tests/lakebase/test_migrations.py` → pass
- `python3 -m pytest tests/lakebase/ -q -m "not lakebase"` →
  `54 passed, 24 deselected in 14.25s`
- `python3 -m pytest tests/lakebase/ -q` →
  `78 passed in 200.54s`
- `python3 .agents/claude/probe_approver_bypass.py` →

```
order: ord_a3d581bc-6f17-4c9c-8ba7-84cf9d5aea2d PENDING_APPROVAL
1) fabricated, never provisioned -> False UNKNOWN_APPROVER
2) same id after one watchlist call -> False APPROVER_NOT_PERMITTED

VERDICT: no bypass
cleanup done
```

- Commit: `3490d3d feat(lakebase): round-5 — separate approver authority from identity, revoke auto-provisioned approvers`

Both test selections and the probe were run from an unsandboxed WSL shell where
Lakebase credential minting succeeds (same environment as rounds 3–4).
