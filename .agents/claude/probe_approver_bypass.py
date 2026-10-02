"""Probe: can a fabricated approver identity pass record_approval?

Round 4 claims record_approval "stops fabricated identities" by requiring the
approver to exist in `users` with role 'trader'. But every write tool calls
_ensure_user(), which upserts any user_id as role 'trader'. Hypothesis: one
watchlist call with an invented user_id mints a valid approver.

Uses unique probe ids and deletes everything it creates.
"""
import sys
import uuid

sys.path.insert(0, "/home/jianj/code/quant_platform_1")

from agent.tools_write import (  # noqa: E402
    ApprovalContext, add_to_watchlist, create_order_intent, record_approval,
)
from db.lakebase import get_lakebase  # noqa: E402

tag = uuid.uuid4().hex[:8]
owner = f"probe-owner-{tag}"
fake = f"probe-FABRICATED-{tag}"
db = get_lakebase()

order = create_order_intent("AAPL", "BUY", 1, notional=200.0, user_id=owner,
                            idempotency_key=f"probe-{tag}")
oid = order["order_id"]
print("order:", oid, order.get("status"))

# Control: a never-seen fabricated id should be rejected.
r1 = record_approval(oid, ApprovalContext(approver_id=fake))
print("1) fabricated, never provisioned ->", r1.get("ok"), r1.get("reason"))

# Bypass: touch any write tool with that id first.
add_to_watchlist("MSFT", user_id=fake)
r2 = record_approval(oid, ApprovalContext(approver_id=fake))
print("2) same id after one watchlist call ->", r2.get("ok"), r2.get("reason"))

print("\nVERDICT:", "BYPASS CONFIRMED" if (not r1.get("ok") and r2.get("ok"))
      else "no bypass")

# Cleanup everything this probe created.
with db.transaction() as conn, conn.cursor() as cur:
    cur.execute("DELETE FROM approvals WHERE order_id = %s", (oid,))
    cur.execute("DELETE FROM agent_actions WHERE user_id IN (%s, %s)", (owner, fake))
    cur.execute("DELETE FROM watchlists WHERE user_id IN (%s, %s)", (owner, fake))
    cur.execute("DELETE FROM orders WHERE order_id = %s", (oid,))
    cur.execute("DELETE FROM users WHERE user_id IN (%s, %s)", (owner, fake))
print("cleanup done")
