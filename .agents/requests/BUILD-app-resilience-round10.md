# BUILD app resilience round 10 — IMPLEMENT NOW (Claude's run of the gate after round 9; small)

You are MiMo. Commit as you go, LF endings, do not touch `.agents/dispatch.sh`, never weaken tests.
Claude (WSL) `python3 -m pytest -q -m "not spark and not lakebase and not databricks"` after round 9 → 2 failed, 7 errors, 1536 passed:
1. tests/api/test_health_diagnostics.py::test_health_probe_reports_warming_state — `detail == 'databricks-sql-connector not installed'` instead
   of 'connecting', although databricks-sql-connector 4.6.0 IS installed (`import databricks.sql` works). Find why the probe concludes "not
   installed" (detection after the round-9 dotted-import changes? a test leaking a patched sys.modules/find_spec?) and fix the root cause; the
   warming state must win while the first connect is in flight. Add a test that a real installed connector is detected.
2. tests/api/test_frontend_serving.py — all 7 tests ERROR when the caller's shell has credential-looking env vars: PUBLIC_DEMO safety check
   correctly refuses (`PublicDemoConfigurationError: ... CLAUDE_CODE_MESSAGING_TOKEN, DATABRICKS_WORKSPACE_ID, ...`). Tests must not depend on the
   caller's environment: the fixture must build a clean, explicit env (monkeypatch.delenv for every var matching the secret patterns, or run the
   app factory with an injected env mapping). Add a test that a secret-looking var in the outer env does not break these fixtures, while the
   safety check itself still raises when the app's OWN env has one.
3. tests/ml/test_ablation.py::test_ablation_runner_varies_feature_set_between_arms — known slow/timeout; give it an explicit
   `@pytest.mark.timeout(...)` adequate for its runtime or mark it `slow` and exclude from this selection in pytest.ini — do not delete it.
Acceptance: the selection above → 0 failed, 0 errors, run from a shell WITH those env vars set. Verdict: .agents/mimo/VERDICT-app-resilience-round10.md.
