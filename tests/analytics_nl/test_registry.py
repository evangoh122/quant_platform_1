"""Tests for registry loading, validation, and coverage."""

import re

import pytest

from analytics_nl.contracts import SEMANTIC_MODEL_VERSION, Metric, Operation
from analytics_nl.registry import RegistryValidationError, load_registry


@pytest.fixture
def registry():
    """Load the real registry."""
    return load_registry()


class TestRegistryLoading:
    """Registry loads without errors."""

    def test_load_succeeds(self, registry):
        assert registry is not None
        assert registry.semantic_model_version == SEMANTIC_MODEL_VERSION

    def test_version_matches(self, registry):
        assert registry.semantic_model_version == SEMANTIC_MODEL_VERSION
        assert registry.semantic_registry_version == SEMANTIC_MODEL_VERSION

    def test_policy_version_matches(self, registry):
        assert registry.policy_version == SEMANTIC_MODEL_VERSION


class TestRegistryCoverage:
    """All 36 metric×operation pairs must be registered."""

    def test_all_pairs_registered(self, registry):
        for metric in Metric:
            for operation in Operation:
                key = f"{metric.value}.{operation.value}"
                assert key in registry.entries, f"Missing registry entry: {key}"

    def test_entry_count(self, registry):
        assert len(registry.entries) == 36


class TestRegistryIdentifiers:
    """All identifiers must match ^[a-z_][a-z0-9_]*$."""

    IDENTIFIER_RE = re.compile(r"^[a-z_][a-z0-9_]*$")

    def test_approved_views_valid(self, registry):
        for view in registry.approved_views:
            assert self.IDENTIFIER_RE.match(view), f"Invalid view identifier: {view!r}"

    def test_entry_serving_views_valid(self, registry):
        for key, entry in registry.entries.items():
            assert self.IDENTIFIER_RE.match(entry.serving_view), (
                f"Entry {key}: invalid serving_view {entry.serving_view!r}"
            )

    def test_input_columns_valid(self, registry):
        for key, entry in registry.entries.items():
            for col in entry.input_columns:
                assert self.IDENTIFIER_RE.match(col), (
                    f"Entry {key}: invalid input_column {col!r}"
                )

    def test_aggregation_tokens_valid(self, registry):
        for key, entry in registry.entries.items():
            assert self.IDENTIFIER_RE.match(entry.aggregation), (
                f"Entry {key}: invalid aggregation {entry.aggregation!r}"
            )

    def test_output_field_names_valid(self, registry):
        for key, entry in registry.entries.items():
            for field in entry.output_fields:
                assert self.IDENTIFIER_RE.match(field.name), (
                    f"Entry {key}: invalid output field name {field.name!r}"
                )

    def test_ordering_fields_valid(self, registry):
        for key, entry in registry.entries.items():
            for field_name, direction in entry.allowed_ordering:
                assert self.IDENTIFIER_RE.match(field_name), (
                    f"Entry {key}: invalid ordering field {field_name!r}"
                )
                assert direction in ("asc", "desc"), (
                    f"Entry {key}: invalid direction {direction!r}"
                )


class TestRegistryViewReferences:
    """Every referenced view must be in the approved list."""

    def test_all_serving_views_approved(self, registry):
        approved = set(registry.approved_views)
        for key, entry in registry.entries.items():
            assert entry.serving_view in approved, (
                f"Entry {key}: serving_view {entry.serving_view!r} not in approved views"
            )

    def test_no_unused_approved_views(self, registry):
        """Every approved view should be referenced by at least one entry."""
        referenced = {entry.serving_view for entry in registry.entries.values()}
        for view in registry.approved_views:
            assert view in referenced, f"Approved view {view!r} is unused"


class TestRegistryVersions:
    """All versions must match SEMANTIC_MODEL_VERSION."""

    def test_entry_versions_match(self, registry):
        for key, entry in registry.entries.items():
            assert entry.entry_version == SEMANTIC_MODEL_VERSION, (
                f"Entry {key}: version mismatch {entry.entry_version!r}"
            )


class TestRegistryLimits:
    """Limits must not exceed policy bounds."""

    def test_row_limits_within_bounds(self, registry):
        for key, entry in registry.entries.items():
            assert entry.row_limit <= 10_000, (
                f"Entry {key}: row_limit {entry.row_limit} exceeds 10000"
            )

    def test_max_entities_reasonable(self, registry):
        for key, entry in registry.entries.items():
            assert entry.max_entities <= 100, (
                f"Entry {key}: max_entities {entry.max_entities} exceeds 100"
            )


class TestRegistryChartFamilies:
    """Chart families must be compatible with output shape."""

    def test_chart_families_valid(self, registry):
        valid_families = {"line", "bar", "table"}
        for key, entry in registry.entries.items():
            for cf in entry.chart_families:
                assert cf in valid_families, (
                    f"Entry {key}: invalid chart family {cf!r}"
                )


class TestRegistryNoPhysicalNames:
    """No physical table names in registry data."""

    PHYSICAL_PATTERNS = ["bronze_", "silver_", "gold_", "delta_", "parquet"]

    def test_no_physical_names_in_views(self, registry):
        for view in registry.approved_views:
            for pattern in self.PHYSICAL_PATTERNS:
                assert pattern not in view.lower(), (
                    f"Physical pattern {pattern!r} in approved view {view!r}"
                )

    def test_no_physical_names_in_entries(self, registry):
        for key, entry in registry.entries.items():
            for pattern in self.PHYSICAL_PATTERNS:
                assert pattern not in entry.serving_view.lower(), (
                    f"Physical pattern {pattern!r} in entry {key} serving_view"
                )


class TestPutCallRatioEntries:
    """put_call_ratio registry entries must enforce mean-only aggregation."""

    def test_aggregate_entry_exists(self, registry):
        key = "put_call_ratio.aggregate"
        assert key in registry.entries

    def test_aggregate_uses_mean_only_token(self, registry):
        entry = registry.entries["put_call_ratio.aggregate"]
        assert entry.aggregation == "mean_only"

    def test_aggregate_enum_allows_only_mean(self, registry):
        entry = registry.entries["put_call_ratio.aggregate"]
        agg_param = entry.parameters["agg_function"]
        assert agg_param.enum == ["mean"]
        assert agg_param.default == "mean"

    def test_all_four_operations_registered(self, registry):
        for op in ("trend", "compare", "rank", "aggregate"):
            key = f"put_call_ratio.{op}"
            assert key in registry.entries, f"Missing {key}"

    def test_all_entries_use_options_view(self, registry):
        for op in ("trend", "compare", "rank", "aggregate"):
            entry = registry.entries[f"put_call_ratio.{op}"]
            assert entry.serving_view == "serve_options_metrics_v1"

    def test_all_entries_have_put_call_ratio_column(self, registry):
        for op in ("trend", "compare", "rank", "aggregate"):
            entry = registry.entries[f"put_call_ratio.{op}"]
            assert "put_call_ratio" in entry.input_columns


def _minimal_valid_registry() -> dict:
    """Build a minimal valid registry dict for mutation testing."""
    return {
        "semantic_registry_version": "1.0.0",
        "semantic_model_version": "1.0.0",
        "policy_version": "1.0.0",
        "approved_views": ["serve_daily_prices_v1"],
        "entries": {
            "price.trend": {
                "layer": "silver",
                "serving_view": "serve_daily_prices_v1",
                "description": "test",
                "input_columns": ["symbol", "event_date", "close_price"],
                "aggregation": "none",
                "required_slots": ["entities", "date_range"],
                "allowed_grouping": ["day"],
                "allowed_ordering": [["event_date", "asc"]],
                "parameters": {
                    "entity_count": {"type": "integer", "min": 1, "max": 10, "default": 1},
                },
                "output_fields": [
                    {"name": "symbol", "type": "string", "nullable": False},
                    {"name": "event_date", "type": "date", "nullable": False},
                    {"name": "close_price", "type": "number", "nullable": False},
                ],
                "chart_families": ["line"],
                "max_entities": 10,
                "row_limit": 10000,
                "entry_version": "1.0.0",
            },
        },
    }


class TestRegistryFailClosed:
    """Registry must reject malformed data — fail closed."""

    def test_unsupported_metric_rejected(self):
        from analytics_nl.registry import _validate_registry
        raw = _minimal_valid_registry()
        raw["entries"]["bogus.trend"] = raw["entries"]["price.trend"].copy()
        errors = _validate_registry(raw)
        assert any("unsupported metric" in e for e in errors), f"Expected unsupported metric error, got {errors}"

    def test_unsupported_operation_rejected(self):
        from analytics_nl.registry import _validate_registry
        raw = _minimal_valid_registry()
        raw["entries"]["price.bogus"] = raw["entries"]["price.trend"].copy()
        errors = _validate_registry(raw)
        assert any("unsupported operation" in e for e in errors), f"Expected unsupported operation error, got {errors}"

    def test_unknown_aggregation_token_rejected(self):
        from analytics_nl.registry import _validate_registry
        raw = _minimal_valid_registry()
        raw["entries"]["price.trend"]["aggregation"] = "bogus_agg"
        errors = _validate_registry(raw)
        assert any("unknown aggregation token" in e for e in errors), f"Expected unknown aggregation error, got {errors}"

    def test_unknown_required_slot_rejected(self):
        from analytics_nl.registry import _validate_registry
        raw = _minimal_valid_registry()
        raw["entries"]["price.trend"]["required_slots"] = ["entities", "bogus_slot"]
        errors = _validate_registry(raw)
        assert any("unknown required slot" in e for e in errors), f"Expected unknown required slot error, got {errors}"

    def test_unknown_output_field_type_rejected(self):
        from analytics_nl.registry import _validate_registry
        raw = _minimal_valid_registry()
        raw["entries"]["price.trend"]["output_fields"].append(
            {"name": "bogus", "type": "bogus_type", "nullable": False}
        )
        errors = _validate_registry(raw)
        assert any("unknown output field type" in e for e in errors), f"Expected unknown output type error, got {errors}"

    def test_unknown_parameter_type_rejected(self):
        from analytics_nl.registry import _validate_registry
        raw = _minimal_valid_registry()
        raw["entries"]["price.trend"]["parameters"]["bogus"] = {"type": "bogus_type"}
        errors = _validate_registry(raw)
        assert any("unknown parameter type" in e for e in errors), f"Expected unknown parameter type error, got {errors}"

    def test_default_below_min_rejected(self):
        from analytics_nl.registry import _validate_registry
        raw = _minimal_valid_registry()
        raw["entries"]["price.trend"]["parameters"]["entity_count"]["default"] = 0
        errors = _validate_registry(raw)
        assert any("default" in e and "< min" in e for e in errors), f"Expected default < min error, got {errors}"

    def test_default_above_max_rejected(self):
        from analytics_nl.registry import _validate_registry
        raw = _minimal_valid_registry()
        raw["entries"]["price.trend"]["parameters"]["entity_count"]["default"] = 999
        errors = _validate_registry(raw)
        assert any("default" in e and "> max" in e for e in errors), f"Expected default > max error, got {errors}"

    def test_extra_entry_rejected(self):
        from analytics_nl.registry import _validate_registry
        raw = _minimal_valid_registry()
        raw["entries"]["price.bogus_extra"] = raw["entries"]["price.trend"].copy()
        errors = _validate_registry(raw)
        assert any("Extra registry entry" in e for e in errors), f"Expected extra entry error, got {errors}"

    def test_unused_approved_view_rejected(self):
        from analytics_nl.registry import _validate_registry
        raw = _minimal_valid_registry()
        raw["approved_views"].append("serve_unused_view")
        errors = _validate_registry(raw)
        assert any("not referenced" in e for e in errors), f"Expected unused view error, got {errors}"