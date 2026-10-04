#!/usr/bin/env python3
"""scripts/build_sec_knowledge_graph.py — Offline CLI for SEC KG build.

Usage:
    python scripts/build_sec_knowledge_graph.py \
        --entities evals/data/sec_entities.jsonl \
        --corpus evals/data/sec_corpus.jsonl \
        --output-dir /tmp/sec-kg-output \
        --format jsonl \
        --as-of 2024-01-01T00:00:00Z
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sec_kg.build import build_graph, validate_and_raise
from sec_kg.model import BUILD_VERSION, ensure_utc


def sha256_file(path: str) -> str:
    """Compute SHA-256 of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(
        description="Build SEC knowledge graph from entity and corpus files"
    )
    parser.add_argument("--entities", required=True,
                        help="Path to sec_entities.jsonl")
    parser.add_argument("--corpus", required=True,
                        help="Path to sec_corpus.jsonl")
    parser.add_argument("--output-dir", required=True,
                        help="Output directory for graph files")
    parser.add_argument("--format", choices=["jsonl", "parquet", "both"],
                        default="jsonl",
                        help="Output format (default: jsonl)")
    parser.add_argument("--as-of",
                        help="Point-in-time filter (ISO 8601)")
    parser.add_argument("--enable-llm-extraction", action="store_true",
                        help="Enable LLM-based enrichment extraction")
    parser.add_argument("--llm-budget", type=int, default=0,
                        help="Maximum LLM calls for enrichment (0=disabled)")

    args = parser.parse_args()

    # Validate inputs
    if not os.path.exists(args.entities):
        print(f"Error: entities file not found: {args.entities}", file=sys.stderr)
        sys.exit(1)
    if not os.path.exists(args.corpus):
        print(f"Error: corpus file not found: {args.corpus}", file=sys.stderr)
        sys.exit(1)

    # Parse as_of
    as_of = None
    if args.as_of:
        as_of = ensure_utc(datetime.fromisoformat(args.as_of))

    # Check parquet availability
    if args.format in ("parquet", "both"):
        try:
            import pyarrow  # noqa: F401
        except ImportError:
            print(
                "Error: pyarrow is required for parquet output. "
                "Install it with: pip install pyarrow",
                file=sys.stderr,
            )
            sys.exit(1)

    # Load inputs
    print(f"Loading entities from {args.entities}...")
    entities = []
    with open(args.entities, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entities.append(json.loads(line))
    print(f"  Loaded {len(entities)} entity rows")

    print(f"Loading corpus from {args.corpus}...")
    corpus = {}
    with open(args.corpus, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                chunk = json.loads(line)
                corpus[chunk["chunk_id"]] = chunk
    print(f"  Loaded {len(corpus)} corpus chunks")

    # Compute input hashes
    entities_hash = sha256_file(args.entities)
    corpus_hash = sha256_file(args.corpus)

    # Optional LLM enrichment
    if args.enable_llm_extraction and args.llm_budget > 0:
        print(f"LLM enrichment enabled with budget={args.llm_budget}")
        from sec_kg.enrichment import extract_enrichments
        enrichment_chunks = list(corpus.values())
        enrichments = extract_enrichments(
            enrichment_chunks, corpus,
            enabled=True, budget=args.llm_budget,
        )
        entities.extend(enrichments)
        print(f"  Added {len(enrichments)} enrichment entities")

    # Build graph
    print("Building knowledge graph...")
    start_time = time.time()
    nodes, edges, stats = build_graph(entities, corpus, BUILD_VERSION)
    build_time = time.time() - start_time
    print(f"  Built {len(nodes)} nodes, {len(edges)} edges in {build_time:.2f}s")

    # Count entity types from input
    entity_type_counts: Dict[str, int] = {}
    for entity in entities:
        etype = str(entity.get("entity_type", "")).lower()
        entity_type_counts[etype] = entity_type_counts.get(etype, 0) + 1

    # Validate rejection reasons — raise on undocumented, write nothing
    try:
        manifest = validate_and_raise(stats, entity_type_counts)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    # Create output directory
    os.makedirs(args.output_dir, exist_ok=True)

    # Write outputs atomically
    def write_jsonl_atomic(path: str, items: list) -> str:
        """Write JSONL atomically via temp file + rename."""
        data = "\n".join(
            json.dumps(item.to_dict(), sort_keys=True) for item in items
        ) + "\n"
        data_bytes = data.encode("utf-8")

        # Write to temp file first
        fd, tmp_path = tempfile.mkstemp(
            dir=os.path.dirname(path), suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(data)
            # Atomic rename
            if os.name == "nt":
                # Windows: remove target first
                if os.path.exists(path):
                    os.remove(path)
            os.rename(tmp_path, path)
        except Exception:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise

        return sha256_bytes(data_bytes)

    # Write nodes
    nodes_path = os.path.join(args.output_dir, "gold_sec_kg_nodes.jsonl")
    nodes_hash = write_jsonl_atomic(nodes_path, nodes)
    print(f"  Wrote {nodes_path} ({len(nodes)} rows, sha256={nodes_hash[:16]}...)")

    # Write edges
    edges_path = os.path.join(args.output_dir, "gold_sec_kg_edges.jsonl")
    edges_hash = write_jsonl_atomic(edges_path, edges)
    print(f"  Wrote {edges_path} ({len(edges)} rows, sha256={edges_hash[:16]}...)")

    # Write manifest (merge shared manifest with offline-specific fields)
    manifest.update({
        "build_version": BUILD_VERSION,
        "build_timestamp": datetime.now(timezone.utc).isoformat(),
        "input_entities_hash": entities_hash,
        "input_corpus_hash": corpus_hash,
        "output_nodes_hash": nodes_hash,
        "output_edges_hash": edges_hash,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "extraction_mode": "llm" if args.enable_llm_extraction else "deterministic",
        "extraction_budget": args.llm_budget,
        "extraction_used": args.enable_llm_extraction and args.llm_budget > 0,
        "as_of": args.as_of,
        "format": args.format,
    })

    manifest_path = os.path.join(args.output_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
    print(f"  Wrote {manifest_path}")

    # Parquet output
    if args.format in ("parquet", "both"):
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq

            # Convert nodes to parquet
            nodes_data = [n.to_dict() for n in nodes]
            nodes_table = pa.Table.from_pylist(nodes_data)
            nodes_parquet_path = os.path.join(
                args.output_dir, "gold_sec_kg_nodes.parquet"
            )
            pq.write_table(nodes_table, nodes_parquet_path)
            print(f"  Wrote {nodes_parquet_path}")

            # Convert edges to parquet
            edges_data = [e.to_dict() for e in edges]
            edges_table = pa.Table.from_pylist(edges_data)
            edges_parquet_path = os.path.join(
                args.output_dir, "gold_sec_kg_edges.parquet"
            )
            pq.write_table(edges_table, edges_parquet_path)
            print(f"  Wrote {edges_parquet_path}")
        except ImportError:
            print(
                "Warning: pyarrow not available, skipping parquet output",
                file=sys.stderr,
            )

    print(f"\nBuild complete in {build_time:.2f}s")
    print(f"  Nodes: {len(nodes)}, Edges: {len(edges)}")
    print(f"  Output: {args.output_dir}")


if __name__ == "__main__":
    main()