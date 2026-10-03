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
import urllib.parse
from collections import OrderedDict
from collections.abc import Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from api.deps import FRONTEND_DIST
from api.routes import analytics, health, market, signals

APP_VERSION = os.getenv("APP_VERSION", "0.1.0")

# ── public-demo rate limiter ──────────────────────────────────────────────────

_RATE_LIMIT_READS = int(os.getenv("RATE_LIMIT_READS", "60"))
_RATE_LIMIT_GLOBAL = int(os.getenv("RATE_LIMIT_GLOBAL", "600"))
_MAX_REQUEST_BODY_BYTES = int(os.getenv("MAX_REQUEST_BODY_BYTES", str(1024 * 1024)))
_REQUEST_TIMEOUT_SECONDS = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "10"))
_LRU_MAX_KEYS = int(os.getenv("RATE_LIMIT_LRU_MAX", "10000"))
_IS_RENDER = bool(os.environ.get("RENDER", "").strip())


def _apply_security_headers(response: Response, *, cache_control: bool = True) -> Response:
    """Apply the standard security header set to *response* in-place."""
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = (
        "default-src 'none'; frame-ancestors 'none'"
    )
    if cache_control:
        response.headers["Cache-Control"] = "no-store"
    return response


def _normalize_api_path(path: str) -> str:
    """Normalise *path* for /api prefix matching.

    Collapse repeated slashes, percent-decode, and case-fold so that
    ``//api/…``, ``/%2fapi/…``, and ``/API/…`` all match the canonical
    ``/api`` prefix.
    """
    decoded = urllib.parse.unquote(path)
    while "//" in decoded:
        decoded = decoded.replace("//", "/")
    return decoded.lower()


class _FixedWindowLimiter:
    """Per-client-IP, bounded in-memory fixed-window rate limiter.

    Tracks request counts in 60-second windows keyed by IP.  Uses a single
    ``OrderedDict`` so LRU eviction removes both the key and its counter —
    no parallel dicts can drift apart.  Includes a global ceiling as a
    backstop.

    When ``is_render`` is True, the client IP is extracted from the
    **rightmost** ``X-Forwarded-For`` entry (the address Render's edge saw).
    Otherwise ``request.client.host`` is used.
    """

    def __init__(
        self,
        limit: int = _RATE_LIMIT_READS,
        window: int = 60,
        global_limit: int = _RATE_LIMIT_GLOBAL,
        lru_max: int = _LRU_MAX_KEYS,
    ):
        self._limit = limit
        self._window = window
        self._global_limit = global_limit
        self._maxsize = lru_max
        self._counts: OrderedDict[str, tuple[int, int]] = OrderedDict()
        self._global_counts: dict[int, int] = {}
        self._last_cleanup = time.monotonic()

    def _cleanup(self, now: float) -> None:
        if now - self._last_cleanup < self._window:
            return
        cutoff = int(now) - self._window * 2
        to_remove = [ip for ip, (w, _) in self._counts.items() if w <= cutoff]
        for ip in to_remove:
            del self._counts[ip]
        self._global_counts = {k: v for k, v in self._global_counts.items() if k > cutoff}
        self._last_cleanup = now

    def check(self, ip: str) -> tuple[bool, int]:
        """Return ``(allowed, retry_after)``."""
        now = time.monotonic()
        self._cleanup(now)
        window_ts = int(now) // self._window

        # ── Per-IP check first (LRU-bounded). ────────────────────────────
        if ip in self._counts:
            stored_window, count = self._counts[ip]
            if stored_window == window_ts:
                if count >= self._limit:
                    return False, self._window - (int(now) % self._window)
                self._counts[ip] = (window_ts, count + 1)
            else:
                self._counts[ip] = (window_ts, 1)
            self._counts.move_to_end(ip)
        else:
            self._counts[ip] = (window_ts, 1)
            if len(self._counts) > self._maxsize:
                self._counts.popitem(last=False)

        # ── Global ceiling (only charged for requests that pass per-IP). ─
        self._global_counts[window_ts] = self._global_counts.get(window_ts, 0) + 1
        if self._global_counts[window_ts] > self._global_limit:
            return False, self._window - (int(now) % self._window)

        return True, 0

    def reset(self) -> None:
        """Reset all counters (for testing)."""
        self._counts.clear()
        self._global_counts.clear()
        self._last_cleanup = time.monotonic()

    @property
    def key_count(self) -> int:
        """Number of distinct IP keys currently tracked."""
        return len(self._counts)


_limiter = _FixedWindowLimiter()


def _get_client_ip(request: Request) -> str:
    """Extract the client IP for rate limiting.

    On Render, use the **rightmost** ``X-Forwarded-For`` entry — that is the
    address Render's edge saw.  Otherwise use ``request.client.host``.
    """
    if _IS_RENDER:
        xff = request.headers.get("x-forwarded-for", "")
        if xff:
            return xff.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


def create_app() -> FastAPI:
    """Application factory.

    In public-demo mode, registers only read-only routers (health, signals,
    market, analytics) and applies security middleware.  Non-demo mode
    preserves the full route set and existing CORS behaviour.

    On Render (``RENDER`` set), refuses to start without ``PUBLIC_DEMO=1``.
    """
    from api.demo import (
        is_public_demo,
        validate_public_demo_environment,
        validate_render_environment,
    )

    validate_render_environment()

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
        norm_path = _normalize_api_path(path)

        # ── reject non-GET/HEAD/OPTIONS on /api ──────────────────────────
        if norm_path.startswith("/api"):
            method = request.method.upper()
            if method not in ("GET", "HEAD", "OPTIONS"):
                resp = JSONResponse(
                    status_code=405,
                    content={"detail": "method not allowed in public demo"},
                )
                _apply_security_headers(resp)
                return resp

            # ── rate limit GET/HEAD ──────────────────────────────────────
            if method in ("GET", "HEAD"):
                client_ip = _get_client_ip(request)
                allowed, retry_after = _limiter.check(client_ip)
                if not allowed:
                    resp = JSONResponse(
                        status_code=429,
                        content={"detail": "rate limit exceeded"},
                    )
                    resp.headers["Retry-After"] = str(retry_after)
                    _apply_security_headers(resp)
                    return resp

            # ── body size (Content-Length) ────────────────────────────────
            content_length = request.headers.get("content-length")
            if content_length and content_length.isdigit():
                if int(content_length) > _MAX_REQUEST_BODY_BYTES:
                    resp = JSONResponse(
                        status_code=413,
                        content={"detail": "request body too large"},
                    )
                    _apply_security_headers(resp)
                    return resp

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
        _apply_security_headers(response, cache_control=norm_path.startswith("/api"))

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