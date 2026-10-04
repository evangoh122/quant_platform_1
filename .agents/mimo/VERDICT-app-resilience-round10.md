# VERDICT: app-resilience-round10 — MiMo
**Status:** APPROVED
**Round:** 10

## Blocking findings
(none)

## Non-blocking notes
- Reordered `check_warehouse_health()` to check `get_warm_state()` before `_warehouse_available()` so the "connecting" state is never masked by an import-detection race
- Added `test_warehouse_available_detects_installed_connector` regression test proving `_warehouse_available()` returns `True` when `databricks-sql-connector` is installed
- `_demo_env` fixture in `test_frontend_serving.py` now strips ambient secret env vars using `api.demo._is_unsafe_key` (same predicate as `test_public_demo_security.py._strip_ambient_secrets`)
- Added `TestAmbientSecretsIsolation` class with two tests: one proving the fixture strips ambient secrets, one proving the safety check still raises for secrets injected after the fixture
- Added `@pytest.mark.timeout(120)` to `test_ablation_runner_varies_feature_set_between_arms` and registered `slow` marker in `pytest.ini`

## Checks run
- `wsl python3 -m pytest tests/api/test_health_diagnostics.py::test_health_probe_reports_warming_state tests/api/test_health_diagnostics.py::test_check_warehouse_health_reports_warming tests/api/test_health_diagnostics.py::test_warehouse_available_detects_installed_connector -v` → 3 passed
- `wsl python3 -m pytest tests/api/test_frontend_serving.py -v` → 9 passed
- `wsl python3 -m pytest -q -m "not spark and not lakebase and not databricks"` → **1548 passed, 97 skipped, 24 deselected, 0 failed, 0 errors** (212s)