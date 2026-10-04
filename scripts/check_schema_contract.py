#!/usr/bin/env python3
"""scripts/check_schema_contract.py — live schema drift detector.

DESCRIBEs each table in the warehouse and diffs against the column contract
in ``db/schema_contract.py``.  Non-zero exit on drift.

Usage:
    python3 scripts/check_schema_contract.py [--catalog CATALOG] [--schema SCHEMA]
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import FrozenSet

# Ensure repo root is on sys.path so `db` and other top-level packages resolve
# when invoked as ``python3 scripts/check_schema_contract.py``.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from db.schema_contract import TABLE_COLUMNS


def _get_warehouse_columns(fqn_table: str) -> FrozenSet[str]:
    """Run DESCRIBE and return the set of column names."""
    from db.delta_adapter import _warehouse_query

    rows = _warehouse_query(f"DESCRIBE {fqn_table}", limit=1000)
    return frozenset(r["col_name"] for r in rows if "col_name" in r)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check schema contract drift")
    parser.add_argument("--catalog", default=None, help="Override catalog")
    parser.add_argument("--schema", default=None, help="Override schema")
    args = parser.parse_args()

    from db.delta_adapter import CATALOG, SCHEMA

    catalog = args.catalog or CATALOG
    schema = args.schema or SCHEMA
    fqn = lambda t: f"{catalog}.{schema}.{t}"

    errors: list[str] = []
    warnings: list[str] = []

    for table, expected_cols in TABLE_COLUMNS.items():
        full_name = fqn(table)
        try:
            live_cols = _get_warehouse_columns(full_name)
        except Exception as exc:
            errors.append(f"DESCRIBE {full_name} failed: {type(exc).__name__}: {exc}")
            continue

        missing_in_live = expected_cols - live_cols
        extra_in_live = live_cols - expected_cols

        if missing_in_live:
            errors.append(
                f"{full_name}: contract columns missing from live table: {sorted(missing_in_live)}"
            )
        if extra_in_live:
            warnings.append(
                f"{full_name}: extra columns in live table (not in contract): {sorted(extra_in_live)}"
            )
        if not missing_in_live and not extra_in_live:
            print(f"OK  {full_name}: {len(expected_cols)} columns match")

    if warnings:
        print("\nWARNINGS (non-blocking):")
        for w in warnings:
            print(f"  ⚠  {w}")

    if errors:
        print("\nDRIFT DETECTED (blocking):")
        for e in errors:
            print(f"  ✗  {e}")
        return 1

    print("\nAll tables match the schema contract.")
    return 0


if __name__ == "__main__":
    sys.exit(main())