"""api/services/sec_knowledge_graph.py — Pure-Python query API for SEC KG.

Provides SecKnowledgeGraph facade over a store protocol, with
JsonlGraphStore for offline/tests and lazily imported SparkGraphStore for Delta.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Protocol, Sequence, Tuple

from sec_kg.model import (
    EDGE_TYPES,
    NODE_TYPES,
    KgEdge,
    KgNode,
    Provenance,
    ensure_utc,
    normalize_cik,
    normalize_ticker,
    normalize_unicode,
    parse_period,
)


# ── Store protocol ──────────────────────────────────────────────────────────

class GraphStore(Protocol):
    """Abstract graph store interface."""
    def iter_nodes(self) -> List[KgNode]: ...
    def iter_edges(self) -> List[KgEdge]: ...
    def get_node(self, node_id: str) -> Optional[KgNode]: ...
    def get_edges_for_node(self, node_id: str, edge_types: Optional[List[str]] = None,
                           as_of: Optional[datetime] = None) -> List[KgEdge]: ...
    def find_nodes(
        self,
        node_type: str,
        cik: Optional[str] = None,
        ticker: Optional[str] = None,
        concept: Optional[str] = None,
        period_start: Optional[str] = None,
        period_end: Optional[str] = None,
        accepted_before: Optional[datetime] = None,
        limit: int = 10000,
    ) -> List[KgNode]: ...
    def find_edges_by_node_ids(
        self,
        node_ids: set,
        edge_types: Optional[List[str]] = None,
        as_of: Optional[datetime] = None,
        limit: int = 100000,
    ) -> List[KgEdge]: ...


# ── JSONL store (offline / tests) ───────────────────────────────────────────

class JsonlGraphStore:
    """Dependency-free in-memory graph store for offline use and tests."""

    def __init__(self):
        self._nodes: Dict[str, KgNode] = {}
        self._edges: List[KgEdge] = []
        self._edges_by_src: Dict[str, List[KgEdge]] = {}
        self._edges_by_dst: Dict[str, List[KgEdge]] = {}

    def load_from_build(self, nodes: List[KgNode], edges: List[KgEdge]) -> None:
        """Load nodes and edges from build_graph output."""
        self._nodes = {n.node_id: n for n in nodes}
        self._edges = list(edges)
        self._edges_by_src = {}
        self._edges_by_dst = {}
        for edge in edges:
            self._edges_by_src.setdefault(edge.src_id, []).append(edge)
            self._edges_by_dst.setdefault(edge.dst_id, []).append(edge)

    def load_from_jsonl(self, nodes_path: str, edges_path: str) -> None:
        """Load from JSONL files."""
        self._nodes = {}
        self._edges = []
        self._edges_by_src = {}
        self._edges_by_dst = {}

        with open(nodes_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                data = json.loads(line)
                prov_data = data.get("provenance", [])
                provenance = tuple(
                    Provenance(
                        accession_number=p["accession_number"],
                        source_chunk_id=p["source_chunk_id"],
                        accepted_ts=datetime.fromisoformat(p["accepted_ts"]),
                    )
                    for p in prov_data
                )
                node = KgNode(
                    node_id=data["node_id"],
                    node_type=data["node_type"],
                    label=data["label"],
                    properties_json=data["properties_json"],
                    provenance=provenance,
                    build_version=data["build_version"],
                )
                self._nodes[node.node_id] = node

        with open(edges_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                data = json.loads(line)
                edge = KgEdge(
                    edge_id=data["edge_id"],
                    src_id=data["src_id"],
                    edge_type=data["edge_type"],
                    dst_id=data["dst_id"],
                    valid_from=datetime.fromisoformat(data["valid_from"]),
                    accession_number=data["accession_number"],
                    source_chunk_id=data["source_chunk_id"],
                    accepted_ts=datetime.fromisoformat(data["accepted_ts"]),
                    confidence=data.get("confidence"),
                    properties_json=data["properties_json"],
                    build_version=data["build_version"],
                )
                self._edges.append(edge)
                self._edges_by_src.setdefault(edge.src_id, []).append(edge)
                self._edges_by_dst.setdefault(edge.dst_id, []).append(edge)

    def iter_nodes(self) -> List[KgNode]:
        return list(self._nodes.values())

    def iter_edges(self) -> List[KgEdge]:
        return list(self._edges)

    def get_node(self, node_id: str) -> Optional[KgNode]:
        return self._nodes.get(node_id)

    def get_edges_for_node(
        self,
        node_id: str,
        edge_types: Optional[List[str]] = None,
        as_of: Optional[datetime] = None,
    ) -> List[KgEdge]:
        """Get edges where node_id is src or dst, filtered by type and PIT."""
        if as_of is not None:
            as_of = ensure_utc(as_of)

        results = []
        for edge in self._edges_by_src.get(node_id, []):
            if edge_types and edge.edge_type not in edge_types:
                continue
            if as_of is not None and edge.valid_from > as_of:
                continue
            results.append(edge)
        for edge in self._edges_by_dst.get(node_id, []):
            if edge_types and edge.edge_type not in edge_types:
                continue
            if as_of is not None and edge.valid_from > as_of:
                continue
            results.append(edge)
        return results

    def find_nodes(
        self,
        node_type: str,
        cik: Optional[str] = None,
        ticker: Optional[str] = None,
        concept: Optional[str] = None,
        period_start: Optional[str] = None,
        period_end: Optional[str] = None,
        accepted_before: Optional[datetime] = None,
        limit: int = 10000,
    ) -> List[KgNode]:
        """Find nodes filtered by type and properties. In-memory for JsonlGraphStore."""
        results = []
        for node in self._nodes.values():
            if node.node_type != node_type:
                continue
            props = json.loads(node.properties_json)
            if cik is not None and props.get("cik", "") != cik:
                continue
            if ticker is not None and props.get("ticker", "").upper() != ticker.upper():
                continue
            if concept is not None:
                node_concept = props.get("entity_key", props.get("metric", ""))
                if normalize_unicode(node_concept).lower() != normalize_unicode(concept).lower():
                    continue
            if period_start is not None and props.get("period_start", "") != period_start:
                continue
            if period_end is not None and props.get("period_end", "") != period_end:
                continue
            if accepted_before is not None:
                accepted_before = ensure_utc(accepted_before)
                has_eligible = any(p.accepted_ts <= accepted_before for p in node.provenance)
                if not has_eligible:
                    continue
            results.append(node)
            if len(results) >= limit:
                break
        return results

    def find_edges_by_node_ids(
        self,
        node_ids: set,
        edge_types: Optional[List[str]] = None,
        as_of: Optional[datetime] = None,
        limit: int = 100000,
    ) -> List[KgEdge]:
        """Find edges where src_id or dst_id is in node_ids. In-memory for JsonlGraphStore."""
        if as_of is not None:
            as_of = ensure_utc(as_of)
        results = []
        for edge in self._edges:
            if edge.src_id not in node_ids and edge.dst_id not in node_ids:
                continue
            if edge_types and edge.edge_type not in edge_types:
                continue
            if as_of is not None and edge.valid_from > as_of:
                continue
            results.append(edge)
            if len(results) >= limit:
                break
        return results


# ── SparkGraphStore (lazy, Delta-backed) ────────────────────────────────────

class SparkGraphStore:
    """Delta-backed graph store.  Lazily imports pyspark."""

    def __init__(self, catalog: str, schema: str):
        self._catalog = catalog
        self._schema = schema
        self._spark = None

    def _get_spark(self):
        if self._spark is None:
            from pyspark.sql import SparkSession
            self._spark = SparkSession.builder.getOrCreate()
        return self._spark

    def _nodes_table(self) -> str:
        return f"{self._catalog}.{self._schema}.gold_sec_kg_nodes"

    def _edges_table(self) -> str:
        return f"{self._catalog}.{self._schema}.gold_sec_kg_edges"

    def iter_nodes(self) -> List[KgNode]:
        from pyspark.sql import functions as F
        spark = self._get_spark()
        # Read epoch seconds to avoid tz-naive datetime from Spark.
        df = spark.table(self._nodes_table()).select(
            "node_id", "node_type", "label", "properties_json", "build_version",
            F.transform(
                F.col("provenance"),
                lambda p: F.struct(
                    p["accession_number"],
                    p["source_chunk_id"],
                    F.unix_timestamp(p["accepted_ts"]).alias("accepted_epoch"),
                ),
            ).alias("provenance"),
        )
        nodes = []
        # Use toLocalIterator to avoid driver-wide collect of whole table.
        for row in df.toLocalIterator():
            provenance = tuple(
                Provenance(
                    accession_number=p["accession_number"],
                    source_chunk_id=p["source_chunk_id"],
                    accepted_ts=datetime.fromtimestamp(
                        int(p["accepted_epoch"]), tz=timezone.utc
                    ),
                )
                for p in (row.provenance or [])
            )
            nodes.append(KgNode(
                node_id=row.node_id,
                node_type=row.node_type,
                label=row.label,
                properties_json=row.properties_json,
                provenance=provenance,
                build_version=row.build_version,
            ))
        return nodes

    def iter_edges(self) -> List[KgEdge]:
        from pyspark.sql import functions as F
        spark = self._get_spark()
        # Read epoch seconds to avoid tz-naive datetime from Spark.
        df = spark.table(self._edges_table()).select(
            "edge_id", "src_id", "edge_type", "dst_id",
            F.unix_timestamp(F.col("valid_from")).alias("valid_from_epoch"),
            "accession_number", "source_chunk_id",
            F.unix_timestamp(F.col("accepted_ts")).alias("accepted_epoch"),
            "confidence", "properties_json", "build_version",
        )
        edges = []
        # Use toLocalIterator to avoid driver-wide collect of whole table.
        for row in df.toLocalIterator():
            edges.append(KgEdge(
                edge_id=row.edge_id,
                src_id=row.src_id,
                edge_type=row.edge_type,
                dst_id=row.dst_id,
                valid_from=datetime.fromtimestamp(
                    int(row.valid_from_epoch), tz=timezone.utc
                ),
                accession_number=row.accession_number,
                source_chunk_id=row.source_chunk_id,
                accepted_ts=datetime.fromtimestamp(
                    int(row.accepted_epoch), tz=timezone.utc
                ),
                confidence=row.confidence,
                properties_json=row.properties_json,
                build_version=row.build_version,
            ))
        return edges

    def get_node(self, node_id: str) -> Optional[KgNode]:
        from pyspark.sql import functions as F
        spark = self._get_spark()
        # Read epoch seconds to avoid tz-naive datetime from Spark.
        df = spark.table(self._nodes_table()).select(
            "node_id", "node_type", "label", "properties_json", "build_version",
            F.transform(
                F.col("provenance"),
                lambda p: F.struct(
                    p["accession_number"],
                    p["source_chunk_id"],
                    F.unix_timestamp(p["accepted_ts"]).alias("accepted_epoch"),
                ),
            ).alias("provenance"),
        ).where(F.col("node_id") == node_id)
        rows = df.collect()
        if not rows:
            return None
        row = rows[0]
        provenance = tuple(
            Provenance(
                accession_number=p["accession_number"],
                source_chunk_id=p["source_chunk_id"],
                accepted_ts=datetime.fromtimestamp(
                    int(p["accepted_epoch"]), tz=timezone.utc
                ),
            )
            for p in (row.provenance or [])
        )
        return KgNode(
            node_id=row.node_id,
            node_type=row.node_type,
            label=row.label,
            properties_json=row.properties_json,
            provenance=provenance,
            build_version=row.build_version,
        )

    def get_edges_for_node(
        self,
        node_id: str,
        edge_types: Optional[List[str]] = None,
        as_of: Optional[datetime] = None,
    ) -> List[KgEdge]:
        from pyspark.sql import functions as F
        spark = self._get_spark()
        # Read epoch seconds to avoid tz-naive datetime from Spark.
        df = spark.table(self._edges_table()).select(
            "edge_id", "src_id", "edge_type", "dst_id",
            F.unix_timestamp(F.col("valid_from")).alias("valid_from_epoch"),
            "accession_number", "source_chunk_id",
            F.unix_timestamp(F.col("accepted_ts")).alias("accepted_epoch"),
            "confidence", "properties_json", "build_version",
        ).where(
            (F.col("src_id") == node_id) | (F.col("dst_id") == node_id)
        )
        if edge_types:
            df = df.where(F.col("edge_type").isin(edge_types))
        if as_of is not None:
            as_of = ensure_utc(as_of)
            # PIT filter using epoch seconds to match the read strategy
            as_of_epoch = int(as_of.timestamp())
            df = df.where(F.col("valid_from_epoch") <= as_of_epoch)

        edges = []
        for row in df.collect():
            edges.append(KgEdge(
                edge_id=row.edge_id,
                src_id=row.src_id,
                edge_type=row.edge_type,
                dst_id=row.dst_id,
                valid_from=datetime.fromtimestamp(
                    int(row.valid_from_epoch), tz=timezone.utc
                ),
                accession_number=row.accession_number,
                source_chunk_id=row.source_chunk_id,
                accepted_ts=datetime.fromtimestamp(
                    int(row.accepted_epoch), tz=timezone.utc
                ),
                confidence=row.confidence,
                properties_json=row.properties_json,
                build_version=row.build_version,
            ))
        return edges

    def find_nodes(
        self,
        node_type: str,
        cik: Optional[str] = None,
        ticker: Optional[str] = None,
        concept: Optional[str] = None,
        period_start: Optional[str] = None,
        period_end: Optional[str] = None,
        accepted_before: Optional[datetime] = None,
        limit: int = 10000,
    ) -> List[KgNode]:
        """Find nodes with Spark-side predicate pushdown and LIMIT.

        All filters use column expressions (no string-built SQL).
        A hard .limit(n) is applied BEFORE collecting.
        """
        from pyspark.sql import functions as F
        spark = self._get_spark()
        df = spark.table(self._nodes_table()).select(
            "node_id", "node_type", "label", "properties_json", "build_version",
            F.transform(
                F.col("provenance"),
                lambda p: F.struct(
                    p["accession_number"],
                    p["source_chunk_id"],
                    F.unix_timestamp(p["accepted_ts"]).alias("accepted_epoch"),
                ),
            ).alias("provenance"),
        )

        # Push predicates into Spark
        df = df.where(F.col("node_type") == node_type)

        if cik is not None:
            df = df.where(F.col("properties_json").contains(f'"cik":"{cik}"'))
        if ticker is not None:
            df = df.where(F.col("properties_json").contains(
                f'"ticker":"{ticker.upper()}"'
            ))
        if concept is not None:
            # Structured column equality on NFKC-normalised, lower-cased value.
            # Parity with JsonlGraphStore: compare normalised input to concept_norm column.
            norm_concept = normalize_unicode(concept).lower()
            df = df.where(F.col("concept_norm") == norm_concept)
        if period_start is not None:
            df = df.where(F.col("properties_json").contains(
                f'"period_start":"{period_start}"'
            ))
        if period_end is not None:
            df = df.where(F.col("properties_json").contains(
                f'"period_end":"{period_end}"'
            ))

        # PIT filter: push as-of predicate into Spark BEFORE limit so
        # ineligible rows never consume the limit budget.
        if accepted_before is not None:
            accepted_before = ensure_utc(accepted_before)
            as_of_epoch = int(accepted_before.timestamp())
            df = df.where(
                F.exists(
                    F.col("provenance"),
                    lambda p: p["accepted_epoch"] <= as_of_epoch,
                )
            )

        # Hard limit BEFORE collecting
        df = df.limit(limit)

        nodes = []
        for row in df.toLocalIterator():
            provenance = tuple(
                Provenance(
                    accession_number=p["accession_number"],
                    source_chunk_id=p["source_chunk_id"],
                    accepted_ts=datetime.fromtimestamp(
                        int(p["accepted_epoch"]), tz=timezone.utc
                    ),
                )
                for p in (row.provenance or [])
            )

            # Post-collect: keep only eligible provenance entries
            if accepted_before is not None:
                eligible = [p for p in provenance if p.accepted_ts <= accepted_before]
                if not eligible:
                    continue
                provenance = tuple(eligible)

            nodes.append(KgNode(
                node_id=row.node_id,
                node_type=row.node_type,
                label=row.label,
                properties_json=row.properties_json,
                provenance=provenance,
                build_version=row.build_version,
            ))
        return nodes

    def find_edges_by_node_ids(
        self,
        node_ids: set,
        edge_types: Optional[List[str]] = None,
        as_of: Optional[datetime] = None,
        limit: int = 100000,
    ) -> List[KgEdge]:
        """Find edges where src_id or dst_id is in node_ids.

        Uses bounded IN predicate in Spark.  Hard .limit(n) before collecting.
        """
        from pyspark.sql import functions as F
        if not node_ids:
            return []

        spark = self._get_spark()
        df = spark.table(self._edges_table()).select(
            "edge_id", "src_id", "edge_type", "dst_id",
            F.unix_timestamp(F.col("valid_from")).alias("valid_from_epoch"),
            "accession_number", "source_chunk_id",
            F.unix_timestamp(F.col("accepted_ts")).alias("accepted_epoch"),
            "confidence", "properties_json", "build_version",
        ).where(
            F.col("src_id").isin(list(node_ids)) | F.col("dst_id").isin(list(node_ids))
        )

        if edge_types:
            df = df.where(F.col("edge_type").isin(edge_types))
        if as_of is not None:
            as_of = ensure_utc(as_of)
            as_of_epoch = int(as_of.timestamp())
            df = df.where(F.col("valid_from_epoch") <= as_of_epoch)

        df = df.limit(limit)

        edges = []
        for row in df.toLocalIterator():
            edges.append(KgEdge(
                edge_id=row.edge_id,
                src_id=row.src_id,
                edge_type=row.edge_type,
                dst_id=row.dst_id,
                valid_from=datetime.fromtimestamp(
                    int(row.valid_from_epoch), tz=timezone.utc
                ),
                accession_number=row.accession_number,
                source_chunk_id=row.source_chunk_id,
                accepted_ts=datetime.fromtimestamp(
                    int(row.accepted_epoch), tz=timezone.utc
                ),
                confidence=row.confidence,
                properties_json=row.properties_json,
                build_version=row.build_version,
            ))
        return edges


# ── SecKnowledgeGraph facade ────────────────────────────────────────────────

class SecKnowledgeGraph:
    """Pure-Python query facade over a graph store."""

    def __init__(self, store: Any):
        self._store = store

    def _pit_filter_nodes(
        self, nodes: List[KgNode], as_of: datetime
    ) -> List[KgNode]:
        """Filter nodes whose provenance is entirely after as_of."""
        as_of = ensure_utc(as_of)
        result = []
        for node in nodes:
            has_eligible = any(p.accepted_ts <= as_of for p in node.provenance)
            if has_eligible:
                result.append(node)
        return result

    def _pit_filter_edges(
        self, edges: List[KgEdge], as_of: datetime
    ) -> List[KgEdge]:
        """Filter edges with valid_from <= as_of."""
        as_of = ensure_utc(as_of)
        return [e for e in edges if e.valid_from <= as_of]

    def get_fact(
        self,
        ticker: str,
        metric: str,
        period: str,
        as_of: datetime,
    ) -> Optional[Dict[str, Any]]:
        """Get the latest eligible XBRL fact as of the requested time.

        Returns dict with value_text, is_restatement, supersedes_fact_id,
        chunk_id, accession_number, accepted_ts, and all source provenance.
        """
        ticker = normalize_ticker(ticker)
        metric = normalize_unicode(metric)
        as_of = ensure_utc(as_of)
        period_start, period_end = parse_period(period)

        # Use filtered accessor — pushes node_type, ticker, period_end into Spark
        nodes = self._store.find_nodes(
            node_type="XbrlFact",
            ticker=ticker,
            concept=metric,
            period_end=period_end,
            period_start=period_start if period_start else None,
            accepted_before=as_of,
            limit=10000,
        )

        # Find matching XbrlFact nodes
        matching_facts = []
        for node in nodes:
            props = json.loads(node.properties_json)

            # PIT filter: at least one provenance <= as_of
            eligible_provs = [p for p in node.provenance if p.accepted_ts <= as_of]
            if not eligible_provs:
                continue

            # Get the latest provenance
            best_prov = max(eligible_provs, key=lambda p: p.accepted_ts)

            matching_facts.append({
                "node": node,
                "props": props,
                "best_prov": best_prov,
                "accepted_ts": best_prov.accepted_ts,
            })

        if not matching_facts:
            return None

        # Sort by accepted_ts, then accession, then node_id
        matching_facts.sort(
            key=lambda f: (f["accepted_ts"].isoformat(),
                           f["best_prov"].accession_number,
                           f["node"].node_id)
        )

        # Get the latest version
        latest = matching_facts[-1]

        # Check if this is a restatement (SUPERSEDES edge exists)
        supersedes_fact_id = None
        is_restatement = False
        for edge in self._pit_filter_edges(
            self._store.get_edges_for_node(latest["node"].node_id, ["SUPERSEDES"]),
            as_of
        ):
            if edge.src_id == latest["node"].node_id:
                is_restatement = True
                supersedes_fact_id = edge.dst_id

        # Collect all provenance
        all_provs = [
            {
                "accession_number": p.accession_number,
                "source_chunk_id": p.source_chunk_id,
                "accepted_ts": p.accepted_ts.isoformat(),
            }
            for p in latest["node"].provenance
            if p.accepted_ts <= as_of
        ]

        return {
            "fact_id": latest["node"].node_id,
            "value_text": latest["props"].get("value_text", ""),
            "decimal_value": latest["props"].get("decimal_value"),
            "unit": latest["props"].get("unit", ""),
            "period_start": latest["props"].get("period_start", ""),
            "period_end": latest["props"].get("period_end", ""),
            "period_type": latest["props"].get("period_type", ""),
            "is_restatement": is_restatement,
            "supersedes_fact_id": supersedes_fact_id,
            "chunk_id": latest["best_prov"].source_chunk_id,
            "accession_number": latest["best_prov"].accession_number,
            "accepted_ts": latest["best_prov"].accepted_ts.isoformat(),
            "citation_level": latest["props"].get("citation_level", "chunk"),
            "source_url": latest["props"].get("source_url", ""),
            "provenance": all_provs,
        }

    def facts_timeseries(
        self,
        ticker: str,
        metric: str,
        as_of: datetime,
    ) -> List[Dict[str, Any]]:
        """Get all facts for a ticker/metric up to as_of, ordered by time.

        After PIT filtering, keeps only the latest eligible version per
        series (cik, concept, period_start, period_end, unit) ordered by
        (accepted_ts, accession) — i.e. restatement selection.
        """
        ticker = normalize_ticker(ticker)
        metric = normalize_unicode(metric)
        as_of = ensure_utc(as_of)

        # Use filtered accessor — pushes node_type, ticker, concept into Spark
        nodes = self._store.find_nodes(
            node_type="XbrlFact",
            ticker=ticker,
            concept=metric,
            accepted_before=as_of,
            limit=10000,
        )

        # Collect all eligible facts grouped by series key
        series: Dict[tuple, Dict[str, Any]] = {}
        for node in nodes:
            props = json.loads(node.properties_json)

            eligible_provs = [p for p in node.provenance if p.accepted_ts <= as_of]
            if not eligible_provs:
                continue

            best_prov = max(eligible_provs, key=lambda p: p.accepted_ts)

            # Series key: (cik, concept, period_start, period_end, unit)
            cik = props.get("cik", "")
            concept = props.get("entity_key", props.get("metric", "")).lower()
            period_start = props.get("period_start", "")
            period_end = props.get("period_end", "")
            unit = props.get("unit", "")
            series_key = (cik, concept, period_start, period_end, unit)

            candidate = {
                "fact_id": node.node_id,
                "value_text": props.get("value_text", ""),
                "decimal_value": props.get("decimal_value"),
                "unit": unit,
                "period_start": period_start,
                "period_end": period_end,
                "period_type": props.get("period_type", ""),
                "chunk_id": best_prov.source_chunk_id,
                "accession_number": best_prov.accession_number,
                "accepted_ts": best_prov.accepted_ts.isoformat(),
                "citation_level": props.get("citation_level", "chunk"),
                "source_url": props.get("source_url", ""),
            }

            # Keep only the latest version per series
            if series_key not in series:
                series[series_key] = candidate
            else:
                existing = series[series_key]
                if (candidate["accepted_ts"], candidate["accession_number"]) > \
                   (existing["accepted_ts"], existing["accession_number"]):
                    series[series_key] = candidate

        results = list(series.values())
        results.sort(key=lambda r: (r["accepted_ts"], r["accession_number"],
                                     r["fact_id"]))
        return results

    def risk_factors(
        self,
        ticker: str,
        as_of: datetime,
    ) -> List[Dict[str, Any]]:
        """Get risk factors for a ticker up to as_of."""
        ticker = normalize_ticker(ticker)
        as_of = ensure_utc(as_of)

        # Use filtered accessor — pushes node_type, ticker into Spark
        nodes = self._store.find_nodes(
            node_type="RiskFactor",
            ticker=ticker,
            accepted_before=as_of,
            limit=10000,
        )

        results = []
        for node in nodes:
            props = json.loads(node.properties_json)

            eligible_provs = [p for p in node.provenance if p.accepted_ts <= as_of]
            if not eligible_provs:
                continue

            best_prov = max(eligible_provs, key=lambda p: p.accepted_ts)

            results.append({
                "node_id": node.node_id,
                "key": props.get("key", ""),
                "value": props.get("value", ""),
                "chunk_id": best_prov.source_chunk_id,
                "accession_number": best_prov.accession_number,
                "accepted_ts": best_prov.accepted_ts.isoformat(),
            })

        results.sort(key=lambda r: (r["accepted_ts"], r["accession_number"]))
        return results

    def neighbors(
        self,
        node_id: str,
        edge_types: List[str],
        as_of: datetime,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Get neighboring nodes connected by specified edge types.

        Validates edge types and applies PIT predicate to every returned edge.
        """
        as_of = ensure_utc(as_of)

        # Validate edge types
        for et in edge_types:
            if et not in EDGE_TYPES:
                raise ValueError(f"Invalid edge type: {et!r}")

        edges = self._store.get_edges_for_node(node_id, edge_types, as_of)
        results = []

        for edge in edges[:limit]:
            # Determine neighbor
            neighbor_id = edge.dst_id if edge.src_id == node_id else edge.src_id
            neighbor = self._store.get_node(neighbor_id)
            if neighbor is None:
                continue

            # PIT check on neighbor node too
            has_eligible_prov = any(
                p.accepted_ts <= as_of for p in neighbor.provenance
            )
            if not has_eligible_prov:
                continue

            results.append({
                "edge_id": edge.edge_id,
                "edge_type": edge.edge_type,
                "neighbor_id": neighbor_id,
                "neighbor_type": neighbor.node_type,
                "neighbor_label": neighbor.label,
                "valid_from": edge.valid_from.isoformat(),
                "accession_number": edge.accession_number,
                "source_chunk_id": edge.source_chunk_id,
                "accepted_ts": edge.accepted_ts.isoformat(),
                "confidence": edge.confidence,
            })

        results.sort(key=lambda r: (r["valid_from"], r["edge_id"]))
        return results