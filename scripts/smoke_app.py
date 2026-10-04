#!/usr/bin/env python3
"""scripts/smoke_app.py — Smoke-test a deployed Databricks App.

Usage:
    python scripts/smoke_app.py <base_url>

Example:
    python scripts/smoke_app.py https://quant-platform-prod.us-east-1.databricksapps.com

Checks:
    1. GET /             → 200 (index.html or hint JSON)
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


def _make_headers() -> dict[str, str]:
    token = __import__("os").environ.get("AUTH_TOKEN", "")
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


def smoke_test(base_url: str) -> bool:
    base = base_url.rstrip("/")
    headers = _make_headers()
    all_pass = True

    for label, path in CHECKS:
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

        # For /, accept either HTML (index.html) or JSON (hint).
        if path == "/":
            content_type = ""
            # urllib may not expose headers easily; check body start
            if body.lstrip()[:1] == b"<" or body.lstrip()[:1] == b"{":
                print(f"PASS  {label} — HTTP {status}")
            else:
                print(f"PASS  {label} — HTTP {status} (unexpected body format)")
        else:
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