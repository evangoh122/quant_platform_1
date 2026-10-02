"""Fixtures for the Lakebase agent-tools test suite.

Pure-logic tests (guardrails, symbol validation, injection) run with no network.
Tests that require the live Lakebase are marked ``@pytest.mark.lakebase`` and are
deselected with ``-m "not lakebase"``.
"""
import uuid

import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "lakebase: requires live Lakebase connectivity "
        "(deselect with `-m 'not lakebase'`)",
    )


@pytest.fixture(scope="session")
def lakebase():
    from db.lakebase import Lakebase

    lb = Lakebase()
    yield lb
    lb.close()


@pytest.fixture(scope="session")
def migrated(lakebase):
    from db.migrate import apply_migrations

    with lakebase.transaction() as conn:
        apply_migrations(conn)
    return lakebase


_CLEANUP_ORDER = [
    "executions",
    "orders",
    "research_notes",
    "watchlists",
    "agent_actions",
    "signals",
    "positions",
    "users",
]


@pytest.fixture
def cleanup_user(migrated):
    """Return a fresh unique user_id and clean up all rows it touched afterwards."""
    user_ids = []

    def _mk() -> str:
        uid = f"test_{uuid.uuid4().hex}"
        user_ids.append(uid)
        return uid

    yield _mk

    for uid in user_ids:
        with migrated.transaction() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM executions WHERE order_id IN "
                    "(SELECT order_id FROM orders WHERE user_id = %s)",
                    (uid,),
                )
                cur.execute("DELETE FROM orders WHERE user_id = %s", (uid,))
                cur.execute("DELETE FROM research_notes WHERE user_id = %s", (uid,))
                cur.execute("DELETE FROM watchlists WHERE user_id = %s", (uid,))
                cur.execute("DELETE FROM agent_actions WHERE user_id = %s", (uid,))
                cur.execute("DELETE FROM users WHERE user_id = %s", (uid,))
