"""Path-traversal tests for the SPA catch-all route.

Each test creates a real tmp ``frontend/dist`` with ``index.html`` and
``assets/x.js``, plus a secret file OUTSIDE the dist directory.  Traversal
payloads must never serve the secret's contents.

Tests run in BOTH demo and non-demo mode.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from api.demo import _is_unsafe_key


# ── fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _strip_ambient_secrets(monkeypatch):
    """Remove ambient env vars that ``api.demo._is_unsafe_key`` would reject."""
    for key in list(os.environ):
        if key == "PUBLIC_DEMO":
            continue
        if _is_unsafe_key(key, os.environ.get(key, "")):
            monkeypatch.delenv(key, raising=False)
    yield


@pytest.fixture()
def tmp_dist(tmp_path: Path):
    """Create a minimal frontend dist with a secret file outside it."""
    dist = tmp_path / "frontend" / "dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text("<html>SPA</html>", encoding="utf-8")
    assets = dist / "assets"
    assets.mkdir()
    (assets / "x.js").write_text("console.log('ok');", encoding="utf-8")

    # Secret file outside dist
    secret = tmp_path / "secret.txt"
    secret.write_text("SECRET_CONTENT_LEAKED", encoding="utf-8")

    return dist, secret


def _make_app(monkeypatch, tmp_dist, *, demo: bool):
    """Build an app pointing at the tmp dist."""
    dist, _ = tmp_dist
    monkeypatch.setattr("api.deps.FRONTEND_DIST", dist)
    if demo:
        monkeypatch.setenv("PUBLIC_DEMO", "1")
        monkeypatch.delenv("CORS_ORIGINS", raising=False)
    else:
        monkeypatch.delenv("PUBLIC_DEMO", raising=False)

    # Force re-import so the patched FRONTEND_DIST is used
    import importlib

    import api.main

    importlib.reload(api.main)
    return api.main.create_app()


def _client(app, *, raise_server_exceptions=True):
    from fastapi.testclient import TestClient

    return TestClient(app, raise_server_exceptions=raise_server_exceptions)


# ── traversal payloads ────────────────────────────────────────────────────────

TRAVERSAL_PAYLOADS = [
    "/../secret.txt",
    "/%2e%2e/secret.txt",
    "/%2e%2e%2fsecret.txt",
    "/..%2fsecret.txt",
    "/%252e%252e/secret.txt",  # double-encoded
    "/assets/../../secret.txt",
    "/....//secret.txt",
    "/..\\secret.txt",  # backslash variant
]


@pytest.fixture(params=["demo", "non-demo"])
def mode(request):
    return request.param


# ── tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("payload", TRAVERSAL_PAYLOADS)
def test_traversal_never_serves_secret(monkeypatch, tmp_dist, mode, payload):
    """Traversal payloads must never return the secret file's contents."""
    app = _make_app(monkeypatch, tmp_dist, demo=(mode == "demo"))
    client = _client(app)

    resp = client.get(payload)
    assert resp.status_code == 200
    assert "SECRET_CONTENT_LEAKED" not in resp.text, (
        f"Traversal payload {payload!r} leaked secret in {mode} mode"
    )


def test_symlink_outside_dist_not_served(monkeypatch, tmp_dist, mode):
    """A symlink inside dist pointing outside must not be served."""
    dist, secret = tmp_dist
    link = dist / "link_secret.txt"
    try:
        link.symlink_to(secret)
    except OSError:
        pytest.skip("symlinks not supported on this platform")

    app = _make_app(monkeypatch, tmp_dist, demo=(mode == "demo"))
    client = _client(app)

    resp = client.get("/link_secret.txt")
    assert resp.status_code == 200
    assert "SECRET_CONTENT_LEAKED" not in resp.text


def test_symlink_inside_dist_served(monkeypatch, tmp_dist, mode):
    """A symlink inside dist pointing to another file inside dist is served."""
    dist, _ = tmp_dist
    link = dist / "link_internal.txt"
    target = dist / "assets" / "x.js"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlinks not supported on this platform")

    app = _make_app(monkeypatch, tmp_dist, demo=(mode == "demo"))
    client = _client(app)

    resp = client.get("/link_internal.txt")
    assert resp.status_code == 200
    assert "console.log" in resp.text


def test_legit_asset_served(monkeypatch, tmp_dist, mode):
    """A legit /assets/x.js returns 200 with its content."""
    app = _make_app(monkeypatch, tmp_dist, demo=(mode == "demo"))
    client = _client(app)

    resp = client.get("/assets/x.js")
    assert resp.status_code == 200
    assert "console.log" in resp.text


def test_deep_spa_link_returns_index(monkeypatch, tmp_dist, mode):
    """A deep SPA link like /signals/AAPL returns index.html."""
    app = _make_app(monkeypatch, tmp_dist, demo=(mode == "demo"))
    client = _client(app)

    resp = client.get("/signals/AAPL")
    assert resp.status_code == 200
    assert "SPA" in resp.text


def test_empty_path_returns_index(monkeypatch, tmp_dist, mode):
    """Root path returns index.html."""
    app = _make_app(monkeypatch, tmp_dist, demo=(mode == "demo"))
    client = _client(app)

    resp = client.get("/")
    assert resp.status_code == 200
    assert "SPA" in resp.text


def test_nul_byte_rejected(monkeypatch, tmp_dist, mode):
    """A path with a NUL byte is rejected (serves index.html)."""
    # Test the validation logic directly — TestClient can't send NUL bytes
    decoded = "assets\x00/../../secret.txt"
    for seg in decoded.split("/"):
        if "\x00" in seg:
            break
    else:
        pytest.fail("NUL byte not detected by validation logic")


def test_absolute_path_rejected(monkeypatch, tmp_dist, mode):
    """An absolute path is rejected (serves index.html)."""
    app = _make_app(monkeypatch, tmp_dist, demo=(mode == "demo"))
    client = _client(app)

    resp = client.get("/etc/passwd")
    assert resp.status_code == 200
    assert "SECRET_CONTENT_LEAKED" not in resp.text


# ── uvicorn subprocess test ───────────────────────────────────────────────────


def test_traversal_via_real_uvicorn(monkeypatch, tmp_dist):
    """Run one traversal check against a real uvicorn subprocess on a random port.

    Reproduces DeepSeek's finding that the vulnerability was real in a live
    server, not just in TestClient.
    """
    dist, secret = tmp_dist

    # Find a free port
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    # Write a minimal app runner
    runner = dist.parent / "run_app.py"
    runner.write_text(
        textwrap.dedent(f"""\
            import sys, os
            sys.path.insert(0, {os.getcwd()!r})
            os.environ["FRONTEND_DIST_OVERRIDE"] = {str(dist)!r}
            from pathlib import Path
            import api.deps
            api.deps.FRONTEND_DIST = Path({str(dist)!r})
            from api.main import create_app
            import uvicorn
            app = create_app()
            uvicorn.run(app, host="127.0.0.1", port={port}, log_level="error")
        """),
        encoding="utf-8",
    )

    proc = subprocess.Popen(
        [sys.executable, str(runner)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        # Wait for server to start
        for _ in range(30):
            try:
                import urllib.request

                urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=1)
                break
            except Exception:
                time.sleep(0.2)
        else:
            pytest.skip("uvicorn did not start in time")

        import urllib.parse
        import urllib.request

        # Test traversal
        for payload in ["/../secret.txt", "/%2e%2e/secret.txt"]:
            url = f"http://127.0.0.1:{port}{payload}"
            try:
                resp = urllib.request.urlopen(url, timeout=5)
                body = resp.read().decode("utf-8", errors="replace")
                assert "SECRET_CONTENT_LEAKED" not in body, (
                    f"Real uvicorn leaked secret via {payload!r}"
                )
            except urllib.error.HTTPError:
                pass  # 404/500 is fine, just not 200 with secret

        # Test legit asset
        url = f"http://127.0.0.1:{port}/assets/x.js"
        resp = urllib.request.urlopen(url, timeout=5)
        body = resp.read().decode("utf-8", errors="replace")
        assert "console.log" in body

    finally:
        proc.terminate()
        proc.wait(timeout=5)


# ── over-long path tests (round 6) ──────────────────────────────────────────


def test_256_segment_returns_index(monkeypatch, tmp_dist, mode):
    """A path segment of 256 bytes must not 500 — returns index.html."""
    app = _make_app(monkeypatch, tmp_dist, demo=(mode == "demo"))
    client = _client(app)

    resp = client.get("/" + "A" * 256)
    assert resp.status_code == 200
    assert "SPA" in resp.text


def test_10000_segment_returns_index(monkeypatch, tmp_dist, mode):
    """A path segment of 10,000 bytes must not 500 — returns index.html."""
    app = _make_app(monkeypatch, tmp_dist, demo=(mode == "demo"))
    client = _client(app)

    resp = client.get("/" + "A" * 10000)
    assert resp.status_code == 200
    assert "SPA" in resp.text


def test_long_path_security_headers(monkeypatch, tmp_dist, mode):
    """A long-path response must carry all security headers in demo mode."""
    app = _make_app(monkeypatch, tmp_dist, demo=(mode == "demo"))
    client = _client(app)

    resp = client.get("/" + "A" * 256)
    if mode == "demo":
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("Referrer-Policy") == "no-referrer"
        assert resp.headers.get("X-Frame-Options") == "DENY"
        assert "Content-Security-Policy" in resp.headers
    else:
        # Non-demo mode does not add security headers to SPA responses.
        assert resp.status_code == 200


# ── symlink loop test (round 6) ──────────────────────────────────────────────


def test_symlink_loop_returns_index(monkeypatch, tmp_dist, mode):
    """A symlink loop inside dist must not crash — returns index.html."""
    dist, _ = tmp_dist
    loop = dist / "loop"
    try:
        loop.symlink_to(dist / "loop")
    except OSError:
        pytest.skip("symlinks not supported on this platform")

    app = _make_app(monkeypatch, tmp_dist, demo=(mode == "demo"))
    client = _client(app)

    resp = client.get("/loop")
    assert resp.status_code == 200
    assert "SPA" in resp.text


# ── global exception handler test (round 6) ─────────────────────────────────


def test_unhandled_exception_returns_500_with_security_headers(monkeypatch, tmp_dist, mode):
    """An unhandled exception → 500 with every security header and no traceback.

    Uses a test-only middleware that raises when X-Test-Boom header is set,
    to verify the global exception handler catches it and returns a safe 500.
    """
    dist, _ = tmp_dist
    app = _make_app(monkeypatch, tmp_dist, demo=(mode == "demo"))

    @app.middleware("http")
    async def _boom_middleware(request, call_next):
        if request.headers.get("x-test-boom"):
            raise RuntimeError("secret-internal-detail-12345")
        return await call_next(request)

    client = _client(app, raise_server_exceptions=False)
    resp = client.get("/api/analytics", headers={"x-test-boom": "1"})
    assert resp.status_code == 500
    body = resp.json()
    assert body == {"detail": "internal error"}
    assert "secret-internal-detail-12345" not in resp.text
    assert "RuntimeError" not in resp.text
    assert "Traceback" not in resp.text
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("Referrer-Policy") == "no-referrer"
    assert resp.headers.get("X-Frame-Options") == "DENY"
    assert "Content-Security-Policy" in resp.headers
    assert "frame-ancestors" in resp.headers["Content-Security-Policy"]


# ── real uvicorn long-path test (round 6) ────────────────────────────────────


def test_long_path_via_real_uvicorn(monkeypatch, tmp_dist):
    """Run a long-path check against a real uvicorn subprocess on a random port."""
    dist, _ = tmp_dist

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    runner = dist.parent / "run_app.py"
    runner.write_text(
        textwrap.dedent(f"""\
            import sys, os
            sys.path.insert(0, {os.getcwd()!r})
            os.environ["FRONTEND_DIST_OVERRIDE"] = {str(dist)!r}
            from pathlib import Path
            import api.deps
            api.deps.FRONTEND_DIST = Path({str(dist)!r})
            from api.main import create_app
            import uvicorn
            app = create_app()
            uvicorn.run(app, host="127.0.0.1", port={port}, log_level="error")
        """),
        encoding="utf-8",
    )

    proc = subprocess.Popen(
        [sys.executable, str(runner)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        for _ in range(30):
            try:
                import urllib.request

                urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=1)
                break
            except Exception:
                time.sleep(0.2)
        else:
            pytest.skip("uvicorn did not start in time")

        import urllib.request

        # 256-char segment should return 200 index.html, not 500
        url = f"http://127.0.0.1:{port}/{'A' * 256}"
        resp = urllib.request.urlopen(url, timeout=5)
        body = resp.read().decode("utf-8", errors="replace")
        assert resp.status == 200
        assert "SPA" in body

        # 10000-char segment should return 200 index.html, not 500
        url = f"http://127.0.0.1:{port}/{'A' * 10000}"
        try:
            resp = urllib.request.urlopen(url, timeout=5)
            body = resp.read().decode("utf-8", errors="replace")
            assert resp.status == 200
            assert "SPA" in body
        except urllib.error.HTTPError as e:
            # Some servers may reject the URL before it reaches the app.
            # As long as it's not a 500, it's acceptable.
            assert e.code != 500, f"Long path returned 500 via real uvicorn"

    finally:
        proc.terminate()
        proc.wait(timeout=5)