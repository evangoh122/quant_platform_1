"""api/routes/health.py — GET /api/health, GET /api/health/trace.

Reports dependency + freshness status with per-dependency latency, last error,
circuit breaker state, and startup stage timings. Each dependency probe runs
with its own hard timeout so the endpoint never hangs.

In public-demo mode the handler short-circuits: it never imports ``db.lakebase``
and never spawns a subprocess, returning 200 fast with both backends reported
as disabled.
"""
from __future__ import annotations

import importlib.util
import time
from typing import Any

from fastapi import APIRouter

from api.schemas import (
    DependencyStatus,
    Freshness,
    HealthResponse,
    HealthTraceResponse,
    StartupStage,
    TraceEvent,
)

router = APIRouter()

_LAKEBASE_TIMEOUT = 3.0
_WAREHOUSE_TIMEOUT = 5.0

_DEMO_DISABLED = DependencyStatus(
    name="lakebase", ok=False, detail="disabled in public demo",
    latency_ms=0, last_error=None, last_ok_at=None, circuit_breaker_state=None,
)
_DEMO_DELTA_DISABLED = DependencyStatus(
    name="delta", ok=False, detail="disabled in public demo",
    latency_ms=0, last_error=None, last_ok_at=None, circuit_breaker_state=None,
)

# Per-probe state for last_ok_at and last_error (module-level, thread-safe)
_lakebase_last_ok_at: float | None = None
_lakebase_last_error: str | None = None
_delta_last_ok_at: float | None = None
_delta_last_error: str | None = None

import threading
_probe_lock = threading.Lock()


def _probe_lakebase() -> tuple[bool, float, str | None]:
    """Probe Lakebase with timeout. Returns (ok, latency_ms, detail)."""
    global _lakebase_last_ok_at, _lakebase_last_error

    from api.deps import lakebase_status

    lb = lakebase_status()
    if lb["circuit_breaker_open"]:
        detail = f"circuit breaker open ({lb['consecutive_failures']} failures)"
        with _probe_lock:
            _lakebase_last_error = detail
        return False, 0.0, detail

    t0 = time.monotonic()
    try:
        from db.lakebase import get_lakebase

        db = get_lakebase()
        row = db.fetchone("SELECT 1")
        elapsed_ms = (time.monotonic() - t0) * 1000
        ok = row is not None and row[0] == 1
        with _probe_lock:
            if ok:
                _lakebase_last_ok_at = time.time()
                _lakebase_last_error = None
            else:
                _lakebase_last_error = "no response"
        return ok, elapsed_ms, "reachable" if ok else "no response"
    except Exception as exc:  # noqa: BLE001
        elapsed_ms = (time.monotonic() - t0) * 1000
        with _probe_lock:
            _lakebase_last_error = type(exc).__name__
        return False, elapsed_ms, type(exc).__name__


def _probe_delta() -> tuple[bool, float, str | None]:
    """Probe Delta/warehouse availability. Returns (ok, latency_ms, detail)."""
    global _delta_last_ok_at, _delta_last_error

    t0 = time.monotonic()
    try:
        from db.delta_adapter import check_warehouse_health
        ok, detail = check_warehouse_health()
        elapsed_ms = (time.monotonic() - t0) * 1000
        with _probe_lock:
            if ok:
                _delta_last_ok_at = time.time()
                _delta_last_error = None
            else:
                _delta_last_error = detail
        return ok, elapsed_ms, detail
    except ImportError:
        elapsed_ms = (time.monotonic() - t0) * 1000
        # Check if warehouse backend is available (pyspark not required)
        try:
            from db.delta_adapter import _warehouse_available
            if _warehouse_available():
                detail = "warehouse connector available"
                with _probe_lock:
                    _delta_last_ok_at = time.time()
                    _delta_last_error = None
                return True, elapsed_ms, detail
        except Exception:  # noqa: BLE001
            pass
        detail = "pyspark not installed"
        with _probe_lock:
            _delta_last_error = detail
        return False, elapsed_ms, detail
    except Exception as exc:  # noqa: BLE001
        elapsed_ms = (time.monotonic() - t0) * 1000
        with _probe_lock:
            _delta_last_error = type(exc).__name__
        return False, elapsed_ms, type(exc).__name__


def _run_with_timeout(fn, timeout: float, probe_name: str) -> tuple[bool, float, str | None]:
    """Run a probe function with a hard timeout.

    Uses a daemon thread so the caller is never blocked past the timeout,
    even if the probe function sleeps indefinitely.
    """
    result: list[Any] = []
    error: list[Exception] = []

    def _target():
        try:
            result.append(fn())
        except Exception as e:
            error.append(e)

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    t.join(timeout=timeout)

    if t.is_alive():
        # Timed out — thread is still running but we don't care (daemon)
        with _probe_lock:
            if probe_name == "lakebase":
                global _lakebase_last_error
                _lakebase_last_error = f"timeout after {timeout}s"
            else:
                global _delta_last_error
                _delta_last_error = f"timeout after {timeout}s"
        return False, timeout * 1000, f"timeout after {timeout}s"

    if error:
        raise error[0]
    return result[0]


@router.get("", response_model=HealthResponse)
def health() -> HealthResponse:
    from api.demo import is_public_demo

    if is_public_demo():
        return HealthResponse(
            status="degraded",
            version="0.1.0",
            dependencies=[_DEMO_DISABLED, _DEMO_DELTA_DISABLED],
            freshness=Freshness(state="unavailable", table="system"),
            role_cache_size=0,
            startup=[],
        )

    dependencies: list[DependencyStatus] = []

    # Lakebase reachability — with timeout
    from api.deps import lakebase_status

    lb = lakebase_status()
    cb_state = "open" if lb["circuit_breaker_open"] else "closed"

    lb_ok, lb_ms, lb_detail = _run_with_timeout(
        _probe_lakebase, _LAKEBASE_TIMEOUT, "lakebase"
    )

    with _probe_lock:
        lb_last_err = _lakebase_last_error

    dependencies.append(DependencyStatus(
        name="lakebase", ok=lb_ok, detail=lb_detail or "",
        latency_ms=round(lb_ms, 1),
        last_error=lb_last_err,
        last_ok_at=_lakebase_last_ok_at,
        circuit_breaker_state=cb_state,
    ))

    # Delta / warehouse probe — with timeout
    delta_ok, delta_ms, delta_detail = _run_with_timeout(
        _probe_delta, _WAREHOUSE_TIMEOUT, "delta"
    )

    with _probe_lock:
        delta_last_err = _delta_last_error

    dependencies.append(DependencyStatus(
        name="delta", ok=delta_ok, detail=delta_detail or "",
        latency_ms=round(delta_ms, 1),
        last_error=delta_last_err,
        last_ok_at=_delta_last_ok_at,
        circuit_breaker_state=None,
    ))

    # Startup stage timings — read from ring buffer
    startup_stages = _get_startup_stages()

    status = "ok" if all(d.ok for d in dependencies) else "degraded"
    return HealthResponse(
        status=status,
        version="0.1.0",
        dependencies=dependencies,
        freshness=Freshness(state="fresh" if status == "ok" else "unavailable", table="system"),
        role_cache_size=lb.get("cache_entries", 0),
        startup=startup_stages,
    )


@router.get("/trace", response_model=HealthTraceResponse)
def health_trace() -> HealthTraceResponse:
    from api.demo import is_public_demo
    if is_public_demo():
        return HealthTraceResponse(recent=[], slow=[])

    from api.diagnostics import ring_buffer

    raw_recent = ring_buffer.snapshot()
    raw_slow = ring_buffer.slow_events()

    recent = [TraceEvent(**e) for e in raw_recent]
    slow = [TraceEvent(**e) for e in raw_slow]
    return HealthTraceResponse(recent=recent, slow=slow)


def _get_startup_stages() -> list[StartupStage]:
    """Read startup stages from the ring buffer (names starting with 'startup_')."""
    from api.diagnostics import ring_buffer

    events = ring_buffer.snapshot()
    return [
        StartupStage(name=e["name"], elapsed_ms=round(e["elapsed_ms"], 1), ok=e["ok"])
        for e in events
        if e["name"].startswith("startup_")
    ]