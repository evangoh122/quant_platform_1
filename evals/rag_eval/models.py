"""evals/rag_eval/models.py — typed data models for the RAG eval harness."""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


# ── Retrieval modes ───────────────────────────────────────────────────────────

RETRIEVAL_MODES = ("bm25", "dense", "hybrid_rrf", "hybrid_rerank")


# ── Golden item ───────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class GoldenItem:
    """A single evaluation question with expected retrieval targets."""
    id: str
    ticker: str
    question: str
    gold_chunk_ids: tuple[str, ...] = ()
    gold_accession_sections: tuple[tuple[str, str], ...] = ()
    item_type: str = "answerable"  # answerable | unanswerable | point_in_time_trap
    # For PIT traps: which filing is the allowed older evidence
    allowed_older_chunk_ids: tuple[str, ...] = ()
    as_of: Optional[str] = None  # ISO UTC; None means now
    gold_answer: Optional[str] = None

    def as_of_datetime(self) -> datetime:
        if self.as_of is None:
            return datetime.now(timezone.utc)
        dt = datetime.fromisoformat(self.as_of)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt


# ── Corpus record ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CorpusRecord:
    """A single chunk from the SEC corpus."""
    chunk_id: str
    ticker: str
    accession: str
    section: str
    form_type: str
    accepted_ts: str  # ISO UTC
    text: str
    chunk_index: int = 0
    source_url: str = ""

    def accepted_datetime(self) -> Optional[datetime]:
        if not self.accepted_ts:
            return None
        dt = datetime.fromisoformat(self.accepted_ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt


# ── Retrieval hit ─────────────────────────────────────────────────────────────

@dataclass
class RetrievalHit:
    """A single retrieval result with all scoring metadata."""
    chunk_id: str
    ticker: str
    accession: str
    section: str
    form_type: str
    accepted_ts: str
    text: str
    rank: int
    retrieval_mode: str = ""
    component_score: Optional[float] = None  # BM25 or cosine score
    rerank_score: Optional[float] = None
    similarity: Optional[float] = None
    distance: Optional[float] = None


# ── Retrieval config ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class RetrievalConfig:
    """One ablation configuration."""
    mode: str  # bm25 | dense | hybrid_rrf | hybrid_rerank
    ticker_filter: bool = True
    top_k: int = 10
    rrf_k: int = 60
    candidate_depth_multiplier: int = 2

    @property
    def candidate_depth(self) -> int:
        return self.top_k * self.candidate_depth_multiplier

    def label(self) -> str:
        ticker = "ticker_on" if self.ticker_filter else "ticker_off"
        return f"{self.mode}__{ticker}"


# ── Item result ───────────────────────────────────────────────────────────────

@dataclass
class ItemResult:
    """Result of running one golden item through one config."""
    item: GoldenItem
    config: RetrievalConfig
    hits: list[RetrievalHit] = field(default_factory=list)
    error: Optional[str] = None
    # Computed metrics (filled by scoring)
    metrics: dict[str, Any] = field(default_factory=dict)
    leakage_count: int = 0
    # Abstention/trap outcomes
    allowed_top_hit: Optional[bool] = None
    abstention_label: Optional[str] = None


# ── Run report ────────────────────────────────────────────────────────────────

@dataclass
class RunReport:
    """Aggregate report for a full eval run."""
    run_id: str = ""
    git_sha: str = ""
    corpus_sha256: str = ""
    golden_sha256: str = ""
    embedding_model: str = ""
    embedding_revision: str = ""
    embedding_dimension: int = 0
    reranker_model: str = ""
    reranker_revision: str = ""
    reranker_disabled_reason: str = ""
    rrf_k: int = 60
    candidate_depth_multiplier: int = 2
    top_k_values: list[int] = field(default_factory=list)
    seed: int = 1729
    adapter_type: str = ""
    cli_args: dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""
    environment: dict[str, str] = field(default_factory=dict)
    item_results: list[ItemResult] = field(default_factory=list)
    # Aggregate metrics
    overall_metrics: dict[str, Any] = field(default_factory=dict)
    per_type_metrics: dict[str, dict[str, Any]] = field(default_factory=dict)
    per_ticker_metrics: dict[str, dict[str, Any]] = field(default_factory=dict)
    per_mode_metrics: dict[str, dict[str, Any]] = field(default_factory=dict)
    secondary_metrics: dict[str, Any] = field(default_factory=dict)
    bootstrap_cis: dict[str, Any] = field(default_factory=dict)
    abstention_results: dict[str, Any] = field(default_factory=dict)
    pit_leakage_total: int = 0
    pit_leakage_by_config: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)