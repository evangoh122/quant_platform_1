"""pipelines/_http_adapter.py — Production HTTP adapter for SEC requests.

Separated from sec_rag_ingest.py to keep the core module importable without
requests being installed at import time.
"""
from __future__ import annotations

import requests

from pipelines.sec_rag_ingest import HttpClient, HttpResponse


class RequestsAdapter:
    """Production HTTP adapter using the requests library."""

    def get(
        self,
        url: str,
        headers: dict[str, str],
        timeout: float = 30.0,
    ) -> HttpResponse:
        resp = requests.get(url, headers=headers, timeout=timeout)
        return HttpResponse(
            status_code=resp.status_code,
            text=resp.text,
            headers=dict(resp.headers),
        )