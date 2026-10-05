"""tests/test_app_yaml.py — Verify app.yaml does not pin personal schema.

The bundle sets CATALOG/SCHEMA via ${var.catalog}/${var.schema}.  app.yaml
must not override these with personal defaults.
"""
from __future__ import annotations

from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_app_yaml_has_no_personal_schema():
    """app.yaml must not contain the personal schema literal 'evangoh_capstone'.

    MUTATION: add 'evangoh_capstone' to app.yaml → FAIL.
    """
    app_yaml = _PROJECT_ROOT / "app.yaml"
    if not app_yaml.exists():
        return  # no app.yaml is fine

    content = app_yaml.read_text()
    assert "evangoh_capstone" not in content, (
        "app.yaml must not pin personal schema 'evangoh_capstone'. "
        "CATALOG/SCHEMA should be injected by the bundle/app resources."
    )


def test_app_yaml_has_no_hardcoded_env_values():
    """app.yaml env section should not have hardcoded value fields.

    The bundle injects CATALOG/SCHEMA via resource configuration.
    Hardcoded values in app.yaml override the bundle and can leak a
    personal dev schema into production.
    """
    import yaml

    app_yaml = _PROJECT_ROOT / "app.yaml"
    if not app_yaml.exists():
        return

    content = app_yaml.read_text()
    # Parse the YAML (handle comments)
    try:
        data = yaml.safe_load(content)
    except Exception:
        return  # YAML parse error — not our concern here

    if not data or "env" not in data:
        return  # no env section is fine

    env_vars = data.get("env") or []
    for entry in env_vars:
        name = entry.get("name", "")
        if name in ("CATALOG", "SCHEMA"):
            assert "value" not in entry, (
                f"app.yaml env '{name}' must not have a hardcoded 'value'. "
                f"The bundle injects this via resource configuration."
            )