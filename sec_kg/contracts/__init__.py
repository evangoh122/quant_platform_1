"""sec_kg/contracts — KG-A executable contracts (pure Python, no Spark).

The modules in this package encode the parts of the knowledge-graph design of
record (``KG_DATA_MODEL_v2`` -> ``v3`` -> ``v4``) that are testable without a
warehouse:

``identity``     stable entity ids, v1/v2 encoders, collisions, aliases, migration
``temporal``     immutable correction events with derived system intervals
``names``        SEC-submissions company-name precedence
``filings``      accession de-duplication of bronze filing rows

Nothing here imports pandas, DuckDB, Spark, Databricks or the network.
"""
from __future__ import annotations

from sec_kg.contracts import (
    filings,
    identity,
    names,
    temporal,
)

__all__ = [
    "filings",
    "identity",
    "names",
    "temporal",
]
