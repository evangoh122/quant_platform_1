#!/usr/bin/env python3
"""pipelines/build_sec_knowledge_graph.py — Databricks Delta build for SEC KG.

Provides build(spark, *, catalog, schema, ...) and CLI entry point.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sec_kg.build import build_graph
from sec_kg.model import BUILD_VERSION


def build(
    spark,
    *,
    catalog: str,
    schema: str,
    enable_llm_extraction: bool = False,
    llm_budget: int = 0,
) -> None:
    """Build SEC knowledge graph Delta tables.

    Args:
        spark: SparkSession
        catalog: Unity Catalog name
        schema: Schema name
        enable_llm_extraction: whether to run LLM enrichment
        llm_budget: max LLM calls (0=disabled)
    """
    from pyspark.sql import functions as F
    from pyspark.sql.types import (
        ArrayType, DoubleType, LongType, StringType, StructField,
        StructType, TimestampType,
    )

    # Read source tables
    entities_df = spark.table(f"{catalog}.{schema}.silver_sec_entities")
    sections_df = spark.table(f"{catalog}.{schema}.silver_sec_sections")

    # Collect chunk metadata for corpus
    chunk_metadata = {}
    for row in sections_df.select(
        "chunk_id", "ticker", "accession_number", "form_type",
        "accepted_ts", "filing_section", "chunk_index"
    ).collect():
        chunk_metadata[row.chunk_id] = {
            "chunk_id": row.chunk_id,
            "ticker": row.ticker,
            "accession_number": row.accession_number,
            "form_type": row.form_type,
            "accepted_epoch": int(row.accepted_ts.timestamp()) if row.accepted_ts else None,
            "filing_section": row.filing_section,
            "chunk_index": row.chunk_index,
            "chunk_text": "",  # Not needed for build
        }

    # Convert entities to list of dicts
    entities = []
    for row in entities_df.collect():
        entities.append({
            "cik": row.cik,
            "ticker": row.ticker,
            "accession_number": row.accession_number,
            "form_type": row.form_type,
            "accepted_epoch": int(row.accepted_ts.timestamp()) if row.accepted_ts else None,
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
    nodes, edges = build_graph(entities, chunk_metadata, BUILD_VERSION)

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
        nodes_data.append((
            node.node_id, node.node_type, node.label,
            node.properties_json, prov_list, node.build_version,
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

    # Create tables if not exist
    spark.sql(f"""
        CREATE TABLE IF NOT EXISTS {nodes_table} (
            node_id STRING NOT NULL,
            node_type STRING NOT NULL,
            label STRING NOT NULL,
            properties_json STRING NOT NULL,
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

    # Idempotent MERGE by ID
    from delta.tables import DeltaTable

    # Merge nodes
    existing_nodes = DeltaTable.forName(spark, nodes_table)
    existing_nodes.alias("target").merge(
        nodes_df.alias("source"),
        "target.node_id = source.node_id"
    ).whenMatchedUpdateAll().whenNotMatchedInsertAll().execute()

    # Merge edges
    existing_edges = DeltaTable.forName(spark, edges_table)
    existing_edges.alias("target").merge(
        edges_df.alias("source"),
        "target.edge_id = source.edge_id"
    ).whenMatchedUpdateAll().whenNotMatchedInsertAll().execute()

    print(f"Build complete: {len(nodes)} nodes, {len(edges)} edges")
    print(f"  Tables: {nodes_table}, {edges_table}")


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
    from pyspark.sql import SparkSession

    spark = SparkSession.builder.getOrCreate()

    build(
        spark,
        catalog=args.catalog,
        schema=args.schema,
        enable_llm_extraction=args.enable_llm_extraction,
        llm_budget=args.llm_budget,
    )


if __name__ == "__main__":
    main()