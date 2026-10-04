"""Extract production view SQL from docs/NL1_PROPOSED_SERVING_VIEWS.md for DuckDB testing.

Every semantic test must obtain its SQL from the production DDL document at
test time, not from hard-coded copies. This module provides the extraction
and DuckDB adaptation functions to make that possible.

Usage::

    from tests.analytics_nl._ddl_extract import extract_view_sql, to_duckdb

    sql = extract_view_sql("serve_relative_performance_v1")
    duckdb_sql = to_duckdb(sql, params={":benchmark": "'SPY'", ":start_date": "'2024-01-01'", ":as_of": "'2025-01-01'"})
"""

from __future__ import annotations

import re
from pathlib import Path

_DDL_PATH = Path(__file__).parent.parent.parent / "docs" / "NL1_PROPOSED_SERVING_VIEWS.md"


def extract_view_sql(
    view_name: str,
    variant: str | None = None,
    doc_path: str | Path | None = None,
) -> str:
    """Extract CREATE VIEW SQL from the production DDL markdown document.

    Args:
        view_name: e.g. "serve_relative_performance_v1"
        variant: "adjusted" for primary DDL, "fallback" for unadjusted fallback,
                 None for views with a single SQL block (auto-selects first).
        doc_path: Override path to the DDL markdown (for mutation testing).
                  Defaults to docs/NL1_PROPOSED_SERVING_VIEWS.md.

    Returns:
        The raw SQL string (with CREATE VIEW ... AS header).

    Raises:
        ValueError: if the view or variant is not found.
    """
    ddl_path = Path(doc_path) if doc_path else _DDL_PATH
    content = ddl_path.read_text(encoding="utf-8")

    # Find the section for this view
    section_pattern = re.compile(
        rf"^## {re.escape(view_name)}\s*$", re.MULTILINE
    )
    m = section_pattern.search(content)
    if not m:
        raise ValueError(f"View section '## {view_name}' not found in {ddl_path}")

    section_start = m.end()
    # Section ends at next ## heading or end of file
    next_heading = re.search(r"^## ", content[section_start:], re.MULTILINE)
    section_end = section_start + next_heading.start() if next_heading else len(content)
    section = content[section_start:section_end]

    # Find all ```sql blocks in this section
    sql_blocks: list[str] = []
    block_pattern = re.compile(r"```sql\s*\n(.*?)```", re.DOTALL)
    for bm in block_pattern.finditer(section):
        sql_blocks.append(bm.group(1).strip())

    if not sql_blocks:
        raise ValueError(f"No SQL blocks found in section '## {view_name}'")

    # Determine which block to return
    if len(sql_blocks) == 1:
        if variant is not None and variant not in ("adjusted", "fallback"):
            raise ValueError(
                f"View '{view_name}' has only one SQL block; "
                f"variant='{variant}' is invalid"
            )
        return sql_blocks[0]

    # Multiple blocks: first is primary/adjusted, second is fallback
    if variant is None:
        variant = "adjusted"
    if variant == "adjusted":
        return sql_blocks[0]
    elif variant == "fallback":
        return sql_blocks[1]
    else:
        raise ValueError(
            f"Unknown variant '{variant}' for '{view_name}'. "
            f"Use 'adjusted' or 'fallback'."
        )


def to_duckdb(sql: str, params: dict[str, str] | None = None) -> str:
    """Adapt Databricks SQL for DuckDB execution.

    Performs:
    1. Named-parameter substitution (:as_of, :start_date, :benchmark → values)
    2. Catalog prefix stripping (${catalog}.${schema}. → empty)
    3. Databricks-only function replacements:
       - to_utc_timestamp(concat(date_col, ' HH:MM:SS'), 'TZ') →
         (date_col::TIMESTAMP + INTERVAL 'HH hours MM minutes SS seconds')

    Args:
        sql: The raw SQL from the DDL document.
        params: Mapping of parameter names (with colon prefix) to SQL value
                expressions, e.g. {":as_of": "'2025-01-01'"}.

    Returns:
        SQL string executable in DuckDB.
    """
    result = sql

    # 1. Named-parameter substitution
    if params:
        for param, value in params.items():
            result = re.sub(
                rf"(?<!\w){re.escape(param)}\b",
                value,
                result,
            )

    # 2. Catalog prefix stripping: ${catalog}.${schema}. → (empty)
    result = re.sub(r"\$\{catalog\}\.\$\{schema\}\.", "", result)

    # 3. Databricks-only function replacements

    # to_utc_timestamp(concat(date_col, ' HH:MM:SS'), 'TZ')
    # → (date_col::TIMESTAMP + INTERVAL 'HH hours MM minutes SS seconds')
    result = re.sub(
        r"to_utc_timestamp\s*\(\s*concat\s*\(\s*(\w+)\s*,\s*'\s*(\d{2}):(\d{2}):(\d{2})\s*'\s*\)\s*,\s*'[^']+'\s*\)",
        lambda m: f"({m.group(1)}::TIMESTAMP + INTERVAL '{int(m.group(2))} hours {int(m.group(3))} minutes {int(m.group(4))} seconds')",
        result,
        flags=re.IGNORECASE,
    )

    # DuckDB evaluates both branches of CASE eagerly, so LN(0) errors even
    # when the WHEN condition would skip the ELSE branch. Guard with GREATEST.
    # Pattern A (reverted DOC): LN(1 + col) → LN(GREATEST(1 + col, 1e-10))
    # Pattern B (legacy COALESCE): LN(1 + COALESCE(col, 0)) → LN(GREATEST(1 + COALESCE(col, 0), 1e-10))
    # This is a DuckDB evaluation-order workaround; production keeps its CASE/NULL semantics.
    result = re.sub(
        r"LN\(1\s*\+\s*COALESCE\((\w+),\s*0\)\)",
        r"LN(GREATEST(1 + COALESCE(\1, 0), 1e-10))",
        result,
        flags=re.IGNORECASE,
    )
    result = re.sub(
        r"LN\(1\s*\+\s*(\w+)\)",
        r"LN(GREATEST(1 + \1, 1e-10))",
        result,
        flags=re.IGNORECASE,
    )

    return result


def list_views() -> list[str]:
    """List all view names defined in the DDL document."""
    content = _DDL_PATH.read_text(encoding="utf-8")
    return re.findall(r"^## (serve_\w+)", content, re.MULTILINE)