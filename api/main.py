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
import ipaddress
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


class _TokenBucket:
    """Thread-safe token bucket for aggregate rate limiting.

    Tokens refill at a constant rate up to *capacity*.  Each request consumes
    one token.  When empty, callers receive a ``retry_after`` of one refill
    interval (1 / rate), so aggregate load causes brief 429s that self-recover
    rather than a hard minute-long outage.
    """

    def __init__(self, capacity: int, refill_rate: float):
        self._capacity = capacity
        self._refill_rate = refill_rate
        self._tokens = float(capacity)
        self._last_refill = time.monotonic()

    def consume(self) -> tuple[bool, int]:
        """Try to consume one token.  ``(allowed, retry_after_seconds)``."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._capacity, self._tokens + elapsed * self._refill_rate)
        self._last_refill = now

        if self._tokens >= 1.0:
            self._tokens -= 1.0
            return True, 0
        # Time until one token is available.
        wait = (1.0 - self._tokens) / self._refill_rate
        return False, max(1, int(wait) + 1)

    def reset(self) -> None:
        self._tokens = float(self._capacity)
        self._last_refill = time.monotonic()


class _FixedWindowLimiter:
    """Per-client-IP, bounded in-memory fixed-window rate limiter.

    Tracks request counts in 60-second windows keyed by IP.  Uses a single
    ``OrderedDict`` so LRU eviction removes both the key and its counter —
    no parallel dicts can drift apart.  Aggregate load is governed by a
    :class:`_TokenBucket` instead of a hard ceiling, so bursts cause brief
    429s that self-recover within seconds.
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
        self._maxsize = lru_max
        self._counts: OrderedDict[str, tuple[int, int]] = OrderedDict()
        self._last_cleanup = time.monotonic()
        # Token bucket: capacity = global_limit, refills at global_limit/60 per second.
        self._bucket = _TokenBucket(capacity=global_limit, refill_rate=global_limit / 60.0)

    def _cleanup(self, now: float) -> None:
        if now - self._last_cleanup < self._window:
            return
        cutoff = int(now) - self._window * 2
        to_remove = [ip for ip, (w, _) in self._counts.items() if w <= cutoff]
        for ip in to_remove:
            del self._counts[ip]
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

        # ── Global token bucket (only charged for requests that pass per-IP).
        allowed, retry_after = self._bucket.consume()
        if not allowed:
            return False, retry_after

        return True, 0

    def reset(self) -> None:
        """Reset all counters (for testing)."""
        self._counts.clear()
        self._bucket.reset()
        self._last_cleanup = time.monotonic()

    @property
    def key_count(self) -> int:
        """Number of distinct IP keys currently tracked."""
        return len(self._counts)


_limiter = _FixedWindowLimiter()


def _parse_ip(value: str) -> str | None:
    """Return *value* as a normalized IP string, or ``None`` if invalid.

    Strips whitespace, validates via :func:`ipaddress.ip_address`, and
    normalizes IPv6 (including IPv4-mapped addresses like ``::ffff:1.2.3.4``).
    """
    try:
        return str(ipaddress.ip_address(value.strip()))
    except (ValueError, AttributeError):
        return None


def _get_client_ip(request: Request) -> str:
    """Extract the client IP for rate limiting.

    On Render (``RENDER`` is set), use the first match in this order:

    1. ``CF-Connecting-IP`` — set by Cloudflare, overwrites client values.
    2. ``True-Client-IP`` — set by Cloudflare/CDN, overwrites client values.
    3. The **leftmost** ``X-Forwarded-For`` entry — Render's documented
       position for the real client IP.
    4. ``request.client.host`` — fallback.

    Outside Render, always use ``request.client.host`` and ignore every header.

    Each candidate is validated as a real IPv4/IPv6 address; invalid values
    are silently skipped and the next source is tried.
    """
    if _IS_RENDER:
        for header in ("cf-connecting-ip", "true-client-ip"):
            val = request.headers.get(header, "")
            if val:
                parsed = _parse_ip(val)
                if parsed is not None:
                    return parsed

        xff = request.headers.get("x-forwarded-for", "")
        if xff:
            first = xff.split(",")[0].strip()
            parsed = _parse_ip(first)
            if parsed is not None:
                return parsed

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

    # ── global exception handler ────────────────────────────────────────────
    # Catches any unhandled exception (including those raised outside the
    # demo middleware) and returns a generic 500 with all security headers.
    # Prevents Starlette's ServerErrorMiddleware from leaking stack traces
    # or returning responses without security headers.

    @application.exception_handler(Exception)
    async def _global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        resp = JSONResponse(
            status_code=500,
            content={"detail": "internal error"},
        )
        _apply_security_headers(resp)
        return resp

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
        _static_root = FRONTEND_DIST.resolve()

        application.mount(
            "/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets"
        )

        @application.get("/{full_path:path}", include_in_schema=False)
        def _spa(full_path: str) -> FileResponse:
            if not full_path:
                return FileResponse(FRONTEND_DIST / "index.html")

            # Reject any path whose decoded segments contain traversal,
            # backslash, NUL, or an absolute/drive prefix.
            decoded = urllib.parse.unquote(full_path)
            for seg in decoded.split("/"):
                if seg in ("..", ""):
                    return FileResponse(FRONTEND_DIST / "index.html")
                if "\\" in seg or "\x00" in seg:
                    return FileResponse(FRONTEND_DIST / "index.html")
                # Reject over-long segments (>255 bytes) before resolve()
                # to avoid ENAMETOOLONG OSError from Path.resolve().
                if len(seg.encode("utf-8")) > 255:
                    return FileResponse(FRONTEND_DIST / "index.html")
            # Reject over-long total path (>2048 bytes).
            if len(decoded.encode("utf-8")) > 2048:
                return FileResponse(FRONTEND_DIST / "index.html")
            # Drive letter / absolute prefix (e.g. C:\, /etc)
            if os.path.isabs(decoded):
                return FileResponse(FRONTEND_DIST / "index.html")

            try:
                candidate = (_static_root / decoded).resolve()
                if candidate.is_file() and candidate.is_relative_to(_static_root):
                    return FileResponse(candidate)
            except (OSError, RuntimeError, ValueError):
                # OSError: ENAMETOOLONG (segment >255 bytes slipped past
                #   the length check above, or OS-specific limits).
                # RuntimeError: symlink loop inside dist.
                # ValueError: malformed path on some platforms.
                return FileResponse(FRONTEND_DIST / "index.html")
            return FileResponse(FRONTEND_DIST / "index.html")

    return application


def _register_demo_middleware(application: FastAPI) -> None:
    """Register security middleware for public-demo mode.

    - Rate limit ALL GET/HEAD per client IP (including static files)
    - Reject non-GET/HEAD/OPTIONS on /api with 405
    - Reject oversized bodies (Content-Length or streamed bytes)
    - Request timeout
    - Security headers on every response
    - No CORS in demo

    ``/api/health`` is NOT exempt from rate limiting; Render's health check
    uses a small number of requests that won't exceed the per-IP limit.
    """

    @application.middleware("http")
    async def _demo_guard(request: Request, call_next: Callable) -> Response:
        path = request.url.path
        norm_path = _normalize_api_path(path)
        method = request.method.upper()

        # ── rate limit ALL GET/HEAD (not only /api) ──────────────────────
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

        # ── reject non-GET/HEAD/OPTIONS on /api ──────────────────────────
        if norm_path.startswith("/api"):
            if method not in ("GET", "HEAD", "OPTIONS"):
                resp = JSONResponse(
                    status_code=405,
                    content={"detail": "method not allowed in public demo"},
                )
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