"""tests/rag/test_rag_eval_round5.py — Round 5 fix: audit report must not lie.

When _pit_filter is disabled the report must show pit_leakage_total > 0 and
status FAIL.  The previous code used ir.leakage_count = -1 (sentinel) which
was silently skipped by `if ir.leakage_count > 0`, producing a report that
claimed "Total leakage: 0 PASS" even when chunks leaked.

This test MUST FAIL on the pre-fix HEAD (where leakage_count was set to -1).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "rag_eval"


class TestDisabledPitFilterReportShowsLeakage:
    """Round 5: disabling _pit_filter must make the report honest about leakage."""

    def test_report_shows_leakage_when_pit_filter_disabled(self, tmp_path, monkeypatch):
        """With _pit_filter disabled, the JSON report must show pit_leakage_total > 0
        and status FAIL.  The Markdown must contain FAIL, not PASS.  Exit code nonzero."""
        # Build corpus: 2 past chunks, 1 future chunk
        past_epoch = 1704067200   # 2024-01-01
        past_epoch2 = 1706745600  # 2024-02-01
        future_epoch = 1723680000  # 2024-08-15
        lines = [
            json.dumps({"chunk_id": "past-001", "ticker": "X", "chunk_text": "past data one",
                         "accepted_epoch": past_epoch, "accession_number": "A1",
                         "filing_section": "s1", "form_type": "10-K"}),
            json.dumps({"chunk_id": "past-002", "ticker": "X", "chunk_text": "past data two",
                         "accepted_epoch": past_epoch2, "accession_number": "A2",
                         "filing_section": "s2", "form_type": "10-K"}),
            json.dumps({"chunk_id": "future-001", "ticker": "X", "chunk_text": "future data",
                         "accepted_epoch": future_epoch, "accession_number": "A3",
                         "filing_section": "s3", "form_type": "10-Q"}),
        ]
        corpus_path = tmp_path / "corpus.jsonl"
        corpus_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        # Build embeddings sidecar
        dim = 384
        vecs = np.random.RandomState(42).randn(3, dim).astype(np.float32)
        vecs = vecs / np.linalg.norm(vecs, axis=1, keepdims=True)
        corpus_content = "\n".join(lines)
        corpus_sha = hashlib.sha256(corpus_content.encode()).hexdigest()
        emb_path = tmp_path / "emb.npz"
        np.savez(
            str(emb_path),
            embeddings=vecs,
            chunk_ids=np.array(["past-001", "past-002", "future-001"]),
            embedding_model="BAAI/bge-small-en-v1.5",
            dimension=dim,
            normalized=True,
            corpus_sha256=corpus_sha,
        )

        # Golden item: as_of before future chunk
        golden_lines = [
            json.dumps({"id": "pit-leak-test", "ticker": "X",
                         "question": "What is the data?",
                         "gold_chunk_ids": ["past-001"],
                         "item_type": "answerable",
                         "as_of": "2024-06-01T00:00:00+00:00"}),
        ]
        golden_path = tmp_path / "golden.jsonl"
        golden_path.write_text("\n".join(golden_lines) + "\n", encoding="utf-8")

        # Disable _pit_filter by monkeypatching it to return all docs
        import api.services.hybrid_retriever as hr

        def _no_pit_filter(docs, as_of=None):
            return docs

        monkeypatch.setattr(hr, "_pit_filter", _no_pit_filter)

        # Run the harness in-process
        from evals.rag_eval.cli import main

        output_dir = tmp_path / "results"
        exit_code = main([
            "--golden", str(golden_path),
            "--corpus", str(corpus_path),
            "--embeddings", str(emb_path),
            "--adapter", "jsonl",
            "--mode", "bm25",
            "--ticker-filter", "off",
            "--top-k", "10",
            "--output-dir", str(output_dir),
        ])

        # Exit code must be nonzero
        assert exit_code != 0, "Harness must exit nonzero when PIT leakage is detected"

        # Read the JSON report
        json_files = list(output_dir.glob("*.json"))
        assert len(json_files) >= 1, f"No JSON report found in {output_dir}"
        report = json.loads(json_files[0].read_text(encoding="utf-8"))

        # pit_leakage_total must be > 0 — the REAL count, not the -1 sentinel
        assert report["pit_leakage_total"] > 0, (
            f"pit_leakage_total must be > 0 when _pit_filter is disabled, "
            f"got {report['pit_leakage_total']}"
        )

        # status must be FAIL
        assert report.get("status") == "FAIL", (
            f"Report status must be FAIL when leakage detected, got {report.get('status')!r}"
        )

        # Read the Markdown report
        md_files = list(output_dir.glob("*.md"))
        assert len(md_files) >= 1, f"No Markdown report found in {output_dir}"
        md_content = md_files[0].read_text(encoding="utf-8")

        # Markdown must contain FAIL, not claim PASS
        assert "FAIL" in md_content, "Markdown report must contain 'FAIL'"
        assert "**Total leakage: 0** PASS" not in md_content, (
            "Markdown must not claim 'Total leakage: 0 PASS' when leakage exists"
        )

    def test_report_shows_pass_when_no_leakage(self, tmp_path):
        """Without mutation, the report must show pit_leakage_total == 0 and status PASS."""
        from evals.rag_eval.cli import main

        # Use the existing smoke fixtures (no mutation)
        corpus_path = FIXTURE_DIR / "corpus_smoke.jsonl"
        emb_path = FIXTURE_DIR / "embeddings_smoke.npz"
        golden_path = FIXTURE_DIR / "golden_smoke.jsonl"

        output_dir = tmp_path / "results"
        exit_code = main([
            "--golden", str(golden_path),
            "--corpus", str(corpus_path),
            "--embeddings", str(emb_path),
            "--adapter", "jsonl",
            "--mode", "bm25",
            "--ticker-filter", "off",
            "--top-k", "5",
            "--output-dir", str(output_dir),
        ])

        assert exit_code == 0, "Harness must exit 0 when no leakage"

        json_files = list(output_dir.glob("*.json"))
        assert len(json_files) >= 1
        report = json.loads(json_files[0].read_text(encoding="utf-8"))

        assert report["pit_leakage_total"] == 0
        assert report.get("status") == "PASS"

    def test_leaked_chunk_ids_populated_in_report(self, tmp_path, monkeypatch):
        """When leakage is detected, leaked_chunk_ids_by_config must be non-empty."""
        past_epoch = 1704067200
        future_epoch = 1723680000
        lines = [
            json.dumps({"chunk_id": "past-001", "ticker": "X", "chunk_text": "past",
                         "accepted_epoch": past_epoch, "accession_number": "A1",
                         "filing_section": "s1", "form_type": "10-K"}),
            json.dumps({"chunk_id": "future-001", "ticker": "X", "chunk_text": "future",
                         "accepted_epoch": future_epoch, "accession_number": "A2",
                         "filing_section": "s2", "form_type": "10-Q"}),
        ]
        corpus_path = tmp_path / "corpus.jsonl"
        corpus_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        dim = 384
        vecs = np.random.RandomState(42).randn(2, dim).astype(np.float32)
        vecs = vecs / np.linalg.norm(vecs, axis=1, keepdims=True)
        corpus_content = "\n".join(lines)
        corpus_sha = hashlib.sha256(corpus_content.encode()).hexdigest()
        emb_path = tmp_path / "emb.npz"
        np.savez(
            str(emb_path),
            embeddings=vecs,
            chunk_ids=np.array(["past-001", "future-001"]),
            embedding_model="BAAI/bge-small-en-v1.5",
            dimension=dim,
            normalized=True,
            corpus_sha256=corpus_sha,
        )

        golden_lines = [
            json.dumps({"id": "pit-test", "ticker": "X", "question": "data?",
                         "gold_chunk_ids": ["past-001"], "item_type": "answerable",
                         "as_of": "2024-06-01T00:00:00+00:00"}),
        ]
        golden_path = tmp_path / "golden.jsonl"
        golden_path.write_text("\n".join(golden_lines) + "\n", encoding="utf-8")

        import api.services.hybrid_retriever as hr
        monkeypatch.setattr(hr, "_pit_filter", lambda docs, as_of=None: docs)

        from evals.rag_eval.cli import main

        output_dir = tmp_path / "results"
        main([
            "--golden", str(golden_path),
            "--corpus", str(corpus_path),
            "--embeddings", str(emb_path),
            "--adapter", "jsonl",
            "--mode", "bm25",
            "--ticker-filter", "off",
            "--top-k", "10",
            "--output-dir", str(output_dir),
        ])

        json_files = list(output_dir.glob("*.json"))
        report = json.loads(json_files[0].read_text(encoding="utf-8"))

        # leaked_chunk_ids_by_config must contain the leaked chunk
        ids_by_cfg = report.get("leaked_chunk_ids_by_config", {})
        assert len(ids_by_cfg) > 0, "leaked_chunk_ids_by_config must be non-empty"
        all_leaked = [cid for ids in ids_by_cfg.values() for cid in ids]
        assert "future-001" in all_leaked, (
            f"future-001 must appear in leaked chunk IDs, got {all_leaked}"
        )

    def test_no_sentinel_leakage_count_in_report(self, tmp_path, monkeypatch):
        """No item_row may have leakage_count == -1 (the old sentinel)."""
        past_epoch = 1704067200
        future_epoch = 1723680000
        lines = [
            json.dumps({"chunk_id": "past-001", "ticker": "X", "chunk_text": "past",
                         "accepted_epoch": past_epoch, "accession_number": "A1",
                         "filing_section": "s1", "form_type": "10-K"}),
            json.dumps({"chunk_id": "future-001", "ticker": "X", "chunk_text": "future",
                         "accepted_epoch": future_epoch, "accession_number": "A2",
                         "filing_section": "s2", "form_type": "10-Q"}),
        ]
        corpus_path = tmp_path / "corpus.jsonl"
        corpus_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        dim = 384
        vecs = np.random.RandomState(42).randn(2, dim).astype(np.float32)
        vecs = vecs / np.linalg.norm(vecs, axis=1, keepdims=True)
        corpus_content = "\n".join(lines)
        corpus_sha = hashlib.sha256(corpus_content.encode()).hexdigest()
        emb_path = tmp_path / "emb.npz"
        np.savez(
            str(emb_path),
            embeddings=vecs,
            chunk_ids=np.array(["past-001", "future-001"]),
            embedding_model="BAAI/bge-small-en-v1.5",
            dimension=dim,
            normalized=True,
            corpus_sha256=corpus_sha,
        )

        golden_lines = [
            json.dumps({"id": "pit-test", "ticker": "X", "question": "data?",
                         "gold_chunk_ids": ["past-001"], "item_type": "answerable",
                         "as_of": "2024-06-01T00:00:00+00:00"}),
        ]
        golden_path = tmp_path / "golden.jsonl"
        golden_path.write_text("\n".join(golden_lines) + "\n", encoding="utf-8")

        import api.services.hybrid_retriever as hr
        monkeypatch.setattr(hr, "_pit_filter", lambda docs, as_of=None: docs)

        from evals.rag_eval.cli import main

        output_dir = tmp_path / "results"
        main([
            "--golden", str(golden_path),
            "--corpus", str(corpus_path),
            "--embeddings", str(emb_path),
            "--adapter", "jsonl",
            "--mode", "bm25",
            "--ticker-filter", "off",
            "--top-k", "10",
            "--output-dir", str(output_dir),
        ])

        json_files = list(output_dir.glob("*.json"))
        report = json.loads(json_files[0].read_text(encoding="utf-8"))

        for row in report.get("item_rows", []):
            assert row.get("leakage_count", 0) != -1, (
                f"Item {row.get('item_id')} has leakage_count == -1 (sentinel). "
                f"Must be the real count."
            )