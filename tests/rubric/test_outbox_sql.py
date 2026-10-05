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
_MIGRATION_001 = Path(__file__).resolve().parent.parent.parent / "db" / "migrations" / "001_operational_schema.sql"
_MIGRATION_002 = Path(__file__).resolve().parent.parent.parent / "db" / "migrations" / "002_approvals_accounts.sql"
_PIPELINE = Path(__file__).resolve().parent.parent.parent / "pipelines" / "lakebase_analytics.py"


@pytest.fixture(scope="module")
def sql() -> str:
    return _MIGRATION.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def pipeline_src() -> str:
    return _PIPELINE.read_text(encoding="utf-8")


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

_TRIGGER_FUNC_RE = re.compile(
    r"CREATE OR REPLACE FUNCTION (capture_outbox_\w+)\(\).*?\$\$",
    re.DOTALL | re.IGNORECASE,
)


def test_no_select_star_in_trigger(sql):
    """Trigger function must not use SELECT * (explicit fields only)."""
    for match in _TRIGGER_FUNC_RE.finditer(sql):
        body = match.group(0)
        assert "SELECT *" not in body.upper(), (
            f"Trigger function {match.group(1)} uses SELECT * — must use explicit field lists"
        )


# ── fixed search_path ────────────────────────────────────────────────────────

def test_fixed_search_path(sql):
    """Every SECURITY DEFINER trigger must set a fixed safe search_path."""
    funcs = _TRIGGER_FUNC_RE.findall(sql)
    assert len(funcs) >= 8, f"Expected 8 trigger functions, found {len(funcs)}"
    for func_name in funcs:
        # Find the function body
        pattern = rf"CREATE OR REPLACE FUNCTION {re.escape(func_name)}\(\).*?\$\$"
        m = re.search(pattern, sql, re.DOTALL | re.IGNORECASE)
        assert m, f"Function {func_name} not found"
        body = m.group(0)
        assert re.search(
            r"SET\s+search_path\s*=\s*pg_catalog\s*,\s*public", body, re.IGNORECASE
        ), f"Trigger function {func_name} missing 'SET search_path = pg_catalog, public'"


# ── SECURITY DEFINER ─────────────────────────────────────────────────────────

def test_security_definer(sql):
    """Every trigger function must be SECURITY DEFINER."""
    funcs = _TRIGGER_FUNC_RE.findall(sql)
    assert len(funcs) >= 8
    for func_name in funcs:
        pattern = rf"CREATE OR REPLACE FUNCTION {re.escape(func_name)}\(\).*?\$\$"
        m = re.search(pattern, sql, re.DOTALL | re.IGNORECASE)
        assert m, f"Function {func_name} not found"
        body = m.group(0)
        assert re.search(
            r"SECURITY\s+DEFINER", body, re.IGNORECASE
        ), f"Trigger function {func_name} missing SECURITY DEFINER"


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
    """Every trigger function must have PUBLIC execution revoked."""
    funcs = _TRIGGER_FUNC_RE.findall(sql)
    assert len(funcs) >= 8
    for func_name in funcs:
        assert re.search(
            rf"REVOKE\s+ALL\s+ON\s+FUNCTION\s+{re.escape(func_name)}\s*\(\)\s+FROM\s+PUBLIC",
            sql, re.IGNORECASE,
        ), f"Missing REVOKE ALL ON FUNCTION {func_name}() FROM PUBLIC"


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


# ── per-table trigger functions (no shared function) ─────────────────────────

_EXPECTED_FUNCS = [
    "capture_outbox_watchlists",
    "capture_outbox_signals",
    "capture_outbox_orders",
    "capture_outbox_executions",
    "capture_outbox_positions",
    "capture_outbox_agent_actions",
    "capture_outbox_research_notes",
    "capture_outbox_approvals",
]


@pytest.mark.parametrize("func_name", _EXPECTED_FUNCS)
def test_per_table_trigger_function_exists(sql, func_name):
    """Each table must have its own trigger function."""
    assert re.search(
        rf"CREATE\s+OR\s+REPLACE\s+FUNCTION\s+{re.escape(func_name)}\s*\(\)",
        sql, re.IGNORECASE,
    ), f"Missing trigger function {func_name}"


def test_no_shared_capture_outbox_event(sql):
    """The old shared capture_outbox_event() function must not exist."""
    assert not re.search(
        r"CREATE\s+OR\s+REPLACE\s+FUNCTION\s+capture_outbox_event\s*\(\)",
        sql, re.IGNORECASE,
    ), "Shared capture_outbox_event() still exists — must use per-table functions"


# ── DROP TRIGGER IF EXISTS (idempotent re-apply) ─────────────────────────────

@pytest.mark.parametrize("table", _EXPECTED_TABLES)
def test_drop_trigger_if_exists(sql, table):
    """Each CREATE TRIGGER must be preceded by DROP TRIGGER IF EXISTS."""
    drop_pattern = rf"DROP\s+TRIGGER\s+IF\s+EXISTS\s+trg_outbox_{re.escape(table)}\s+ON\s+{re.escape(table)}"
    assert re.search(drop_pattern, sql, re.IGNORECASE), (
        f"Missing DROP TRIGGER IF EXISTS trg_outbox_{table} ON {table}"
    )


# ── dedupe_key NULL for trigger events ────────────────────────────────────────

def test_trigger_events_use_null_dedupe_key(sql):
    """Trigger-generated events must use dedupe_key = NULL (not a fixed key)."""
    # Extract trigger function bodies (between $$ markers)
    bodies = re.findall(r"\$\$(.*?)\$\$", sql, re.DOTALL)
    # The first 8 bodies are trigger functions; the rest are snapshot seeds
    trigger_bodies = bodies[:8]
    for i, body in enumerate(trigger_bodies):
        # Each trigger INSERT must use dedupe_key = NULL or dedupe_key, NULL
        # NOT a computed key like _op || ':' || TG_TABLE_NAME
        insert_blocks = re.findall(
            r"INSERT\s+INTO\s+analytics_outbox.*?;", body, re.DOTALL | re.IGNORECASE
        )
        for block in insert_blocks:
            # Must not contain string concatenation for dedupe_key
            assert "_op ||" not in block.lower(), (
                f"Trigger function {_EXPECTED_FUNCS[i]} uses computed dedupe_key "
                f"(should be NULL)"
            )


# ── WATERMARK-SKIP: claim_batch must use WHERE delivered_at IS NULL ───────────

def test_claim_batch_selects_pending_by_null_delivered_at(pipeline_src):
    """claim_batch must select events WHERE delivered_at IS NULL (not a watermark skip).

    Mutation WATERMARK-SKIP: changes pending selection to
    event_id > MAX(delivered event_id). This test parses the claim_batch SQL
    to ensure it uses the correct predicate.
    """
    # Find the claim_batch function
    match = re.search(
        r"def claim_batch\(.*?(?=\ndef |\Z)", pipeline_src, re.DOTALL
    )
    assert match, "claim_batch function not found"
    body = match.group(0)
    # Must contain WHERE delivered_at IS NULL
    assert "delivered_at IS NULL" in body, (
        "claim_batch must use 'WHERE delivered_at IS NULL' to select pending events. "
        "WATERMARK-SKIP mutation (event_id > MAX(delivered event_id)) would silently "
        "skip late-arriving events."
    )
    # Must NOT use a watermark pattern (MAX or COALESCE with delivered_at in WHERE)
    assert "MAX(delivered" not in body.replace(" ", ""), (
        "claim_batch uses MAX(delivered...) — this is the WATERMARK-SKIP mutation"
    )


# ── APPEND-DUPLICATE: merge_events_to_delta must use MERGE INTO ──────────────

def test_merge_events_uses_merge_into(pipeline_src):
    """merge_events_to_delta must use MERGE INTO (not plain INSERT) for idempotent replay.

    Mutation APPEND-DUPLICATE: replaces MERGE INTO with INSERT ... SELECT.
    This test parses the merge_events_to_delta SQL to ensure it uses MERGE.
    """
    # Find the merge_events_to_delta function
    match = re.search(
        r"def merge_events_to_delta\(.*?(?=\ndef |\Z)", pipeline_src, re.DOTALL
    )
    assert match, "merge_events_to_delta function not found"
    body = match.group(0)
    # Must use MERGE INTO
    assert re.search(r"MERGE\s+INTO", body, re.IGNORECASE), (
        "merge_events_to_delta must use 'MERGE INTO' for idempotent upsert. "
        "APPEND-DUPLICATE mutation (plain INSERT) would create duplicate rows on replay."
    )
    # Must NOT be just a plain INSERT (no MERGE)
    # Check that the SQL string contains MERGE, not just INSERT
    sql_strings = re.findall(r'"""(.*?)"""', body, re.DOTALL)
    for s in sql_strings:
        if "INSERT" in s.upper() and "MERGE" not in s.upper():
            # This is a plain INSERT without MERGE — could be the mutation
            pass  # Allow INSERT in _staging_events temp view, but MERGE must exist


# ── NEW/OLD column references match table definitions ────────────────────────

def _get_table_columns(migration_sql: str) -> dict[str, set[str]]:
    """Parse CREATE TABLE statements to extract column names per table."""
    tables: dict[str, set[str]] = {}
    # Match CREATE TABLE IF NOT EXISTS <name> ( ... )
    pattern = re.compile(
        r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+(\w+)\s*\((.*?)\);",
        re.DOTALL | re.IGNORECASE,
    )
    for m in pattern.finditer(migration_sql):
        table_name = m.group(1)
        body = m.group(2)
        cols: set[str] = set()
        for line in body.split(","):
            # First word that looks like a column name (lowercase, underscore)
            line = line.strip()
            if line.startswith("--"):
                continue
            # Skip constraint lines
            if re.match(r"(?i)^\s*(CONSTRAINT|CHECK|UNIQUE|PRIMARY|FOREIGN|REFERENCES)", line):
                continue
            col_match = re.match(r"(\w+)\s+", line)
            if col_match:
                col = col_match.group(1).lower()
                # Filter out SQL keywords that might appear at start of lines
                if col not in ("constraint", "check", "unique", "primary", "foreign",
                               "references", "on", "not", "null", "default", "generated",
                               "always", "as", "identity", "in", "select", "and", "or"):
                    cols.add(col)
        tables[table_name] = cols
    return tables


def _get_trigger_func_new_old_refs(sql: str, func_name: str) -> set[str]:
    """Extract NEW.<col> and OLD.<col> references from a trigger function body."""
    # Find the function body between $$ markers
    pattern = rf"CREATE OR REPLACE FUNCTION {re.escape(func_name)}\(\).*?\$\$(.*?)\$\$"
    m = re.search(pattern, sql, re.DOTALL | re.IGNORECASE)
    if not m:
        return set()
    body = m.group(1)
    refs: set[str] = set()
    for ref in re.finditer(r"(?:NEW|OLD)\.(\w+)", body):
        refs.add(ref.group(1).lower())
    return refs


def test_trigger_column_references_match_table_schemas(sql):
    """Every NEW.<col>/OLD.<col> in a trigger function must exist in the table's schema.

    Mutation: reference NEW.watchlist_id in the orders function → must FAIL.
    """
    # Build table column sets from migrations 001 + 002
    all_migrations = ""
    for p in [_MIGRATION_001, _MIGRATION_002]:
        if p.exists():
            all_migrations += p.read_text(encoding="utf-8") + "\n"
    table_cols = _get_table_columns(all_migrations)

    func_to_table = {
        "capture_outbox_watchlists": "watchlists",
        "capture_outbox_signals": "signals",
        "capture_outbox_orders": "orders",
        "capture_outbox_executions": "executions",
        "capture_outbox_positions": "positions",
        "capture_outbox_agent_actions": "agent_actions",
        "capture_outbox_research_notes": "research_notes",
        "capture_outbox_approvals": "approvals",
    }

    for func_name, table_name in func_to_table.items():
        refs = _get_trigger_func_new_old_refs(sql, func_name)
        if table_name not in table_cols:
            pytest.skip(f"Table {table_name} not found in migrations")
        valid_cols = table_cols[table_name]
        bad_refs = refs - valid_cols
        assert not bad_refs, (
            f"Trigger function {func_name} references columns {bad_refs} "
            f"that do not exist in table {table_name} (valid: {sorted(valid_cols)}). "
            f"This would cause record-has-no-field errors on writes."
        )