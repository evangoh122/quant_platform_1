from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


class ChatRequest(BaseModel):
    # 4000 matches the hard cap enforced by input_rails.check_input; keep them in
    # sync so oversize input is rejected once at the schema boundary rather than
    # passing validation and then 400-ing at runtime.
    message: str = Field(min_length=1, max_length=4000)
    ticker: Optional[str] = Field(default="NVDA", max_length=10)
    history: Optional[List[Dict[str, str]]] = Field(default=None, max_length=50)
    # Conjoint `role_based` personalization: when set to one of the role keys
    # (compliance_officer, equity_research_analyst, credit_analyst,
    # relationship_manager), the answer's tone/emphasis is tailored to it.
    # None (the default) → role-agnostic answer.
    role: Optional[str] = Field(
        default=None,
        max_length=40,
        pattern="^(compliance_officer|equity_research_analyst|credit_analyst|relationship_manager)?$",
    )


# ── Structured Output Models ─────────────────────────────────────────────────

# section_id → human-readable citation label. Lookup keys are normalised to
# lowercase snake_case ("Item 7" → "item_7"); unmapped ids fall back to the
# raw section_id.
SECTION_LABELS = {
    "item_1": "Item 1 — Business",
    "item_1a": "Item 1A — Risk Factors",
    "item_7": "Item 7 — MD&A",
    "item_7a": "Item 7A — Quantitative Disclosures",
    "item_8": "Item 8 — Financial Statements",
    "business": "Business",
    "md_and_a": "MD&A",
    "full_text": "Full Filing",
    "risk_factors": "Risk Factors",
    "prospectus_summary": "Prospectus Summary",
}


class SourceItem(BaseModel):
    """A retrieved source chunk with metadata. Matches frontend Source interface."""
    ticker: str = ""
    accession: str = ""
    section: str = ""
    text: str = ""
    edgar_url: str = ""
    distance: Optional[float] = None
    # Exact-citation fields (document / section / paragraph provenance)
    form_type: str = ""
    period_of_report: str = ""
    chunk_index: Optional[int] = None
    snippet: str = ""


class VerificationResult(BaseModel):
    """Verification status and reasoning."""
    status: str = "not_checked"  # PASS, FAIL, SKIPPED, ERROR, not_checked
    reasoning: str = ""


class PipelineStatus(BaseModel):
    """Status of each pipeline node."""
    input: str = "pending"
    retrieval: str = "pending"
    classifier: str = "pending"
    extraction: str = "pending"
    eval: str = "pending"
    math: str = "pending"
    verification: str = "pending"
    output: str = "pending"


class ChatResponse(BaseModel):
    """Structured response from all chat endpoints.

    All endpoints return this consistent shape. Fields not applicable
    to a given mode are omitted (None) rather than missing.
    """
    type: str = "text"  # "text", "table", "error"
    answer: str = ""

    # The company the query actually resolved to (may differ from the requested
    # ticker when the question names a different company). The UI persists this
    # so follow-ups stay grounded on the same company.
    ticker: str = ""

    # Retrieval sources
    sources: List[SourceItem] = Field(default_factory=list)

    # Financial data
    xbrl_facts: List[Dict[str, Any]] = Field(default_factory=list)
    relevant_xbrl: List[Dict[str, Any]] = Field(default_factory=list)
    xbrl_badge: str = ""
    xbrl_group: str = ""
    polygon_data: List[Dict[str, Any]] = Field(default_factory=list)

    # Standard Response Framework — educational layers (sections 3–5).
    # Additive, display-only; empty when not applicable (abstention) or disabled.
    what_it_means: str = ""
    how_to_interpret: str = ""
    follow_ups: List[str] = Field(default_factory=list)

    # Verification
    verification: VerificationResult = Field(default_factory=VerificationResult)

    # Math / calculation trace
    math_steps: List[str] = Field(default_factory=list)

    # Pipeline status
    pipeline_status: PipelineStatus = Field(default_factory=PipelineStatus)

    # Graph RAG specific. Triples carry source refs + node types (Phase C) so
    # the Evidence Graph is auditable, so values are mixed (str + float).
    entities: List[str] = Field(default_factory=list)
    triples: List[Dict[str, Any]] = Field(default_factory=list)

    # Optional chart spec (recharts). Built deterministically from XBRL facts
    # when the LLM calls the charting tool — never from model-generated numbers.
    # Shape: {type, title, metric, unit, data:[{period, value}]}.
    chart: Optional[Dict[str, Any]] = None

    # SQL mode specific
    sql: Optional[str] = None
    data: Optional[List[Dict[str, Any]]] = None

    # Confidence / eval
    confidence: Optional[float] = None
    eval_route: Optional[str] = None  # AUTO, SAMPLED_REVIEW, ESCALATE

    # Lineage / audit
    lineage: Optional[Dict[str, Any]] = None

    # Sentiment / management tone (Phase B — populated post-processing)
    tone_analysis: Optional[Dict[str, Any]] = None


# ── Sentiment Analysis Models ────────────────────────────────────────────────

class SectionSentiment(BaseModel):
    """Loughran-McDonald sentiment counts for a single filing section."""
    section_type: str
    total_words: int = 0
    positive: int = 0
    negative: int = 0
    uncertainty: int = 0
    litigious: int = 0
    constraining: int = 0
    strong_modal: int = 0
    weak_modal: int = 0
    net_sentiment: float = 0.0
    tone_score: float = 0.0


class FilingSentiment(BaseModel):
    """Full sentiment analysis result for a filing."""
    ticker: str
    accession: str = ""
    form_type: str = ""
    period_of_report: str = ""
    sections: List[SectionSentiment] = Field(default_factory=list)
    totals: Dict[str, int] = Field(default_factory=dict)
    total_words: int = 0
    overall_net_sentiment: float = 0.0
    overall_tone_score: float = 0.0


class SentimentDelta(BaseModel):
    """Per-category change between two filings."""
    previous: int = 0
    current: int = 0
    delta: int = 0
    pct_change: float = 0.0


class FilingSentimentCompare(BaseModel):
    """Comparison of sentiment between two filings."""
    ticker: str
    filing_a: Dict[str, str] = Field(default_factory=dict)
    filing_b: Dict[str, str] = Field(default_factory=dict)
    changes: Dict[str, SentimentDelta] = Field(default_factory=dict)
    tone_shift: float = 0.0


class ToneShiftResult(BaseModel):
    """Embedding-based cosine similarity between MD&A sections."""
    ticker: str
    filing_a: Dict[str, str] = Field(default_factory=dict)
    filing_b: Dict[str, str] = Field(default_factory=dict)
    similarity: float = 0.0
    interpretation: str = ""
    thresholds: Dict[str, str] = Field(default_factory=dict)
