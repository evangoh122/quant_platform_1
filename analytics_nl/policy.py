"""Policy classifier — pure, side-effect-free intent classification."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from importlib import resources
from typing import Any

import yaml

from analytics_nl.contracts import (
    CanonicalIntent,
    CostClass,
    Grouping,
    Metric,
    Operation,
    PolicyOutcome,
    PolicyReasonCode,
    SEMANTIC_MODEL_VERSION,
)
from analytics_nl.registry import RegistryData, RegistryEntry

_IDENTIFIER_RE = re.compile(r"^[a-z_][a-z0-9_]*$")

# Metrics that use unadjusted prices — corporate-action sensitive
_UNADJUSTED_PRICE_METRICS = frozenset({
    Metric.return_,
    Metric.realized_volatility,
    Metric.drawdown,
    Metric.momentum,
    Metric.relative_performance,
})


class PolicyValidationError(Exception):
    """Raised when policy bounds data fails validation."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__(f"Policy validation failed: {errors}")


@dataclass(frozen=True)
class HardBounds:
    date_bound_years: int
    row_bound: int
    ticker_bound: int | None = None


@dataclass(frozen=True)
class SoftThresholds:
    max_days: int
    max_entities: int
    max_rows: int


@dataclass(frozen=True)
class PolicyBounds:
    policy_version: str
    semantic_model_version: str
    gold: HardBounds
    silver: HardBounds
    cheap: SoftThresholds
    normal: SoftThresholds
    known_splits: tuple[tuple[str, date, float], ...] = ()
    adjusted_source_available: bool = False


def load_policy_bounds() -> PolicyBounds:
    """Load and validate policy bounds from YAML."""
    ref = resources.files("analytics_nl.data").joinpath("policy_bounds_v1.yaml")
    text = ref.read_text(encoding="utf-8")
    raw = yaml.safe_load(text)

    errors: list[str] = []

    # Validate policy version
    pv = raw.get("policy_version")
    if pv != SEMANTIC_MODEL_VERSION:
        errors.append(f"policy_version mismatch: expected {SEMANTIC_MODEL_VERSION}, got {pv}")

    smv = raw.get("semantic_model_version")
    if smv != SEMANTIC_MODEL_VERSION:
        errors.append(f"semantic_model_version mismatch: expected {SEMANTIC_MODEL_VERSION}, got {smv}")

    # Validate hard_bounds structure
    hb = raw.get("hard_bounds")
    if not isinstance(hb, dict):
        errors.append("hard_bounds must be a dict")
        hb = {}
    for layer_name in ("gold", "silver"):
        layer_raw = hb.get(layer_name)
        if not isinstance(layer_raw, dict):
            errors.append(f"hard_bounds.{layer_name} must be a dict")
            continue
        for key in ("date_bound_years", "row_bound"):
            val = layer_raw.get(key)
            if val is None:
                errors.append(f"hard_bounds.{layer_name}.{key} is required")
            elif not isinstance(val, int) or isinstance(val, bool):
                errors.append(f"hard_bounds.{layer_name}.{key} must be int, got {type(val).__name__}")
            elif val <= 0:
                errors.append(f"hard_bounds.{layer_name}.{key} must be positive, got {val}")
        if layer_name == "silver":
            tb = layer_raw.get("ticker_bound")
            if tb is None:
                errors.append("hard_bounds.silver.ticker_bound is required")
            elif not isinstance(tb, int) or isinstance(tb, bool):
                errors.append(f"hard_bounds.silver.ticker_bound must be int, got {type(tb).__name__}")
            elif tb <= 0:
                errors.append(f"hard_bounds.silver.ticker_bound must be positive, got {tb}")

    gold_raw = hb.get("gold", {})
    silver_raw = hb.get("silver", {})

    gold = HardBounds(
        date_bound_years=gold_raw.get("date_bound_years", 10),
        row_bound=gold_raw.get("row_bound", 5000),
    )
    silver = HardBounds(
        date_bound_years=silver_raw.get("date_bound_years", 2),
        ticker_bound=silver_raw.get("ticker_bound", 10),
        row_bound=silver_raw.get("row_bound", 10000),
    )

    # Validate soft_thresholds structure
    st = raw.get("soft_thresholds")
    if not isinstance(st, dict):
        errors.append("soft_thresholds must be a dict")
        st = {}
    for tier_name in ("cheap", "normal"):
        tier_raw = st.get(tier_name)
        if not isinstance(tier_raw, dict):
            errors.append(f"soft_thresholds.{tier_name} must be a dict")
            continue
        for key in ("max_days", "max_entities", "max_rows"):
            val = tier_raw.get(key)
            if val is None:
                errors.append(f"soft_thresholds.{tier_name}.{key} is required")
            elif not isinstance(val, int) or isinstance(val, bool):
                errors.append(f"soft_thresholds.{tier_name}.{key} must be int, got {type(val).__name__}")
            elif val <= 0:
                errors.append(f"soft_thresholds.{tier_name}.{key} must be positive, got {val}")

    cheap_raw = st.get("cheap", {})
    normal_raw = st.get("normal", {})

    cheap = SoftThresholds(
        max_days=cheap_raw.get("max_days", 31),
        max_entities=cheap_raw.get("max_entities", 2),
        max_rows=cheap_raw.get("max_rows", 500),
    )
    normal = SoftThresholds(
        max_days=normal_raw.get("max_days", 366),
        max_entities=normal_raw.get("max_entities", 5),
        max_rows=normal_raw.get("max_rows", 2500),
    )

    # Validate ordering: cheap <= normal for each threshold
    if not errors:
        if cheap.max_days > normal.max_days:
            errors.append(f"cheap.max_days ({cheap.max_days}) > normal.max_days ({normal.max_days})")
        if cheap.max_entities > normal.max_entities:
            errors.append(f"cheap.max_entities ({cheap.max_entities}) > normal.max_entities ({normal.max_entities})")
        if cheap.max_rows > normal.max_rows:
            errors.append(f"cheap.max_rows ({cheap.max_rows}) > normal.max_rows ({normal.max_rows})")

    if errors:
        raise PolicyValidationError(errors)

    # Load known splits (optional — empty list if not present)
    known_splits_raw = raw.get("known_splits", [])
    known_splits: list[tuple[str, date, float]] = []
    for split in known_splits_raw:
        sym = split.get("symbol", "")
        ex = split.get("ex_date")
        ratio = split.get("ratio", 0.0)
        if sym and ex and ratio > 0:
            known_splits.append((sym, ex, ratio))

    # Load adjusted source availability flag (optional — default false)
    adjusted_source_available = raw.get("adjusted_source_available", False)

    return PolicyBounds(
        policy_version=pv,
        semantic_model_version=smv,
        gold=gold,
        silver=silver,
        cheap=cheap,
        normal=normal,
        known_splits=tuple(known_splits),
        adjusted_source_available=bool(adjusted_source_available),
    )


def classify_intent(
    intent: CanonicalIntent,
    registry: RegistryData,
    bounds: PolicyBounds,
    *,
    as_of: date,
    coverage_stats: dict[str, tuple[int, int]] | None = None,
) -> PolicyOutcome:
    """Classify a canonical intent against policy bounds.

    Pure function: no network, clock, SQL, logging, environment, or mutable globals.
    Returns a PolicyOutcome that gates NL2 compilation.

    coverage_stats: optional dict mapping pair_key to (sample_count, total_count).
        Used to check coverage for metrics with coverage metadata.
    """
    reasons: list[PolicyReasonCode] = []
    pair_key = f"{intent.metric.value}.{intent.operation.value}"

    # 1. Check pair is registered
    entry = registry.entries.get(pair_key)
    if entry is None:
        reasons.append(PolicyReasonCode.PAIR_NOT_REGISTERED)
        return _reject(intent, bounds, reasons)

    # 2. Validate entity types against registry
    allowed_types = set(entry.allowed_entity_types)
    for e in intent.entities:
        if e.entity_type.value not in allowed_types:
            reasons.append(PolicyReasonCode.ENTITY_NOT_ALLOWED)

    # 2b. Corporate-action safety: reject unadjusted-price metrics over known splits
    # When adjusted source is available, skip rejection — adjusted returns are safe.
    if (
        intent.metric in _UNADJUSTED_PRICE_METRICS
        and bounds.known_splits
        and not bounds.adjusted_source_available
    ):
        requested_symbols = {e.canonical_id for e in intent.entities}
        for sym, ex_date, _ratio in bounds.known_splits:
            if sym in requested_symbols and intent.date_range.start <= ex_date <= intent.date_range.end:
                reasons.append(PolicyReasonCode.UNADJUSTED_CORPORATE_ACTION)
                return _reject(intent, bounds, reasons)

    # 3. Check entity count against entry limit
    entity_count = len(intent.entities)
    if entity_count > entry.max_entities:
        reasons.append(PolicyReasonCode.TICKER_LIMIT_EXCEEDED)
    if entity_count < entry.min_entities:
        reasons.append(PolicyReasonCode.TOO_FEW_ENTITIES)

    # 4. Check date range
    if intent.date_range.end > as_of:
        reasons.append(PolicyReasonCode.FUTURE_DATE)

    if intent.date_range.end < intent.date_range.start:
        reasons.append(PolicyReasonCode.END_BEFORE_START)

    days = (intent.date_range.end - intent.date_range.start).days + 1  # inclusive

    # Get layer-specific bounds
    if entry.layer == "gold":
        layer_bounds = bounds.gold
    else:
        layer_bounds = bounds.silver

    # 5. Date bound check — use year arithmetic for accuracy
    from datetime import timedelta
    # The earliest allowed start date is (end_date - N years)
    # Use replace to handle leap years correctly
    try:
        earliest_allowed = intent.date_range.end.replace(
            year=intent.date_range.end.year - layer_bounds.date_bound_years
        )
    except ValueError:
        # Feb 29 → Feb 28 when target year is not a leap year
        earliest_allowed = intent.date_range.end.replace(
            year=intent.date_range.end.year - layer_bounds.date_bound_years,
            day=28,
        )
    if intent.date_range.start < earliest_allowed:
        reasons.append(PolicyReasonCode.DATE_RANGE_EXCEEDED)

    # 6. Silver ticker bound check
    if entry.layer == "silver" and layer_bounds.ticker_bound is not None:
        if entity_count > layer_bounds.ticker_bound:
            reasons.append(PolicyReasonCode.TICKER_LIMIT_EXCEEDED)

    # 7. Row limit check
    requested_limit = intent.limit
    if requested_limit > entry.row_limit:
        reasons.append(PolicyReasonCode.ROW_LIMIT_EXCEEDED)
    if requested_limit > layer_bounds.row_bound:
        reasons.append(PolicyReasonCode.ROW_LIMIT_EXCEEDED)

    # 8. Grouping check
    if intent.grouping.value not in entry.allowed_grouping:
        reasons.append(PolicyReasonCode.GROUPING_NOT_ALLOWED)

    # 9. Intraday rejection (defensive)
    # Grouping enum only allows daily-or-coarser values, but defensive check
    intraday_values = {"hour", "minute", "second", "tick"}
    if intent.grouping.value in intraday_values:
        reasons.append(PolicyReasonCode.INTRADAY_UNSUPPORTED)

    # 10. Required slots check
    if "entities" in entry.required_slots and entity_count == 0:
        reasons.append(PolicyReasonCode.MISSING_REQUIRED_SLOT)
    if "date_range" in entry.required_slots:
        # date_range is always present in CanonicalIntent
        pass

    # 11. Coverage check for sparse metrics (all operations)
    # Fail closed: if a metric has coverage metadata in the registry
    # (e.g. availability: snapshot_only), but coverage_stats is not provided
    # or the pair_key is missing from the stats, reject with INSUFFICIENT_DATA.
    if entry.coverage is not None:
        if coverage_stats is None:
            # No stats provided for a metric that requires coverage check
            reasons.append(PolicyReasonCode.INSUFFICIENT_DATA)
        else:
            stats = coverage_stats.get(pair_key)
            if stats is None:
                # Pair key not found in provided stats
                reasons.append(PolicyReasonCode.INSUFFICIENT_DATA)
            else:
                sample_count, total_count = stats
                if (
                    total_count <= 0
                    or sample_count < 0
                    or sample_count > total_count
                ):
                    reasons.append(PolicyReasonCode.INSUFFICIENT_DATA)
                else:
                    coverage_ratio = sample_count / total_count
                    if coverage_ratio < entry.coverage.min_coverage_ratio:
                        reasons.append(PolicyReasonCode.INSUFFICIENT_DATA)

    # If any hard violations, reject
    hard_violations = {
        PolicyReasonCode.PAIR_NOT_REGISTERED,
        PolicyReasonCode.DATE_RANGE_EXCEEDED,
        PolicyReasonCode.TICKER_LIMIT_EXCEEDED,
        PolicyReasonCode.ROW_LIMIT_EXCEEDED,
        PolicyReasonCode.FUTURE_DATE,
        PolicyReasonCode.END_BEFORE_START,
        PolicyReasonCode.INTRADAY_UNSUPPORTED,
        PolicyReasonCode.MISSING_REQUIRED_SLOT,
        PolicyReasonCode.GROUPING_NOT_ALLOWED,
        PolicyReasonCode.ENTITY_NOT_ALLOWED,
        PolicyReasonCode.TOO_FEW_ENTITIES,
        PolicyReasonCode.INSUFFICIENT_DATA,
    }
    if any(r in hard_violations for r in reasons):
        return _reject(intent, bounds, reasons)

    # Classify cost
    if (
        days <= bounds.cheap.max_days
        and entity_count <= bounds.cheap.max_entities
        and requested_limit <= bounds.cheap.max_rows
    ):
        cost_class = CostClass.CHEAP
        reasons.append(PolicyReasonCode.ACCEPTED_CHEAP)
    elif (
        days <= bounds.normal.max_days
        and entity_count <= bounds.normal.max_entities
        and requested_limit <= bounds.normal.max_rows
    ):
        cost_class = CostClass.NORMAL
        reasons.append(PolicyReasonCode.ACCEPTED_NORMAL)
    else:
        cost_class = CostClass.EXPENSIVE
        reasons.append(PolicyReasonCode.ACCEPTED_EXPENSIVE)

    # Sort reasons for determinism
    reasons.sort(key=lambda r: r.value)

    return PolicyOutcome(
        semantic_model_version=SEMANTIC_MODEL_VERSION,
        policy_version=bounds.policy_version,
        cost_class=cost_class,
        reason_codes=reasons,
        detail=f"Classified as {cost_class.value}: {', '.join(r.value for r in reasons)}",
        allows_compilation=True,
    )


def _reject(
    intent: CanonicalIntent,
    bounds: PolicyBounds,
    reasons: list[PolicyReasonCode],
) -> PolicyOutcome:
    """Create a REJECT policy outcome."""
    reasons.sort(key=lambda r: r.value)
    return PolicyOutcome(
        semantic_model_version=SEMANTIC_MODEL_VERSION,
        policy_version=bounds.policy_version,
        cost_class=CostClass.REJECT,
        reason_codes=reasons,
        detail=f"Rejected: {', '.join(r.value for r in reasons)}",
        allows_compilation=False,
    )