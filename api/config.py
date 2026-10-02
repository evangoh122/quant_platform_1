import os
from pathlib import Path
from loguru import logger
from dotenv import load_dotenv


def _validate_db_path(path: str) -> str:
    """Validate DB_PATH against an allowlist of roots (prevents path traversal).

    Allowed: anywhere under the project root, or under the persistent-storage
    mount (PERSIST_DIR, default /data on HF Spaces) so the DB can live on a
    volume that survives restarts.
    """
    if not path or not path.strip():
        logger.warning("DB_PATH is empty, falling back to default.")
        return str(Path(__file__).parent.parent / "data" / "rag.duckdb")
    resolved = Path(path).resolve()
    project_root = Path(__file__).parent.parent.resolve()
    allowed_roots = [str(project_root)]
    persist_dir = os.getenv("PERSIST_DIR", "/data").strip()
    if persist_dir:
        allowed_roots.append(str(Path(persist_dir).resolve()))
    if not any(str(resolved).startswith(root) for root in allowed_roots):
        logger.warning(f"DB_PATH '{path}' is outside allowed roots {allowed_roots}. Falling back to default.")
        return str(project_root / "data" / "rag.duckdb")
    return str(resolved)


class Config:
    def __init__(self):
        # Load .env from the root directory
        load_dotenv(Path(__file__).parent.parent / ".env")
        self._db_path = None
        self._review_db_path = None

    @property
    def DB_PATH(self) -> str:
        if self._db_path is None:
            self._db_path = _validate_db_path(os.getenv("DB_PATH", "./data/rag.duckdb"))
        return self._db_path

    @property
    def REVIEW_DB_PATH(self) -> str:
        """Runtime DB holding the audit log + review/testing queue.

        This data is generated at runtime and must SURVIVE container restarts,
        so it lives on the persistent-storage volume (PERSIST_DIR — e.g. HF
        Spaces persistent storage mounted at /data) whenever that volume is
        actually mounted and writable. Falls back to the local project dir for
        dev. An explicit REVIEW_DB_PATH env var always wins.

        NOTE: keep the MAIN DB_PATH OFF the persistent volume — it is restored
        fresh from the HF dataset each boot, and persisting it would pin a stale
        corpus.
        """
        if self._review_db_path is None:
            explicit = os.getenv("REVIEW_DB_PATH")
            if explicit:
                self._review_db_path = explicit
            else:
                persist = os.getenv("PERSIST_DIR", "/data").strip()
                if persist and os.path.isdir(persist) and os.access(persist, os.W_OK):
                    self._review_db_path = str(Path(persist) / "review_queue.duckdb")
                else:
                    self._review_db_path = "./data/review_queue.duckdb"
        return self._review_db_path

    # ── LangSmith (tracing & observability) ──────────────────────────────────
    @property
    def LANGSMITH_API_KEY(self) -> str | None:
        return os.getenv("LANGSMITH_API_KEY") or None

    @property
    def LANGSMITH_PROJECT(self) -> str:
        return os.getenv("LANGSMITH_PROJECT", "rag-workbench")

    @property
    def LANGSMITH_TRACING(self) -> bool:
        return os.getenv("LANGSMITH_TRACING", "false").lower() == "true"

    # Phase 8: Drift alert thresholds
    @property
    def DRIFT_AGREEMENT_FLOOR(self) -> float:
        return float(os.getenv("DRIFT_AGREEMENT_FLOOR", "0.95"))

    @property
    def DRIFT_CONCEPT_SPIKE_THRESHOLD(self) -> int:
        return int(os.getenv("DRIFT_CONCEPT_SPIKE_THRESHOLD", "50"))

    # Provider Settings
    @property
    def CHAT_PROVIDER(self) -> str:
        return os.getenv("CHAT_PROVIDER", "deepseek").lower()

    @property
    def CHAT_MODEL(self) -> str | None:
        return os.getenv("CHAT_MODEL")

    # API Keys
    @property
    def DEEPSEEK_API_KEY(self) -> str | None:
        return os.getenv("DEEPSEEK_API_KEY") or os.getenv("DEEP_SEEK_API_KEY")

    @property
    def DEEPSEEK_MAX_TOKENS(self) -> int:
        return int(os.getenv("DEEPSEEK_MAX_TOKENS", "4096"))

    @property
    def DEEPSEEK_TEMPERATURE(self) -> float:
        return float(os.getenv("DEEPSEEK_TEMPERATURE", "0.1"))

    @property
    def OPENAI_API_KEY(self) -> str | None:
        return os.getenv("OPENAI_API_KEY")

    @property
    def ANTHROPIC_API_KEY(self) -> str | None:
        return os.getenv("ANTHROPIC_API_KEY")

    @property
    def GOOGLE_API_KEY(self) -> str | None:
        return os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")

    @property
    def MIMO_API_KEY(self) -> str | None:
        return os.getenv("MIMO_API_KEY") or os.getenv("XIAOMI_API_KEY")

    @property
    def POLYGON_API_KEY(self) -> str | None:
        return os.getenv("POLYGON_API_KEY") or None

    # ── PostHog (server-side read of product analytics) ───────────────────────
    @property
    def POSTHOG_API_KEY(self) -> str | None:
        # Personal API key (read scope) — only needed to pull aggregates back
        # from PostHog's Query API for the analytics page. Self-capture to
        # DuckDB works without it.
        return os.getenv("POSTHOG_API_KEY") or os.getenv("POSTHOG_PERSONAL_API_KEY") or None

    @property
    def POSTHOG_PROJECT_ID(self) -> str | None:
        return os.getenv("POSTHOG_PROJECT_ID") or None

    @property
    def POSTHOG_API_HOST(self) -> str:
        return os.getenv("POSTHOG_API_HOST", "https://us.posthog.com").rstrip("/")

    # MiMo reasoning model needs large token budget
    @property
    def MIMO_MAX_TOKENS(self) -> int:
        return int(os.getenv("MIMO_MAX_TOKENS", "16384"))

    @property
    def MIMO_TEMPERATURE(self) -> float:
        return float(os.getenv("MIMO_TEMPERATURE", "0.1"))

    # ── Reranker Settings ─────────────────────────────────────────────────────
    @property
    def RERANKER_MODEL(self) -> str:
        return os.getenv("RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")

    @property
    def RERANKER_TOP_K(self) -> int:
        return int(os.getenv("RERANKER_TOP_K", "5"))

    # Embedding Settings
    @property
    def EMBEDDING_PROVIDER(self) -> str:
        return os.getenv("EMBEDDING_PROVIDER", "huggingface").lower()

    @property
    def HF_EMBEDDING_MODEL(self) -> str:
        return os.getenv("HF_EMBEDDING_MODEL", "Qwen/Qwen3-Embedding-8B")

    @property
    def ST_EMBEDDING_MODEL(self) -> str:
        # Local sentence-transformers model (runs in-process, no inference API).
        # Qwen3-Embedding-0.6B is 1024-dim — strong retrieval quality, ~1.2GB,
        # small enough to run in-process on the Space (the 8B variant OOMs).
        return os.getenv("ST_EMBEDDING_MODEL", "Qwen/Qwen3-Embedding-0.6B")

    @property
    def ACTIVE_EMBEDDING_MODEL(self) -> str:
        """The embedding model actually in use, per the configured provider.
        Use this for display/telemetry instead of reading provider-specific
        env vars directly."""
        provider = os.getenv("EMBEDDING_PROVIDER", "huggingface").lower()
        if provider in ("sentence-transformers", "sentence_transformers", "local", "st"):
            return self.ST_EMBEDDING_MODEL
        return self.HF_EMBEDDING_MODEL

    @property
    def EMBEDDING_QUERY_PREFIX(self) -> str:
        return os.getenv("EMBEDDING_QUERY_PREFIX", "")

    @property
    def EMBEDDING_DIM(self) -> int:
        # Explicit override always wins; otherwise default per provider.
        explicit = os.getenv("EMBEDDING_DIM")
        if explicit:
            return int(explicit)
        provider = os.getenv("EMBEDDING_PROVIDER", "huggingface").lower()
        if provider in ("sentence-transformers", "sentence_transformers", "local", "st"):
            return 1024  # Qwen/Qwen3-Embedding-0.6B
        if provider == "huggingface":
            return 4096  # Qwen/Qwen3-Embedding-8B
        return 4096

    def get_provider_config(self):
        providers = {
            "deepseek": {
                "base_url": os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
                "default_model": os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
                "api_key": self.DEEPSEEK_API_KEY,
                "max_tokens": self.DEEPSEEK_MAX_TOKENS,
                "temperature": self.DEEPSEEK_TEMPERATURE,
            },
            "openai": {
                "base_url": os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
                "default_model": os.getenv("OPENAI_MODEL", "gpt-4o"),
                "api_key": self.OPENAI_API_KEY,
                "max_tokens": int(os.getenv("OPENAI_MAX_TOKENS", "4096")),
                "temperature": float(os.getenv("OPENAI_TEMPERATURE", "0.1")),
            },
            "anthropic": {
                "base_url": "https://api.anthropic.com/v1",
                "default_model": os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
                "api_key": self.ANTHROPIC_API_KEY,
                "max_tokens": int(os.getenv("ANTHROPIC_MAX_TOKENS", "4096")),
                "temperature": float(os.getenv("ANTHROPIC_TEMPERATURE", "0.1")),
            },
            "mimo": {
                "base_url": os.getenv("MIMO_BASE_URL", "https://token-plan-sgp.xiaomimimo.com/v1"),
                "default_model": os.getenv("MIMO_MODEL", "mimo-v2.5-pro"),
                "api_key": self.MIMO_API_KEY,
                "max_tokens": self.MIMO_MAX_TOKENS,
                "temperature": self.MIMO_TEMPERATURE,
            },
        }

        if self.CHAT_PROVIDER not in providers:
            logger.warning(f"Unknown CHAT_PROVIDER '{self.CHAT_PROVIDER}', falling back to deepseek")
            return providers["deepseek"]

        cfg = providers[self.CHAT_PROVIDER]

        if not cfg.get("api_key"):
            logger.warning(f"No API key set for provider '{self.CHAT_PROVIDER}'")

        return {
            "base_url": cfg["base_url"],
            "model": self.CHAT_MODEL or cfg["default_model"],
            "api_key": cfg["api_key"],
            "max_tokens": cfg.get("max_tokens", 4096),
            "temperature": cfg.get("temperature", 0.3),
        }

    def validate_startup(self):
        """Warn on missing but recommended env vars."""
        provider = self.CHAT_PROVIDER
        if provider == "deepseek" and not self.DEEPSEEK_API_KEY:
            logger.warning("DEEPSEEK_API_KEY not set — deepseek provider will fail")
        elif provider == "openai" and not self.OPENAI_API_KEY:
            logger.warning("OPENAI_API_KEY not set — openai provider will fail")
        elif provider == "anthropic" and not self.ANTHROPIC_API_KEY:
            logger.warning("ANTHROPIC_API_KEY not set — anthropic provider will fail")
        elif provider == "mimo" and not self.MIMO_API_KEY:
            logger.warning("MIMO_API_KEY/XIAOMI_API_KEY not set — mimo provider will fail")

        if not self.GOOGLE_API_KEY and provider not in ("mimo", "openai", "anthropic"):
            logger.warning("GOOGLE_API_KEY/GEMINI_API_KEY not set — embeddings may fail if using default")

    def init_langsmith(self):
        """Initialise LangSmith if enabled."""
        if self.LANGSMITH_TRACING and self.LANGSMITH_API_KEY:
            os.environ["LANGCHAIN_TRACING_V2"] = "true"
            os.environ["LANGCHAIN_API_KEY"] = self.LANGSMITH_API_KEY
            os.environ["LANGCHAIN_PROJECT"] = self.LANGSMITH_PROJECT


# Global instance
config = Config()

# Export 'Config' as the instance for backward compatibility with 'Config.ATTRIBUTE'
Config = config

TICKER_TO_CIK = {
    "ADI": "0000006281", "AMD": "0000002488", "AVGO": "0001730168",
    "INTC": "0000050863", "MU": "0000723125", "NVDA": "0001045810",
    "QCOM": "0000804328", "TXN": "0000097476", "TSM": "0001046179",
    "MRVL": "0001835632", "NXPI": "0001413447", "MCHP": "0000827054",
    "MPWR": "0001280452", "SWKS": "0000004127", "QRVO": "0001604778",
    "ON": "0001097864", "AMAT": "0000006951", "LRCX": "0000707549",
    "KLAC": "0000319201", "TER": "0000097210", "ENTG": "0001101302",
    "ONTO": "0000704532", "FORM": "0001039399", "PLAB": "0000810136",
    "COHU": "0000021535", "KLIC": "0000056978", "ICHR": "0001652535",
    "VECO": "0000103145", "AEHR": "0001040470", "ACLS": "0000897077",
    "AMKR": "0001047127",
    "STM": "0000932787",
    "RKLB": "0001819994",
    "SPCX": "0001181412",
}

