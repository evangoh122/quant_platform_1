# BUILD: Render lane B round 2 (MiMo)

Claude ran your lane-B commit on WSL: **10 failed**. Your verdict said APPROVED because Windows has a
different environment. Both defects are in the TESTS, so the security logic in `api/demo.py` stays
as is (fail-closed is correct).

## 1. The tests depend on the ambient environment
On WSL, the shell has `CLAUDE_CODE_MESSAGING_TOKEN` and `DATABRICKS_WORKSPACE_ID`. `api/demo.py`
correctly refuses to start, so 9 tests in `tests/api/test_public_demo_security.py` raise
`PublicDemoConfigurationError`. Any CI runner or developer machine can carry such variables.

Fix: add an autouse fixture in that test module. Before each test it removes every env var that
`api/demo.py` would treat as a secret: the `LAKEBASE_` and `DATABRICKS_` prefixes, and the
`*_API_KEY`, `*_TOKEN` and `*_SECRET` suffixes, plus whatever else the checker matches. Use
`monkeypatch.delenv`, and reuse the same predicate function from `api/demo.py` so the two can't
drift. Keep the explicit tests that set one variable per family and expect refusal.

Prove it: run the suite with `CLAUDE_CODE_MESSAGING_TOKEN=x DATABRICKS_WORKSPACE_ID=y` exported.
It must pass.

## 2. Test pollution breaks `tests/api/test_rbac.py`
`tests/api/test_rbac.py::test_new_viewer_cannot_approve_order` passes alone, but fails (503 instead
of 403) when it runs after `test_public_demo_security.py`:

    python3 -m pytest -q tests/api/test_rbac.py tests/api/test_public_demo_security.py   # order may vary; run both orders

Find the leak: a reloaded `api.main`/`api.deps` module, the app/router state, the rate-limiter
state, `PUBLIC_DEMO` left set, or `sys.modules` edits. Every demo test must restore global state:
use `monkeypatch` for env and `sys.modules`, and reload modules back to the non-demo state in
teardown. Better still, build apps with `create_app()` and don't reload modules.

Prove it: run with `-p no:randomly`, in both file orders, plus the full
`python3 -m pytest -q --ignore=tests/lakebase`. Paste the output.

LF line endings only. Don't touch `.agents/dispatch.sh`. Commit. Update
`.agents/mimo/VERDICT-render-lane-b.md` (round 2).
