"""
execution_rails.py — Phase 14: Execution Rail (SQL/Math Safety).

Enforces read-only access for SQL mode and bounds math execution to prevent
resource exhaustion or arbitrary code execution.

Usage:
    from api.services.guardrails.execution_rails import check_execution, ExecutionVerdict
    verdict = check_execution(sql="SELECT ...", math_expr="1 + 2")
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class ExecutionVerdict:
    allowed: bool
    reason: Optional[str] = None
    mode: Optional[str] = None  # "sql" | "math" | "unknown"


# ── SQL safety checks ────────────────────────────────────────────────────────

# Additional SQL keywords beyond the chat_engine blocklist
_SQL_DANGEROUS_PATTERNS: list[tuple[str, str]] = [
    # DDL
    (r"\b(ALTER|CREATE|DROP|TRUNCATE)\b", "DDL statement not allowed"),
    # DML
    (r"\b(INSERT|UPDATE|DELETE|MERGE)\b", "DML statement not allowed"),
    # System functions
    (r"\bduckdb_\w+\s*\(", "DuckDB internal function not allowed"),
    (r"\binformation_schema\b", "Schema enumeration not allowed"),
    # File/network access
    (r"\b(read_csv|read_parquet|read_json|read_blob)\b", "File access not allowed"),
    (r"\b(httpfs|http|url)\b", "Network access not allowed"),
    # Attach/detach
    (r"\b(ATTACH|DETACH)\b", "Database attach not allowed"),
    # Multi-statement
    (r";\s*\w", "Multi-statement SQL not allowed"),
]

_COMPILED_SQL: list[tuple[re.Pattern, str]] = [
    (re.compile(p, re.IGNORECASE), reason)
    for p, reason in _SQL_DANGEROUS_PATTERNS
]


def check_sql(sql: str) -> ExecutionVerdict:
    """Validate that SQL is read-only and safe.

    Args:
        sql: The SQL query string to validate.

    Returns:
        ExecutionVerdict with allowed=True if the SQL is safe.
    """
    if not sql or not sql.strip():
        return ExecutionVerdict(allowed=True, mode="sql")

    # Must start with SELECT or WITH
    first = sql.strip().lstrip().split(None, 1)[0].upper()
    if first not in ("SELECT", "WITH"):
        return ExecutionVerdict(
            allowed=False,
            reason=f"SQL must start with SELECT or WITH, got: {first}",
            mode="sql",
        )

    # Check dangerous patterns
    for compiled, reason in _COMPILED_SQL:
        if compiled.search(sql):
            return ExecutionVerdict(
                allowed=False,
                reason=reason,
                mode="sql",
            )

    # Length check
    if len(sql) > 8192:
        return ExecutionVerdict(
            allowed=False,
            reason="SQL query too long (max 8192 chars)",
            mode="sql",
        )

    return ExecutionVerdict(allowed=True, mode="sql")


# ── Math safety checks ───────────────────────────────────────────────────────

# Max expression length
_MAX_MATH_EXPR_LEN = 1024

# Blocked math functions (potential code execution)
_MATH_BLOCKED: set[str] = {
    "exec", "eval", "compile", "import", "__import__",
    "open", "file", "read", "write", "delete",
    "system", "popen", "subprocess", "os",
    "globals", "locals", "vars", "dir",
    "getattr", "setattr", "delattr",
    "input", "raw_input",
}


def check_math(expression: str) -> ExecutionVerdict:
    """Validate that a math expression is safe to evaluate.

    Args:
        expression: The math expression string.

    Returns:
        ExecutionVerdict with allowed=True if the expression is safe.
    """
    if not expression or not expression.strip():
        return ExecutionVerdict(allowed=True, mode="math")

    # Length check
    if len(expression) > _MAX_MATH_EXPR_LEN:
        return ExecutionVerdict(
            allowed=False,
            reason=f"Math expression too long (max {_MAX_MATH_EXPR_LEN} chars)",
            mode="math",
        )

    # Check for blocked functions/keywords
    tokens = set(re.findall(r"\b[a-z_]\w*\b", expression.lower()))
    found = tokens & _MATH_BLOCKED
    if found:
        return ExecutionVerdict(
            allowed=False,
            reason=f"Blocked function/keyword in math expression: {', '.join(sorted(found))}",
            mode="math",
        )

    # Check for string literals (potential code injection)
    if re.search(r'["\']', expression):
        return ExecutionVerdict(
            allowed=False,
            reason="String literals not allowed in math expressions",
            mode="math",
        )

    return ExecutionVerdict(allowed=True, mode="math")


def check_execution(
    sql: Optional[str] = None,
    math_expr: Optional[str] = None,
) -> ExecutionVerdict:
    """Check both SQL and math execution safety.

    Args:
        sql: Optional SQL query to validate.
        math_expr: Optional math expression to validate.

    Returns:
        ExecutionVerdict with allowed=True if all checks pass.
    """
    if sql is not None:
        result = check_sql(sql)
        if not result.allowed:
            return result

    if math_expr is not None:
        result = check_math(math_expr)
        if not result.allowed:
            return result

    return ExecutionVerdict(allowed=True)
