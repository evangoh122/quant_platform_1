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
    Operation,
    PolicyOutcome,
    PolicyReasonCode,
    SEMANTIC_MODEL_VERSION,
)
from analytics_nl.registry import RegistryData, RegistryEntry

_IDENTIFIER_RE = re.compile(r"^[a-z_][a-z0-9_]*$")


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


def load_policy_bounds() -> PolicyBounds:
    """Load and validate policy bounds from YAML."""
    ref = resources.files("analytics_nl.data").joinpath("policy_bounds_v1.yaml")
    text = ref.read_text(encoding="utf-8")
    raw = yaml.safe_load(text)

    errors: list[str] = []

    pv = raw.get("policy_version")
    smv = raw.get("semantic_model_version")
    if smv != SEMANTIC_MODEL_VERSION:
        errors.append(f"semantic_model_version mismatch: expected {SEMANTIC_MODEL_VERSION}, got {smv}")

    hb = raw.get("hard_bounds", {})
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

    st = raw.get("soft_thresholds", {})
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

    if errors:
        raise PolicyValidationError(errors)

    return PolicyBounds(
        policy_version=pv,
        semantic_model_version=smv,
        gold=gold,
        silver=silver,
        cheap=cheap,
        normal=normal,
    )


def classify_intent(
    intent: CanonicalIntent,
    registry: RegistryData,
    bounds: PolicyBounds,
    *,
    as_of: date,
) -> PolicyOutcome:
    """Classify a canonical intent against policy bounds.

    Pure function: no network, clock, SQL, logging, environment, or mutable globals.
    Returns a PolicyOutcome that gates NL2 compilation.
    """
    reasons: list[PolicyReasonCode] = []
    pair_key = f"{intent.metric.value}.{intent.operation.value}"

    # 1. Check pair is registered
    entry = registry.entries.get(pair_key)
    if entry is None:
        reasons.append(PolicyReasonCode.PAIR_NOT_REGISTERED)
        return _reject(intent, bounds, reasons)

    # 2. Validate entity types against registry
    allowed_entity_types = {e.entity_type for e in intent.entities}
    # All entities must be valid types (already enforced by contract)

    # 3. Check entity count against entry limit
    entity_count = len(intent.entities)
    if entity_count > entry.max_entities:
        reasons.append(PolicyReasonCode.TICKER_LIMIT_EXCEEDED)

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