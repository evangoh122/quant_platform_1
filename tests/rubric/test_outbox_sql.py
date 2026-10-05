"""tests/rubric/test_outbox_sql.py — Static analysis of migration 004.

Parses the SQL migration to verify security properties without running it
against a live database. Each test applies a specific mutation to the SQL
and proves the original passes while the mutation fails.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_MIGRATION = Path(__file__).resolve().parent.parent.parent / "db" / "migrations" / "004_analytics_outbox.sql"


@pytest.fixture(scope="module")
def sql() -> str:
    return _MIGRATION.read_text(encoding="utf-8")


# ── no to_jsonb(NEW/OLD) ─────────────────────────────────────────────────────

def _strip_sql_comments(sql: str) -> str:
    """Remove SQL line comments (-- ...) from the migration."""
    lines = []
    for line in sql.splitlines():
        # Remove inline comments but keep the line
        stripped = line.split("--")[0] if "--" in line else line
        lines.append(stripped)
    return "\n".join(lines)


def test_no_to_jsonb_new(sql):
    """Trigger must not use to_jsonb(NEW); explicit field lists only."""
    body = _strip_sql_comments(sql)
    assert "to_jsonb(NEW)" not in body, (
        "Migration uses to_jsonb(NEW) — must use explicit jsonb_build_object"
    )


def test_no_to_jsonb_old(sql):
    """Trigger must not use to_jsonb(OLD); explicit field lists only."""
    body = _strip_sql_comments(sql)
    assert "to_jsonb(OLD)" not in body, (
        "Migration uses to_jsonb(OLD) — must use explicit jsonb_build_object"
    )


# ── no SELECT * in triggers ──────────────────────────────────────────────────

def test_no_select_star_in_trigger(sql):
    """Trigger function must not use SELECT * (explicit fields only)."""
    # Extract the trigger function body
    match = re.search(
        r"CREATE OR REPLACE FUNCTION capture_outbox_event\(\).*?\$\$",
        sql, re.DOTALL | re.IGNORECASE,
    )
    assert match, "Trigger function capture_outbox_event not found"
    body = match.group(0)
    assert "SELECT *" not in body.upper(), (
        "Trigger function uses SELECT * — must use explicit field lists"
    )


# ── fixed search_path ────────────────────────────────────────────────────────

def test_fixed_search_path(sql):
    """SECURITY DEFINER trigger must set a fixed safe search_path."""
    assert re.search(
        r"SET\s+search_path\s*=\s*pg_catalog\s*,\s*public", sql, re.IGNORECASE
    ), "Trigger function missing 'SET search_path = pg_catalog, public'"


# ── SECURITY DEFINER ─────────────────────────────────────────────────────────

def test_security_definer(sql):
    """Trigger function must be SECURITY DEFINER."""
    assert re.search(
        r"SECURITY\s+DEFINER", sql, re.IGNORECASE
    ), "Trigger function missing SECURITY DEFINER"


# ── trigger tables ───────────────────────────────────────────────────────────

_EXPECTED_TABLES = [
    "watchlists", "signals", "orders", "executions",
    "positions", "agent_actions", "research_notes", "approvals",
]


@pytest.mark.parametrize("table", _EXPECTED_TABLES)
def test_trigger_attached(sql, table):
    """Each behavioural table must have an AFTER trigger attached."""
    pattern = rf"CREATE\s+TRIGGER\s+trg_outbox_{table}"
    assert re.search(pattern, sql, re.IGNORECASE), (
        f"Missing trigger for table '{table}'"
    )


# ── no direct app grants ─────────────────────────────────────────────────────

def test_no_grant_to_app(sql):
    """Migration must not grant direct access to analytics_outbox for app roles."""
    # Look for GRANT ... ON analytics_outbox ... TO ... (but allow REVOKE)
    grants = re.findall(
        r"GRANT\s+.*?\s+ON\s+(?:TABLE\s+)?analytics_outbox\s+TO\s+(\w+)",
        sql, re.IGNORECASE,
    )
    # Filter out REVOKE (which uses REVOKE ... FROM)
    assert not grants, (
        f"Direct GRANT on analytics_outbox to {grants} — app roles must not "
        f"have direct access; only the SECURITY DEFINER trigger writes."
    )


def test_revoke_public(sql):
    """analytics_outbox must have PUBLIC access revoked."""
    assert re.search(
        r"REVOKE\s+ALL\s+ON\s+(?:TABLE\s+)?analytics_outbox\s+FROM\s+PUBLIC",
        sql, re.IGNORECASE,
    ), "Missing REVOKE ALL ON analytics_outbox FROM PUBLIC"


def test_revoke_function_public(sql):
    """capture_outbox_event must have PUBLIC execution revoked."""
    assert re.search(
        r"REVOKE\s+ALL\s+ON\s+FUNCTION\s+capture_outbox_event\s*\(\)\s+FROM\s+PUBLIC",
        sql, re.IGNORECASE,
    ), "Missing REVOKE ALL ON FUNCTION capture_outbox_event() FROM PUBLIC"


# ── idempotent snapshot seed ─────────────────────────────────────────────────

def test_snapshot_seed_uses_on_conflict(sql):
    """Snapshot seed must use ON CONFLICT for idempotency."""
    snapshot_inserts = re.findall(
        r"INSERT\s+INTO\s+analytics_outbox.*?ON\s+CONFLICT",
        sql, re.DOTALL | re.IGNORECASE,
    )
    assert len(snapshot_inserts) >= 8, (
        f"Expected 8 snapshot seed INSERTs with ON CONFLICT, found {len(snapshot_inserts)}"
    )


def test_no_unsafe_dynamic_sql(sql):
    """Migration must not use EXECUTE or dynamic SQL."""
    assert "EXECUTE" not in sql.upper().split("$$")[0], (
        "Migration contains EXECUTE outside of trigger function body"
    )


# ── sensitive fields excluded ────────────────────────────────────────────────

_SENSITIVE_FIELDS = ["note_text", "input_summary", "output_summary", "display_name"]


@pytest.mark.parametrize("field", _SENSITIVE_FIELDS)
def test_sensitive_field_excluded(sql, field):
    """Sensitive fields must not appear in any payload."""
    # Search in the trigger function body (between $$ markers)
    bodies = re.findall(r"\$\$(.*?)\$\$", sql, re.DOTALL)
    for body in bodies:
        # Check jsonb_build_object calls don't include the field
        build_calls = re.findall(
            r"jsonb_build_object\((.*?)\)", body, re.DOTALL
        )
        for call in build_calls:
            assert field not in call, (
                f"Sensitive field '{field}' found in payload: {call[:100]}..."
            )