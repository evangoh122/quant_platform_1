import os
import importlib


def test_config_schema_default(monkeypatch):
    monkeypatch.delenv("SCHEMA", raising=False)
    from config import settings
    importlib.reload(settings)
    assert settings.SCHEMA == "evangoh_capstone"


def test_config_schema_override(monkeypatch):
    monkeypatch.setenv("SCHEMA", "custom_schema")
    from config import settings
    importlib.reload(settings)
    assert settings.SCHEMA == "custom_schema"


def test_api_config_schema_default(monkeypatch):
    monkeypatch.delenv("SCHEMA", raising=False)
    from api.config import Config as _Config
    import api.config as cfg_mod
    importlib.reload(cfg_mod)
    assert cfg_mod.config.SCHEMA == "evangoh_capstone"


def test_api_config_schema_override(monkeypatch):
    monkeypatch.setenv("SCHEMA", "custom_schema")
    import api.config as cfg_mod
    importlib.reload(cfg_mod)
    assert cfg_mod.config.SCHEMA == "custom_schema"

def test_run_silver_gold_schema_arg(monkeypatch):
    import sys
    import types

    # CI has no databricks-connect; the module imports it at top level. Stub it.
    try:
        import databricks.connect  # noqa: F401
    except ImportError:
        fake = types.ModuleType("databricks.connect")
        fake.DatabricksSession = object
        monkeypatch.setitem(sys.modules, "databricks.connect", fake)
        monkeypatch.delitem(sys.modules, "pipelines.run_silver_gold", raising=False)
    import pipelines.run_silver_gold as r
    # Register the originals so monkeypatch restores them after main() rebinds them.
    monkeypatch.setattr(r, "SCHEMA", r.SCHEMA)
    monkeypatch.setattr(r, "FQN", r.FQN)
    monkeypatch.setattr(sys, "argv", ["run_silver_gold.py", "--schema", "evangoh_capstone_prod", "--counts"])

    def _stop():
        raise SystemExit(0)

    monkeypatch.setattr(r, "get_spark", _stop)
    try:
        r.main()
    except SystemExit:
        pass
    assert r.FQN == "bootcamp_students.evangoh_capstone_prod"
