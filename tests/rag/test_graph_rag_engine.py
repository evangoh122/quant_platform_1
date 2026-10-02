"""
tests/test_graph_rag_engine.py — Unit tests for the GraphRAG engine.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from api.services.graph_rag_engine import (
    extract_entities, query_graph, generate_answer, run_graph_rag,
    EntitiesOutput
)

class TestGraphRAGEngine:
    @patch("api.services.graph_rag_engine._get_llm")
    def test_extract_entities(self, mock_get_llm):
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        
        # Mock structured output
        mock_structured_llm = MagicMock()
        mock_llm.with_structured_output.return_value = mock_structured_llm
        mock_structured_llm.invoke.return_value = EntitiesOutput(entities=["Apple", "iPhone"])
        
        state = {"query": "Tell me about Apple's iPhone"}
        result = extract_entities(state)
        
        assert result["search_entities"] == ["Apple", "iPhone"]
        mock_llm.with_structured_output.assert_called_with(EntitiesOutput)

    @patch("api.services.graph_rag_engine.db_manager.execute")
    def test_query_graph(self, mock_execute):
        mock_cursor = MagicMock()
        mock_execute.return_value = mock_cursor
        # Row shape mirrors the Phase C SELECT: base triple + node types +
        # source refs (chunk_id/source_file/source_loc) + confidence.
        mock_cursor.fetchall.return_value = [
            ("AAPL", "Apple", "manufactures", "iPhone",
             "Company", "Product", "AAPL:acc1:5", "acc1", "item_1", 0.92)
        ]

        state = {
            "ticker": "AAPL",
            "search_entities": ["Apple"]
        }
        result = query_graph(state)

        assert len(result["extracted_triples"]) == 1
        t = result["extracted_triples"][0]
        assert t["subject"] == "Apple"
        assert t["predicate"] == "manufactures"
        assert t["object"] == "iPhone"
        # Phase C: source refs + types are plumbed through for auditability.
        assert t["subject_type"] == "Company"
        assert t["object_type"] == "Product"
        assert t["chunk_id"] == "AAPL:acc1:5"
        assert t["source_file"] == "acc1"
        assert t["source_loc"] == "item_1"
        assert t["confidence"] == 0.92

    @patch("api.services.graph_rag_engine._get_llm")
    def test_generate_answer(self, mock_get_llm):
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_llm.invoke.return_value.content = "Apple makes the iPhone."
        
        state = {
            "query": "What does Apple make?",
            "ticker": "AAPL",
            "extracted_triples": [{"subject": "Apple", "predicate": "makes", "object": "iPhone"}]
        }
        result = generate_answer(state)
        
        assert result["final_answer"] == "Apple makes the iPhone."

    @patch("api.services.graph_rag_engine.extract_entities")
    @patch("api.services.graph_rag_engine.query_graph")
    @patch("api.services.graph_rag_engine.generate_answer")
    def test_run_graph_rag_flow(self, mock_gen, mock_query, mock_ext):
        # We need to mock the nodes to avoid actually running the LLM
        mock_ext.return_value = {"search_entities": ["E1"]}
        mock_query.return_value = {"extracted_triples": [{"subject": "S1", "predicate": "P1", "object": "O1"}]}
        mock_gen.return_value = {"final_answer": "Final Answer"}
        
        result = run_graph_rag("query", "TICKER")
        
        assert result["final_answer"] == "Final Answer"
        assert result["search_entities"] == ["E1"]
        assert result["extracted_triples"] == [{"subject": "S1", "predicate": "P1", "object": "O1"}]
