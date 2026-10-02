"""Probe: round-5 must still let a properly granted approver approve their OWN
order, while rejecting cross-user approval. Self-cleaning."""
import subprocess
import sys
import uuid

sys.path.insert(0, "/home/jianj/code/quant_platform_1")
from agent.tools_write import ApprovalContext, create_order_intent, record_approval  # noqa: E402
from db.lakebase import get_lakebase  # noqa: E402

db = get_lakebase()
with db.transaction() as conn, conn.cursor() as cur:
    cur.execute("SELECT role, COUNT(*) FROM users GROUP BY role ORDER BY role")
    print("live users by role:", cur.fetchall())
    cur.execute("SELECT version FROM schema_migrations ORDER BY version")
    print("applied migrations:", [r[0] for r in cur.fetchall()])

tag = uuid.uuid4().hex[:8]
alice, bob = f"probe-alice-{tag}", f"probe-bob-{tag}"
oa = create_order_intent("AAPL", "BUY", 1, notional=200.0, user_id=alice,
                         idempotency_key=f"pa-{tag}")["order_id"]
create_order_intent("MSFT", "BUY", 1, notional=200.0, user_id=bob,
                    idempotency_key=f"pb-{tag}")

g = subprocess.run([sys.executable, "scripts/grant_approver.py", alice],
                   capture_output=True, text=True,
                   cwd="/home/jianj/code/quant_platform_1")
print("grant_approver exit:", g.returncode, (g.stdout or g.stderr).strip()[:120])

r_own = record_approval(oa, ApprovalContext(approver_id=alice))
r_cross = record_approval(oa, ApprovalContext(approver_id=bob))
print("granted owner approves own order ->", r_own.get("ok"), r_own.get("reason"))
print("other user approves alice's order ->", r_cross.get("ok"), r_cross.get("reason"))

with db.transaction() as conn, conn.cursor() as cur:
    cur.execute("DELETE FROM approvals WHERE order_id IN (SELECT order_id FROM orders WHERE user_id IN (%s,%s))", (alice, bob))
    cur.execute("DELETE FROM agent_actions WHERE user_id IN (%s,%s)", (alice, bob))
    cur.execute("DELETE FROM orders WHERE user_id IN (%s,%s)", (alice, bob))
    cur.execute("DELETE FROM users WHERE user_id IN (%s,%s)", (alice, bob))
print("cleanup done")
