"""tests/rag/test_rag_eval_round3.py — Round 3 fixes: timestamp loading, PIT leakage fail-closed.

Tests prove the bugs exist on current HEAD and that the fixes work.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from evals.rag_eval.corpus import JsonlCorpusAdapter, install_offline_corpus
from evals.rag_eval.models import GoldenItem, RetrievalConfig, RetrievalHit
from evals.rag_eval.retrieve import assert_no_pit_leakage, retrieve_item


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "rag_eval"


class TestAcceptedEpochLoadsCorrectly:
    """Round 3 fix: corpus must parse accepted_epoch → ISO UTC."""

    def test_accepted_epoch_only_loads_with_iso_time(self, tmp_path):
        """A JSONL record with only accepted_epoch loads with correct ISO time."""
        from evals.rag_eval.corpus import JsonlCorpusAdapter

        # 2024-01-15T00:00:00+00:00 as epoch = 1705276800
        epoch = 1705276800
        obj = {"chunk_id": "c1", "ticker": "X", "chunk_text": "hello", "accepted_epoch": epoch}
        corpus_path = tmp_path / "corpus.jsonl"
        corpus_path.write_text(json.dumps(obj) + "\n", encoding="utf-8")

        adapter = JsonlCorpusAdapter.from_files(corpus_path, None)
        rec = adapter.records()[0]
        # Must produce an ISO UTC timestamp, not empty string
        assert rec.accepted_ts != "", "accepted_epoch must be parsed to ISO UTC"
        assert "2024-01-15" in rec.accepted_ts
        # Must be parseable
        dt = datetime.fromisoformat(rec.accepted_ts.replace("Z", "+00:00"))
        assert dt.year == 2024
        assert dt.month == 1
        assert dt.day == 15

    def test_accepted_ts_fallback_still_works(self, tmp_path):
        """A record with accepted_ts (string) still works as before."""
        from evals.rag_eval.corpus import JsonlCorpusAdapter

        obj = {"chunk_id": "c1", "ticker": "X", "chunk_text": "hello",
               "accepted_ts": "2024-03-01T00:00:00+00:00"}
        corpus_path = tmp_path / "corpus.jsonl"
        corpus_path.write_text(json.dumps(obj) + "\n", encoding="utf-8")

        adapter = JsonlCorpusAdapter.from_files(corpus_path, None)
        rec = adapter.records()[0]
        assert rec.accepted_ts == "2024-03-01T00:00:00+00:00"

    def test_both_fields_epoch_takes_precedence(self, tmp_path):
        """When both accepted_epoch and accepted_ts exist, epoch wins."""
        from evals.rag_eval.corpus import JsonlCorpusAdapter

        epoch = 1705276800  # 2024-01-15
        obj = {"chunk_id": "c1", "ticker": "X", "chunk_text": "hello",
               "accepted_epoch": epoch,
               "accepted_ts": "2023-06-01T00:00:00+00:00"}
        corpus_path = tmp_path / "corpus.jsonl"
        corpus_path.write_text(json.dumps(obj) + "\n", encoding="utf-8")

        adapter = JsonlCorpusAdapter.from_files(corpus_path, None)
        rec = adapter.records()[0]
        # Epoch should take precedence
        assert "2024-01-15" in rec.accepted_ts


class TestMissingTimestampRaises:
    """Round 3 fix: records with neither accepted_epoch nor accepted_ts must raise."""

    def test_neither_field_raises_at_load(self, tmp_path):
        """A record with neither accepted_epoch nor accepted_ts → load error."""
        from evals.rag_eval.corpus import JsonlCorpusAdapter

        obj = {"chunk_id": "c1", "ticker": "X", "chunk_text": "hello"}
        corpus_path = tmp_path / "corpus.jsonl"
        corpus_path.write_text(json.dumps(obj) + "\n", encoding="utf-8")

        with pytest.raises(ValueError, match="accepted.*(epoch|ts)"):
            JsonlCorpusAdapter.from_files(corpus_path, None)

    def test_empty_string_neither_field_raises(self, tmp_path):
        """A record with empty string accepted_ts and no accepted_epoch → load error."""
        from evals.rag_eval.corpus import JsonlCorpusAdapter

        obj = {"chunk_id": "c1", "ticker": "X", "chunk_text": "hello", "accepted_ts": ""}
        corpus_path = tmp_path / "corpus.jsonl"
        corpus_path.write_text(json.dumps(obj) + "\n", encoding="utf-8")

        with pytest.raises(ValueError, match="accepted.*(epoch|ts)"):
            JsonlCorpusAdapter.from_files(corpus_path, None)


class TestMissingTimestampIsPitViolation:
    """Round 3 fix: missing/unparseable timestamp must count as PIT VIOLATION, not be skipped."""

    def test_missing_timestamp_is_leakage(self):
        """A hit with empty accepted_ts must be counted as leakage."""
        as_of = datetime(2024, 6, 1, tzinfo=timezone.utc)
        hits = [
            RetrievalHit(
                chunk_id="c1", ticker="X", accession="A1", section="s1",
                form_type="10-K", accepted_ts="",
                text="no timestamp", rank=1,
            ),
        ]
        # Currently this passes silently (skips the hit). Must fail.
        with pytest.raises(ValueError, match="PIT leakage|missing timestamp"):
            assert_no_pit_leakage(hits, as_of)

    def test_unparseable_timestamp_is_leakage(self):
        """A hit with unparseable accepted_ts must be counted as leakage."""
        as_of = datetime(2024, 6, 1, tzinfo=timezone.utc)
        hits = [
            RetrievalHit(
                chunk_id="c1", ticker="X", accession="A1", section="s1",
                form_type="10-K", accepted_ts="not-a-date",
                text="bad timestamp", rank=1,
            ),
        ]
        with pytest.raises(ValueError, match="PIT leakage|unparseable"):
            assert_no_pit_leakage(hits, as_of)


class TestScoreAbstentionMissingTimestamp:
    """Round 3 fix: score_abstention must not silently skip hits with missing timestamps."""

    def test_unanswerable_missing_ts_is_leakage(self):
        """An unanswerable item with a hit missing timestamp → future_leakage."""
        from evals.rag_eval.metrics import score_abstention

        item = GoldenItem(
            id="t1", ticker="X", question="q",
            item_type="unanswerable",
            as_of="2024-06-01T00:00:00+00:00",
        )
        hits = [
            RetrievalHit(
                chunk_id="c1", ticker="X", accession="A1", section="s1",
                form_type="10-K", accepted_ts="",
                text="no ts", rank=1,
            ),
        ]
        result = score_abstention(item, hits)
        # Currently this returns "top_hit_present" because the hit is silently skipped.
        # Must be "future_leakage" or the run must abort.
        assert result["abstention_label"] in ("future_leakage",), (
            f"Missing timestamp must be treated as leakage, got {result['abstention_label']}"
        )

    def test_pit_trap_missing_ts_is_leakage(self):
        """A PIT trap with a hit missing timestamp → future_leakage."""
        from evals.rag_eval.metrics import score_abstention

        item = GoldenItem(
            id="t1", ticker="X", question="q",
            item_type="point_in_time_trap",
            as_of="2024-06-01T00:00:00+00:00",
        )
        hits = [
            RetrievalHit(
                chunk_id="c1", ticker="X", accession="A1", section="s1",
                form_type="10-K", accepted_ts="",
                text="no ts", rank=1,
            ),
        ]
        result = score_abstention(item, hits)
        assert result["allowed_top_hit"] is False
        assert result["abstention_label"] in ("future_leakage",), (
            f"Missing timestamp must be treated as leakage, got {result['abstention_label']}"
        )


class TestEndToEndPitFilterBlocksFutureChunks:
    """Round 3 fix: end-to-end test that PIT filter works for the RIGHT reason."""

    def test_future_chunk_not_returned(self, tmp_path):
        """An item whose as_of precedes some chunk's accepted_epoch must not return that chunk."""
        from evals.rag_eval.corpus import JsonlCorpusAdapter

        # Create corpus with one past and one future chunk
        past_epoch = 1704067200  # 2024-01-01
        future_epoch = 1723680000  # 2024-08-15
        lines = [
            json.dumps({"chunk_id": "past-001", "ticker": "X", "chunk_text": "past data",
                        "accepted_epoch": past_epoch, "accession_number": "A1",
                        "filing_section": "s1", "form_type": "10-K"}),
            json.dumps({"chunk_id": "future-001", "ticker": "X", "chunk_text": "future data",
                        "accepted_epoch": future_epoch, "accession_number": "A2",
                        "filing_section": "s2", "form_type": "10-Q"}),
        ]
        corpus_path = tmp_path / "corpus.jsonl"
        corpus_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        # Build embeddings sidecar
        dim = 384
        vecs = np.random.RandomState(42).randn(2, dim).astype(np.float32)
        vecs = vecs / np.linalg.norm(vecs, axis=1, keepdims=True)
        import hashlib
        corpus_content = "\n".join(lines)
        corpus_sha = hashlib.sha256(corpus_content.encode()).hexdigest()
        emb_path = tmp_path / "emb.npz"
        np.savez(
            str(emb_path),
            embeddings=vecs,
            chunk_ids=np.array(["past-001", "future-001"]),
            embedding_model="test",
            dimension=dim,
            normalized=True,
            corpus_sha256=corpus_sha,
        )

        adapter = JsonlCorpusAdapter.from_files(corpus_path, emb_path)

        # as_of = 2024-06-01 (before future chunk)
        item = GoldenItem(
            id="test-pit", ticker="X", question="test question",
            gold_chunk_ids=("past-001",),
            as_of="2024-06-01T00:00:00+00:00",
        )
        config = RetrievalConfig(mode="bm25", ticker_filter=False, top_k=10)

        hits = retrieve_item(item, config, adapter)
        hit_ids = {h.chunk_id for h in hits}
        assert "future-001" not in hit_ids, "Future chunk must be filtered by PIT filter"

    def test_disabling_pit_filter_causes_leakage(self, tmp_path):
        """Disabling the PIT filter must make the leakage gate FAIL."""
        from evals.rag_eval.corpus import JsonlCorpusAdapter

        # Create corpus with one past and one future chunk
        past_epoch = 1704067200  # 2024-01-01
        future_epoch = 1723680000  # 2024-08-15
        lines = [
            json.dumps({"chunk_id": "past-001", "ticker": "X", "chunk_text": "past data",
                        "accepted_epoch": past_epoch, "accession_number": "A1",
                        "filing_section": "s1", "form_type": "10-K"}),
            json.dumps({"chunk_id": "future-001", "ticker": "X", "chunk_text": "future data",
                        "accepted_epoch": future_epoch, "accession_number": "A2",
                        "filing_section": "s2", "form_type": "10-Q"}),
        ]
        corpus_path = tmp_path / "corpus.jsonl"
        corpus_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        # Build embeddings sidecar
        dim = 384
        vecs = np.random.RandomState(42).randn(2, dim).astype(np.float32)
        vecs = vecs / np.linalg.norm(vecs, axis=1, keepdims=True)
        import hashlib
        corpus_content = "\n".join(lines)
        corpus_sha = hashlib.sha256(corpus_content.encode()).hexdigest()
        emb_path = tmp_path / "emb.npz"
        np.savez(
            str(emb_path),
            embeddings=vecs,
            chunk_ids=np.array(["past-001", "future-001"]),
            embedding_model="test",
            dimension=dim,
            normalized=True,
            corpus_sha256=corpus_sha,
        )

        adapter = JsonlCorpusAdapter.from_files(corpus_path, emb_path)

        # as_of = 2024-06-01 (before future chunk)
        item = GoldenItem(
            id="test-pit", ticker="X", question="test question",
            gold_chunk_ids=("past-001",),
            as_of="2024-06-01T00:00:00+00:00",
        )
        config = RetrievalConfig(mode="bm25", ticker_filter=False, top_k=10)

        # Disable PIT filter by patching _pit_filter to pass through all docs
        from api.services import hybrid_retriever as hr

        original_pit_filter = hr._pit_filter

        def _no_pit_filter(docs, as_of=None):
            return docs  # No filtering!

        with patch.object(hr, "_pit_filter", _no_pit_filter):
            hits = retrieve_item(item, config, adapter)

        # Now check leakage — must detect the future chunk
        as_of = item.as_of_datetime()
        with pytest.raises(ValueError, match="PIT leakage"):
            assert_no_pit_leakage(hits, as_of)


class TestRetrieverMetadataHasAcceptedTs:
    """Round 3 fix: verify retriever passes accepted_ts in doc metadata."""

    def test_retriever_doc_metadata_has_accepted_ts(self, tmp_path):
        """The production retriever must include accepted_ts in Document metadata."""
        from evals.rag_eval.corpus import JsonlCorpusAdapter

        epoch = 1705276800  # 2024-01-15
        obj = {"chunk_id": "c1", "ticker": "X", "chunk_text": "hello",
               "accepted_epoch": epoch, "accession_number": "A1",
               "filing_section": "s1", "form_type": "10-K"}
        corpus_path = tmp_path / "corpus.jsonl"
        corpus_path.write_text(json.dumps(obj) + "\n", encoding="utf-8")

        adapter = JsonlCorpusAdapter.from_files(corpus_path, None)

        # Install into production and check metadata
        with install_offline_corpus(adapter):
            import api.services.hybrid_retriever as hr
            from langchain_core.documents import Document

            # The corpus is installed. Check that the Document has accepted_ts.
            docs = hr._bm25_docs
            assert docs is not None
            assert len(docs) > 0
            doc = docs[0]
            assert "accepted_ts" in doc.metadata
            assert doc.metadata["accepted_ts"] != "", (
                "accepted_ts must be populated in Document metadata"
            )
            assert "2024-01-15" in doc.metadata["accepted_ts"]