# Deployment — Lakebase agent tools

## Approver authority (out-of-band grant only)

Approval of a paper order is recorded by `agent/tools_write.record_approval`,
which accepts only an `ApprovalContext` whose `approver_id`:

1. is an actual `ApprovalContext` instance;
2. resolves to an existing `users` row whose `role` is `'trader'`;
3. is the **owner** of the order (a single-user paper-trading tool: "explicit
   human approval" means a user confirming their own order).

`role = 'trader'` is **never** granted automatically:

- `agent/tools_write._ensure_user` provisions previously-unseen identities with
  the non-approving `'viewer'` role.
- No module under `agent/` may insert or update `users.role`.

The only path to `'trader'` is the out-of-band admin CLI:

```bash
python scripts/grant_approver.py <user_id>
```

Run it as a human operator for each principal you have explicitly vetted. The
remediation migration `db/migrations/003_revoke_auto_provisioned_approvers.sql`
downgrades every pre-existing `'trader'` row to `'viewer'`; re-grant vetted
principals after applying it.

## Applying migrations

```bash
python -m db.migrate
```

Forward-only, ordered by filename, re-runnable. Applied versions are recorded in
`schema_migrations`.
