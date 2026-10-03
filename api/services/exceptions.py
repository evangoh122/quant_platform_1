"""api/services/exceptions.py — Shared exception types for retrieval services.

Separated from hybrid_retriever.py to avoid circular imports with embeddings.py.
"""


class CorpusUnavailableError(Exception):
    """Raised when the retrieval corpus cannot be loaded from Delta tables.

    Callers must surface this as a structured "retrieval unavailable" result
    so the agent can report the failure — never silently return an empty list.
    """


class EmbeddingConfigError(CorpusUnavailableError):
    """Raised when the embedding provider is misconfigured.

    This is a loud configuration error — callers must NOT degrade to BM25-only.
    Only a TRANSIENT runtime failure of a correctly configured embedder may
    degrade.  Missing tokens, unknown providers, and unloadable models are
    configuration bugs that must surface immediately.

    Subclass of CorpusUnavailableError so search_sec_filings surfaces it as
    retrieval_unavailable with the missing setting name — never the secret value.
    """