"""api/diagnostics.py — Stage timing and health diagnostics.

Provides:
  * ``stage(name, **safe_fields)`` — context manager that logs ``STAGE start``
    and ``STAGE done`` (with elapsed ms, ok/error) at INFO to stdout.
  * ``StageRingBuffer`` — thread-safe bounded ring buffer (last ~200 events)
    for the ``/api/health/trace`` endpoint.
  * ``timed_request`` — middleware helper that logs per-request timing with
    the slowest stage.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Optional

_log = logging.getLogger("api.diagnostics")
_log.setLevel(logging.INFO)

# ── ring buffer ───────────────────────────────────────────────────────────────

_MAX_EVENTS = 200
_SLOW_THRESHOLD_MS = 2000


@dataclass
class StageEvent:
    name: str
    elapsed_ms: float
    ok: bool
    error: Optional[str] = None
    extra: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


class StageRingBuffer:
    """Thread-safe bounded ring buffer for recent stage events."""

    def __init__(self, maxlen: int = _MAX_EVENTS):
        self._buf: deque[StageEvent] = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def append(self, event: StageEvent) -> None:
        with self._lock:
            self._buf.append(event)

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                {
                    "name": e.name,
                    "elapsed_ms": round(e.elapsed_ms, 1),
                    "ok": e.ok,
                    "error": e.error,
                    "extra": e.extra,
                    "ts": e.timestamp,
                }
                for e in self._buf
            ]

    def slow_events(self, threshold_ms: float = _SLOW_THRESHOLD_MS) -> list[dict[str, Any]]:
        with self._lock:
            return [
                {
                    "name": e.name,
                    "elapsed_ms": round(e.elapsed_ms, 1),
                    "ok": e.ok,
                    "error": e.error,
                    "extra": e.extra,
                    "ts": e.timestamp,
                }
                for e in self._buf
                if e.elapsed_ms >= threshold_ms
            ]

    def clear(self) -> None:
        with self._lock:
            self._buf.clear()


# Process-wide singleton
ring_buffer = StageRingBuffer()

# ── per-request stage tracking ────────────────────────────────────────────────

_request_stages: ContextVar[list[StageEvent]] = ContextVar("_request_stages", default=[])


@contextmanager
def stage(name: str, **safe_fields: Any):
    """Context manager that logs STAGE start/done with elapsed ms.

    Usage::

        with stage("lakebase_connect", table="users"):
            ...

    Logs ``STAGE start <name>`` and ``STAGE done <name> ms=<elapsed> ok=<bool>``
    at INFO.  On failure logs ``error=<ExceptionType>`` and re-raises.

    ``safe_fields`` are logged as ``key=value`` pairs — **never** pass secrets,
    tokens, connection strings, or user emails.
    """
    fields_str = " ".join(f"{k}={v}" for k, v in safe_fields.items()) if safe_fields else ""
    suffix = f" {fields_str}" if fields_str else ""
    _log.info("STAGE start %s%s", name, suffix)

    t0 = time.monotonic()
    try:
        yield
        elapsed = (time.monotonic() - t0) * 1000
        _log.info("STAGE done %s%s ms=%.1f ok=True", name, suffix, elapsed)
        event = StageEvent(name=name, elapsed_ms=elapsed, ok=True, extra=safe_fields)
    except Exception as exc:
        elapsed = (time.monotonic() - t0) * 1000
        _log.info(
            "STAGE done %s%s ms=%.1f ok=False error=%s",
            name, suffix, elapsed, type(exc).__name__,
        )
        event = StageEvent(
            name=name, elapsed_ms=elapsed, ok=False,
            error=type(exc).__name__, extra=safe_fields,
        )
        ring_buffer.append(event)
        _append_request_stage(event)
        raise

    ring_buffer.append(event)
    _append_request_stage(event)
    return event


def _append_request_stage(event: StageEvent) -> None:
    try:
        stages = _request_stages.get()
        stages.append(event)
    except Exception:  # noqa: BLE001 — context var may not be set
        pass


def get_request_stages() -> list[StageEvent]:
    try:
        return list(_request_stages.get())
    except Exception:
        return []


def reset_request_stages() -> None:
    _request_stages.set([])


def slowest_stage(stages: list[StageEvent]) -> Optional[StageEvent]:
    if not stages:
        return None
    return max(stages, key=lambda s: s.elapsed_ms)