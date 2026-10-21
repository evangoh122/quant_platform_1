"""Evidently drift monitoring for the baseline-signal ML lane.

Pipeline demonstration; baseline signals, no edge claimed.

Two drift questions are answered for the baseline-signal feature frame used by
``ml/features.py`` / ``ml/train.py`` / ``ml/score.py``:

  1. **Feature drift** — did the model-input distribution move between a
     *reference* window and a *current* window?
  2. **Prediction drift** — did the baseline signal itself (the ``probability``
     column that ``ml/score.py`` writes to ``gold_trading_signals``) move?

Nothing here re-implements the feature pipeline: frames come from
``ml/synthetic_data.make_synthetic_matrix`` (or a CSV/Parquet snapshot of the
same schema), the design matrix is ``ml.train.prepare_features``, and the
prediction column is produced by ``ml.score.score_rows``.

Evidently is an **optional** dependency (pinned in ``requirements-dev.txt``
only) and is imported lazily inside the functions that need it, so
``import ml.monitoring`` and the pure-Python helpers below work without it.

Outputs (see ``DriftReport.write``): an HTML report and a small JSON summary
with per-feature drift flags and the share of drifted features, written under
``ml/results/`` (gitignored; see ``ml/results/.gitignore``).
"""

from __future__ import annotations

import html as _html
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple, Union

import pandas as pd

from ml.features import FEATURE_SETS

# Shown in the JSON summary, on the HTML report and on the CLI output.
DRIFT_LABEL = "pipeline demonstration; baseline signals, no edge claimed"

# ``dataset_drift`` fires when at least this share of the features drifted.
DEFAULT_DRIFT_SHARE_THRESHOLD = 0.5
# Per-feature statistical-test threshold handed to Evidently (its own default).
DEFAULT_STATTEST_THRESHOLD = 0.05

# Prediction columns checked for prediction drift. ``probability`` is the
# baseline signal produced through ``ml.score.score_rows``.
PREDICTION_COLUMNS: Tuple[str, ...] = ("probability",)

SUMMARY_KEYS: Tuple[str, ...] = (
    "label",
    "generated_at",
    "tool",
    "source",
    "windows",
    "feature_drift",
    "prediction_drift",
    "html_report",
)

SUMMARY_BLOCK_KEYS: Tuple[str, ...] = (
    "per_feature_drift",
    "n_features",
    "n_drifted_features",
    "share_of_drifted_features",
    "drift_share_threshold",
    "dataset_drift",
)

Source = Union[str, Path, pd.DataFrame, None]


# ── Optional dependency ──────────────────────────────────────────────────────


def _require_evidently() -> Tuple[Any, Any]:
    """Import Evidently lazily; fail with a clear message when it is absent."""
    try:
        from evidently import Report
        from evidently.presets import DataDriftPreset
    except ImportError as exc:  # pragma: no cover - only without evidently
        raise ImportError(
            "evidently is required to compute drift reports but is not "
            "installed. Install the optional dev dependency pinned in "
            "requirements-dev.txt (e.g. `pip install -r requirements-dev.txt`)."
        ) from exc
    return Report, DataDriftPreset


def _evidently_version() -> str:
    import evidently

    return str(getattr(evidently, "__version__", "unknown"))


# ── Loading the baseline-signal feature frame ────────────────────────────────


def validate_feature_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Check a frame carries the baseline-signal schema and return it as-is."""
    required = list(FEATURE_SETS["D"]) + ["symbol", "prediction_ts", "label"]
    missing = [c for c in required if c not in frame.columns]
    if missing:
        raise ValueError(f"feature frame is missing required columns: {missing}")
    return frame


def load_feature_frame(
    source: Source = "synthetic",
    *,
    seed: int = 42,
    n_symbols: int = 18,
    n_bars: int = 400,
    label_method: str = "fixed",
) -> pd.DataFrame:
    """Load the baseline-signal feature frame.

    ``source="synthetic"`` (default) builds the deterministic offline frame from
    ``ml/synthetic_data.py`` — the same frame the ML tests and
    ``ml/run_ablation.py`` use, so no Spark/Databricks is needed.  A path loads
    a ``.csv`` / ``.parquet`` snapshot of the same schema; a DataFrame is
    validated and returned unchanged.
    """
    if isinstance(source, pd.DataFrame):
        frame = source
    elif source is None or source == "synthetic":
        from ml.synthetic_data import make_synthetic_matrix

        frame = make_synthetic_matrix(
            n_symbols=n_symbols,
            n_bars=n_bars,
            seed=seed,
            label_method=label_method,
        )
    else:
        path = Path(source)
        if path.suffix.lower() in {".parquet", ".pq"}:
            frame = pd.read_parquet(path)
        else:
            frame = pd.read_csv(path)
    return validate_feature_frame(frame)


def split_windows(
    frame: pd.DataFrame,
    *,
    reference_frac: float = 0.6,
    time_col: str = "prediction_ts",
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Split a feature frame into ``(reference, current)`` windows on time order.

    The reference window gets the earliest ``reference_frac`` of the distinct
    timestamps; the current window gets the rest.
    """
    if not 0.0 < reference_frac < 1.0:
        raise ValueError("reference_frac must lie in (0, 1)")
    if time_col not in frame.columns:
        raise ValueError(f"feature frame has no '{time_col}' column")
    times = pd.Index(pd.unique(frame[time_col])).sort_values()
    if len(times) < 2:
        raise ValueError("need at least two distinct timestamps to split windows")
    cut = min(max(int(len(times) * reference_frac), 1), len(times) - 1)
    split_ts = times[cut]
    reference = frame[frame[time_col] < split_ts]
    current = frame[frame[time_col] >= split_ts]
    if reference.empty or current.empty:
        raise ValueError("window split produced an empty reference or current window")
    return reference.copy(), current.copy()


def _resolve_feature_cols(frame: pd.DataFrame, feature_cols: Optional[Sequence[str]]) -> List[str]:
    if feature_cols is None:
        feature_cols = FEATURE_SETS["D"]
    missing = [c for c in feature_cols if c not in frame.columns]
    if missing:
        raise ValueError(f"feature frame is missing requested feature columns: {missing}")
    return list(feature_cols)


# ── Baseline-signal predictions ──────────────────────────────────────────────


def encode_features(frame: pd.DataFrame, feature_cols: Sequence[str]) -> pd.DataFrame:
    """Numeric design matrix for ``frame`` — delegates to ``ml.train.prepare_features``."""
    from ml.train import prepare_features

    return prepare_features(frame, list(feature_cols))


def baseline_signal_probabilities(
    reference: pd.DataFrame,
    current: pd.DataFrame,
    *,
    feature_cols: Optional[Sequence[str]] = None,
    seed: int = 42,
    model_factory: Optional[Callable[[int], Any]] = None,
    model_version: str = "baseline-drift-demo",
) -> Tuple[pd.Series, pd.Series]:
    """Score both windows through the production baseline-signal path.

    The model is the lane's baseline classifier (``ml.train.make_baseline``),
    fit on the **reference** window's labels only, and the probabilities come
    back through ``ml.score.score_rows`` — the same row builder that feeds
    ``gold_trading_signals``.  Returns one ``probability`` Series per window,
    indexed like the input frames.
    """
    from ml.score import score_rows
    from ml.train import make_baseline

    cols = _resolve_feature_cols(reference, feature_cols)
    if "label" not in reference.columns:
        raise ValueError("the reference window must carry the 'label' column")

    X_ref = encode_features(reference, cols)
    X_cur = encode_features(current, cols).reindex(columns=X_ref.columns, fill_value=0.0)

    factory = make_baseline if model_factory is None else model_factory
    model = factory(seed)
    model.fit(X_ref, reference["label"].astype(int).to_numpy())

    def _probabilities(frame: pd.DataFrame, X: pd.DataFrame) -> pd.Series:
        scored_input = X.copy()
        scored_input.insert(0, "feature_snapshot_id", "drift-monitoring")
        scored_input.insert(0, "prediction_ts", frame["prediction_ts"].to_numpy())
        scored_input.insert(0, "symbol", frame["symbol"].to_numpy())
        rows = score_rows(
            scored_input,
            model,
            model_version=model_version,
            feature_cols=list(X.columns),
        )
        return pd.Series(rows["probability"].to_numpy(), index=frame.index, name="probability")

    return _probabilities(reference, X_ref), _probabilities(current, X_cur)


# ── Drift summary (pure Python — the threshold logic) ────────────────────────


def summarize_drift(
    per_feature_drift: Mapping[str, bool],
    *,
    drift_share_threshold: float = DEFAULT_DRIFT_SHARE_THRESHOLD,
) -> Dict[str, Any]:
    """Collapse per-feature drift flags into the summary block.

    ``dataset_drift`` fires when ``share_of_drifted_features`` reaches
    ``drift_share_threshold`` (``>=``); a single drifted feature is an
    observation, not a dataset-level alert.
    """
    threshold = float(drift_share_threshold)
    if not 0.0 < threshold <= 1.0:
        raise ValueError("drift_share_threshold must lie in (0, 1]")
    flags = {str(name): bool(drifted) for name, drifted in per_feature_drift.items()}
    if not flags:
        raise ValueError("per_feature_drift must not be empty")
    n_features = len(flags)
    n_drifted = int(sum(flags.values()))
    share = n_drifted / n_features
    return {
        "per_feature_drift": flags,
        "n_features": n_features,
        "n_drifted_features": n_drifted,
        "share_of_drifted_features": share,
        "drift_share_threshold": threshold,
        "dataset_drift": bool(share >= threshold),
    }


def build_summary(
    *,
    feature_drift: Mapping[str, Any],
    prediction_drift: Mapping[str, Any],
    reference_rows: int,
    current_rows: int,
    prediction_columns: Sequence[str],
    source: str,
    tool: Optional[Mapping[str, str]] = None,
    label: str = DRIFT_LABEL,
    generated_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Assemble the JSON summary document (schema: ``SUMMARY_KEYS``)."""
    return {
        "label": label,
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "tool": dict(tool) if tool is not None else None,
        "source": source,
        "windows": {
            "reference_rows": int(reference_rows),
            "current_rows": int(current_rows),
            "prediction_columns": [str(c) for c in prediction_columns],
        },
        "feature_drift": dict(feature_drift),
        "prediction_drift": dict(prediction_drift),
        "html_report": None,
    }


# ── Evidently-backed drift report ────────────────────────────────────────────


def _extract_per_column_drift(
    snapshot: Any,
    groups: Mapping[str, Sequence[str]],
) -> Dict[str, Dict[str, bool]]:
    """Pull per-column drift flags out of an Evidently snapshot.

    A column is drifted when its Evidently ``ValueDrift`` test FAILs.
    """
    data = snapshot.dict() if hasattr(snapshot, "dict") else {}
    found: Dict[str, Dict[str, bool]] = {name: {} for name in groups}
    for test in data.get("tests", []):
        params = (test.get("metric_config") or {}).get("params") or {}
        if not str(params.get("type", "")).endswith("ValueDrift"):
            continue
        column = params.get("column")
        raw_status = test.get("status")
        status = str(getattr(raw_status, "value", raw_status)).upper()
        if status not in {"SUCCESS", "FAIL"}:
            raise RuntimeError(
                f"unexpected evidently drift-test status {status!r} for column {column!r}"
            )
        drifted = status == "FAIL"
        for name, cols in groups.items():
            if column in cols:
                found[name][str(column)] = drifted
    missing = {
        name: [c for c in cols if c not in found[name]] for name, cols in groups.items()
    }
    missing = {name: cols for name, cols in missing.items() if cols}
    if missing:
        raise RuntimeError(
            f"evidently returned no per-column drift result for: {missing}"
        )
    return found


@dataclass
class DriftReport:
    """A computed drift analysis: JSON-serializable summary + Evidently snapshot."""

    summary: Dict[str, Any]
    snapshot: Any

    def write(self, output_dir: Union[str, Path], name: str = "drift") -> Dict[str, Path]:
        """Write ``<name>_report.html`` and ``<name>_summary.json`` under ``output_dir``."""
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        html_path = out_dir / f"{name}_report.html"
        json_path = out_dir / f"{name}_summary.json"

        self.summary["html_report"] = html_path.name
        html_path.write_text(
            _with_label_banner(self.snapshot.get_html_str(False), self.summary["label"]),
            encoding="utf-8",
        )
        json_path.write_text(
            json.dumps(self.summary, indent=2, sort_keys=False) + "\n", encoding="utf-8"
        )
        return {"html": html_path, "json": json_path}


def _with_label_banner(html: str, label: str) -> str:
    """Put the demonstration label at the top of the rendered report body."""
    banner = (
        '<div style="margin:16px;padding:12px 16px;border:1px solid #999;'
        'border-radius:6px;font-family:sans-serif;font-size:14px;">'
        f"<strong>{_html.escape(label)}</strong></div>"
    )
    marker = "<body>"
    if marker in html:
        return html.replace(marker, marker + "\n" + banner, 1)
    return banner + html


def run_drift_report(
    reference: pd.DataFrame,
    current: pd.DataFrame,
    *,
    feature_cols: Optional[Sequence[str]] = None,
    prediction_cols: Sequence[str] = PREDICTION_COLUMNS,
    drift_share_threshold: float = DEFAULT_DRIFT_SHARE_THRESHOLD,
    stattest_threshold: float = DEFAULT_STATTEST_THRESHOLD,
    seed: int = 42,
    model_factory: Optional[Callable[[int], Any]] = None,
    compute_predictions: bool = True,
    label: str = DRIFT_LABEL,
    source: str = "synthetic window split",
) -> DriftReport:
    """Compute feature-drift and prediction-drift summaries with Evidently.

    ``reference`` / ``current`` are baseline-signal feature frames (see
    ``load_feature_frame``).  The model-input drift is measured on the encoded
    design matrix (``ml.train.prepare_features`` — exactly what the baseline
    model sees).  Prediction drift is measured on ``prediction_cols``; with
    ``compute_predictions=True`` those columns are the baseline-signal
    probabilities scored through ``ml.score.score_rows`` (model fit on the
    reference window only).

    Raises ``ImportError`` when Evidently is not installed.
    """
    Report, DataDriftPreset = _require_evidently()
    validate_feature_frame(reference)
    validate_feature_frame(current)
    cols = _resolve_feature_cols(reference, feature_cols)

    if compute_predictions:
        ref_pred, cur_pred = baseline_signal_probabilities(
            reference,
            current,
            feature_cols=cols,
            seed=seed,
            model_factory=model_factory,
        )
        reference = reference.assign(probability=ref_pred)
        current = current.assign(probability=cur_pred)

    prediction_names = [str(c) for c in prediction_cols]
    missing = [
        c
        for c in prediction_names
        if c not in reference.columns or c not in current.columns
    ]
    if missing:
        raise ValueError(f"prediction columns missing from the windows: {missing}")

    X_ref = encode_features(reference, cols)
    X_cur = encode_features(current, cols).reindex(columns=X_ref.columns, fill_value=0.0)
    feature_names = list(X_ref.columns)

    ref_data = X_ref.copy()
    cur_data = X_cur.copy()
    for column in prediction_names:
        ref_data[column] = reference[column].to_numpy()
        cur_data[column] = current[column].to_numpy()

    report = Report(
        [
            DataDriftPreset(
                columns=feature_names,
                drift_share=drift_share_threshold,
                threshold=stattest_threshold,
            ),
            DataDriftPreset(
                columns=prediction_names,
                drift_share=drift_share_threshold,
                threshold=stattest_threshold,
            ),
        ],
        include_tests=True,
    )
    snapshot = report.run(reference_data=ref_data, current_data=cur_data)

    flags = _extract_per_column_drift(
        snapshot, {"feature": feature_names, "prediction": prediction_names}
    )
    summary = build_summary(
        feature_drift=summarize_drift(
            flags["feature"], drift_share_threshold=drift_share_threshold
        ),
        prediction_drift=summarize_drift(
            flags["prediction"], drift_share_threshold=drift_share_threshold
        ),
        reference_rows=len(reference),
        current_rows=len(current),
        prediction_columns=prediction_names,
        source=source,
        tool={"name": "evidently", "version": _evidently_version()},
        label=label,
    )
    return DriftReport(summary=summary, snapshot=snapshot)
