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
    """All 32 metric×operation pairs must be registered."""

    def test_all_pairs_registered(self, registry):
        for metric in Metric:
            for operation in Operation:
                key = f"{metric.value}.{operation.value}"
                assert key in registry.entries, f"Missing registry entry: {key}"

    def test_entry_count(self, registry):
        assert len(registry.entries) == 32


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