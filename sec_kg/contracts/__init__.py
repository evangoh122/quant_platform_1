"""sec_kg/contracts — KG-A executable contracts (pure Python, no Spark).

The modules in this package encode the parts of the knowledge-graph design of
record (``KG_DATA_MODEL_v2`` -> ``v3`` -> ``v4``) that are testable without a
warehouse:

``identity``     stable entity ids, v1/v2 encoders, collisions, aliases, migration
``temporal``     immutable correction events with derived system intervals
``facts``        series/assertion/observation keys, reconciliation, linking
``registry``     typed join contracts and the edge contract registry
``publication``  generation manifest and compare-and-swap publication
``names``        SEC-submissions company-name precedence
``filings``      accession de-duplication of bronze filing rows

Nothing here imports pandas, DuckDB, Spark, Databricks or the network.
"""
from __future__ import annotations

from sec_kg.contracts import (
    facts,
    filings,
    identity,
    names,
    publication,
    registry,
    temporal,
)

__all__ = [
    "facts",
    "filings",
    "identity",
    "names",
    "publication",
    "registry",
    "temporal",
]
