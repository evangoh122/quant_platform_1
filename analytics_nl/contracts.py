"""NL1 Pydantic v2 contracts — strict, frozen, dependency-light.

Every model uses ConfigDict(extra="forbid", strict=True) to prevent silent
coercion and reject unknown fields at the wire level.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from enum import Enum
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------

SEMANTIC_MODEL_VERSION: str = "1.0.0"

# ---------------------------------------------------------------------------
# Shared config
# ---------------------------------------------------------------------------

_STRICT = ConfigDict(extra="forbid", strict=True)

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class Operation(str, Enum):
    """Supported analytics operations."""

    trend = "trend"
    compare = "compare"
    rank = "rank"
    aggregate = "aggregate"


class Metric(str, Enum):
    """Supported analytics metrics.  Market capitalization is intentionally
    excluded because there is no governed shares-outstanding source."""

    price = "price"
    return_ = "return"
    volume = "volume"
    realized_volatility = "realized_volatility"
    drawdown = "drawdown"
    momentum = "momentum"
    relative_performance = "relative_performance"
    implied_volatility = "implied_volatility"
    put_call_ratio = "put_call_ratio"


class EntityType(str, Enum):
    """Discriminator for entity references."""

    ticker = "ticker"
    sector = "sector"
    index = "index"


class Grouping(str, Enum):
    """Allowed grouping values (daily-or-coarser)."""

    day = "day"
    week = "week"
    month = "month"
    quarter = "quarter"
    year = "year"
    ticker = "ticker"
    sector = "sector"


class CostClass(str, Enum):
    """Policy cost classification."""

    CHEAP = "CHEAP"
    NORMAL = "NORMAL"
    EXPENSIVE = "EXPENSIVE"
    REJECT = "REJECT"


class PolicyReasonCode(str, Enum):
    """Deterministic reason codes for policy decisions."""

    ACCEPTED_CHEAP = "ACCEPTED_CHEAP"
    ACCEPTED_NORMAL = "ACCEPTED_NORMAL"
    ACCEPTED_EXPENSIVE = "ACCEPTED_EXPENSIVE"
    INTRADAY_UNSUPPORTED = "INTRADAY_UNSUPPORTED"
    DATE_RANGE_EXCEEDED = "DATE_RANGE_EXCEEDED"
    TICKER_LIMIT_EXCEEDED = "TICKER_LIMIT_EXCEEDED"
    ROW_LIMIT_EXCEEDED = "ROW_LIMIT_EXCEEDED"
    MISSING_REQUIRED_SLOT = "MISSING_REQUIRED_SLOT"
    GROUPING_NOT_ALLOWED = "GROUPING_NOT_ALLOWED"
    ORDERING_NOT_ALLOWED = "ORDERING_NOT_ALLOWED"
    PAIR_NOT_REGISTERED = "PAIR_NOT_REGISTERED"
    ENTITY_NOT_ALLOWED = "ENTITY_NOT_ALLOWED"
    FUTURE_DATE = "FUTURE_DATE"
    END_BEFORE_START = "END_BEFORE_START"
    UNADJUSTED_CORPORATE_ACTION = "UNADJUSTED_CORPORATE_ACTION"
    TOO_FEW_ENTITIES = "TOO_FEW_ENTITIES"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class CacheStatus(str, Enum):
    """Cache status for provenance envelopes."""

    hit = "hit"
    miss = "miss"
    bypass = "bypass"


class CoverageStatus(str, Enum):
    """Status for metric coverage in aggregate/rank/compare responses."""

    ok = "ok"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class RelativeDate(str, Enum):
    """Closed set of relative date expressions.

    Each value is a canonical wire value that ``resolve_relative_date`` accepts.
    Aliases (e.g. "last month" → ``last_month``) are handled in the deterministic
    alias layer, NOT in the LLM schema.
    """

    last_week = "last_week"
    last_month = "last_month"
    last_quarter = "last_quarter"
    last_year = "last_year"
    ytd = "ytd"
    mtd = "mtd"
    qtd = "qtd"
    last_5_days = "last_5_days"
    last_30_days = "last_30_days"
    last_90_days = "last_90_days"
    last_252_days = "last_252_days"


class ChartType(str, Enum):
    """Approved chart types."""

    line = "line"
    bar = "bar"
    table = "table"


class DataType(str, Enum):
    """Scalar data types for chart axis/series."""

    string = "string"
    number = "number"
    integer = "integer"
    date = "date"


# ---------------------------------------------------------------------------
# Identifier patterns
# ---------------------------------------------------------------------------

_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.]{0,9}$")
_SECTOR_RE = re.compile(r"^[a-z_][a-z0-9_]*$")
_IDENTIFIER_RE = re.compile(r"^[a-z_][a-z0-9_]*$")
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_SQL_METACHAR_RE = re.compile(r"""["`\\;]|--|/\*|\*/""")
_PROMPT_INJECTION_RE = re.compile(
    r"ignore\s+previous|reveal\s+(?:the\s+)?system|you\s+are\s+now|forget\s+(?:your|all)|disregard\s+(?:all|previous)|system\s*:|override\s+(?:safety|all)|bypass\s+(?:safety|all|filters)|ignore\s+(?:all|safety|constraints)|forget\s+(?:all|safety|constraints)",
    re.IGNORECASE,
)
_ENTITY_MENTION_PATTERN: str = r"^[A-Za-z0-9][A-Za-z0-9 .&\-/'_]{0,24}$"
_ENTITY_MENTION_RE = re.compile(_ENTITY_MENTION_PATTERN)
_SQL_KEYWORD_RE = re.compile(
    r"\b(?:SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|UNION|EXEC|EXECUTE|TRUNCATE|GRANT|REVOKE)\b",
    re.IGNORECASE,
)
_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
_TRACE_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")

# LLM forbidden property names (must not appear in LLM intent JSON Schema)
_LLM_FORBIDDEN_PROPS = frozenset({
    "sql", "query", "table", "view", "column", "code", "predicate",
    "order_by", "expression", "prompt", "url", "html", "javascript",
})


# ---------------------------------------------------------------------------
# Base models
# ---------------------------------------------------------------------------


class StrictModel(BaseModel):
    """Base with extra=forbid and strict coercion."""

    model_config = _STRICT


class FrozenStrictModel(BaseModel):
    """Immutable base with extra=forbid and strict coercion."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


# ---------------------------------------------------------------------------
# Entity references (discriminated union)
# ---------------------------------------------------------------------------


class TickerEntity(FrozenStrictModel):
    """Canonical ticker reference."""

    entity_type: Literal[EntityType.ticker] = EntityType.ticker
    canonical_id: Annotated[str, Field(min_length=1, max_length=10)]

    @field_validator("canonical_id")
    @classmethod
    def validate_ticker(cls, v: str) -> str:
        if not _TICKER_RE.match(v):
            raise ValueError(
                f"Ticker must match ^[A-Z][A-Z0-9.]{{0,9}}$, got {v!r}"
            )
        return v


class SectorEntity(FrozenStrictModel):
    """Canonical sector reference."""

    entity_type: Literal[EntityType.sector] = EntityType.sector
    canonical_id: Annotated[str, Field(min_length=1, max_length=64)]

    @field_validator("canonical_id")
    @classmethod
    def validate_sector(cls, v: str) -> str:
        if not _SECTOR_RE.match(v):
            raise ValueError(
                f"Sector must match ^[a-z_][a-z0-9_]*$, got {v!r}"
            )
        return v


class IndexEntity(FrozenStrictModel):
    """Canonical index reference."""

    entity_type: Literal[EntityType.index] = EntityType.index
    canonical_id: Annotated[str, Field(min_length=1, max_length=10)]

    @field_validator("canonical_id")
    @classmethod
    def validate_index(cls, v: str) -> str:
        if not _TICKER_RE.match(v):
            raise ValueError(
                f"Index must match ^[A-Z][A-Z0-9.]{{0,9}}$, got {v!r}"
            )
        return v


# Discriminated union
EntityRef = Annotated[
    Union[TickerEntity, SectorEntity, IndexEntity],
    Field(discriminator="entity_type"),
]

CanonicalEntity = Union[TickerEntity, SectorEntity, IndexEntity]


# ---------------------------------------------------------------------------
# Date range
# ---------------------------------------------------------------------------


class DateRange(FrozenStrictModel):
    """Inclusive date range with start <= end."""

    start: date
    end: date

    @model_validator(mode="after")
    def validate_order(self) -> DateRange:
        if self.end < self.start:
            raise ValueError(
                f"end ({self.end}) must be >= start ({self.start})"
            )
        return self


# ---------------------------------------------------------------------------
# Canonical intent
# ---------------------------------------------------------------------------


class CanonicalIntent(FrozenStrictModel):
    """Resolved canonical intent — all entities are canonical IDs."""

    semantic_model_version: Annotated[str, Field(min_length=1, max_length=32, pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")]
    operation: Operation
    metric: Metric
    entities: Annotated[list[EntityRef], Field(min_length=1, max_length=100)]
    date_range: DateRange
    grouping: Grouping
    limit: Annotated[int, Field(gt=0, le=10_000)]

    @field_validator("semantic_model_version")
    @classmethod
    def validate_version(cls, v: str) -> str:
        if v != SEMANTIC_MODEL_VERSION:
            raise ValueError(
                f"Version mismatch: expected {SEMANTIC_MODEL_VERSION}, got {v}"
            )
        return v

    @model_validator(mode="after")
    def validate_unique_entities(self) -> CanonicalIntent:
        seen: set[tuple[str, str]] = set()
        for e in self.entities:
            key = (e.entity_type.value, e.canonical_id)
            if key in seen:
                raise ValueError(
                    f"Duplicate entity: {e.entity_type.value}:{e.canonical_id}"
                )
            seen.add(key)
        return self


# ---------------------------------------------------------------------------
# LLM output (pre-resolution)
# ---------------------------------------------------------------------------


class LLMEntityMention(FrozenStrictModel):
    """Short plain-text entity mention from LLM output."""

    text: Annotated[str, Field(min_length=1, max_length=25, pattern=_ENTITY_MENTION_PATTERN)]

    @model_validator(mode="before")
    @classmethod
    def _normalize_text(cls, data: dict) -> dict:
        """Normalize smart apostrophe U+2019 → ASCII apostrophe U+0027 before field validation."""
        if isinstance(data, dict) and "text" in data and isinstance(data["text"], str):
            data = dict(data)
            data["text"] = unicodedata.normalize("NFKC", data["text"]).replace("\u2019", "'")
        return data

    @field_validator("text")
    @classmethod
    def validate_text(cls, v: str) -> str:
        if not _ENTITY_MENTION_RE.match(v):
            raise ValueError(
                "Entity mention must match allowlist pattern: "
                "alphanumeric start, alphanumeric/space/dot/ampersand/apostrophe/hyphen/slash/underscore only"
            )
        if _CONTROL_CHAR_RE.search(v):
            raise ValueError("Control characters not allowed in entity mention")
        if _SQL_METACHAR_RE.search(v):
            raise ValueError("SQL/comment metacharacters not allowed in entity mention")
        if _SQL_KEYWORD_RE.search(v):
            raise ValueError("SQL keywords not allowed in entity mention")
        if _PROMPT_INJECTION_RE.search(v):
            raise ValueError("Prompt injection patterns not allowed in entity mention")
        return v


class DateExpression(FrozenStrictModel):
    """Date expression from LLM — either explicit range or relative text."""

    explicit_range: DateRange | None = None
    relative: RelativeDate | None = None

    @model_validator(mode="after")
    def validate_one_set(self) -> DateExpression:
        if self.explicit_range is None and self.relative is None:
            raise ValueError("Either explicit_range or relative must be set")
        if self.explicit_range is not None and self.relative is not None:
            raise ValueError("Only one of explicit_range or relative may be set")
        return self


class LLMIntentOutput(FrozenStrictModel):
    """LLM extraction output — contains unresolved aliases.

    This model intentionally excludes SQL, code, table, view, column,
    predicate, order_by, expression, prompt, url, html, javascript fields.
    """

    semantic_model_version: Annotated[str, Field(min_length=1, max_length=32, pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")]
    operation: Operation
    metric: Metric
    entity_mentions: Annotated[
        list[LLMEntityMention], Field(min_length=1, max_length=50)
    ]
    date_expression: DateExpression
    grouping: Grouping | None = None
    limit: Annotated[int, Field(gt=0, le=10_000)] | None = None

    @field_validator("semantic_model_version")
    @classmethod
    def validate_version(cls, v: str) -> str:
        if v != SEMANTIC_MODEL_VERSION:
            raise ValueError(
                f"Version mismatch: expected {SEMANTIC_MODEL_VERSION}, got {v}"
            )
        return v


# ---------------------------------------------------------------------------
# Policy and provenance
# ---------------------------------------------------------------------------


class PolicyOutcome(FrozenStrictModel):
    """Result of policy classification — gate for NL2 compilation."""

    semantic_model_version: Annotated[str, Field(min_length=1, max_length=32)]
    policy_version: Annotated[str, Field(min_length=1, max_length=32)]
    cost_class: CostClass
    reason_codes: Annotated[list[PolicyReasonCode], Field(min_length=1)]
    detail: Annotated[str, Field(min_length=1, max_length=1000)]
    allows_compilation: bool

    @field_validator("semantic_model_version")
    @classmethod
    def validate_version(cls, v: str) -> str:
        if v != SEMANTIC_MODEL_VERSION:
            raise ValueError(
                f"Version mismatch: expected {SEMANTIC_MODEL_VERSION}, got {v}"
            )
        return v

    @model_validator(mode="after")
    def validate_compilation(self) -> PolicyOutcome:
        if self.cost_class == CostClass.REJECT and self.allows_compilation:
            raise ValueError(
                "REJECT cost class must have allows_compilation=false"
            )
        if self.cost_class != CostClass.REJECT and not self.allows_compilation:
            raise ValueError(
                "Non-REJECT cost class must have allows_compilation=true"
            )
        return self


class ProvenanceEnvelope(FrozenStrictModel):
    """Provenance record for executed queries."""

    statement_id: Annotated[str, Field(min_length=1, max_length=64)]
    sanitized_sql: Annotated[str, Field(min_length=1, max_length=50_000)]
    intent: CanonicalIntent
    semantic_model_version: Annotated[str, Field(min_length=1, max_length=32)]
    dataset_version: Annotated[str, Field(min_length=1, max_length=64)]
    policy_version: Annotated[str, Field(min_length=1, max_length=32)]
    cost_class: CostClass
    rows: Annotated[int, Field(ge=0)]
    runtime_ms: Annotated[float, Field(ge=0)]
    cache_status: CacheStatus
    trace_id: Annotated[str, Field(min_length=1, max_length=128)]

    @field_validator("semantic_model_version")
    @classmethod
    def validate_version(cls, v: str) -> str:
        if v != SEMANTIC_MODEL_VERSION:
            raise ValueError(
                f"Version mismatch: expected {SEMANTIC_MODEL_VERSION}, got {v}"
            )
        return v

    @field_validator("statement_id")
    @classmethod
    def validate_statement_id(cls, v: str) -> str:
        if not _ID_RE.match(v):
            raise ValueError(f"statement_id must match {_ID_RE.pattern}")
        return v

    @field_validator("trace_id")
    @classmethod
    def validate_trace_id(cls, v: str) -> str:
        if not _TRACE_ID_RE.match(v):
            raise ValueError(f"trace_id must match {_TRACE_ID_RE.pattern}")
        return v


# ---------------------------------------------------------------------------
# Chart models
# ---------------------------------------------------------------------------


class ChartAxis(FrozenStrictModel):
    """Chart axis reference."""

    field_name: Annotated[str, Field(min_length=1, max_length=100)]
    display_label: Annotated[str, Field(min_length=1, max_length=50)]
    data_type: DataType
    unit: Annotated[str, Field(max_length=20)] | None = None


class ChartSeries(FrozenStrictModel):
    """Chart series reference."""

    field_name: Annotated[str, Field(min_length=1, max_length=100)]
    display_label: Annotated[str, Field(min_length=1, max_length=50)]
    data_type: DataType
    unit: Annotated[str, Field(max_length=20)] | None = None


class LineChartConfig(FrozenStrictModel):
    """Configuration for line charts (time series)."""

    chart_type: Literal[ChartType.line] = ChartType.line
    x_axis: ChartAxis
    y_axes: Annotated[list[ChartAxis], Field(min_length=1, max_length=5)]
    series: Annotated[list[ChartSeries], Field(min_length=1, max_length=20)]


class BarChartConfig(FrozenStrictModel):
    """Configuration for bar charts (comparisons/ranks)."""

    chart_type: Literal[ChartType.bar] = ChartType.bar
    x_axis: ChartAxis
    y_axes: Annotated[list[ChartAxis], Field(min_length=1, max_length=5)]
    series: Annotated[list[ChartSeries], Field(min_length=1, max_length=20)]


class TableColumn(FrozenStrictModel):
    """Table column reference."""

    field_name: Annotated[str, Field(min_length=1, max_length=100)]
    display_label: Annotated[str, Field(min_length=1, max_length=50)]
    data_type: DataType
    unit: Annotated[str, Field(max_length=20)] | None = None


class TableConfig(FrozenStrictModel):
    """Configuration for table (universal fallback)."""

    chart_type: Literal[ChartType.table] = ChartType.table
    columns: Annotated[list[TableColumn], Field(min_length=1, max_length=50)]


# Discriminated union for chart configs
ChartConfig = Annotated[
    Union[LineChartConfig, BarChartConfig, TableConfig],
    Field(discriminator="chart_type"),
]


class ChartEnvelope(FrozenStrictModel):
    """Chart envelope with version and approved config."""

    semantic_model_version: Annotated[str, Field(min_length=1, max_length=32)]
    chart_config: ChartConfig

    @field_validator("semantic_model_version")
    @classmethod
    def validate_version(cls, v: str) -> str:
        if v != SEMANTIC_MODEL_VERSION:
            raise ValueError(
                f"Version mismatch: expected {SEMANTIC_MODEL_VERSION}, got {v}"
            )
        return v


# ---------------------------------------------------------------------------
# Alias resolution trace
# ---------------------------------------------------------------------------


class AliasResolutionStatus(str, Enum):
    """Status of alias resolution."""

    success = "success"
    unknown = "unknown"
    ambiguous = "ambiguous"
    rejected = "rejected"


class AliasResolutionTrace(FrozenStrictModel):
    """Trace record for a single alias resolution attempt."""

    original_input: Annotated[str, Field(min_length=1, max_length=200)]
    normalized_input: Annotated[str, Field(min_length=1, max_length=200)]
    registry_version: Annotated[str, Field(min_length=1, max_length=32)]
    resolver_kind: Annotated[str, Field(min_length=1, max_length=50)]
    status: AliasResolutionStatus
    canonical_entity: CanonicalEntity | None = None
    matched_alias: Annotated[str, Field(max_length=200)] | None = None
    source: Annotated[str, Field(max_length=100)] | None = None
    reason_code: Annotated[str, Field(max_length=100)] | None = None


class AliasResolutionEnvelope(FrozenStrictModel):
    """Envelope for alias resolution results."""

    semantic_model_version: Annotated[str, Field(min_length=1, max_length=32)]
    traces: Annotated[list[AliasResolutionTrace], Field(min_length=1)]

    @field_validator("semantic_model_version")
    @classmethod
    def validate_version(cls, v: str) -> str:
        if v != SEMANTIC_MODEL_VERSION:
            raise ValueError(
                f"Version mismatch: expected {SEMANTIC_MODEL_VERSION}, got {v}"
            )
        return v


# ---------------------------------------------------------------------------
# Aggregate response coverage contract
# ---------------------------------------------------------------------------


class CoverageResult(FrozenStrictModel):
    """Aggregate response with coverage-aware status.

    The status field is bound to CoverageStatus (ok | INSUFFICIENT_DATA).
    agg_value is nullable ONLY when status == INSUFFICIENT_DATA.
    """

    symbol: Annotated[str, Field(min_length=1, max_length=10)]
    agg_value: Annotated[float, Field(strict=True)] | None = None
    sample_count: Annotated[int, Field(ge=0)]
    coverage_ratio: Annotated[float, Field(ge=0.0, le=1.0)]
    status: CoverageStatus

    @model_validator(mode="after")
    def validate_agg_value_nullability(self) -> CoverageResult:
        if self.status == CoverageStatus.ok and self.agg_value is None:
            raise ValueError(
                "agg_value must not be null when status is 'ok'"
            )
        if self.status == CoverageStatus.INSUFFICIENT_DATA and self.agg_value is not None:
            raise ValueError(
                "agg_value must be null when status is 'INSUFFICIENT_DATA'"
            )
        return self