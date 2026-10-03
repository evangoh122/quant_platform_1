"""tests/rag/test_sec_kg_agent_tool.py — red tests for query_sec_facts agent tool."""
from __future__ import annotations

import pytest
from datetime import datetime, timezone


class TestQuerySecFactsValidation:
    """Strict Pydantic input model rejects wrong types before store access."""

    def test_rejects_naive_as_of(self):
        from agent.tools_retrieval import query_sec_facts
        with pytest.raises((ValueError, TypeError)):
            query_sec_facts("NVDA", "Revenues", "2024-01-28",
                            datetime(2024, 6, 1))

    def test_rejects_string_as_of(self):
        from agent.tools_retrieval import query_sec_facts
        with pytest.raises((ValueError, TypeError)):
            query_sec_facts("NVDA", "Revenues", "2024-01-28", "2024-06-01")

    def test_rejects_extra_kwargs(self):
        from agent.tools_retrieval import query_sec_facts
        with pytest.raises((ValueError, TypeError)):
            query_sec_facts("NVDA", "Revenues", "2024-01-28",
                            datetime(2024, 6, 1, tzinfo=timezone.utc),
                            bogus=True)

    def test_rejects_injection_ticker(self):
        from agent.tools_retrieval import query_sec_facts
        with pytest.raises(ValueError):
            query_sec_facts("'; DROP TABLE --", "Revenues", "2024-01-28",
                            datetime(2024, 6, 1, tzinfo=timezone.utc))

    def test_rejects_non_string_metric(self):
        from agent.tools_retrieval import query_sec_facts
        with pytest.raises((ValueError, TypeError)):
            query_sec_facts("NVDA", 123, "2024-01-28",
                            datetime(2024, 6, 1, tzinfo=timezone.utc))

    def test_rejects_empty_metric(self):
        from agent.tools_retrieval import query_sec_facts
        with pytest.raises((ValueError, TypeError)):
            query_sec_facts("NVDA", "", "2024-01-28",
                            datetime(2024, 6, 1, tzinfo=timezone.utc))

    def test_rejects_empty_period(self):
        from agent.tools_retrieval import query_sec_facts
        with pytest.raises((ValueError, TypeError)):
            query_sec_facts("NVDA", "Revenues", "",
                            datetime(2024, 6, 1, tzinfo=timezone.utc))

    def test_valid_call_returns_envelope(self):
        """Valid call with a mock graph returns untrusted_tool_data envelope."""
        from sec_kg.model import company_id
        from sec_kg.build import build_graph
        from api.services.sec_knowledge_graph import JsonlGraphStore, SecKnowledgeGraph

        entities = [{
            "cik": "0001045810", "ticker": "NVDA",
            "accession_number": "0001045810-24-000001",
            "form_type": "10-K", "accepted_epoch": 1700000000,
            "entity_type": "xbrl_fact", "entity_key": "Revenues",
            "entity_value": "2943719000", "entity_unit": "USD",
            "period_start": "", "period_end": "2024-01-28",
            "confidence": 1.0, "source_chunk_id": "c1",
        }, {
            "cik": "0001045810", "ticker": "NVDA",
            "accession_number": "0001045810-24-000001",
            "form_type": "10-K", "accepted_epoch": 1700000000,
            "entity_type": "company", "entity_key": "NVIDIA",
            "entity_value": "NVIDIA Corporation",
            "entity_unit": "", "period_start": "", "period_end": "",
            "confidence": 1.0, "source_chunk_id": "c1",
        }]
        corpus = {
            "c1": {"chunk_id": "c1", "ticker": "NVDA",
                   "accession_number": "0001045810-24-000001",
                   "form_type": "10-K", "accepted_epoch": 1700000000,
                   "filing_section": "item1", "chunk_index": 0,
                   "chunk_text": "text"},
        }
        nodes, edges = build_graph(entities, corpus, "test-1.0")
        store = JsonlGraphStore()
        store.load_from_build(nodes, edges)
        kg = SecKnowledgeGraph(store)

        from agent.tools_retrieval import query_sec_facts
        result = query_sec_facts(
            "NVDA", "Revenues", "2024-01-28",
            datetime(2024, 6, 1, tzinfo=timezone.utc),
            graph=kg,
        )
        assert result["content_type"] == "untrusted_tool_data"
        assert "results" in result
        assert "provenance" in result