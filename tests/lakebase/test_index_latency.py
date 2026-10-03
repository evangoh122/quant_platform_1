"""Index and latency evidence — require live Lakebase (`-m lakebase`).

Item 19 of the close-out: prove the operational queries are index-backed and
measure the read/write latency of the agent tools against the live instance.

Index proof — DONE.
    ``test_operational_queries_use_indexes`` runs ``EXPLAIN (FORMAT JSON)`` on
    each operational query with ``enable_seqscan = off`` and asserts the planner
    uses an index scan rather than a sequential scan. (On a nearly-empty table
    the cost planner prefers a seq scan, so seq scan is disabled for the
    assertion; the index must still exist and be usable.)

Latency budgets — UNVERIFIED (not met from this environment).
    ``test_read_write_latency_p50_p95`` measures p50/p95 read/write latency and
    prints the numbers. The stated budgets (<500 ms read / <800 ms write) are
    **not met** here: measured read p95 ≈ 610 ms and write p95 ≈ 1380 ms, with
    the read *p50* already ≈ 570 ms. The ~570 ms floor is the WSL→us-west-2
    Lakebase network round-trip, not query cost — the EXPLAIN test above shows
    every query is index-backed, so the database work itself is milliseconds.
    The budgets therefore remain unverified in this environment and must be
    re-measured from a co-located runner before being trusted.
"""
import json
import time
import uuid

import pytest

pytestmark = pytest.mark.lakebase

import agent.tools_write as tw
from agent.tools_retrieval import get_open_orders


# ── operational queries and the index that must serve each ────────────────────
_OPERATIONAL_QUERIES = [
    (
        "get_open_orders",
        "SELECT order_id, symbol, side, quantity, notional, order_type, "
        "limit_price, status, idempotency_key, created_at FROM orders "
        "WHERE user_id = 'probe_user' AND status = ANY(ARRAY['PENDING_APPROVAL',"
        "'APPROVED','SUBMITTED','PARTIALLY_FILLED']) ORDER BY created_at DESC",
    ),
    (
        "get_watchlist",
        "SELECT symbol, created_at FROM watchlists WHERE user_id = 'probe_user' "
        "ORDER BY created_at DESC",
    ),
    (
        "get_portfolio_positions",
        "SELECT account_id, symbol, quantity, avg_cost, market_price, "
        "realized_pnl, unrealized_pnl, updated_at FROM positions "
        "WHERE account_id = 'probe_user' ORDER BY symbol",
    ),
    (
        "create_order_intent_replay",
        "SELECT order_id, status, idempotency_key FROM orders "
        "WHERE idempotency_key = 'probe_key'",
    ),
    (
        "placement_order_fetch",
        "SELECT order_id, user_id, signal_id, broker, side, quantity, notional, "
        "order_type, limit_price, status, idempotency_key, symbol, broker_order_id "
        "FROM orders WHERE order_id = 'probe_order'",
    ),
    (
        "approval_read",
        "SELECT approver_id FROM approvals WHERE order_id = 'probe_order'",
    ),
    (
        "account_read",
        "SELECT buying_power FROM accounts WHERE account_id = 'probe_user'",
    ),
    (
        "position_notional",
        "SELECT COALESCE(SUM(quantity * avg_cost), 0) FROM positions "
        "WHERE account_id = 'probe_user' AND symbol = 'AAPL'",
    ),
    (
        "signal_read",
        "SELECT prediction_ts FROM signals WHERE signal_id = 'probe_signal'",
    ),
]


def _explain_text(db, query):
    with db.transaction() as conn:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL enable_seqscan = off")
            cur.execute("EXPLAIN (FORMAT JSON) " + query)
            plan = cur.fetchone()[0]
    return json.dumps(plan)


def test_operational_queries_use_indexes(migrated):
    for label, query in _OPERATIONAL_QUERIES:
        text = _explain_text(migrated, query)
        assert "Seq Scan" not in text, (
            f"{label}: planner chose a sequential scan despite an index:\n{text}"
        )
        assert "Index Scan" in text, (
            f"{label}: no index scan in plan:\n{text}"
        )


def _percentile(samples, p):
    s = sorted(samples)
    k = (len(s) - 1) * p
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


# Sanity bound for the latency test only — this is NOT the production budget.
# The real <500 ms read / <800 ms write budgets are unverified here (see module
# docstring); this bound merely catches a hung connection.
_SANITY_MS = 10_000


def test_read_write_latency_p50_p95(migrated, cleanup_user):
    uid = cleanup_user()
    # Warm up pool + plans so the measurement reflects steady-state latency.
    get_open_orders(user_id=uid, db=migrated)
    tw.create_order_intent("TEST", "BUY", 1, notional=10.0, user_id=uid, db=migrated)

    n = 20
    reads_ms, writes_ms = [], []
    for _ in range(n):
        t0 = time.perf_counter()
        get_open_orders(user_id=uid, db=migrated)
        reads_ms.append((time.perf_counter() - t0) * 1000)

        t0 = time.perf_counter()
        tw.create_order_intent(
            "TEST", "BUY", 1, notional=10.0,
            idempotency_key=f"lat-{uuid.uuid4()}", user_id=uid, db=migrated,
        )
        writes_ms.append((time.perf_counter() - t0) * 1000)

    r50, r95 = _percentile(reads_ms, 0.50), _percentile(reads_ms, 0.95)
    w50, w95 = _percentile(writes_ms, 0.50), _percentile(writes_ms, 0.95)

    print(
        f"LATENCY read  p50={r50:.1f}ms p95={r95:.1f}ms "
        f"(n={n}, min={min(reads_ms):.1f} max={max(reads_ms):.1f})"
    )
    print(
        f"LATENCY write p50={w50:.1f}ms p95={w95:.1f}ms "
        f"(n={n}, min={min(writes_ms):.1f} max={max(writes_ms):.1f})"
    )

    assert r95 < _SANITY_MS, f"read p95 {r95:.1f}ms exceeds sanity bound"
    assert w95 < _SANITY_MS, f"write p95 {w95:.1f}ms exceeds sanity bound"
