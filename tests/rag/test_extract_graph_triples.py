"""
tests/test_extract_graph_triples.py — Phase B: filing-derived triple extraction.

Covers identity/normalisation helpers, LLM-output validation (vocab gate,
confidence floor, cap), schema migration, persistence/idempotency, the XBRL
VERIFIED_BY linking, and the end-to-end orchestrator with a mocked client.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import duckdb

from scripts import extract_graph_triples as ext


# ── helpers ──────────────────────────────────────────────────────────────────

def _mock_client(payload: str):
    """An OpenAI-shaped client whose completion returns `payload` as content."""
    client = MagicMock()
    client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=payload))]
    )
    return client


def _mem_db():
    conn = duckdb.connect(":memory:")
    ext.ensure_schema(conn)
    return conn


# ── identity / normalisation ─────────────────────────────────────────────────

class TestHelpers:
    def test_make_chunk_id(self):
        assert ext.make_chunk_id("NVDA", "0001045810-24-000029", 3) == \
            "NVDA:0001045810-24-000029:3"

    def test_make_chunk_id_missing_index(self):
        assert ext.make_chunk_id("MU", "acc", None) == "MU:acc:-"

    def test_triple_id_deterministic_and_case_insensitive(self):
        a = ext.triple_id("NVDA", "Nvidia", "HAS_SEGMENT", "Data Center", "c1")
        b = ext.triple_id("NVDA", "nvidia", "has_segment", "data center", "c1")
        assert a == b  # content-dedupe is case-insensitive
        c = ext.triple_id("NVDA", "Nvidia", "HAS_SEGMENT", "Gaming", "c1")
        assert a != c

    def test_normalise_predicate(self):
        assert ext._normalise_predicate("has segment") == "HAS_SEGMENT"
        assert ext._normalise_predicate("competes-with") == "COMPETES_WITH"
        assert ext._normalise_predicate("") == "RELATED_TO"


# ── LLM output validation ────────────────────────────────────────────────────

class TestExtractTriplesFromChunk:
    def test_happy_path_parses_and_validates(self):
        payload = (
            '{"triples": [{"subject": "NVIDIA", "subject_type": "Company", '
            '"predicate": "has segment", "object": "Data Center", '
            '"object_type": "Segment", "confidence": 0.9}]}'
        )
        out = ext.extract_triples_from_chunk("text", "NVDA", _mock_client(payload), "m")
        assert len(out) == 1
        t = out[0]
        assert t["subject"] == "NVIDIA"
        assert t["predicate"] == "HAS_SEGMENT"  # normalised
        assert t["object_type"] == "Segment"
        assert t["confidence"] == 0.9

    def test_drops_invalid_node_types(self):
        payload = (
            '{"triples": [{"subject": "X", "subject_type": "Wizard", '
            '"predicate": "P", "object": "Y", "object_type": "Company", '
            '"confidence": 0.9}]}'
        )
        assert ext.extract_triples_from_chunk("t", "NVDA", _mock_client(payload), "m") == []

    def test_confidence_floor_filters(self, monkeypatch):
        monkeypatch.setattr(ext, "MIN_CONFIDENCE", 0.5)
        payload = (
            '{"triples": [{"subject": "A", "subject_type": "Company", '
            '"predicate": "P", "object": "B", "object_type": "Risk", '
            '"confidence": 0.2}]}'
        )
        assert ext.extract_triples_from_chunk("t", "NVDA", _mock_client(payload), "m") == []

    def test_caps_triples_per_chunk(self, monkeypatch):
        monkeypatch.setattr(ext, "MAX_TRIPLES_PER_CHUNK", 2)
        one = ('{"subject": "A", "subject_type": "Company", "predicate": "P", '
               '"object": "B", "object_type": "Risk", "confidence": 0.9}')
        payload = '{"triples": [' + ",".join([one] * 5) + ']}'
        out = ext.extract_triples_from_chunk("t", "NVDA", _mock_client(payload), "m")
        assert len(out) == 2

    def test_empty_text_returns_empty_without_calling_llm(self):
        client = _mock_client("{}")
        assert ext.extract_triples_from_chunk("   ", "NVDA", client, "m") == []
        client.chat.completions.create.assert_not_called()

    def test_malformed_json_returns_empty(self):
        assert ext.extract_triples_from_chunk("t", "NVDA", _mock_client("not json"), "m") == []

    def test_tolerates_json_fence(self):
        payload = (
            '```json\n{"triples": [{"subject": "A", "subject_type": "Company", '
            '"predicate": "FACES_RISK", "object": "Supply Shortage", '
            '"object_type": "Risk", "confidence": 0.8}]}\n```'
        )
        out = ext.extract_triples_from_chunk("t", "NVDA", _mock_client(payload), "m")
        assert len(out) == 1 and out[0]["predicate"] == "FACES_RISK"


# ── persistence / schema ─────────────────────────────────────────────────────

class TestPersistence:
    def test_schema_has_typed_columns(self):
        conn = _mem_db()
        cols = {r[1] for r in conn.execute("PRAGMA table_info('graph_triples')").fetchall()}
        assert {"subject_type", "object_type", "chunk_id"} <= cols

    def test_persist_is_idempotent(self):
        conn = _mem_db()
        row = {
            "id": ext.triple_id("NVDA", "A", "P", "B", "c1"),
            "ticker": "NVDA", "subject": "A", "predicate": "P", "object": "B",
            "confidence": 0.9, "source_file": "acc", "source_loc": "item_1",
            "subject_type": "Company", "object_type": "Risk", "chunk_id": "c1",
        }
        ext.persist_triples(conn, [row])
        ext.persist_triples(conn, [row])  # re-run
        n = conn.execute("SELECT COUNT(*) FROM graph_triples").fetchone()[0]
        assert n == 1  # deterministic id + INSERT OR IGNORE dedupes


# ── XBRL linking ─────────────────────────────────────────────────────────────

class TestXbrlLinking:
    def _seed_xbrl(self, conn):
        conn.execute("""
            CREATE TABLE xbrl_facts (ticker VARCHAR, concept VARCHAR)
        """)
        conn.execute("INSERT INTO xbrl_facts VALUES ('NVDA', 'Revenues')")

    def test_links_metric_to_xbrl_concept(self):
        conn = _mem_db()
        self._seed_xbrl(conn)
        conn.execute(ext.INSERT_SQL, [
            ext.triple_id("NVDA", "Revenue", "REPORTS_METRIC", "Revenue", "c1"),
            "NVDA", "NVIDIA", "REPORTS_METRIC", "Revenue", 0.9,
            "acc", "item_7", "Company", "Metric", "c1",
        ])
        linked = ext.link_xbrl_metrics(conn, "NVDA")
        assert linked == 1
        edge = conn.execute(
            "SELECT subject, predicate, object, object_type FROM graph_triples "
            "WHERE predicate = 'VERIFIED_BY'"
        ).fetchone()
        assert edge == ("Revenue", "VERIFIED_BY", "Revenues", "XBRL")

    def test_no_xbrl_table_returns_zero(self):
        conn = _mem_db()  # no xbrl_facts table
        assert ext.link_xbrl_metrics(conn, "NVDA") == 0


# ── orchestrator ─────────────────────────────────────────────────────────────

class TestOrchestrator:
    def test_end_to_end_with_mock_client(self, tmp_path):
        db = str(tmp_path / "t.duckdb")
        conn = duckdb.connect(db)
        ext.ensure_schema(conn)
        conn.execute("""
            CREATE TABLE edgar_embeddings (
                ticker VARCHAR, accession VARCHAR, text TEXT, section_id VARCHAR,
                chunk_index INTEGER, form_type VARCHAR, period_of_report VARCHAR,
                content_type VARCHAR
            )
        """)
        conn.execute(
            "INSERT INTO edgar_embeddings VALUES "
            "('NVDA','acc1','NVIDIA operates a Data Center segment.','item_1',0,'10-K','2024-01-28','narrative')"
        )
        conn.close()

        payload = (
            '{"triples": [{"subject": "NVIDIA", "subject_type": "Company", '
            '"predicate": "HAS_SEGMENT", "object": "Data Center", '
            '"object_type": "Segment", "confidence": 0.95}]}'
        )
        n = ext.run_extract_graph_triples(
            ["nvda"], db_path=db, client=_mock_client(payload), model="m"
        )
        assert n == 1
        conn = duckdb.connect(db)
        row = conn.execute(
            "SELECT ticker, subject, predicate, object, subject_type, object_type, "
            "chunk_id, source_file, source_loc FROM graph_triples"
        ).fetchone()
        assert row == (
            "NVDA", "NVIDIA", "HAS_SEGMENT", "Data Center",
            "Company", "Segment", "NVDA:acc1:0", "acc1", "item_1",
        )

    def test_skips_ticker_with_no_chunks(self, tmp_path):
        db = str(tmp_path / "t.duckdb")
        conn = duckdb.connect(db)
        ext.ensure_schema(conn)
        conn.execute("""
            CREATE TABLE edgar_embeddings (
                ticker VARCHAR, accession VARCHAR, text TEXT, section_id VARCHAR,
                chunk_index INTEGER, form_type VARCHAR, period_of_report VARCHAR,
                content_type VARCHAR
            )
        """)
        conn.close()
        client = _mock_client("{}")
        n = ext.run_extract_graph_triples(["ZZZZ"], db_path=db, client=client, model="m")
        assert n == 0
        client.chat.completions.create.assert_not_called()

    def test_parse_tickers(self):
        assert ext._parse_tickers("nvda, mu  amd") == ["NVDA", "MU", "AMD"]
        assert ext._parse_tickers("") == []
        assert ext._parse_tickers(None) == []
