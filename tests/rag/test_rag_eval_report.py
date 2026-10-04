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


class TestReportTextStripping:
    """test_report_text_stripping_and_include_text_flag"""

    def _make_report_with_text(self, text: str) -> RunReport:
        item = GoldenItem(id="t1", ticker="NVDA", question="q", gold_chunk_ids=("c1",))
        config = RetrievalConfig(mode="bm25", ticker_filter=True)
        ir = ItemResult(
            item=item,
            config=config,
            hits=[RetrievalHit(
                chunk_id="c1", ticker="NVDA", accession="A1", section="s1",
                form_type="10-K", accepted_ts="2024-01-01T00:00:00+00:00",
                text=text, rank=1,
            )],
            metrics={"recall_at_1": 1.0},
        )
        return RunReport(
            run_id="test-run-text",
            git_sha="abc1234",
            adapter_type="jsonl",
            cli_args={"mode": "all"},
            timestamp=datetime.now(timezone.utc).isoformat(),
            item_results=[ir],
            overall_metrics={"recall_at_5": 0.8},
        )

    def test_default_report_has_no_text_field(self):
        """Default report JSON must not contain 'text' or 'chunk_text' in hits."""
        long_text = "The company reported revenue of $42 billion for fiscal year 2024."
        report = build_report(self._make_report_with_text(long_text))
        report_json = json.dumps(report)
        assert "text" not in report_json or '"text"' not in report_json
        assert "chunk_text" not in report_json

    def test_default_report_has_no_raw_sentence(self):
        """Default report must not leak raw filing text sentences."""
        secret_sentence = "NVIDIA reported record quarterly revenue of $26.5 billion"
        report = build_report(self._make_report_with_text(secret_sentence))
        report_json = json.dumps(report)
        assert secret_sentence not in report_json

    def test_include_text_truncates_to_200(self):
        """With --include-text, hit text is truncated to 200 chars."""
        long_text = "x" * 500
        report = build_report(self._make_report_with_text(long_text), include_text=True)
        hits = report["item_results"][0]["hits"]
        assert len(hits[0]["text"]) == 200

    def test_include_text_preserves_short_text(self):
        """With --include-text, short text is preserved."""
        short_text = "short text"
        report = build_report(self._make_report_with_text(short_text), include_text=True)
        hits = report["item_results"][0]["hits"]
        assert hits[0]["text"] == "short text"

    def test_cli_args_paths_redacted_to_basename(self):
        """Absolute paths in cli_args are redacted to basename."""
        rr = RunReport(
            run_id="test",
            cli_args={
                "golden": "/home/user/project/data/golden.jsonl",
                "corpus": "relative/corpus.jsonl",
                "mode": "all",
            },
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        report = build_report(rr)
        assert report["cli_args"]["golden"] == "golden.jsonl"
        assert report["cli_args"]["corpus"] == "relative/corpus.jsonl"
        assert report["cli_args"]["mode"] == "all"

    def test_cli_args_path_objects_redacted_to_basename(self):
        """Pathlib.Path objects in cli_args are redacted to basename string."""
        rr = RunReport(
            run_id="test",
            cli_args={
                "golden": Path("/home/user/project/data/golden.jsonl"),
                "corpus": Path("relative/corpus.jsonl"),
                "mode": "all",
            },
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        report = build_report(rr)
        # Path objects must be converted to plain strings (basename)
        assert report["cli_args"]["golden"] == "golden.jsonl"
        assert isinstance(report["cli_args"]["golden"], str)
        # Relative paths should not be changed (use Path to normalize separators)
        assert Path(report["cli_args"]["corpus"]) == Path("relative/corpus.jsonl")
        assert report["cli_args"]["mode"] == "all"

    def test_write_json_has_no_text_in_hits(self, tmp_path):
        """Written JSON report file has no text field in hits."""
        report = build_report(self._make_report_with_text("secret content"))
        json_path, _ = write_report(report, tmp_path, date(2024, 6, 1))
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        hits = data["item_results"][0]["hits"]
        assert "text" not in hits[0]
        assert "chunk_text" not in hits[0]


class TestRecursiveRedaction:
    """Recursive redaction of paths in nested cli_args structures."""

    def test_list_of_paths_redacted(self):
        """List of absolute paths redacted to basenames."""
        rr = RunReport(
            run_id="test",
            cli_args={"files": ["/home/x/a.jsonl", "/tmp/b.jsonl"]},
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        report = build_report(rr)
        assert report["cli_args"]["files"] == ["a.jsonl", "b.jsonl"]

    def test_tuple_of_paths_redacted(self):
        """Tuple of absolute paths redacted to basenames (preserves tuple type)."""
        rr = RunReport(
            run_id="test",
            cli_args={"files": ("/home/x/a.jsonl", "/tmp/b.jsonl")},
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        report = build_report(rr)
        result = report["cli_args"]["files"]
        assert isinstance(result, tuple)
        assert result == ("a.jsonl", "b.jsonl")

    def test_set_of_paths_redacted(self):
        """Set of absolute paths redacted to basenames."""
        rr = RunReport(
            run_id="test",
            cli_args={"files": {"/home/x/a.jsonl", "/tmp/b.jsonl"}},
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        report = build_report(rr)
        assert report["cli_args"]["files"] == {"a.jsonl", "b.jsonl"}

    def test_dict_with_path_values_redacted(self):
        """Dict with path values redacted to basenames."""
        rr = RunReport(
            run_id="test",
            cli_args={"mapping": {"golden": "/home/x/golden.jsonl", "corpus": "/tmp/corpus.jsonl"}},
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        report = build_report(rr)
        assert report["cli_args"]["mapping"]["golden"] == "golden.jsonl"
        assert report["cli_args"]["mapping"]["corpus"] == "corpus.jsonl"

    def test_nested_list_in_dict_redacted(self):
        """Nested list inside dict: paths redacted to basenames."""
        rr = RunReport(
            run_id="test",
            cli_args={"a": [Path("/home/x/y.jsonl"), "/tmp/a/b.jsonl"]},
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        report = build_report(rr)
        assert report["cli_args"]["a"] == ["y.jsonl", "b.jsonl"]

    def test_deeply_nested_redaction(self):
        """Deeply nested structure: all paths redacted."""
        rr = RunReport(
            run_id="test",
            cli_args={
                "level1": {
                    "level2": ["/home/x/deep.jsonl", {"inner": "/tmp/inner.jsonl"}],
                }
            },
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        report = build_report(rr)
        assert report["cli_args"]["level1"]["level2"][0] == "deep.jsonl"
        assert report["cli_args"]["level1"]["level2"][1]["inner"] == "inner.jsonl"

    def test_pathlib_path_in_nested_redacted(self):
        """Pathlib.Path objects in nested structures redacted to string basenames."""
        rr = RunReport(
            run_id="test",
            cli_args={"paths": [Path("/home/x/a.jsonl"), Path("/tmp/b.jsonl")]},
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        report = build_report(rr)
        result = report["cli_args"]["paths"]
        assert result == ["a.jsonl", "b.jsonl"]
        assert isinstance(result[0], str)

    def test_relative_paths_preserved_in_nested(self):
        """Relative paths in nested structures preserved as strings."""
        rr = RunReport(
            run_id="test",
            cli_args={"files": ["relative/path.jsonl", "/home/x/abs.jsonl"]},
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        report = build_report(rr)
        assert report["cli_args"]["files"][0] == "relative/path.jsonl"
        assert report["cli_args"]["files"][1] == "abs.jsonl"


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "rag_eval"


class TestCliEndToEndReport:
    """End-to-end: drive cli.main with real absolute Path args, verify no path leaks."""

    def test_report_no_path_leaks(self, tmp_path):
        """JSON and Markdown reports must contain no absolute paths or PosixPath repr."""
        from evals.rag_eval.cli import main

        corpus_path = FIXTURE_DIR / "corpus_smoke.jsonl"
        emb_path = FIXTURE_DIR / "embeddings_smoke.npz"
        golden_path = FIXTURE_DIR / "golden_smoke.jsonl"

        # Use absolute paths for output_dir (real absolute Path args)
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

        assert exit_code == 0, f"Harness must exit 0, got {exit_code}"

        # Read JSON report
        json_files = list(output_dir.glob("*.json"))
        assert len(json_files) >= 1, f"No JSON report in {output_dir}"
        json_content = json_files[0].read_text(encoding="utf-8")

        # Read Markdown report
        md_files = list(output_dir.glob("*.md"))
        assert len(md_files) >= 1, f"No Markdown report in {output_dir}"
        md_content = md_files[0].read_text(encoding="utf-8")

        # Assert no path leaks in either report
        tmp_str = str(tmp_path)

        for content, label in [(json_content, "JSON"), (md_content, "Markdown")]:
            # No tmp_path leaked
            assert tmp_str not in content, (
                f"{label} report contains tmp_path: {tmp_str}"
            )
            # No "/home" path component
            assert "/home" not in content, (
                f"{label} report contains '/home' path"
            )
            # No PosixPath repr
            assert "PosixPath" not in content, (
                f"{label} report contains 'PosixPath' repr"
            )