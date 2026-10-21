"""Tests for ``ml/monitoring.py`` + ``ml/run_drift_report.py`` (Evidently drift).

Evidently is an OPTIONAL dev dependency, so everything that does not need it
runs without it; the drift-report tests use ``pytest.importorskip("evidently")``.

The threshold logic in ``ml.monitoring.summarize_drift`` is the mutation target
for the build request: removing it must fail ``test_summarize_drift_threshold_logic``
and the shifted/unshifted drift tests.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from ml.features import FEATURE_SETS
from ml.monitoring import (
    DRIFT_LABEL,
    SUMMARY_BLOCK_KEYS,
    SUMMARY_KEYS,
    build_summary,
    load_feature_frame,
    run_drift_report,
    split_windows,
    summarize_drift,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
CLI = REPO_ROOT / "ml" / "run_drift_report.py"


# ── Clean import / CLI without evidently ─────────────────────────────────────


def test_module_imports_cleanly_without_evidently():
    """ml.monitoring and ml.run_drift_report must import with evidently blocked."""
    code = (
        "import sys\n"
        "class _BlockEvidently:\n"
        "    def find_spec(self, name, path=None, target=None):\n"
        "        if name.split('.')[0] == 'evidently':\n"
        "            raise ModuleNotFoundError(\"No module named 'evidently'\")\n"
        "        return None\n"
        "sys.meta_path.insert(0, _BlockEvidently())\n"
        "import ml.monitoring\n"
        "import ml.run_drift_report\n"
        "assert 'evidently' not in sys.modules, 'evidently must be imported lazily'\n"
        "print('OK')\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code], cwd=REPO_ROOT, capture_output=True, text=True
    )
    assert proc.returncode == 0, proc.stderr
    assert "OK" in proc.stdout


def test_run_drift_report_help_works_without_evidently():
    proc = subprocess.run(
        [sys.executable, str(CLI), "--help"], cwd=REPO_ROOT, capture_output=True, text=True
    )
    assert proc.returncode == 0, proc.stderr
    assert "--drift-share-threshold" in proc.stdout
    assert "--reference-frac" in proc.stdout
    assert DRIFT_LABEL in proc.stdout


# ── Loading the baseline-signal feature frame ────────────────────────────────


@pytest.mark.timeout(120)
def test_load_feature_frame_synthetic_matches_baseline_feature_set():
    frame = load_feature_frame("synthetic", seed=11, n_symbols=4, n_bars=60)
    assert not frame.empty
    for col in FEATURE_SETS["D"]:
        assert col in frame.columns
    assert {"symbol", "prediction_ts", "label"} <= set(frame.columns)


@pytest.mark.timeout(120)
def test_load_feature_frame_rejects_missing_feature_columns():
    frame = load_feature_frame("synthetic", seed=11, n_symbols=4, n_bars=60)
    broken = frame.drop(columns=["rsi_14"])
    with pytest.raises(ValueError, match="missing required columns"):
        load_feature_frame(broken)


@pytest.mark.timeout(120)
def test_split_windows_is_temporal_and_disjoint():
    frame = load_feature_frame("synthetic", seed=11, n_symbols=4, n_bars=60)
    reference, current = split_windows(frame, reference_frac=0.6)
    assert len(reference) > 0 and len(current) > 0
    assert reference["prediction_ts"].max() < current["prediction_ts"].min()
    assert len(reference) + len(current) == len(frame)


def test_split_windows_rejects_bad_reference_frac():
    frame = pd.DataFrame({"prediction_ts": [1, 2, 3]})
    with pytest.raises(ValueError, match="reference_frac"):
        split_windows(frame, reference_frac=1.0)


# ── Summary schema + threshold logic (pure Python, no evidently) ─────────────


def test_summarize_drift_threshold_logic():
    """The share-based dataset-drift threshold (mutation target)."""
    none_drifted = summarize_drift({"a": False, "b": False})
    assert none_drifted["share_of_drifted_features"] == 0.0
    assert none_drifted["n_drifted_features"] == 0
    assert none_drifted["dataset_drift"] is False

    all_drifted = summarize_drift({"a": True, "b": True})
    assert all_drifted["share_of_drifted_features"] == 1.0
    assert all_drifted["dataset_drift"] is True

    # Boundary: a share exactly at the threshold counts as dataset drift (>=).
    half = summarize_drift({"a": True, "b": False}, drift_share_threshold=0.5)
    assert half["share_of_drifted_features"] == 0.5
    assert half["dataset_drift"] is True

    third = summarize_drift(
        {"a": True, "b": False, "c": False}, drift_share_threshold=0.5
    )
    assert third["share_of_drifted_features"] == pytest.approx(1 / 3)
    assert third["dataset_drift"] is False

    # A single drifted feature is an observation, not a dataset-level alert.
    one_of_four = summarize_drift(
        {"a": True, "b": False, "c": False, "d": False}, drift_share_threshold=0.5
    )
    assert one_of_four["dataset_drift"] is False

    strict = summarize_drift({"a": True, "b": True}, drift_share_threshold=1.0)
    assert strict["dataset_drift"] is True
    relaxed = summarize_drift({"a": True, "b": False}, drift_share_threshold=0.9)
    assert relaxed["dataset_drift"] is False


def test_summarize_drift_rejects_empty_flags_and_bad_threshold():
    with pytest.raises(ValueError, match="must not be empty"):
        summarize_drift({})
    with pytest.raises(ValueError, match="drift_share_threshold"):
        summarize_drift({"a": True}, drift_share_threshold=0.0)
    with pytest.raises(ValueError, match="drift_share_threshold"):
        summarize_drift({"a": True}, drift_share_threshold=1.5)


def test_build_summary_schema():
    summary = build_summary(
        feature_drift=summarize_drift({"a": True, "b": False}),
        prediction_drift=summarize_drift({"probability": False}),
        reference_rows=10,
        current_rows=5,
        prediction_columns=["probability"],
        source="synthetic window split",
        tool={"name": "evidently", "version": "0.7.23"},
        generated_at="2026-01-01T00:00:00+00:00",
    )
    assert tuple(summary) == SUMMARY_KEYS
    assert summary["label"] == DRIFT_LABEL
    assert summary["tool"] == {"name": "evidently", "version": "0.7.23"}
    assert summary["windows"] == {
        "reference_rows": 10,
        "current_rows": 5,
        "prediction_columns": ["probability"],
    }
    assert summary["html_report"] is None
    for block in ("feature_drift", "prediction_drift"):
        assert tuple(summary[block]) == SUMMARY_BLOCK_KEYS
    json.dumps(summary)  # must be JSON-serializable


# ── Drift detection (needs evidently) ────────────────────────────────────────


@pytest.fixture(scope="module")
def drift_windows():
    """(reference, unshifted copy of reference, reference shifted by +3.0)."""
    frame = load_feature_frame("synthetic", seed=7, n_symbols=6, n_bars=120)
    reference, _current = split_windows(frame, reference_frac=0.6)
    unshifted = reference.copy()
    shifted = reference.copy()
    numeric = [c for c in FEATURE_SETS["D"] if pd.api.types.is_numeric_dtype(shifted[c])]
    shifted[numeric] = shifted[numeric] + 3.0
    return reference, unshifted, shifted


@pytest.mark.timeout(180)
def test_unshifted_copy_reports_no_drift(drift_windows):
    pytest.importorskip("evidently")
    reference, unshifted, _shifted = drift_windows
    drift = run_drift_report(reference, unshifted)
    assert drift.summary["label"] == DRIFT_LABEL

    feature_drift = drift.summary["feature_drift"]
    assert feature_drift["dataset_drift"] is False
    assert feature_drift["share_of_drifted_features"] == 0.0
    assert set(feature_drift["per_feature_drift"].values()) == {False}

    prediction_drift = drift.summary["prediction_drift"]
    assert prediction_drift["dataset_drift"] is False
    assert prediction_drift["per_feature_drift"]["probability"] is False


@pytest.mark.timeout(180)
def test_shifted_window_reports_feature_and_prediction_drift(drift_windows):
    pytest.importorskip("evidently")
    reference, _unshifted, shifted = drift_windows
    drift = run_drift_report(reference, shifted)

    feature_drift = drift.summary["feature_drift"]
    assert feature_drift["dataset_drift"] is True
    assert feature_drift["share_of_drifted_features"] >= feature_drift["drift_share_threshold"]
    assert feature_drift["per_feature_drift"]["return_1m"] is True

    prediction_drift = drift.summary["prediction_drift"]
    assert prediction_drift["dataset_drift"] is True
    assert prediction_drift["per_feature_drift"]["probability"] is True


@pytest.mark.timeout(180)
def test_written_summary_json_schema_and_label(tmp_path, drift_windows):
    pytest.importorskip("evidently")
    reference, unshifted, _shifted = drift_windows
    drift = run_drift_report(reference, unshifted)
    paths = drift.write(tmp_path)

    assert paths["html"].exists() and paths["html"].stat().st_size > 0
    summary = json.loads(paths["json"].read_text(encoding="utf-8"))
    assert tuple(summary) == SUMMARY_KEYS
    assert summary["label"] == DRIFT_LABEL
    assert summary["html_report"] == paths["html"].name
    assert summary["tool"]["name"] == "evidently"
    assert summary["windows"]["reference_rows"] == len(reference)
    assert summary["windows"]["current_rows"] == len(reference)
    assert DRIFT_LABEL in paths["html"].read_text(encoding="utf-8")


@pytest.mark.timeout(300)
def test_cli_writes_artifacts_under_output_dir(tmp_path):
    pytest.importorskip("evidently")
    proc = subprocess.run(
        [
            sys.executable,
            str(CLI),
            "--output-dir",
            str(tmp_path),
            "--n-symbols",
            "4",
            "--n-bars",
            "60",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert (tmp_path / "drift_report.html").exists()
    summary = json.loads((tmp_path / "drift_summary.json").read_text(encoding="utf-8"))
    assert tuple(summary) == SUMMARY_KEYS
    assert summary["label"] == DRIFT_LABEL
    assert DRIFT_LABEL in proc.stdout
