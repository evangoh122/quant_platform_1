"""api/routes/health.py — GET /api/health.

Reports dependency + freshness status. Deliberately non-fatal: an unavailable
Delta or Lakebase backend degrades to ``degraded`` rather than 500-ing, so the
Databricks App health probe stays meaningful while data backends are cold.

In public-demo mode the handler short-circuits: it never imports ``db.lakebase``
and never spawns a subprocess, returning 200 fast with both backends reported
as disabled.
"""
from __future__ import annotations

import importlib.util

from fastapi import APIRouter

from api.schemas import DependencyStatus, Freshness, HealthResponse

router = APIRouter()

_DEMO_DISABLED = DependencyStatus(
    name="lakebase", ok=False, detail="disabled in public demo"
)
_DEMO_DELTA_DISABLED = DependencyStatus(
    name="delta", ok=False, detail="disabled in public demo"
)


@router.get("", response_model=HealthResponse)
def health() -> HealthResponse:
    from api.demo import is_public_demo

    if is_public_demo():
        return HealthResponse(
            status="degraded",
            version="0.1.0",
            dependencies=[_DEMO_DISABLED, _DEMO_DELTA_DISABLED],
            freshness=Freshness(state="unavailable", table="system"),
        )

    dependencies: list[DependencyStatus] = []

    # Lakebase reachability (mints a token + opens a pooled connection).
    try:
        from db.lakebase import get_lakebase

        db = get_lakebase()
        row = db.fetchone("SELECT 1")
        ok = row is not None and row[0] == 1
        dependencies.append(
            DependencyStatus(name="lakebase", ok=ok, detail="reachable" if ok else "no response")
        )
    except Exception as exc:  # noqa: BLE001
        dependencies.append(
            DependencyStatus(name="lakebase", ok=False, detail=type(exc).__name__)
        )

    # Delta / Spark availability (pyspark is not required locally).
    if importlib.util.find_spec("pyspark") is None:
        dependencies.append(
            DependencyStatus(name="delta", ok=False, detail="pyspark not installed")
        )
    else:
        dependencies.append(DependencyStatus(name="delta", ok=True, detail="pyspark available"))

    status = "ok" if all(d.ok for d in dependencies) else "degraded"
    return HealthResponse(
        status=status,
        version="0.1.0",
        dependencies=dependencies,
        freshness=Freshness(state="fresh" if status == "ok" else "unavailable", table="system"),
    )
