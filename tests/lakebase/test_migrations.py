"""Migration tests — require live Lakebase (`-m lakebase`)."""
import pytest

pytestmark = pytest.mark.lakebase

EXPECTED_TABLES = {
    "users",
    "watchlists",
    "signals",
    "orders",
    "executions",
    "positions",
    "agent_actions",
    "research_notes",
}

BEHAVIOURAL_TABLES = {
    "watchlists",
    "signals",
    "orders",
    "executions",
    "positions",
    "agent_actions",
    "research_notes",
}


def test_migration_is_rerunnable(migrated):
    from db.migrate import apply_migrations

    with migrated.transaction() as conn:
        applied = apply_migrations(conn)
    assert applied == []


def test_migrations_build_schema_from_scratch(lakebase):
    """Apply migrations to an empty scratch schema and verify it builds the
    full schema from nothing (not just idempotency against a shared schema)."""
    import uuid

    from db.migrate import apply_migrations

    schema = f"scratch_{uuid.uuid4().hex[:12]}"
    expected_tables = EXPECTED_TABLES | {"approvals", "accounts", "schema_migrations"}

    with lakebase.connection() as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("CREATE SCHEMA " + schema)
            cur.execute("SELECT set_config('search_path', %s, false)", (schema,))
        conn.autocommit = False
        try:
            applied = apply_migrations(conn)
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = %s",
                    (schema,),
                )
                present = {r[0] for r in cur.fetchall()}
            assert set(applied) >= {"001_operational_schema", "002_approvals_accounts"}
            assert expected_tables <= present
        finally:
            conn.rollback()
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute("SELECT set_config('search_path', 'public', false)")
                cur.execute("DROP SCHEMA IF EXISTS " + schema + " CASCADE")
            conn.autocommit = False


def test_all_eight_tables_exist(migrated):
    rows = migrated.execute(
        """
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public'
        """
    )
    present = {r[0] for r in rows}
    assert EXPECTED_TABLES <= present


def test_replica_identity_full_on_behavioural_tables(migrated):
    rows = migrated.execute(
        """
        SELECT c.relname, c.relreplident
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relkind = 'r'
        """
    )
    repl = {r[0]: r[1] for r in rows}
    for table in BEHAVIOURAL_TABLES:
        assert repl.get(table) == "f", f"{table} should have REPLICA IDENTITY FULL"


def test_idempotency_key_is_unique(migrated):
    rows = migrated.execute(
        """
        SELECT conname
        FROM pg_constraint
        WHERE conrelid = 'orders'::regclass AND contype = 'u'
        """
    )
    names = {r[0] for r in rows}
    assert any("idempotency_key" in n for n in names)


def test_orders_status_check_rejects_invalid(migrated, cleanup_user):
    uid = cleanup_user()
    with pytest.raises(Exception):
        with migrated.transaction() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO users (user_id, display_name, role) VALUES (%s, %s, %s)",
                    (uid, uid, "trader"),
                )
                cur.execute(
                    """
                    INSERT INTO orders
                        (order_id, user_id, symbol, broker, side, quantity, notional,
                         order_type, status, idempotency_key)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    ("o_bad", uid, "TEST", "PAPER", "BUY", 1, 10.0, "MARKET",
                     "NOT_A_STATUS", "ik_bad"),
                )


def test_migration_003_downgrades_preexisting_trader(lakebase):
    """003 revokes approval authority from a pre-existing 'trader' row.

    Runs 001 + 002, seeds a 'trader' (as round-4 auto-provisioning would have),
    then applies 003 and asserts the role becomes 'viewer'. Executed in a scratch
    schema so the shared schema is untouched.
    """
    import uuid
    from pathlib import Path

    migrations = Path("db/migrations")
    schema = f"scratch_{uuid.uuid4().hex[:12]}"
    trader = f"trader_{uuid.uuid4().hex}"

    with lakebase.connection() as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("CREATE SCHEMA " + schema)
            cur.execute("SELECT set_config('search_path', %s, false)", (schema,))
        conn.autocommit = False
        try:
            with conn.cursor() as cur:
                cur.execute((migrations / "001_operational_schema.sql").read_text())
                cur.execute((migrations / "002_approvals_accounts.sql").read_text())
                cur.execute(
                    "INSERT INTO users (user_id, display_name, role) VALUES (%s, %s, 'trader')",
                    (trader, trader),
                )
                cur.execute(
                    (migrations / "003_revoke_auto_provisioned_approvers.sql").read_text()
                )
                cur.execute("SELECT role FROM users WHERE user_id = %s", (trader,))
                assert cur.fetchone() == ("viewer",)
            conn.rollback()
        finally:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute("SELECT set_config('search_path', 'public', false)")
                cur.execute("DROP SCHEMA IF EXISTS " + schema + " CASCADE")
            conn.autocommit = False
