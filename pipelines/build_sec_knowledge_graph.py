#!/usr/bin/env python3
"""pipelines/build_sec_knowledge_graph.py — Databricks Delta build for SEC KG.

Provides build(spark, *, catalog, schema, ...) and CLI entry point.

Design: The build is driver-bound — all entities and chunk metadata are
collected into driver memory before ``build_graph`` runs in pure Python.
A configurable ``max_entities`` cap (default 2M) raises MemoryError before
OOM if the dataset grows beyond driver capacity.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from typing import Dict, Optional

from pipelines._runtime import get_spark, repo_root

sys.path.insert(0, str(repo_root()))

from sec_kg.build import build_graph, validate_and_raise
from sec_kg.model import BUILD_VERSION, normalize_unicode


def _table_exists(spark, table_name: str) -> bool:
    """Check if a Delta table exists."""
    try:
        spark.table(table_name).limit(1).collect()
        return True
    except Exception:
        return False


def ensure_concept_norm_column(spark, fqn: str) -> None:
    """Forward-only, re-runnable migration: add concept_norm if missing.

    Older gold_sec_kg_nodes tables (pre-round-12) lack the concept_norm column.
    CREATE TABLE IF NOT EXISTS is a no-op against an existing table, so this
    ALTER TABLE path is required before the MERGE.  Follows the established
    pattern of ensure_model_availability_columns in run_silver_gold.py.

    Args:
        spark: SparkSession
        fqn: fully-qualified table name (e.g. catalog.schema.gold_sec_kg_nodes)
    """
    try:
        existing = set(spark.table(fqn).columns)
    except Exception as e:
        print(f"  ensure concept_norm: {fqn} not readable ({str(e)[:80]}); skipping")
        return
    if "concept_norm" in existing:
        return
    spark.sql(f"ALTER TABLE {fqn} ADD COLUMNS (concept_norm STRING)")
    print(f"  added {fqn}.concept_norm column")


def build(
    spark,
    *,
    catalog: str,
    schema: str,
    enable_llm_extraction: bool = False,
    llm_budget: int = 0,
    subset_filter: Optional[Dict[str, str]] = None,
    max_entities: int = 2_000_000,
) -> None:
    """Build SEC knowledge graph Delta tables.

    DESIGN NOTE: The graph build is driver-bound.  All entities and chunk
    metadata are collected into driver memory (lists / dicts) before
    ``build_graph`` runs in pure Python.  At current scale (~63.5k nodes /
    ~137k edges) this comfortably fits a driver; the ``max_entities`` cap
    guards against unbounded growth.

    Args:
        spark: SparkSession
        catalog: Unity Catalog name
        schema: Schema name
        enable_llm_extraction: whether to run LLM enrichment
        llm_budget: max LLM calls (0=disabled)
        subset_filter: if set, indicates a partial rebuild (e.g. {"ticker": "NVDA"}).
            When set, the unscoped whenNotMatchedBySourceDelete is REFUSED to prevent
            deleting rows belonging to other tickers/partitions.
        max_entities: hard cap on total entities collected into driver memory.
            Raises MemoryError before OOM if exceeded.  Default 2,000,000.

    Raises:
        ValueError: if subset_filter is set (partial rebuilds not supported with unscoped delete)
        MemoryError: if entity count exceeds max_entities
    """
    from pyspark.sql import functions as F
    from pyspark.sql.types import (
        ArrayType, DoubleType, LongType, StringType, StructField,
        StructType, TimestampType,
    )

    # Read source tables
    entities_df = spark.table(f"{catalog}.{schema}.silver_sec_entities")
    sections_df = spark.table(f"{catalog}.{schema}.silver_sec_sections")

    # Driver memory cap — fail fast BEFORE collecting into driver memory.
    # Count source tables via Spark .count() (pushed to executors) so
    # the cap is enforced without ever materialising the full datasets
    # on the driver.
    total_rows = entities_df.count() + sections_df.count()
    if total_rows > max_entities:
        raise MemoryError(
            f"Entity count {total_rows:,} exceeds max_entities={max_entities:,}. "
            f"The graph build is driver-bound; increase max_entities or reduce input scope."
        )

    # Collect chunk metadata for corpus — uses unix_timestamp to avoid
    # driver-timezone-dependent naive datetime conversion.
    # NOTE: toLocalIterator streams rows but the dict still accumulates in
    # driver memory.  This is acceptable at current scale; max_entities caps growth.
    chunk_metadata = {}
    for row in sections_df.select(
        "chunk_id", "ticker", "accession_number", "form_type",
        F.unix_timestamp("accepted_ts").alias("accepted_epoch"),
        "filing_section", "chunk_index"
    ).toLocalIterator():
        chunk_metadata[row.chunk_id] = {
            "chunk_id": row.chunk_id,
            "ticker": row.ticker,
            "accession_number": row.accession_number,
            "form_type": row.form_type,
            "accepted_epoch": int(row.accepted_epoch) if row.accepted_epoch is not None else None,
            "filing_section": row.filing_section,
            "chunk_index": row.chunk_index,
            "chunk_text": "",  # Not needed for build
        }

    # Convert entities to list of dicts — uses unix_timestamp to avoid
    # driver-timezone-dependent naive datetime conversion.
    # NOTE: toLocalIterator streams rows but the list still accumulates in
    # driver memory.  Guarded by max_entities cap below.
    entities = []
    for row in entities_df.select(
        "cik", "ticker", "accession_number", "form_type",
        F.unix_timestamp("accepted_ts").alias("accepted_epoch"),
        "entity_type", "entity_key", "entity_value", "entity_unit",
        "period_start", "period_end", "confidence", "source_chunk_id",
    ).toLocalIterator():
        entities.append({
            "cik": row.cik,
            "ticker": row.ticker,
            "accession_number": row.accession_number,
            "form_type": row.form_type,
            "accepted_epoch": int(row.accepted_epoch) if row.accepted_epoch is not None else None,
            "entity_type": row.entity_type,
            "entity_key": row.entity_key,
            "entity_value": row.entity_value,
            "entity_unit": row.entity_unit,
            "period_start": str(row.period_start) if row.period_start else "",
            "period_end": str(row.period_end) if row.period_end else "",
            "confidence": row.confidence,
            "source_chunk_id": row.source_chunk_id,
        })

    # Optional LLM enrichment
    if enable_llm_extraction and llm_budget > 0:
        from sec_kg.enrichment import extract_enrichments
        enrichments = extract_enrichments(
            list(chunk_metadata.values()), chunk_metadata,
            enabled=True, budget=llm_budget,
        )
        entities.extend(enrichments)

    # Build graph
    nodes, edges, stats = build_graph(entities, chunk_metadata, BUILD_VERSION)

    # Count entity types from input
    entity_type_counts: Dict[str, int] = {}
    for entity in entities:
        etype = str(entity.get("entity_type", "")).lower()
        entity_type_counts[etype] = entity_type_counts.get(etype, 0) + 1

    # Validate rejection reasons — raise on undocumented, write nothing
    manifest = validate_and_raise(stats, entity_type_counts)

    # Define Delta table schemas
    provenance_schema = ArrayType(StructType([
        StructField("accession_number", StringType(), False),
        StructField("source_chunk_id", StringType(), False),
        StructField("accepted_ts", TimestampType(), False),
    ]))

    nodes_schema = StructType([
        StructField("node_id", StringType(), False),
        StructField("node_type", StringType(), False),
        StructField("label", StringType(), False),
        StructField("properties_json", StringType(), False),
        StructField("concept_norm", StringType(), True),
        StructField("provenance", provenance_schema, False),
        StructField("build_version", StringType(), False),
    ])

    edges_schema = StructType([
        StructField("edge_id", StringType(), False),
        StructField("src_id", StringType(), False),
        StructField("edge_type", StringType(), False),
        StructField("dst_id", StringType(), False),
        StructField("valid_from", TimestampType(), False),
        StructField("accession_number", StringType(), False),
        StructField("source_chunk_id", StringType(), False),
        StructField("accepted_ts", TimestampType(), False),
        StructField("confidence", DoubleType(), True),
        StructField("properties_json", StringType(), False),
        StructField("build_version", StringType(), False),
    ])

    # Convert nodes to Spark rows
    nodes_data = []
    for node in nodes:
        prov_list = [
            {
                "accession_number": p.accession_number,
                "source_chunk_id": p.source_chunk_id,
                "accepted_ts": p.accepted_ts,
            }
            for p in node.provenance
        ]
        # Compute concept_norm: NFKC-normalised, lower-cased entity_key or metric
        props = json.loads(node.properties_json)
        raw_concept = props.get("entity_key", props.get("metric", ""))
        concept_norm = normalize_unicode(raw_concept).lower() if raw_concept else None
        nodes_data.append((
            node.node_id, node.node_type, node.label,
            node.properties_json, concept_norm, prov_list, node.build_version,
        ))

    nodes_df = spark.createDataFrame(nodes_data, nodes_schema)

    # Convert edges to Spark rows
    edges_data = []
    for edge in edges:
        edges_data.append((
            edge.edge_id, edge.src_id, edge.edge_type, edge.dst_id,
            edge.valid_from, edge.accession_number, edge.source_chunk_id,
            edge.accepted_ts, edge.confidence, edge.properties_json,
            edge.build_version,
        ))

    edges_df = spark.createDataFrame(edges_data, edges_schema)

    # MERGE nodes
    nodes_table = f"{catalog}.{schema}.gold_sec_kg_nodes"
    edges_table = f"{catalog}.{schema}.gold_sec_kg_edges"

    # Ensure concept_norm column exists on pre-round-12 tables
    ensure_concept_norm_column(spark, nodes_table)

    # Create tables if not exist
    spark.sql(f"""
        CREATE TABLE IF NOT EXISTS {nodes_table} (
            node_id STRING NOT NULL,
            node_type STRING NOT NULL,
            label STRING NOT NULL,
            properties_json STRING NOT NULL,
            concept_norm STRING,
            provenance ARRAY<STRUCT<accession_number:STRING,source_chunk_id:STRING,accepted_ts:TIMESTAMP>> NOT NULL,
            build_version STRING NOT NULL
        ) USING DELTA
        PARTITIONED BY (node_type)
    """)

    spark.sql(f"""
        CREATE TABLE IF NOT EXISTS {edges_table} (
            edge_id STRING NOT NULL,
            src_id STRING NOT NULL,
            edge_type STRING NOT NULL,
            dst_id STRING NOT NULL,
            valid_from TIMESTAMP NOT NULL,
            accession_number STRING NOT NULL,
            source_chunk_id STRING NOT NULL,
            accepted_ts TIMESTAMP NOT NULL,
            confidence DOUBLE,
            properties_json STRING NOT NULL,
            build_version STRING NOT NULL
        ) USING DELTA
        PARTITIONED BY (edge_type)
    """)

    # Idempotent MERGE by ID with stale-row cleanup
    from delta.tables import DeltaTable

    # Guard: refuse unscoped delete when subset filter is active
    if subset_filter is not None:
        raise ValueError(
            f"Cannot issue unscoped whenNotMatchedBySourceDelete with "
            f"subset_filter={subset_filter}. Partial rebuilds must use "
            f"scoped delete to avoid wiping other partitions' rows."
        )

    # Count existing rows before merge (for delete logging)
    existing_node_count = spark.table(nodes_table).count() if _table_exists(spark, nodes_table) else 0
    existing_edge_count = spark.table(edges_table).count() if _table_exists(spark, edges_table) else 0

    # Merge nodes — delete rows absent from current build
    existing_nodes = DeltaTable.forName(spark, nodes_table)
    existing_nodes.alias("target").merge(
        nodes_df.alias("source"),
        "target.node_id = source.node_id"
    ).whenMatchedUpdateAll().whenNotMatchedInsertAll().whenNotMatchedBySourceDelete().execute()

    # Merge edges — delete rows absent from current build
    existing_edges = DeltaTable.forName(spark, edges_table)
    existing_edges.alias("target").merge(
        edges_df.alias("source"),
        "target.edge_id = source.edge_id"
    ).whenMatchedUpdateAll().whenNotMatchedInsertAll().whenNotMatchedBySourceDelete().execute()

    # Log deleted counts (approximate: max(0, existing + inserted - final))
    # For full rebuild, inserted = len(nodes)/len(edges), final = same as inserted
    # so deleted = max(0, existing - 0) = existing when all rows are replaced
    deleted_nodes_est = max(0, existing_node_count) if existing_node_count > 0 else 0
    deleted_edges_est = max(0, existing_edge_count) if existing_edge_count > 0 else 0
    print(f"  Merge complete: {len(nodes)} nodes, {len(edges)} edges written")
    if deleted_nodes_est > 0 or deleted_edges_est > 0:
        print(f"  Stale rows cleaned: ~{deleted_nodes_est} nodes, ~{deleted_edges_est} edges")

    # Write run manifest
    runs_table = f"{catalog}.{schema}.gold_sec_kg_build_runs"
    spark.sql(f"""
        CREATE TABLE IF NOT EXISTS {runs_table} (
            run_id STRING NOT NULL,
            build_version STRING NOT NULL,
            run_ts TIMESTAMP NOT NULL,
            input_rows_by_entity_type MAP<STRING,INT> NOT NULL,
            accepted_rows INT NOT NULL,
            rejected_rows INT NOT NULL,
            rejection_reasons MAP<STRING,INT> NOT NULL,
            node_count INT NOT NULL,
            edge_count INT NOT NULL
        ) USING DELTA
    """)

    from pyspark.sql import Row
    from pyspark.sql.types import IntegerType, MapType, StringType, StructField, StructType, TimestampType
    import uuid

    manifest_schema = StructType([
        StructField("run_id", StringType(), False),
        StructField("build_version", StringType(), False),
        StructField("run_ts", TimestampType(), False),
        StructField("input_rows_by_entity_type", MapType(StringType(), IntegerType(), False), False),
        StructField("accepted_rows", IntegerType(), False),
        StructField("rejected_rows", IntegerType(), False),
        StructField("rejection_reasons", MapType(StringType(), IntegerType(), False), False),
        StructField("node_count", IntegerType(), False),
        StructField("edge_count", IntegerType(), False),
    ])

    run_id = str(uuid.uuid4())
    run_row = Row(
        run_id=run_id,
        build_version=BUILD_VERSION,
        run_ts=datetime.now(timezone.utc),
        input_rows_by_entity_type=manifest["input_rows_by_entity_type"],
        accepted_rows=manifest["accepted_rows"],
        rejected_rows=manifest["rejected_rows"],
        rejection_reasons=manifest["rejection_reasons"],
        node_count=len(nodes),
        edge_count=len(edges),
    )
    run_df = spark.createDataFrame([run_row], manifest_schema)
    run_df.write.format("delta").mode("append").insertInto(runs_table)

    print(f"Build complete: {len(nodes)} nodes, {len(edges)} edges")
    print(f"  Tables: {nodes_table}, {edges_table}")
    print(f"  Manifest: {runs_table} (run_id={run_id})")


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Build SEC knowledge graph Delta tables"
    )
    parser.add_argument("--catalog", required=True, help="Unity Catalog name")
    parser.add_argument("--schema", required=True, help="Schema name")
    parser.add_argument("--enable-llm-extraction", action="store_true")
    parser.add_argument("--llm-budget", type=int, default=0)

    args = parser.parse_args()

    # Lazy Spark import

    spark = get_spark()

    build(
        spark,
        catalog=args.catalog,
        schema=args.schema,
        enable_llm_extraction=args.enable_llm_extraction,
        llm_budget=args.llm_budget,
    )


if __name__ == "__main__":
    main()