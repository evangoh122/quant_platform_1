"""tests/rag/test_rag_eval_report.py — Tests for report generation."""
from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import json
import pytest

from evals.rag_eval.models import (
    GoldenItem,
    ItemResult,
    RetrievalConfig,
    RetrievalHit,
    RunReport,
)
from evals.rag_eval.report import build_report, render_markdown, write_report


def _make_report(pit_leakage_total=0) -> RunReport:
    item = GoldenItem(id="t1", ticker="NVDA", question="q", gold_chunk_ids=("c1",))
    config = RetrievalConfig(mode="bm25", ticker_filter=True)
    ir = ItemResult(
        item=item,
        config=config,
        hits=[RetrievalHit(
            chunk_id="c1", ticker="NVDA", accession="A1", section="s1",
            form_type="10-K", accepted_ts="2024-01-01T00:00:00+00:00",
            text="text", rank=1,
        )],
        metrics={"recall_at_1": 1.0, "recall_at_5": 1.0, "mrr_at_10": 1.0},
        leakage_count=pit_leakage_total,
    )
    return RunReport(
        run_id="test-run-001",
        git_sha="abc1234",
        corpus_sha256="deadbeef" * 8,
        golden_sha256="cafebabe" * 8,
        embedding_model="BAAI/bge-small-en-v1.5",
        embedding_dimension=384,
        rrf_k=60,
        candidate_depth_multiplier=2,
        top_k_values=[10],
        seed=1729,
        adapter_type="jsonl",
        cli_args={"mode": "all"},
        timestamp=datetime.now(timezone.utc).isoformat(),
        environment={"platform": "linux"},
        item_results=[ir],
        overall_metrics={"recall_at_5": 0.8, "mrr_at_10": 0.7},
        per_type_metrics={"answerable": {"recall_at_5": 0.8}},
        per_ticker_metrics={"NVDA": {"recall_at_5": 0.9}},
        bootstrap_cis={"recall_at_5": {"mean": 0.8, "lower": 0.6, "upper": 0.95, "n": 5}},
        abstention_results={},
        pit_leakage_total=pit_leakage_total,
        pit_leakage_by_config={},
    )


class TestReportHasBreakdownsAndConfig:
    """test_report_has_breakdowns_cis_and_config"""

    def test_build_report_contains_config(self):
        report = build_report(_make_report())
        assert report["run_id"] == "test-run-001"
        assert report["git_sha"] == "abc1234"
        assert report["embedding_model"] == "BAAI/bge-small-en-v1.5"
        assert report["rrf_k"] == 60

    def test_build_report_contains_metrics(self):
        report = build_report(_make_report())
        assert report["overall_metrics"]["recall_at_5"] == 0.8

    def test_build_report_contains_item_rows(self):
        report = build_report(_make_report())
        assert len(report["item_rows"]) == 1
        assert report["item_rows"][0]["item_id"] == "t1"

    def test_markdown_contains_sections(self):
        report = build_report(_make_report())
        md = render_markdown(report)
        assert "Configuration" in md
        assert "PIT Leakage Gate" in md
        assert "Overall Metrics" in md

    def test_markdown_contains_bootstrap_ci(self):
        report = build_report(_make_report())
        md = render_markdown(report)
        assert "Bootstrap" in md
        assert "0.8" in md


class TestReportRefusesSuccessWithPitLeak:
    """test_report_refuses_success_with_pit_leak"""

    def test_leakage_shown_in_report(self):
        report = build_report(_make_report(pit_leakage_total=2))
        assert report["pit_leakage_total"] == 2

    def test_markdown_shows_fail(self):
        report = build_report(_make_report(pit_leakage_total=2))
        md = render_markdown(report)
        assert "FAIL" in md


class TestReportWritesJsonAndMarkdown:
    """test_report_writes_json_and_markdown"""

    def test_write_creates_files(self, tmp_path):
        report = build_report(_make_report())
        json_path, md_path = write_report(report, tmp_path, date(2024, 6, 1))
        assert json_path.exists()
        assert md_path.exists()
        assert json_path.suffix == ".json"
        assert md_path.suffix == ".md"

    def test_write_non_overwrite(self, tmp_path):
        """Writing to the same date twice adds a suffix."""
        report = build_report(_make_report())
        json_path1, md_path1 = write_report(report, tmp_path, date(2024, 6, 1))
        report["run_id"] = "test-run-002"
        json_path2, md_path2 = write_report(report, tmp_path, date(2024, 6, 1))
        assert json_path1 != json_path2
        assert json_path1.exists()
        assert json_path2.exists()

    def test_json_is_valid(self, tmp_path):
        report = build_report(_make_report())
        json_path, _ = write_report(report, tmp_path, date(2024, 6, 1))
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["run_id"] == "test-run-001"