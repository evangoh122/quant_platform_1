"""tests/test_smoke_app.py — Tests for the deployment smoke test.

Verifies that scripts/smoke_app.py correctly:
  1. Accepts HTML with <div id="root"> + valid hashed asset → PASS
  2. Rejects the missing-build JSON hint → FAIL
  3. Rejects arbitrary non-HTML content → FAIL
  4. Rejects HTML missing <div id="root"> → FAIL
  5. Rejects HTML with asset that returns non-200 → FAIL
"""
from __future__ import annotations

import io
import json
from unittest.mock import MagicMock, patch

import pytest


def _html_response(body: str, content_type: str = "text/html") -> MagicMock:
    """Build a mock urllib response."""
    resp = MagicMock()
    resp.status = 200
    resp.read.return_value = body.encode("utf-8")
    resp.headers = {"Content-Type": content_type}
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def _json_response(body: dict, status: int = 200) -> MagicMock:
    """Build a mock JSON response."""
    resp = MagicMock()
    resp.status = status
    resp.read.return_value = json.dumps(body).encode("utf-8")
    resp.headers = {"Content-Type": "application/json"}
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


_GOOD_HTML = (
    '<!doctype html><html><body>'
    '<div id="root"></div>'
    '<script type="module" src="/assets/index-abc123.js"></script>'
    '</body></html>'
)

_GOOD_JS = 'console.log("hello");'


def _make_urlopen(responses: dict[str, MagicMock]):
    """Build a mock urlopen that returns responses by URL."""
    def _urlopen(req, timeout=15):
        url = req.full_url
        if url in responses:
            return responses[url]
        raise FileNotFoundError(f"No mock for {url}")
    return _urlopen


@patch("urllib.request.urlopen")
def test_smoke_passes_with_valid_build(mock_urlopen):
    """Valid HTML with <div id="root"> + hashed asset → all pass."""
    from scripts.smoke_app import smoke_test

    mock_urlopen.side_effect = _make_urlopen({
        "http://test.example.com/": _html_response(_GOOD_HTML),
        "http://test.example.com/assets/index-abc123.js": _html_response(_GOOD_JS, "application/javascript"),
        "http://test.example.com/api/health": _json_response({"status": "ok"}),
        "http://test.example.com/api/signals": _json_response({"data": []}),
        "http://test.example.com/api/market/NVDA": _json_response({"symbol": "NVDA"}),
        "http://test.example.com/api/analytics": _json_response({"data": []}),
        "http://test.example.com/api/portfolio": _json_response({"positions": []}),
        "http://test.example.com/api/watchlists": _json_response({"data": []}),
    })

    assert smoke_test("http://test.example.com") is True


@patch("urllib.request.urlopen")
def test_smoke_fails_on_json_hint(mock_urlopen):
    """Missing-build JSON hint → FAIL."""
    from scripts.smoke_app import smoke_test

    hint = json.dumps({"error": "no frontend build", "hint": "run npm run build"}).encode()
    resp = MagicMock()
    resp.status = 200
    resp.read.return_value = hint
    resp.headers = {"Content-Type": "application/json"}
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)

    mock_urlopen.side_effect = _make_urlopen({
        "http://test.example.com/": resp,
    })

    assert smoke_test("http://test.example.com") is False


@patch("urllib.request.urlopen")
def test_smoke_fails_on_non_html(mock_urlopen):
    """Arbitrary non-HTML content → FAIL."""
    from scripts.smoke_app import smoke_test

    resp = MagicMock()
    resp.status = 200
    resp.read.return_value = b"this is not HTML at all"
    resp.headers = {"Content-Type": "text/plain"}
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)

    mock_urlopen.side_effect = _make_urlopen({
        "http://test.example.com/": resp,
    })

    assert smoke_test("http://test.example.com") is False


@patch("urllib.request.urlopen")
def test_smoke_fails_on_missing_root_div(mock_urlopen):
    """HTML without <div id="root"> → FAIL."""
    from scripts.smoke_app import smoke_test

    bad_html = '<!doctype html><html><body><p>no root div</p></body></html>'
    resp = _html_response(bad_html)

    mock_urlopen.side_effect = _make_urlopen({
        "http://test.example.com/": resp,
    })

    assert smoke_test("http://test.example.com") is False


@patch("urllib.request.urlopen")
def test_smoke_fails_on_asset_not_found(mock_urlopen):
    """HTML with asset that returns 404 → FAIL."""
    from scripts.smoke_app import smoke_test

    asset_resp = MagicMock()
    asset_resp.status = 404
    asset_resp.__enter__ = lambda s: s
    asset_resp.__exit__ = MagicMock(return_value=False)

    mock_urlopen.side_effect = _make_urlopen({
        "http://test.example.com/": _html_response(_GOOD_HTML),
        "http://test.example.com/assets/index-abc123.js": asset_resp,
    })

    assert smoke_test("http://test.example.com") is False