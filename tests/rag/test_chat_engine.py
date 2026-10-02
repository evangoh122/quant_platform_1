"""
tests/test_chat_engine.py — Unit tests for the SQL-based chat engine.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
import pandas as pd
from api.services.chat_engine import (
    clean_sql, strip_sql_comments, validate_read_only_sql,
    summarise_results, chat_sql
)

class TestChatEngineUtils:
    def test_clean_sql(self):
        sql = "```sql\nSELECT * FROM table;\n```"
        assert clean_sql(sql) == "SELECT * FROM table;"
        assert clean_sql("  SELECT 1;  ") == "SELECT 1;"

    def test_strip_sql_comments(self):
        sql = "SELECT * -- comment\nFROM table /* block\ncomment */ WHERE 1=1;"
        stripped = strip_sql_comments(sql)
        assert "-- comment" not in stripped
        assert "block" not in stripped
        assert "SELECT * FROM table WHERE 1=1;" in " ".join(stripped.split())

    def test_validate_read_only_sql_valid(self):
        assert validate_read_only_sql("SELECT * FROM stocks") is None
        assert validate_read_only_sql("WITH t AS (SELECT 1) SELECT * FROM t") is None

    def test_validate_read_only_sql_invalid(self):
        assert "only SELECT and WITH" in validate_read_only_sql("DROP TABLE stocks")
        assert "blocked keyword" in validate_read_only_sql("SELECT * FROM stocks; DELETE FROM stocks")
        assert "internal DuckDB functions" in validate_read_only_sql("SELECT duckdb_version()")

class TestChatEngineCore:
    @patch("api.services.chat_engine.OpenAI")
    @patch("api.services.chat_engine.Config.get_provider_config")
    def test_summarise_results(self, mock_cfg, mock_openai):
        mock_cfg.return_value = {"api_key": "test", "base_url": "test", "model": "test"}
        mock_client = mock_openai.return_value
        mock_client.chat.completions.create.return_value.choices[0].message.content = "The result is 10."
        
        df = pd.DataFrame({"col1": [10]})
        summary = summarise_results("What is the result?", df)
        assert summary == "The result is 10."

    @patch("api.services.chat_engine.db_manager.get_connection")
    @patch("api.services.chat_engine.get_sql_client")
    @patch("api.services.chat_engine.Config.get_provider_config")
    @patch("api.services.chat_engine.summarise_results")
    def test_chat_sql_table_response(self, mock_summarise, mock_cfg, mock_get_client, mock_get_conn):
        mock_cfg.return_value = {"model": "test-model"}
        mock_summarise.return_value = "Summary answer"
        
        # Mock LLM response generating SQL
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.chat.completions.create.return_value.choices[0].message.content = "SELECT * FROM stocks"
        
        # Mock DB execution
        mock_conn = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_df = pd.DataFrame({"ticker": ["AAPL"], "price": [150.0]})
        mock_conn.execute.return_value.df.return_value = mock_df
        
        result = chat_sql("Show me AAPL price")
        
        assert result["type"] == "table"
        assert result["sql"] == "SELECT * FROM stocks"
        assert result["answer"] == "Summary answer"
        assert result["data"][0]["ticker"] == "AAPL"

    @patch("api.services.chat_engine.get_sql_client")
    @patch("api.services.chat_engine.Config.get_provider_config")
    def test_chat_sql_text_response(self, mock_cfg, mock_get_client):
        mock_cfg.return_value = {"model": "test-model"}
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.chat.completions.create.return_value.choices[0].message.content = "ANSWER: Hello there!"
        
        result = chat_sql("Hi")
        assert result["type"] == "text"
        assert result["answer"] == "Hello there!"

    @patch("api.services.chat_engine.get_sql_client")
    @patch("api.services.chat_engine.Config.get_provider_config")
    def test_chat_sql_error_response(self, mock_cfg, mock_get_client):
        mock_cfg.return_value = {"model": "test-model"}
        mock_client = mock_get_client.return_value
        mock_client.chat.completions.create.side_effect = Exception("LLM Error")
        
        result = chat_sql("Broken query")
        assert result["type"] == "error"
        assert "Failed to generate" in result["answer"]
