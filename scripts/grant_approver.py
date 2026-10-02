"""scripts/grant_approver.py — grant approval authority to a user (out-of-band).

Approval authority (``users.role = 'trader'``) is the single role that
``agent/tools_write.record_approval`` accepts. It is **never** granted by an
agent tool or by auto-provisioning:

* ``agent.tools_write._ensure_user`` provisions previously-unseen identities
  with the non-approving ``'viewer'`` role;
* no module under ``agent/`` may insert or update ``users.role``.

This script is the *only* path to the ``'trader'`` role, and it lives outside
``agent/`` so it is not reachable from the agent tool surface. It must be run
by a human operator with direct access to the Lakebase credentials:

    python scripts/grant_approver.py <user_id>

It upserts the user and sets ``role = 'trader'`` (idempotent). The migration
``db/migrations/003_revoke_auto_provisioned_approvers.sql`` revokes any
``'trader'`` role that existed before this separation, so re-run this script
for every principal you have explicitly vetted. See ``docs/DEPLOYMENT.md``.
"""
from __future__ import annotations

import sys

from db.lakebase import get_lakebase


def grant_approver(user_id: str) -> None:
    """Upsert ``user_id`` and set ``role = 'trader'`` (idempotent)."""
    db = get_lakebase()
    try:
        with db.transaction() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO users (user_id, display_name, role, created_at)
                    VALUES (%s, %s, 'trader', now())
                    ON CONFLICT (user_id) DO UPDATE SET role = 'trader'
                    """,
                    (user_id, user_id),
                )
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python scripts/grant_approver.py <user_id>")
    grant_approver(sys.argv[1])
    print(f"granted approver role ('trader') to {sys.argv[1]}")
