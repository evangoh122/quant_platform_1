"""db/migrate.py — forward-only, re-runnable Lakebase migration runner.

Migrations live in `db/migrations/*.sql`, ordered by filename. Applied versions
are recorded in `schema_migrations`; each file is applied exactly once, inside
a single transaction, and recorded. Re-running is a no-op for applied files.
"""
from __future__ import annotations

from pathlib import Path
from typing import List

import psycopg

MIGRATIONS_DIR = Path(__file__).parent / "migrations"

# These statements may not run inside a transaction block. We currently emit
# none of them, but the runner checks defensively before wrapping.
NON_TRANSACTIONAL_PREFIXES = ("CREATE DATABASE", "ALTER SYSTEM", "DROP DATABASE")


def _ensure_meta(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version      TEXT PRIMARY KEY,
                applied_at   TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )


def _applied_versions(conn: psycopg.Connection) -> set:
    with conn.cursor() as cur:
        cur.execute("SELECT version FROM schema_migrations")
        return {row[0] for row in cur.fetchall()}


def _migration_files() -> List[Path]:
    return sorted(MIGRATIONS_DIR.glob("*.sql"))


def apply_migrations(conn: psycopg.Connection) -> List[str]:
    """Apply pending migrations in order. Returns the versions applied this run."""
    _ensure_meta(conn)
    applied = _applied_versions(conn)
    newly_applied: List[str] = []

    for path in _migration_files():
        version = path.stem
        if version in applied:
            continue

        sql = path.read_text(encoding="utf-8")
        if sql.strip().startswith(NON_TRANSACTIONAL_PREFIXES):
            raise NotImplementedError(
                f"Migration {version} contains a statement that cannot run in a "
                f"transaction. Refuse to run it safely."
            )

        with conn.cursor() as cur:
            cur.execute(sql)
            cur.execute(
                "INSERT INTO schema_migrations (version) VALUES (%s)",
                (version,),
            )
        conn.commit()
        newly_applied.append(version)

    return newly_applied


def migrate(conn: psycopg.Connection) -> List[str]:
    """Convenience wrapper that returns newly applied versions."""
    return apply_migrations(conn)


if __name__ == "__main__":
    import sys

    from db.lakebase import Lakebase

    lb = Lakebase()
    try:
        with lb.transaction() as conn:
            applied_now = apply_migrations(conn)
        print(f"Applied migrations: {applied_now or 'none (already up to date)'}")
    finally:
        lb.close()
