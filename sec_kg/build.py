"""sec_kg/build.py — deterministic, backend-neutral knowledge graph builder.

Consumes entity and chunk mappings, emits validated nodes/edges, aggregates
sorted provenance, and links rows by accession/chunk.  Input order must not
affect output bytes.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence, Tuple

import re

from sec_kg.model import (
    BUILD_VERSION,
    EdgeType,
    KgEdge,
    KgNode,
    NodeType,
    Provenance,
    chunk_id_from_parts,
    company_id,
    deterministic_json,
    ensure_utc,
    epoch_to_utc,
    event_id,
    filing_id,
    iso_date,
    make_edge_id,
    metric_id,
    normalize_accession,
    normalize_cik,
    normalize_ticker,
    normalize_unicode,
    normalize_unit,
    optional_entity_id,
    parse_decimal,
    period_id,
    risk_factor_id,
    section_id,
    xbrl_fact_id,
)


# ── Allowed rejection reasons ────────────────────────────────────────────────

ALLOWED_REJECTION_REASONS: set = {
    "unknown_entity_type",
    "missing_cik_or_accession",
    "missing_xbrl_identity",
    "missing_period_end",
    "missing_accepted_epoch",
    "dangling_edge",
    "missing_segment_identity",
    "missing_product_identity",
    "missing_customer_identity",
}
# Also allow *_error:ExceptionType patterns for per-entity-type error buckets
_ERROR_PREFIXES = {
    "company_error", "filing_error", "chunk_error", "xbrl_error",
    "risk_factor_error", "event_error", "segment_error", "product_error",
    "customer_error",
}


# ── Rejection tracking ──────────────────────────────────────────────────────

class BuildStats:
    """Tracks rejected rows and their reasons for manifest reporting."""

    def __init__(self):
        self.rejected: List[Tuple[str, str]] = []  # (reason, row_summary)
        self.accepted = 0

    def reject(self, reason: str, row_summary: str = ""):
        self.rejected.append((reason, row_summary))

    def accept(self):
        self.accepted += 1

    @property
    def rejection_counts(self) -> Dict[str, int]:
        counts: Dict[str, int] = defaultdict(int)
        for reason, _ in self.rejected:
            counts[reason] += 1
        return dict(counts)


# ── Conflict detection ──────────────────────────────────────────────────────

def detect_conflicts(nodes: List[KgNode]) -> List[str]:
    """Detect same stable ID mapping to conflicting type/identity content.

    Returns list of conflict descriptions.  Empty list = no conflicts.
    """
    seen: Dict[str, Tuple[str, str]] = {}  # node_id -> (node_type, label)
    conflicts = []
    for node in nodes:
        if node.node_id in seen:
            prev_type, prev_label = seen[node.node_id]
            if prev_type != node.node_type or prev_label != node.label:
                conflicts.append(
                    f"Conflicting identity for {node.node_id}: "
                    f"({prev_type}, {prev_label!r}) vs "
                    f"({node.node_type}, {node.label!r})"
                )
        else:
            seen[node.node_id] = (node.node_type, node.label)
    return conflicts


# ── Source chunk resolution ──────────────────────────────────────────────────

def _edgar_filing_url(cik: str, accession: str) -> str:
    """Build EDGAR filing URL from CIK and accession number."""
    cik_clean = cik.lstrip("0")
    acc_clean = accession.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{cik_clean}/{acc_clean}/{accession}-index.htm"


_NUMBER_RE = re.compile(r"-?\d+(?:,\d{3})*(?:\.\d+)?")


def _extract_numbers_from_text(text: str) -> List[float]:
    """Extract all numeric values from text, handling comma-separated thousands."""
    results = []
    for m in _NUMBER_RE.finditer(text):
        s = m.group().replace(",", "")
        try:
            results.append(float(s))
        except ValueError:
            continue
    return results


def _normalize_number_str(s: str) -> Optional[float]:
    """Normalize a number string (possibly with commas) to float."""
    s = s.strip().replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def _chunk_text_matches_value(
    chunk_text: str,
    entity_value: str,
    period: str,
    metric: str,
) -> bool:
    """Conservative check: chunk text contains the entity value AND period or metric.

    Handles normalised forms like 274300000 ↔ "274.3 million" ↔ "274,300".
    Returns True only when confident the chunk contains the fact.
    """
    if not chunk_text or not entity_value:
        return False

    target = _normalize_number_str(entity_value)
    if target is None or target == 0:
        return False

    text_numbers = _extract_numbers_from_text(chunk_text)

    value_matched = False
    for n in text_numbers:
        if n == 0:
            continue
        if abs(n - target) / max(abs(target), abs(n)) < 0.0001:
            value_matched = True
            break

    if not value_matched:
        return False

    if period and period in chunk_text:
        return True
    if metric and metric.lower() in chunk_text.lower():
        return True

    return False


def resolve_source_chunk_id(
    accession: str,
    entity_chunk_id: Optional[str],
    corpus_by_accession: Dict[str, List[str]],
    corpus_chunk_ids: Optional[set] = None,
    corpus: Optional[Dict[str, Dict[str, Any]]] = None,
    entity_value: Optional[str] = None,
    metric: Optional[str] = None,
    period: Optional[str] = None,
) -> Tuple[str, bool, str]:
    """Resolve source_chunk_id for an entity row.

    Returns (chunk_id, synthetic_source, citation_level).
    citation_level is "chunk" when the chunk resolves in the corpus
    AND (for XBRL facts) the chunk text verifiably contains the fact,
    or "filing" when falling back to filing-level citation.

    If entity has a chunk_id AND it exists in corpus, use it.
    If accession has chunks in corpus AND entity_value is not given,
    use lexicographically smallest.
    If entity_value is given, verify chunk text contains the value
    in normalised form AND period or metric.  Otherwise filing level.
    """
    if corpus_chunk_ids is None:
        corpus_chunk_ids = set()

    acc_norm = normalize_accession(accession)

    if entity_chunk_id and entity_chunk_id.strip():
        chunk_candidate = normalize_unicode(entity_chunk_id)
        if chunk_candidate in corpus_chunk_ids:
            if entity_value and corpus:
                chunk_text = corpus.get(chunk_candidate, {}).get("chunk_text", "")
                if _chunk_text_matches_value(chunk_text, entity_value,
                                              period or "", metric or ""):
                    return chunk_candidate, False, "chunk"
                return f"filing:{acc_norm}", True, "filing"
            return chunk_candidate, False, "chunk"
        # chunk_id present but not in corpus — fall through to accession lookup

    chunks = corpus_by_accession.get(acc_norm, [])
    if chunks:
        if entity_value and corpus:
            for cid in sorted(chunks):
                chunk_text = corpus.get(cid, {}).get("chunk_text", "")
                if _chunk_text_matches_value(chunk_text, entity_value,
                                              period or "", metric or ""):
                    return cid, False, "chunk"
            return f"filing:{acc_norm}", True, "filing"
        return sorted(chunks)[0], False, "chunk"

    return f"filing:{acc_norm}", True, "filing"


# ── Core build ──────────────────────────────────────────────────────────────

def build_graph(
    entities: Sequence[Dict[str, Any]],
    corpus: Dict[str, Dict[str, Any]],
    build_version: str = BUILD_VERSION,
) -> Tuple[List[KgNode], List[KgEdge], BuildStats]:
    """Build the knowledge graph from entity rows and corpus chunks.

    Args:
        entities: list of entity dicts from sec_entities.jsonl
        corpus: dict mapping chunk_id to chunk metadata dict
        build_version: version string for provenance

    Returns:
        (nodes, edges, stats) — validated, sorted, deterministic + rejection stats
    """
    stats = BuildStats()

    # Pre-index corpus by accession for chunk resolution
    corpus_by_accession: Dict[str, List[str]] = defaultdict(list)
    corpus_chunk_ids: set = set()
    for chunk_id, chunk_data in corpus.items():
        acc = normalize_accession(chunk_data.get("accession_number", ""))
        if acc:
            corpus_by_accession[acc].append(chunk_id)
        corpus_chunk_ids.add(chunk_id)

    # Separate entity types
    company_rows = []
    filing_rows = []
    xbrl_fact_rows = []
    risk_factor_rows = []
    event_rows = []
    segment_rows = []
    product_rows = []
    customer_rows = []

    for entity in entities:
        etype = normalize_unicode(entity.get("entity_type", "")).lower()
        if etype == "company":
            company_rows.append(entity)
        elif etype == "filing":
            filing_rows.append(entity)
        elif etype == "xbrl_fact":
            xbrl_fact_rows.append(entity)
        elif etype == "risk_factor":
            risk_factor_rows.append(entity)
        elif etype == "event":
            event_rows.append(entity)
        elif etype == "segment":
            segment_rows.append(entity)
        elif etype == "product":
            product_rows.append(entity)
        elif etype == "customer":
            customer_rows.append(entity)
        else:
            stats.reject(f"unknown_entity_type:{etype}", str(entity.get("entity_key", "")))

    # Build nodes and edges
    nodes: Dict[str, KgNode] = {}  # node_id -> KgNode (for dedup)
    _node_prov_keys: Dict[str, set] = {}  # node_id -> set of prov tuples
    _node_prov_lists: Dict[str, List[Provenance]] = {}  # node_id -> mutable prov list
    edges: List[KgEdge] = []

    def _ensure_node(node_id: str, node_type: str, label: str,
                     properties: Dict[str, Any],
                     prov: Provenance) -> None:
        """Add or merge provenance into a node."""
        if node_id in nodes:
            # Check if this provenance is already tracked
            prov_keys = _node_prov_keys[node_id]
            new_prov_key = (prov.accession_number, prov.source_chunk_id,
                            prov.accepted_ts.isoformat())
            if new_prov_key not in prov_keys:
                prov_keys.add(new_prov_key)
                _node_prov_lists[node_id].append(prov)
        else:
            props_json = deterministic_json(properties)
            nodes[node_id] = KgNode(
                node_id=node_id,
                node_type=node_type,
                label=label,
                properties_json=props_json,
                provenance=(),  # placeholder, finalized at end
                build_version=build_version,
            )
            _node_prov_keys[node_id] = {
                (prov.accession_number, prov.source_chunk_id,
                 prov.accepted_ts.isoformat())
            }
            _node_prov_lists[node_id] = [prov]

    def _add_edge(src_id: str, edge_type: str, dst_id: str,
                  accession: str, source_chunk_id: str,
                  accepted_ts: datetime,
                  confidence: Optional[float] = None,
                  properties: Optional[Dict[str, Any]] = None) -> None:
        """Add an edge if endpoints exist."""
        edge_id = make_edge_id(src_id, edge_type, dst_id, accession,
                               source_chunk_id, accepted_ts)
        props = properties or {}
        edges.append(KgEdge(
            edge_id=edge_id,
            src_id=src_id,
            edge_type=edge_type,
            dst_id=dst_id,
            valid_from=ensure_utc(accepted_ts),
            accession_number=normalize_accession(accession),
            source_chunk_id=normalize_unicode(source_chunk_id),
            accepted_ts=ensure_utc(accepted_ts),
            confidence=confidence,
            properties_json=deterministic_json(props),
            build_version=build_version,
        ))

    # ── Process companies ────────────────────────────────────────────────────
    company_ciks: set = set()
    for row in company_rows:
        try:
            cik = normalize_cik(str(row.get("cik", "")))
            ticker = normalize_ticker(str(row.get("ticker", "")))
            accession = normalize_accession(str(row.get("accession_number", "")))
            if not cik or not accession:
                stats.reject("missing_cik_or_accession", str(row.get("entity_key", "")))
                continue

            accepted_ts = _get_accepted_ts(row)
            chunk_resolved, synthetic, citation_level = resolve_source_chunk_id(
                accession, row.get("source_chunk_id"), corpus_by_accession,
                corpus_chunk_ids
            )
            cid = company_id(cik)

            properties = {
                "cik": cik,
                "ticker": ticker,
                "company_name": normalize_unicode(str(row.get("entity_value", ""))),
            }
            if synthetic:
                properties["synthetic_source"] = True

            prov = Provenance(
                accession_number=accession,
                source_chunk_id=chunk_resolved,
                accepted_ts=accepted_ts,
            )
            _ensure_node(cid, NodeType.COMPANY.value,
                         properties["company_name"], properties, prov)
            company_ciks.add(cik)
            stats.accept()
        except Exception as e:
            stats.reject(f"company_error:{e}", str(row.get("entity_key", "")))

    # ── Process filings ──────────────────────────────────────────────────────
    filing_accessions: Dict[str, str] = {}  # accession -> cik
    for row in filing_rows:
        try:
            cik = normalize_cik(str(row.get("cik", "")))
            accession = normalize_accession(str(row.get("accession_number", "")))
            if not cik or not accession:
                stats.reject("missing_cik_or_accession", str(row.get("entity_key", "")))
                continue

            accepted_ts = _get_accepted_ts(row)
            chunk_resolved, synthetic, citation_level = resolve_source_chunk_id(
                accession, row.get("source_chunk_id"), corpus_by_accession,
                corpus_chunk_ids
            )
            fid = filing_id(cik, accession)
            cid = company_id(cik)

            properties = {
                "cik": cik,
                "accession_number": accession,
                "form_type": normalize_unicode(str(row.get("form_type", ""))),
                "ticker": normalize_ticker(str(row.get("ticker", ""))),
            }
            if synthetic:
                properties["synthetic_source"] = True

            prov = Provenance(
                accession_number=accession,
                source_chunk_id=chunk_resolved,
                accepted_ts=accepted_ts,
            )
            _ensure_node(fid, NodeType.FILING.value,
                         f"Filing {accession}", properties, prov)
            filing_accessions[accession] = cik

            # FILED edge
            _add_edge(cid, EdgeType.FILED.value, fid,
                      accession, chunk_resolved, accepted_ts)
            stats.accept()
        except Exception as e:
            stats.reject(f"filing_error:{e}", str(row.get("entity_key", "")))

    # ── Process corpus chunks → Section + Chunk nodes ────────────────────────
    for chunk_id_str, chunk_data in corpus.items():
        try:
            accession = normalize_accession(str(chunk_data.get("accession_number", "")))
            filing_sec = normalize_unicode(str(chunk_data.get("filing_section", "")))
            cik_for_filing = filing_accessions.get(accession, "")
            accepted_epoch = chunk_data.get("accepted_epoch")
            if accepted_epoch is None:
                stats.reject("missing_accepted_epoch", chunk_id_str)
                continue
            accepted_ts = epoch_to_utc(accepted_epoch)

            # Section node
            sec_id = section_id(accession, filing_sec)
            sec_prov = Provenance(
                accession_number=accession,
                source_chunk_id=chunk_id_str,
                accepted_ts=accepted_ts,
            )
            _ensure_node(sec_id, NodeType.SECTION.value,
                         filing_sec, {"filing_section": filing_sec,
                                      "accession_number": accession}, sec_prov)

            # Chunk node
            chk_id = chunk_id_from_parts(chunk_id_str)
            chk_prov = Provenance(
                accession_number=accession,
                source_chunk_id=chunk_id_str,
                accepted_ts=accepted_ts,
            )
            _ensure_node(chk_id, NodeType.CHUNK.value,
                         f"Chunk {chunk_id_str[:16]}",
                         {"chunk_id": chunk_id_str,
                          "accession_number": accession,
                          "chunk_index": chunk_data.get("chunk_index", 0)},
                         chk_prov)

            # HAS_SECTION and HAS_CHUNK edges (if filing exists)
            fid = filing_id(cik_for_filing, accession) if cik_for_filing else None
            if fid and fid in nodes:
                _add_edge(fid, EdgeType.HAS_SECTION.value, sec_id,
                          accession, chunk_id_str, accepted_ts)
                _add_edge(sec_id, EdgeType.HAS_CHUNK.value, chk_id,
                          accession, chunk_id_str, accepted_ts)
        except Exception as e:
            stats.reject(f"chunk_error:{e}", chunk_id_str)

    # ── Process XBRL facts ───────────────────────────────────────────────────
    # Group by series key for restatement detection
    xbrl_by_series: Dict[Tuple, List[Tuple[Dict, str, datetime]]] = defaultdict(list)
    for row in xbrl_fact_rows:
        try:
            cik = normalize_cik(str(row.get("cik", "")))
            accession = normalize_accession(str(row.get("accession_number", "")))
            metric_concept = normalize_unicode(str(row.get("entity_key", "")))
            period_start_val = row.get("period_start")
            period_start_raw = str(period_start_val) if period_start_val is not None else ""
            period_end_val = row.get("period_end")
            period_end_raw = str(period_end_val) if period_end_val is not None else ""
            unit = normalize_unit(str(row.get("entity_unit", "")))
            if not cik or not accession or not metric_concept:
                stats.reject("missing_xbrl_identity", str(row.get("entity_key", "")))
                continue
            if not period_end_raw:
                stats.reject("missing_period_end", str(row.get("entity_key", "")))
                continue

            period_start = iso_date(period_start_raw) if period_start_raw else ""
            period_end = iso_date(period_end_raw)

            series_key = (normalize_cik(cik), metric_concept.lower(),
                          period_start, period_end, unit)
            accepted_ts = _get_accepted_ts(row)
            xbrl_by_series[series_key].append((row, accession, accepted_ts))
            stats.accept()
        except Exception as e:
            stats.reject(f"xbrl_error:{e}", str(row.get("entity_key", "")))

    # Process each series: sort by (accepted_ts, accession, node_id), build facts
    xbrl_fact_nodes: Dict[str, Dict] = {}  # fact_id -> {node, value, ts, ...}
    for series_key, versions in xbrl_by_series.items():
        # Sort deterministically
        versions.sort(key=lambda v: (v[2].isoformat(), v[1]))

        prev_fact_id = None
        prev_value = None
        for row, accession, accepted_ts in versions:
            cik = normalize_cik(str(row.get("cik", "")))
            metric_concept = normalize_unicode(str(row.get("entity_key", "")))
            value_text = normalize_unicode(str(row.get("entity_value", "")))
            unit = normalize_unit(str(row.get("entity_unit", "")))
            period_start_val = row.get("period_start")
            period_start_raw = str(period_start_val) if period_start_val is not None else ""
            period_end_val = row.get("period_end")
            period_end_raw = str(period_end_val) if period_end_val is not None else ""
            period_start = iso_date(period_start_raw) if period_start_raw else ""
            period_end = iso_date(period_end_raw)
            ticker = normalize_ticker(str(row.get("ticker", "")))
            form_type = normalize_unicode(str(row.get("form_type", "")))
            source_chunk_id_raw = row.get("source_chunk_id")
            chunk_resolved, synthetic, citation_level = resolve_source_chunk_id(
                accession, source_chunk_id_raw, corpus_by_accession,
                corpus_chunk_ids, corpus=corpus,
                entity_value=value_text,
                metric=metric_concept,
                period=period_end_raw,
            )
            confidence = row.get("confidence")

            decimal_value = parse_decimal(value_text)

            fact_id = xbrl_fact_id(cik, accession, metric_concept,
                                    period_start, period_end, unit,
                                    value_text, chunk_resolved)
            metric_node_id = metric_id(metric_concept)
            period_node_id = period_id(period_start, period_end)
            chunk_node_id = chunk_id_from_parts(chunk_resolved)
            company_node_id = company_id(cik)
            filing_node_id = filing_id(cik, accession)

            properties = {
                "value_text": value_text,
                "decimal_value": str(decimal_value) if decimal_value is not None else None,
                "unit": unit,
                "period_start": period_start,
                "period_end": period_end,
                "period_type": "instant" if not period_start else "duration",
                "form_type": form_type,
                "ticker": ticker,
                "cik": cik,
                "metric": metric_concept,
                "citation_level": citation_level,
            }
            if citation_level == "filing":
                properties["source_url"] = _edgar_filing_url(cik, accession)
            if synthetic:
                properties["synthetic_source"] = True

            prov = Provenance(
                accession_number=accession,
                source_chunk_id=chunk_resolved,
                accepted_ts=accepted_ts,
            )

            # Ensure all related nodes exist
            _ensure_node(fact_id, NodeType.XBRL_FACT.value,
                         f"{metric_concept}={value_text}", properties, prov)
            _ensure_node(metric_node_id, NodeType.METRIC.value,
                         metric_concept, {"concept": metric_concept}, prov)
            _ensure_node(period_node_id, NodeType.PERIOD.value,
                         f"{period_start or '?'}/{period_end}",
                         {"period_start": period_start, "period_end": period_end},
                         prov)
            # Ensure chunk node only when citation resolves to a real chunk
            if citation_level == "chunk":
                if chunk_node_id not in nodes:
                    _ensure_node(chunk_node_id, NodeType.CHUNK.value,
                                 f"Chunk {chunk_resolved[:16]}",
                                 {"chunk_id": chunk_resolved,
                                  "accession_number": accession}, prov)
            # Ensure company if not already built
            if company_node_id not in nodes:
                _ensure_node(company_node_id, NodeType.COMPANY.value,
                             ticker, {"cik": cik, "ticker": ticker,
                                       "synthetic_source": True}, prov)
            # Ensure filing node for filing-level citations
            if citation_level == "filing" and filing_node_id not in nodes:
                _ensure_node(filing_node_id, NodeType.FILING.value,
                             f"Filing {accession}",
                             {"accession_number": accession, "cik": cik,
                              "form_type": form_type,
                              "source_url": _edgar_filing_url(cik, accession),
                              "synthetic_source": True}, prov)

            # Edges: Company -> REPORTED_FACT -> Fact
            _add_edge(company_node_id, EdgeType.REPORTED_FACT.value,
                      fact_id, accession, chunk_resolved, accepted_ts, confidence)
            # Fact -> INSTANCE_OF -> Metric
            _add_edge(fact_id, EdgeType.INSTANCE_OF.value,
                      metric_node_id, accession, chunk_resolved, accepted_ts)
            # Fact -> FOR_PERIOD -> Period
            _add_edge(fact_id, EdgeType.FOR_PERIOD.value,
                      period_node_id, accession, chunk_resolved, accepted_ts)
            # Fact -> SOURCED_FROM -> Chunk (only when chunk resolves)
            if citation_level == "chunk":
                _add_edge(fact_id, EdgeType.SOURCED_FROM.value,
                          chunk_node_id, accession, chunk_resolved, accepted_ts)

            # SUPERSEDES edge: different value from previous version
            if prev_fact_id is not None and prev_value != value_text:
                _add_edge(fact_id, EdgeType.SUPERSEDES.value,
                          prev_fact_id, accession, chunk_resolved, accepted_ts)

            xbrl_fact_nodes[fact_id] = {
                "node_id": fact_id,
                "value": value_text,
                "accepted_ts": accepted_ts,
                "prev_fact_id": prev_fact_id,
            }
            prev_fact_id = fact_id
            prev_value = value_text

    # ── Process risk factors ─────────────────────────────────────────────────
    for row in risk_factor_rows:
        try:
            cik = normalize_cik(str(row.get("cik", "")))
            accession = normalize_accession(str(row.get("accession_number", "")))
            key = normalize_unicode(str(row.get("entity_key", "")))
            value = normalize_unicode(str(row.get("entity_value", "")))
            if not cik or not accession:
                stats.reject("missing_cik_or_accession", str(row.get("entity_key", "")))
                continue

            accepted_ts = _get_accepted_ts(row)
            source_chunk_id_raw = row.get("source_chunk_id")
            chunk_resolved, synthetic, citation_level = resolve_source_chunk_id(
                accession, source_chunk_id_raw, corpus_by_accession,
                corpus_chunk_ids
            )
            confidence = row.get("confidence")

            rf_id = risk_factor_id(cik, accession, chunk_resolved, key, value)
            filing_node_id = filing_id(cik, accession)
            chunk_node_id = chunk_id_from_parts(chunk_resolved)

            properties = {
                "key": key,
                "value": value,
                "cik": cik,
                "accession_number": accession,
                "ticker": normalize_ticker(str(row.get("ticker", ""))),
                "citation_level": citation_level,
            }
            if citation_level == "filing":
                properties["source_url"] = _edgar_filing_url(cik, accession)
            if synthetic:
                properties["synthetic_source"] = True

            prov = Provenance(
                accession_number=accession,
                source_chunk_id=chunk_resolved,
                accepted_ts=accepted_ts,
            )
            _ensure_node(rf_id, NodeType.RISK_FACTOR.value,
                         key, properties, prov)

            # Ensure endpoints
            if filing_node_id not in nodes:
                _ensure_node(filing_node_id, NodeType.FILING.value,
                             f"Filing {accession}",
                             {"accession_number": accession, "cik": cik,
                              "synthetic_source": True}, prov)
            if citation_level == "chunk" and chunk_node_id not in nodes:
                _ensure_node(chunk_node_id, NodeType.CHUNK.value,
                             f"Chunk {chunk_resolved[:16]}",
                             {"chunk_id": chunk_resolved,
                              "accession_number": accession}, prov)

            # DISCLOSED_RISK edge (always to filing)
            _add_edge(filing_node_id, EdgeType.DISCLOSED_RISK.value,
                      rf_id, accession, chunk_resolved, accepted_ts, confidence)
            # SOURCED_FROM edge (only when chunk resolves)
            if citation_level == "chunk":
                _add_edge(rf_id, EdgeType.SOURCED_FROM.value,
                          chunk_node_id, accession, chunk_resolved, accepted_ts)
            stats.accept()
        except Exception as e:
            stats.reject(f"risk_factor_error:{e}", str(row.get("entity_key", "")))

    # ── Process events ───────────────────────────────────────────────────────
    for row in event_rows:
        try:
            cik = normalize_cik(str(row.get("cik", "")))
            accession = normalize_accession(str(row.get("accession_number", "")))
            key = normalize_unicode(str(row.get("entity_key", "")))
            value = normalize_unicode(str(row.get("entity_value", "")))
            if not cik or not accession:
                stats.reject("missing_cik_or_accession", str(row.get("entity_key", "")))
                continue

            accepted_ts = _get_accepted_ts(row)
            source_chunk_id_raw = row.get("source_chunk_id")
            chunk_resolved, synthetic, citation_level = resolve_source_chunk_id(
                accession, source_chunk_id_raw, corpus_by_accession,
                corpus_chunk_ids
            )
            confidence = row.get("confidence")

            ev_id = event_id(cik, accession, chunk_resolved, key, value)
            filing_node_id = filing_id(cik, accession)
            chunk_node_id = chunk_id_from_parts(chunk_resolved)

            properties = {
                "key": key,
                "value": value,
                "cik": cik,
                "accession_number": accession,
                "ticker": normalize_ticker(str(row.get("ticker", ""))),
                "citation_level": citation_level,
            }
            if citation_level == "filing":
                properties["source_url"] = _edgar_filing_url(cik, accession)
            if synthetic:
                properties["synthetic_source"] = True

            prov = Provenance(
                accession_number=accession,
                source_chunk_id=chunk_resolved,
                accepted_ts=accepted_ts,
            )
            _ensure_node(ev_id, NodeType.EVENT.value,
                         key, properties, prov)

            if filing_node_id not in nodes:
                _ensure_node(filing_node_id, NodeType.FILING.value,
                             f"Filing {accession}",
                             {"accession_number": accession, "cik": cik,
                              "synthetic_source": True}, prov)
            if citation_level == "chunk" and chunk_node_id not in nodes:
                _ensure_node(chunk_node_id, NodeType.CHUNK.value,
                             f"Chunk {chunk_resolved[:16]}",
                             {"chunk_id": chunk_resolved,
                              "accession_number": accession}, prov)

            _add_edge(filing_node_id, EdgeType.REPORTED_EVENT.value,
                      ev_id, accession, chunk_resolved, accepted_ts, confidence)
            if citation_level == "chunk":
                _add_edge(ev_id, EdgeType.SOURCED_FROM.value,
                          chunk_node_id, accession, chunk_resolved, accepted_ts)
            stats.accept()
        except Exception as e:
            stats.reject(f"event_error:{e}", str(row.get("entity_key", "")))

    # ── Process optional entities (segment/product/customer) ─────────────────
    for rows, etype, edge_type in [
        (segment_rows, "segment", EdgeType.HAS_SEGMENT),
        (product_rows, "product", EdgeType.HAS_PRODUCT),
        (customer_rows, "customer", EdgeType.HAS_CUSTOMER),
    ]:
        for row in rows:
            try:
                cik = normalize_cik(str(row.get("cik", "")))
                accession = normalize_accession(str(row.get("accession_number", "")))
                label = normalize_unicode(str(row.get("entity_value", "")))
                if not cik or not label:
                    stats.reject(f"missing_{etype}_identity", str(row.get("entity_key", "")))
                    continue

                accepted_ts = _get_accepted_ts(row)
                source_chunk_id_raw = row.get("source_chunk_id")
                chunk_resolved, synthetic, citation_level = resolve_source_chunk_id(
                    accession, source_chunk_id_raw, corpus_by_accession,
                    corpus_chunk_ids
                )

                opt_id = optional_entity_id(etype, cik, label)
                company_node_id = company_id(cik)

                properties = {
                    "label": label,
                    "cik": cik,
                    "ticker": normalize_ticker(str(row.get("ticker", ""))),
                }
                if synthetic:
                    properties["synthetic_source"] = True

                prov = Provenance(
                    accession_number=accession,
                    source_chunk_id=chunk_resolved,
                    accepted_ts=accepted_ts,
                )
                node_type = {
                    "segment": NodeType.SEGMENT,
                    "product": NodeType.PRODUCT,
                    "customer": NodeType.CUSTOMER,
                }[etype]
                _ensure_node(opt_id, node_type.value, label, properties, prov)

                if company_node_id not in nodes:
                    _ensure_node(company_node_id, NodeType.COMPANY.value,
                                 properties.get("ticker", ""),
                                 {"cik": cik, "ticker": properties.get("ticker", ""),
                                  "synthetic_source": True}, prov)

                _add_edge(company_node_id, edge_type.value, opt_id,
                          accession, chunk_resolved, accepted_ts)
                stats.accept()
            except Exception as e:
                stats.reject(f"{etype}_error:{e}", str(row.get("entity_key", "")))

    # ── Finalize provenance ────────────────────────────────────────────────────
    for node_id in nodes:
        prov_list = _node_prov_lists[node_id]
        prov_list.sort(key=lambda p: (p.accepted_ts.isoformat(),
                                       p.accession_number, p.source_chunk_id))
        existing = nodes[node_id]
        nodes[node_id] = KgNode(
            node_id=existing.node_id,
            node_type=existing.node_type,
            label=existing.label,
            properties_json=existing.properties_json,
            provenance=tuple(prov_list),
            build_version=existing.build_version,
        )

    # ── Validate endpoints ───────────────────────────────────────────────────
    node_ids = set(nodes.keys())
    valid_edges = []
    for edge in edges:
        if edge.src_id not in node_ids or edge.dst_id not in node_ids:
            stats.reject("dangling_edge", edge.edge_id)
            continue
        valid_edges.append(edge)

    # ── Detect conflicts ─────────────────────────────────────────────────────
    node_list = list(nodes.values())
    conflicts = detect_conflicts(node_list)
    if conflicts:
        raise ValueError(f"Conflicting node identities detected: {conflicts}")

    # ── Sort deterministically ───────────────────────────────────────────────
    node_list.sort(key=lambda n: n.node_id)
    valid_edges.sort(key=lambda e: e.edge_id)

    return node_list, valid_edges, stats


def validate_rejection_reasons(stats: BuildStats) -> List[str]:
    """Return list of undocumented rejection reasons (empty = all documented)."""
    undocumented = []
    for reason in stats.rejection_counts:
        prefix = reason.split(":")[0]
        if prefix not in ALLOWED_REJECTION_REASONS and prefix not in _ERROR_PREFIXES:
            undocumented.append(reason)
    return undocumented


def validate_and_raise(
    stats: BuildStats,
    entity_type_counts: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    """Validate rejection reasons and raise on undocumented ones.

    Shared by the offline script and the Databricks pipeline so their
    behaviour cannot drift.

    Args:
        stats: BuildStats from build_graph()
        entity_type_counts: input rows by entity_type (optional, for manifest)

    Returns:
        manifest dict with exact stats

    Raises:
        ValueError: if any rejection reason is not in ALLOWED_REJECTION_REASONS
    """
    undocumented = validate_rejection_reasons(stats)
    if undocumented:
        raise ValueError(
            f"Undocumented rejection reasons detected: {undocumented}. "
            f"Aborting — no tables written."
        )

    manifest: Dict[str, Any] = {
        "input_rows_by_entity_type": entity_type_counts or {},
        "accepted_rows": stats.accepted,
        "rejected_rows": len(stats.rejected),
        "rejection_reasons": dict(stats.rejection_counts),
    }
    return manifest


def _get_accepted_ts(row: Dict[str, Any]) -> datetime:
    """Extract and normalize accepted_ts from entity row."""
    epoch = row.get("accepted_epoch")
    if epoch is not None:
        return epoch_to_utc(epoch)
    ts = row.get("accepted_ts")
    if ts is not None:
        if isinstance(ts, datetime):
            return ensure_utc(ts)
        if isinstance(ts, (int, float)):
            return epoch_to_utc(ts)
        if isinstance(ts, str):
            return ensure_utc(datetime.fromisoformat(ts))
    raise ValueError("No accepted_epoch or accepted_ts in entity row")


# ── Q&A candidate proposals ─────────────────────────────────────────────────

def propose_xbrl_qa_candidates(
    store: Any,
    ticker: str,
    as_of: datetime,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """Propose deterministic Q&A candidates from numeric XBRL facts.

    Returns records with question_template, answer_value, metric, period,
    unit, fact_id, accession, source_chunk, and accepted_ts.

    Only proposes numeric, nonblank-unit facts with real chunk provenance.
    Dedupes using PIT/restatement rules.  Never claims proposals are final.
    """
    from sec_kg.model import normalize_ticker, parse_decimal

    ticker = normalize_ticker(ticker)
    as_of = ensure_utc(as_of)

    # Get all XBRL facts for this ticker
    candidates = []

    # Collect facts from store
    all_facts = []
    for node in store.iter_nodes():
        if node.node_type != "XbrlFact":
            continue
        props = json.loads(node.properties_json)
        if props.get("ticker", "").upper() != ticker:
            continue

        # Check PIT: all provenance must be <= as_of
        eligible = False
        for p in node.provenance:
            if p.accepted_ts <= as_of:
                eligible = True
                break
        if not eligible:
            continue

        # Must be numeric with non-blank unit
        value_text = props.get("value_text", "")
        unit = props.get("unit", "")
        if not unit or not value_text:
            continue
        decimal_val = parse_decimal(value_text)
        if decimal_val is None:
            continue

        # Must have real (non-synthetic) chunk provenance
        has_real_chunk = False
        for p in node.provenance:
            if p.accepted_ts <= as_of and not p.source_chunk_id.startswith("filing:"):
                has_real_chunk = True
                break
        if not has_real_chunk:
            continue

        all_facts.append({
            "node_id": node.node_id,
            "metric": props.get("entity_key", props.get("metric", "")),
            "value_text": value_text,
            "unit": unit,
            "period_start": props.get("period_start", ""),
            "period_end": props.get("period_end", ""),
            "provenance": node.provenance,
            "accepted_ts": max(p.accepted_ts for p in node.provenance
                               if p.accepted_ts <= as_of),
        })

    # Dedupe by logical series key (metric, period_start, period_end, unit)
    # Keep only the latest version per series
    series: Dict[Tuple, Dict] = {}
    for fact in all_facts:
        key = (fact["metric"].lower(), fact["period_start"],
               fact["period_end"], fact["unit"])
        if key not in series or fact["accepted_ts"] > series[key]["accepted_ts"]:
            series[key] = fact

    # Build candidates
    for key, fact in sorted(series.items(), key=lambda x: x[1]["accepted_ts"],
                            reverse=True)[:limit]:
        prov = fact["provenance"]
        # Find the provenance entry used
        best_prov = max(
            (p for p in prov if p.accepted_ts <= as_of),
            key=lambda p: p.accepted_ts,
        )
        candidates.append({
            "question_template": (
                f"What was {ticker}'s {fact['metric']} for the period "
                f"ending {fact['period_end']}?"
            ),
            "answer_value": fact["value_text"],
            "metric": fact["metric"],
            "period_start": fact["period_start"],
            "period_end": fact["period_end"],
            "unit": fact["unit"],
            "fact_id": fact["node_id"],
            "accession": best_prov.accession_number,
            "source_chunk": best_prov.source_chunk_id,
            "accepted_ts": best_prov.accepted_ts.isoformat(),
        })

    return candidates