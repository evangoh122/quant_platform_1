# VERDICT: lakebase-agent-tools ROUND 4 — Claude (first pass; Codex follows)
**Status:** CHANGES_REQUESTED — one blocking finding, narrow fix
**Round:** 4

## What round 4 got right

- `record_approval` now looks up the approver with a read-only
  `SELECT role FROM users WHERE user_id = %s` and returns structured
  `UNKNOWN_APPROVER` / `APPROVER_NOT_PERMITTED` reasons, writing an audit row on
  each rejection. `_ensure_user` is **not** called for the approver — verified.
- The "non-bypassable" overclaims are gone: grep for `non-bypassable`,
  `by construction`, `unforgeable` finds nothing. Docstrings now say plainly the
  check "stops fabricated identities, not a same-process caller".
- Diff is small (3 files) and no round 2–3 fix regressed.
- Offline suite: `53 passed, 21 deselected`.

## Blocking finding — the approver check is bypassable in two calls (proven live)

The round-4 claim "this stops fabricated identities" is **false**, and I
demonstrated it against the live Lakebase instance rather than arguing it
from source.

Mechanism:
- `_ensure_user` (`agent/tools_write.py:128`) upserts **any** `user_id` with
  role **`'trader'`**.
- `_APPROVER_ROLES = ("trader",)` (`agent/tools_write.py:100`).
- Every agent-facing write tool — `add_to_watchlist` (`:157`),
  `save_research_note` (`:183`), `create_order_intent` (`:211`) — accepts an
  arbitrary `user_id` and calls `_ensure_user` on it.

So any identity that has ever been passed to *any* write tool becomes a
permitted approver.

Live probe (`scratchpad/probe_approver_bypass.py`, all rows cleaned up):

```
order: ord_ebcec365-... PENDING_APPROVAL
1) fabricated, never provisioned  -> False UNKNOWN_APPROVER
2) same id after one watchlist call -> True  None
VERDICT: BYPASS CONFIRMED
```

The control case shows the check works for a never-seen id; the second line
shows one `add_to_watchlist(..., user_id=fake)` mints a valid approver.

This is the same pattern as round 3 — a guarantee stated more strongly than the
code delivers — just one level deeper.

## Required fix (small)

Separate *existence* from *approval authority*:

1. Auto-provisioned users must **not** receive an approver role. Provision them
   as a non-approving role (e.g. `'viewer'` or `'agent'`), and make approval
   require a role that only an explicit, out-of-band provisioning step grants.
2. Add `_grant_approver(user_id)` (or a migration/seed) as the only path to an
   approver role, and do not expose it as an agent tool.
3. Regression test reproducing the probe: fabricate id → touch a write tool →
   `record_approval` must still return `APPROVER_NOT_PERMITTED`, and
   `submit_order.assert_not_called()`.
4. Keep the docstring honest: it may claim "auto-provisioned identities cannot
   approve"; it must not claim protection against a same-process caller.

Migration needed: the role column probably has a CHECK or default — add a new
forward-only migration rather than editing 001/002.

## Not blocking, recorded

- Self-approval: the order owner can approve their own order. Correct for a
  single-user paper-trading research tool, where "explicit human approval"
  means the user confirms their own trade. Flag only if a four-eyes rule is
  ever required.

## Gate

**BLOCKED** pending a narrow round 5. Codex validates next per the owner's
process; Codex should confirm or refute this finding independently.
