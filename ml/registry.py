"""MLflow tracking for the ML ablation lane.

Logs runs with params, metrics, the feature-set version (A/B/C/D) and the
random seed so every run is reproducible. Registration of the promoted model
version is also here.

MLflow is imported lazily so the pure-logic tests (which assert the params
dict carries the feature-set version and seed) run without an MLflow install.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


def build_run_tags(
    feature_set: str,
    seed: int,
    model_type: str,
    data_window: str,
) -> Dict[str, str]:
    """The tags/params a run must carry to be reproducible.

    ``data_window`` is the ISO range of the training data (e.g.
    "2026-01-05T00:00:00Z/2026-01-30T00:00:00Z") or "synthetic".
    """
    return {
        "feature_set": feature_set,
        "seed": str(seed),
        "model_type": model_type,
        "data_window": data_window,
    }


def log_run(
    run_name: str,
    params: Dict[str, Any],
    metrics: Dict[str, float],
    tags: Optional[Dict[str, str]] = None,
    experiment_name: str = "ml_ablation",
    artifacts: Optional[Dict[str, str]] = None,
) -> Optional[str]:
    """Log an ablation run to MLflow and return the run id.

    ``metrics`` are logged as MLflow metrics; ``tags``/``params`` become run
    params. ``artifacts`` maps a local file path to an artifact name.
    """
    import mlflow

    mlflow.set_experiment(experiment_name)
    with mlflow.start_run(run_name=run_name) as run:
        if params:
            mlflow.log_params({k: str(v) for k, v in params.items()})
        if tags:
            mlflow.log_params(tags)
        for k, v in metrics.items():
            if v is None:
                continue
            try:
                mlflow.log_metric(k, float(v))
            except (TypeError, ValueError):
                continue
        if artifacts:
            for name, path in artifacts.items():
                mlflow.log_artifact(path, artifact_path=name)
        return run.info.run_id


def register_model(
    run_id: str,
    model_name: str,
    artifact_path: str = "model",
    stage: str = "None",
) -> Any:
    """Register the model produced by ``run_id`` under ``model_name``."""
    import mlflow

    result = mlflow.register_model(
        f"runs:/{run_id}/{artifact_path}", model_name, tags=None
    )
    if stage and stage != "None":
        from mlflow.tracking import MlflowClient

        MlflowClient().transition_model_version_stage(
            name=model_name, version=result.version, stage=stage
        )
    return result
