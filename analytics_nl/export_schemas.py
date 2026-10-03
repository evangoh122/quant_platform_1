"""Schema exporter — generates deterministic JSON Schema artifacts from Pydantic models."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from analytics_nl.contracts import (
    AliasResolutionEnvelope,
    CanonicalIntent,
    ChartEnvelope,
    LLMIntentOutput,
    PolicyOutcome,
    ProvenanceEnvelope,
    SEMANTIC_MODEL_VERSION,
)

_SCHEMA_DIR = Path(__file__).parent / "schemas"

# Map of filename → (model, title, description)
_SCHEMAS: list[tuple[str, type, str, str]] = [
    (
        "canonical_intent.v1.json",
        CanonicalIntent,
        "NL1 Canonical Intent Schema",
        "Resolved canonical intent with all entities as canonical IDs.",
    ),
    (
        "llm_intent_output.v1.json",
        LLMIntentOutput,
        "NL1 LLM Intent Output Schema",
        "LLM extraction output with unresolved entity mentions. "
        "Intentionally excludes SQL, code, table, view, column, predicate, "
        "order_by, expression, prompt, url, html, javascript fields.",
    ),
    (
        "policy_outcome.v1.json",
        PolicyOutcome,
        "NL1 Policy Outcome Schema",
        "Policy classification result. Gates NL2 compilation.",
    ),
    (
        "chart.v1.json",
        ChartEnvelope,
        "NL1 Chart Envelope Schema",
        "Approved chart configuration with line/bar/table discriminator.",
    ),
    (
        "provenance.v1.json",
        ProvenanceEnvelope,
        "NL1 Provenance Envelope Schema",
        "Provenance record for executed queries.",
    ),
    (
        "alias_resolution.v1.json",
        AliasResolutionEnvelope,
        "NL1 Alias Resolution Schema",
        "Envelope for alias resolution results with trace records.",
    ),
]


def _generate_schema(model: type, title: str, description: str) -> dict:
    """Generate a JSON Schema from a Pydantic model."""
    schema = model.model_json_schema()

    # Add metadata
    schema["$id"] = f"https://analytics-nl/schemas/{title.lower().replace(' ', '-')}"
    schema["title"] = title
    schema["description"] = description

    # Ensure additionalProperties is false at top level
    if "additionalProperties" not in schema:
        schema["additionalProperties"] = False

    return schema


def _normalize_schema(schema: dict) -> str:
    """Serialize schema to deterministic JSON string."""
    return json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def generate_all_schemas() -> dict[str, str]:
    """Generate all schemas and return {filename: content} mapping."""
    result = {}
    for filename, model, title, description in _SCHEMAS:
        schema = _generate_schema(model, title, description)
        result[filename] = _normalize_schema(schema)
    return result


def check_schemas() -> bool:
    """Check if checked-in schemas match generated ones. Returns True if OK."""
    generated = generate_all_schemas()
    ok = True

    for filename, expected_content in generated.items():
        path = _SCHEMA_DIR / filename
        if not path.exists():
            print(f"MISSING: {path}")
            ok = False
            continue

        actual_content = path.read_text(encoding="utf-8")
        if actual_content != expected_content:
            print(f"DIFFERS: {path}")
            # Show first difference
            expected_lines = expected_content.splitlines()
            actual_lines = actual_content.splitlines()
            for i, (e, a) in enumerate(zip(expected_lines, actual_lines)):
                if e != a:
                    print(f"  Line {i + 1}:")
                    print(f"    expected: {e}")
                    print(f"    actual:   {a}")
                    break
            ok = False

    return ok


def write_schemas() -> None:
    """Write all schemas to disk."""
    _SCHEMA_DIR.mkdir(parents=True, exist_ok=True)
    generated = generate_all_schemas()

    for filename, content in generated.items():
        path = _SCHEMA_DIR / filename
        path.write_text(content, encoding="utf-8", newline="\n")
        print(f"Wrote {path}")


def main() -> None:
    """CLI entry point."""
    if len(sys.argv) < 2:
        print("Usage: python -m analytics_nl.export_schemas [--check|--write]")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "--check":
        if check_schemas():
            print("All schemas match.")
            sys.exit(0)
        else:
            print("Schema check failed.")
            sys.exit(1)
    elif cmd == "--write":
        write_schemas()
        print("All schemas written.")
    else:
        print(f"Unknown command: {cmd}")
        print("Usage: python -m analytics_nl.export_schemas [--check|--write]")
        sys.exit(1)


if __name__ == "__main__":
    main()