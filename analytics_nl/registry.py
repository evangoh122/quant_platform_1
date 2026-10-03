"""Semantic registry loader — loads and validates the YAML registry data."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from importlib import resources
from typing import Any

import yaml

from analytics_nl.contracts import SEMANTIC_MODEL_VERSION

_IDENTIFIER_RE = re.compile(r"^[a-z_][a-z0-9_]*$")


class RegistryValidationError(Exception):
    """Raised when registry data fails validation."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__(f"Registry validation failed: {errors}")


@dataclass(frozen=True)
class OutputField:
    name: str
    type: str
    nullable: bool


@dataclass(frozen=True)
class ParameterDef:
    type: str
    min: int | float | None = None
    max: int | float | None = None
    default: Any = None
    required: bool = True
    enum: list[str] | None = None


@dataclass(frozen=True)
class RegistryEntry:
    pair_key: str
    layer: str
    serving_view: str
    description: str
    input_columns: tuple[str, ...]
    aggregation: str
    required_slots: tuple[str, ...]
    allowed_grouping: tuple[str, ...]
    allowed_ordering: tuple[tuple[str, str], ...]
    parameters: dict[str, ParameterDef]
    output_fields: tuple[OutputField, ...]
    chart_families: tuple[str, ...]
    max_entities: int
    row_limit: int
    entry_version: str


@dataclass(frozen=True)
class RegistryData:
    semantic_registry_version: str
    semantic_model_version: str
    policy_version: str
    approved_views: tuple[str, ...]
    entries: dict[str, RegistryEntry]


def _validate_identifier(value: str, context: str) -> None:
    if not _IDENTIFIER_RE.match(value):
        raise RegistryValidationError(
            [f"Invalid identifier {value!r} in {context}: must match ^[a-z_][a-z0-9_]*$"]
        )


def _load_raw() -> dict[str, Any]:
    ref = resources.files("analytics_nl.data").joinpath("semantic_registry_v1.yaml")
    text = ref.read_text(encoding="utf-8")
    return yaml.safe_load(text)


def _parse_parameter(name: str, raw: dict[str, Any]) -> ParameterDef:
    _validate_identifier(name, f"parameter name {name!r}")
    ptype = raw.get("type", "string")
    return ParameterDef(
        type=ptype,
        min=raw.get("min"),
        max=raw.get("max"),
        default=raw.get("default"),
        required=raw.get("required", True),
        enum=raw.get("enum"),
    )


def _parse_entry(pair_key: str, raw: dict[str, Any]) -> RegistryEntry:
    layer = raw["layer"]
    serving_view = raw["serving_view"]
    input_columns = tuple(raw.get("input_columns", []))
    aggregation = raw["aggregation"]
    required_slots = tuple(raw.get("required_slots", []))
    allowed_grouping = tuple(raw.get("allowed_grouping", []))
    allowed_ordering = tuple(tuple(o) for o in raw.get("allowed_ordering", []))
    parameters = {k: _parse_parameter(k, v) for k, v in raw.get("parameters", {}).items()}
    output_fields = tuple(
        OutputField(name=f["name"], type=f["type"], nullable=f["nullable"])
        for f in raw.get("output_fields", [])
    )
    chart_families = tuple(raw.get("chart_families", []))
    max_entities = raw.get("max_entities", 100)
    row_limit = raw.get("row_limit", 10000)
    entry_version = raw.get("entry_version", "1.0.0")
    description = raw.get("description", "")

    return RegistryEntry(
        pair_key=pair_key,
        layer=layer,
        serving_view=serving_view,
        description=description,
        input_columns=input_columns,
        aggregation=aggregation,
        required_slots=required_slots,
        allowed_grouping=allowed_grouping,
        allowed_ordering=allowed_ordering,
        parameters=parameters,
        output_fields=output_fields,
        chart_families=chart_families,
        max_entities=max_entities,
        row_limit=row_limit,
        entry_version=entry_version,
    )


def _validate_registry(raw: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    # Top-level versions
    sem_ver = raw.get("semantic_model_version")
    if sem_ver != SEMANTIC_MODEL_VERSION:
        errors.append(f"semantic_model_version mismatch: expected {SEMANTIC_MODEL_VERSION}, got {sem_ver}")

    # Approved views
    approved_views = raw.get("approved_views", [])
    for v in approved_views:
        _validate_identifier(v, f"approved_view {v!r}")

    # Check for duplicates
    if len(approved_views) != len(set(approved_views)):
        errors.append("Duplicate approved views found")

    entries = raw.get("entries", {})
    if not entries:
        errors.append("No entries defined")

    # Validate each entry
    for pair_key, entry_raw in entries.items():
        # Pair key format
        parts = pair_key.split(".")
        if len(parts) != 2:
            errors.append(f"Invalid pair key format: {pair_key!r} (expected metric.operation)")
            continue

        metric, operation = parts
        _validate_identifier(metric, f"metric in {pair_key!r}")
        _validate_identifier(operation, f"operation in {pair_key!r}")

        # Serving view must be in approved list
        sv = entry_raw.get("serving_view", "")
        if sv not in approved_views:
            errors.append(f"Entry {pair_key}: serving_view {sv!r} not in approved_views")

        # Layer
        layer = entry_raw.get("layer", "")
        if layer not in ("gold", "silver"):
            errors.append(f"Entry {pair_key}: layer must be 'gold' or 'silver', got {layer!r}")

        # Input columns
        for col in entry_raw.get("input_columns", []):
            _validate_identifier(col, f"input_column in {pair_key!r}")

        # Aggregation token
        agg = entry_raw.get("aggregation", "")
        _validate_identifier(agg, f"aggregation in {pair_key!r}")

        # Required slots
        for slot in entry_raw.get("required_slots", []):
            _validate_identifier(slot, f"required_slot in {pair_key!r}")

        # Grouping
        for g in entry_raw.get("allowed_grouping", []):
            _validate_identifier(g, f"grouping in {pair_key!r}")

        # Ordering
        for ordering in entry_raw.get("allowed_ordering", []):
            if len(ordering) != 2:
                errors.append(f"Entry {pair_key}: ordering must be (field, direction)")
            else:
                _validate_identifier(ordering[0], f"ordering field in {pair_key!r}")
                if ordering[1] not in ("asc", "desc"):
                    errors.append(f"Entry {pair_key}: ordering direction must be 'asc' or 'desc'")

        # Output fields
        output_field_names = set()
        for f in entry_raw.get("output_fields", []):
            fname = f.get("name", "")
            _validate_identifier(fname, f"output_field in {pair_key!r}")
            if fname in output_field_names:
                errors.append(f"Entry {pair_key}: duplicate output field {fname!r}")
            output_field_names.add(fname)

        # Parameters
        for pname in entry_raw.get("parameters", {}):
            _validate_identifier(pname, f"parameter in {pair_key!r}")

        # Chart families
        for cf in entry_raw.get("chart_families", []):
            if cf not in ("line", "bar", "table"):
                errors.append(f"Entry {pair_key}: invalid chart family {cf!r}")

        # Versions
        ev = entry_raw.get("entry_version")
        if ev != SEMANTIC_MODEL_VERSION:
            errors.append(f"Entry {pair_key}: entry_version mismatch: {ev!r}")

        # Limits
        re_max = entry_raw.get("row_limit", 10000)
        if re_max > 10000:
            errors.append(f"Entry {pair_key}: row_limit {re_max} exceeds policy bound 10000")

    # Coverage: check all 8 metrics × 4 operations
    from analytics_nl.contracts import Metric, Operation

    for m in Metric:
        for o in Operation:
            key = f"{m.value}.{o.value}"
            if key not in entries:
                errors.append(f"Missing registry entry for {key}")

    return errors


def load_registry() -> RegistryData:
    """Load and validate the semantic registry from YAML.

    Returns an immutable RegistryData. Raises RegistryValidationError on failure.
    """
    raw = _load_raw()
    errors = _validate_registry(raw)
    if errors:
        raise RegistryValidationError(errors)

    approved_views = tuple(raw["approved_views"])
    entries = {}
    for pair_key, entry_raw in raw["entries"].items():
        entries[pair_key] = _parse_entry(pair_key, entry_raw)

    return RegistryData(
        semantic_registry_version=raw["semantic_registry_version"],
        semantic_model_version=raw["semantic_model_version"],
        policy_version=raw["policy_version"],
        approved_views=approved_views,
        entries=entries,
    )