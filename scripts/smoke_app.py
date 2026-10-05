#!/usr/bin/env python3
"""scripts/smoke_app.py — Smoke-test a deployed Databricks App.

Usage:
    python scripts/smoke_app.py <base_url>

Example:
    python scripts/smoke_app.py https://quant-platform-prod.us-east-1.databricksapps.com

Checks:
    1. GET /             → 200 with HTML containing <div id="root"> and a
                           hashed asset that GETs 200 (rejects JSON hint / non-HTML)
    2. GET /api/health   → 200 with JSON status
    3. GET /api/signals  → 200
    4. GET /api/market/NVDA → 200
    5. GET /api/analytics → 200
    6. GET /api/portfolio → 200
    7. GET /api/watchlists → 200

Prints PASS or FAIL per check.  No secrets are embedded; if the app
requires authentication, set the AUTH_TOKEN environment variable to a
Databricks personal access token or OAuth token.
"""

from __future__ import annotations

import re
import sys
import urllib.request
import json


CHECKS = [
    ("GET /", "/"),
    ("GET /api/health", "/api/health"),
    ("GET /api/signals", "/api/signals"),
    ("GET /api/market/NVDA", "/api/market/NVDA"),
    ("GET /api/analytics", "/api/analytics"),
    ("GET /api/portfolio", "/api/portfolio"),
    ("GET /api/watchlists", "/api/watchlists"),
]

_ASSET_RE = re.compile(r'src=["\'](/assets/[^"\']+\.js)["\']')


def _make_headers() -> dict[str, str]:
    token = __import__("os").environ.get("AUTH_TOKEN", "")
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


def _check_frontend_build(base: str, headers: dict[str, str]) -> bool:
    """Verify the frontend was actually built and shipped.

    Returns True only if:
    - Response is HTML (not JSON hint)
    - HTML contains <div id="root">
    - HTML contains a hashed asset reference (/assets/*.js)
    - The referenced asset GETs 200
    """
    url = f"{base}/"
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            status = resp.status
            body = resp.read()
            content_type = resp.headers.get("Content-Type", "")
    except Exception as exc:
        print(f"FAIL  GET / — {exc}")
        return False

    if status != 200:
        print(f"FAIL  GET / — HTTP {status}")
        return False

    text = body.decode("utf-8", errors="replace")

    # Must be HTML, not JSON (missing-build hint)
    if "text/html" not in content_type and not text.lstrip().startswith("<"):
        print(f"FAIL  GET / — not HTML (Content-Type: {content_type})")
        return False

    # Reject the missing-build JSON hint
    stripped = body.lstrip()
    if stripped[:1] == b"{":
        try:
            hint = json.loads(body)
            if "error" in hint or "hint" in hint:
                print(f"FAIL  GET / — missing-build JSON hint: {hint}")
                return False
        except json.JSONDecodeError:
            pass

    # Must contain <div id="root">
    if '<div id="root">' not in text:
        print("FAIL  GET / — missing <div id=\"root\">")
        return False

    # Must contain a hashed asset reference
    m = _ASSET_RE.search(text)
    if not m:
        print("FAIL  GET / — no hashed asset reference found")
        return False

    # Verify the asset GETs 200
    asset_path = m.group(1)
    asset_url = f"{base}{asset_path}"
    asset_req = urllib.request.Request(asset_url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(asset_req, timeout=15) as asset_resp:
            if asset_resp.status != 200:
                print(f"FAIL  GET {asset_path} — HTTP {asset_resp.status}")
                return False
    except Exception as exc:
        print(f"FAIL  GET {asset_path} — {exc}")
        return False

    print(f"PASS  GET / — HTML with <div id=\"root\"> + {asset_path} → 200")
    return True


def smoke_test(base_url: str) -> bool:
    base = base_url.rstrip("/")
    headers = _make_headers()
    all_pass = True

    # Check 1: frontend build verification (special handling)
    if not _check_frontend_build(base, headers):
        all_pass = False

    # Checks 2-7: API routes
    for label, path in CHECKS[1:]:
        url = f"{base}{path}"
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                status = resp.status
                body = resp.read()
        except Exception as exc:
            print(f"FAIL  {label} — {exc}")
            all_pass = False
            continue

        if status != 200:
            print(f"FAIL  {label} — HTTP {status}")
            all_pass = False
            continue

        # API routes should return JSON
        try:
            json.loads(body)
            print(f"PASS  {label} — HTTP {status}")
        except json.JSONDecodeError:
            print(f"FAIL  {label} — HTTP {status} but response is not JSON")
            all_pass = False

    return all_pass


def main() -> None:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <base_url>", file=sys.stderr)
        sys.exit(1)

    base_url = sys.argv[1]
    print(f"Smoke-testing: {base_url}\n")

    ok = smoke_test(base_url)
    print()
    if ok:
        print("ALL CHECKS PASSED")
    else:
        print("SOME CHECKS FAILED")
        sys.exit(1)


if __name__ == "__main__":
    main()