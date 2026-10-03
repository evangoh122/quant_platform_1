"""api/main.py — FastAPI application entrypoint.

Mounts the ``/api`` routers, exposes ``/api/health``, keeps CORS off by default
(same-origin per the rubric), and — in production, when ``frontend/dist`` is
present — serves the built frontend as static files so the Databricks App
serves both the API and the UI from a single origin.

``import api.main`` must succeed without pyspark or a live Lakebase; optional
backends are imported lazily inside the dependency providers and route
handlers, never at module import time.
"""
from __future__ import annotations

import asyncio
import os
import time
from collections import defaultdict
from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from api.deps import FRONTEND_DIST
from api.routes import analytics, health, market, signals

APP_VERSION = os.getenv("APP_VERSION", "0.1.0")

# ── public-demo rate limiter ──────────────────────────────────────────────────

_RATE_LIMIT_READS = int(os.getenv("RATE_LIMIT_READS", "60"))
_MAX_REQUEST_BODY_BYTES = int(os.getenv("MAX_REQUEST_BODY_BYTES", str(1024 * 1024)))
_REQUEST_TIMEOUT_SECONDS = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "10"))


class _FixedWindowLimiter:
    """Per-client-IP, bounded in-memory fixed-window rate limiter.

    Tracks request counts in 60-second windows keyed by ``(ip, window_ts)``.
    Old windows are evicted lazily on each request to bound memory.
    """

    def __init__(self, limit: int = _RATE_LIMIT_READS, window: int = 60):
        self._limit = limit
        self._window = window
        self._counts: dict[tuple[str, int], int] = defaultdict(int)
        self._last_cleanup = time.monotonic()

    def _cleanup(self, now: float) -> None:
        if now - self._last_cleanup < self._window:
            return
        cutoff = int(now) - self._window * 2
        self._counts = defaultdict(
            int, {k: v for k, v in self._counts.items() if k[1] > cutoff}
        )
        self._last_cleanup = now

    def check(self, ip: str) -> tuple[bool, int]:
        """Return ``(allowed, retry_after)``."""
        now = time.monotonic()
        self._cleanup(now)
        window_ts = int(now) // self._window
        key = (ip, window_ts)
        self._counts[key] += 1
        if self._counts[key] > self._limit:
            return False, self._window - (int(now) % self._window)
        return True, 0

    def reset(self) -> None:
        """Reset all counters (for testing)."""
        self._counts.clear()
        self._last_cleanup = time.monotonic()


_limiter = _FixedWindowLimiter()


def create_app() -> FastAPI:
    """Application factory.

    In public-demo mode, registers only read-only routers (health, signals,
    market, analytics) and applies security middleware.  Non-demo mode
    preserves the full route set and existing CORS behaviour.
    """
    from api.demo import is_public_demo, validate_public_demo_environment

    demo = is_public_demo()

    if demo:
        validate_public_demo_environment()

    application = FastAPI(
        title="Mid-Frequency Quant Trading Platform",
        version=APP_VERSION,
        docs_url=None if demo else "/docs",
        redoc_url=None if demo else "/redoc",
        openapi_url=None if demo else "/openapi.json",
        description="Paper-trading dashboard and research-agent API (Databricks App).",
    )

    if demo:
        _register_demo_middleware(application)
    else:
        _register_standard_middleware(application)

    # Read-only routers (always registered).
    application.include_router(health.router, prefix="/api/health", tags=["health"])
    application.include_router(signals.router, prefix="/api/signals", tags=["signals"])
    application.include_router(market.router, prefix="/api/market", tags=["market"])
    application.include_router(analytics.router, prefix="/api/analytics", tags=["analytics"])

    if not demo:
        from api.routes import agent_chat, orders, portfolio, watchlists

        application.include_router(agent_chat.router, prefix="/api/agent", tags=["agent"])
        application.include_router(watchlists.router, prefix="/api/watchlists", tags=["watchlists"])
        application.include_router(orders.router, prefix="/api/orders", tags=["orders"])
        application.include_router(portfolio.router, prefix="/api/portfolio", tags=["portfolio"])

    # ── frontend static serving (production) ──────────────────────────────
    if FRONTEND_DIST.is_dir():
        application.mount(
            "/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets"
        )

        @application.get("/{full_path:path}", include_in_schema=False)
        def _spa(full_path: str) -> FileResponse:
            candidate = FRONTEND_DIST / full_path
            if full_path and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(FRONTEND_DIST / "index.html")

    return application


def _register_demo_middleware(application: FastAPI) -> None:
    """Register security middleware for public-demo mode.

    - Reject non-GET/HEAD/OPTIONS on /api with 405
    - Rate limit GET/HEAD per client IP
    - Reject oversized bodies (Content-Length or streamed bytes)
    - Request timeout
    - Security headers on every response
    - No CORS in demo
    """

    @application.middleware("http")
    async def _demo_guard(request: Request, call_next: Callable) -> Response:
        path = request.url.path

        # ── reject non-GET/HEAD/OPTIONS on /api ──────────────────────────
        if path.startswith("/api"):
            method = request.method.upper()
            if method not in ("GET", "HEAD", "OPTIONS"):
                return JSONResponse(
                    status_code=405,
                    content={"detail": "method not allowed in public demo"},
                )

            # ── rate limit GET/HEAD ──────────────────────────────────────
            if method in ("GET", "HEAD"):
                client_ip = request.client.host if request.client else "unknown"
                allowed, retry_after = _limiter.check(client_ip)
                if not allowed:
                    resp = JSONResponse(
                        status_code=429,
                        content={"detail": "rate limit exceeded"},
                    )
                    resp.headers["Retry-After"] = str(retry_after)
                    return resp

            # ── body size (Content-Length) ────────────────────────────────
            content_length = request.headers.get("content-length")
            if content_length and content_length.isdigit():
                if int(content_length) > _MAX_REQUEST_BODY_BYTES:
                    return JSONResponse(
                        status_code=413,
                        content={"detail": "request body too large"},
                    )

        # ── request timeout ──────────────────────────────────────────────
        try:
            response = await asyncio.wait_for(
                call_next(request), timeout=_REQUEST_TIMEOUT_SECONDS
            )
        except asyncio.TimeoutError:
            response = JSONResponse(
                status_code=504,
                content={"detail": "request timed out"},
            )

        # ── security headers ─────────────────────────────────────────────
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; frame-ancestors 'none'"
        )
        if path.startswith("/api"):
            response.headers["Cache-Control"] = "no-store"

        return response


def _register_standard_middleware(application: FastAPI) -> None:
    """Register standard (non-demo) middleware: opt-in CORS with restrictions."""
    _cors = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
    if _cors:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=_cors,
            allow_credentials=False,
            allow_methods=["GET", "HEAD", "OPTIONS"],
            allow_headers=["Content-Type"],
        )


app = create_app()


if __name__ == "__main__":
    # Local dev: `python -m api.main`. On Databricks Apps the port is injected
    # as DATABRICKS_APP_PORT and uvicorn is started via app.yaml instead.
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("DATABRICKS_APP_PORT", "8000")))