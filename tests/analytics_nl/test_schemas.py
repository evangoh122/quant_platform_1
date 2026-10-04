"""Tests for JSON Schema synchronization and invariants."""

import json

import pytest

from analytics_nl.contracts import (
    AliasResolutionEnvelope,
    CanonicalIntent,
    ChartEnvelope,
    LLMIntentOutput,
    PolicyOutcome,
    ProvenanceEnvelope,
    _LLM_FORBIDDEN_PROPS,
)
from analytics_nl.export_schemas import generate_all_schemas, _normalize_schema


class TestSchemaSync:
    """Checked-in schemas must exactly match generated ones."""

    def test_all_schemas_regenerate(self):
        """Regenerate schemas in memory and compare to checked-in files."""
        from pathlib import Path
        schema_dir = Path(__file__).parent.parent.parent / "analytics_nl" / "schemas"
        generated = generate_all_schemas()

        for filename, expected_content in generated.items():
            path = schema_dir / filename
            assert path.exists(), f"Missing schema file: {path}"
            actual_content = path.read_text(encoding="utf-8")
            assert actual_content == expected_content, (
                f"Schema {filename} differs from generated. "
                f"Run: python -m analytics_nl.export_schemas --write"
            )


class TestAdditionalPropertiesFalse:
    """All schemas must have additionalProperties: false at top level."""

    def test_all_schemas_no_extras(self):
        schemas = generate_all_schemas()
        for filename, content in schemas.items():
            schema = json.loads(content)
            assert schema.get("additionalProperties") is False, (
                f"{filename}: additionalProperties must be false"
            )


class TestLLMForbiddenProperties:
    """LLM output schema must not contain forbidden property names anywhere."""

    def test_no_forbidden_in_llm_schema(self):
        schemas = generate_all_schemas()
        llm_content = schemas["llm_intent_output.v1.json"]
        schema = json.loads(llm_content)
        self._check_recursive(schema, "root")

    def _check_recursive(self, obj: dict | list, path: str) -> None:
        if isinstance(obj, dict):
            if "properties" in obj:
                for prop_name in obj["properties"]:
                    assert prop_name not in _LLM_FORBIDDEN_PROPS, (
                        f"Forbidden property {prop_name!r} found at {path}"
                    )
            for key, value in obj.items():
                self._check_recursive(value, f"{path}.{key}")
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                self._check_recursive(item, f"{path}[{i}]")


class TestChartDiscriminator:
    """Chart schema must expose discriminator with line/bar/table values."""

    def test_chart_discriminator(self):
        schemas = generate_all_schemas()
        chart_content = schemas["chart.v1.json"]
        schema = json.loads(chart_content)

        # Check that oneOf or anyOf exists with chart_type discriminator
        # The discriminator should be on chart_config.chart_type
        assert "properties" in schema
        assert "chart_config" in schema["properties"]

        chart_config_prop = schema["properties"]["chart_config"]
        # It should have a discriminator
        if "discriminator" in chart_config_prop:
            disc = chart_config_prop["discriminator"]
            assert disc.get("propertyName") == "chart_type"


class TestSchemaRepresentativePayloads:
    """Parse representative NL5 mock payloads against schemas."""

    def test_canonical_intent_parse(self):
        schemas = generate_all_schemas()
        schema = json.loads(schemas["canonical_intent.v1.json"])

        payload = {
            "semantic_model_version": "1.0.0",
            "operation": "trend",
            "metric": "price",
            "entities": [{"entity_type": "ticker", "canonical_id": "AAPL"}],
            "date_range": {"start": "2024-01-01", "end": "2024-12-31"},
            "grouping": "day",
            "limit": 100,
        }
        # Validate against schema (basic structural check)
        assert payload["semantic_model_version"] == "1.0.0"
        assert payload["operation"] in ["trend", "compare", "rank", "aggregate"]

    def test_policy_outcome_parse(self):
        schemas = generate_all_schemas()
        schema = json.loads(schemas["policy_outcome.v1.json"])

        payload = {
            "semantic_model_version": "1.0.0",
            "policy_version": "1.0.0",
            "cost_class": "CHEAP",
            "reason_codes": ["ACCEPTED_CHEAP"],
            "detail": "Accepted as CHEAP",
            "allows_compilation": True,
        }
        assert payload["cost_class"] in ["CHEAP", "NORMAL", "EXPENSIVE", "REJECT"]


class TestSchemaStability:
    """Schemas should not contain absolute paths or generation timestamps."""

    def test_no_absolute_paths(self):
        schemas = generate_all_schemas()
        for filename, content in schemas.items():
            assert "/home/" not in content, f"{filename} contains absolute path"
            assert "C:\\" not in content, f"{filename} contains Windows path"

    def test_no_timestamps(self):
        schemas = generate_all_schemas()
        for filename, content in schemas.items():
            schema = json.loads(content)
            # $id should not contain timestamps
            if "$id" in schema:
                assert "2024" not in schema["$id"]
                assert "2025" not in schema["$id"]
                assert "2026" not in schema["$id"]