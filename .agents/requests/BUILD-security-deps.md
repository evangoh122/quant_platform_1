# BUILD-security-deps round 1 — IMPLEMENT NOW (dependency vulnerabilities flagged by Aikido / pip-audit)

You are MiMo. Branch `fix/security-deps` (off origin/main). Stay on it — do not create/switch branches. Commit per item, LF endings, do not touch
`.agents/dispatch.sh`, never weaken tests.
Context: Aikido opened PR #12 ("Fix 1 critical issue in langchain and 26 other issues": SQL injection in LangChain, webhook bypass + directory
traversal RCE in MLflow, command injection in model serving, Host-header validation bypass in Starlette, plus gunicorn, websockets, protobuf,
langsmith). It was REJECTED by all four reviewers because it exact-pinned blindly (e.g. DOWNGRADED langchain to ==0.2.0, pinned starlette==1.0.1
independently of fastapi, lxml==4.9.1). Do the fix properly.
Claude's pip-audit baseline today (`uvx pip-audit -r <file>`), full JSON for render in `.agents/claude/pip-audit-render-2026-10-05.json`:
- requirements-render.txt (USED BY THE LIVE RENDER DEPLOY, render.yaml:6): `fastapi==0.115.6` pulls `starlette 0.41.3` → 14 known vulns
  (fixes at >=0.47.2 … >=1.3.1). HIGHEST PRIORITY.
- requirements.txt (lower-bounded ranges): resolves clean today EXCEPT `oauthlib 3.3.1` (transitive via databricks-sql-connector; fix >= 4.0.0) —
  but the lower bounds still PERMIT the vulnerable versions Aikido flagged (langchain>=0.1.0, langchain-community>=0.1.0, mlflow>=2.10.0, …).
- requirements-app.txt: clean. frontend `npm audit --omit=dev`: clean.
Changes:
1. requirements-render.txt: bump fastapi (+ uvicorn) to versions whose starlette constraint is >= the latest-fix starlette version reported
   (prefer the newest compatible fastapi; keep exact pins in this file since it is the deploy lockfile). Verify `pip-audit -r requirements-render.txt`
   → 0 vulns.
2. requirements.txt / requirements-app.txt: raise LOWER BOUNDS (not exact pins, no downgrades) to the first non-vulnerable versions for every package
   Aikido/pip-audit flag: langchain, langchain-community, langchain-core, langsmith, langgraph, mlflow, starlette (via fastapi floor), gunicorn,
   websockets, protobuf, lxml, oauthlib (add an explicit `oauthlib>=4.0.0` only if databricks-sql-connector allows it — check its metadata; if it
   caps oauthlib<4, record that as an accepted risk with justification instead). Use the advisory data from `pip-audit -f json` for the exact
   fix versions. If `mlflow` is not imported by app/runtime code (Aikido says it is imported nowhere), move it out of the app requirements into
   requirements-dev or the ML/job requirements where it is actually used — do not delete what ml/ jobs need (grep first).
3. CI: add a `pip-audit` step to .github/workflows/ci.yml for requirements-render.txt and requirements-app.txt (fail on any vuln; allow an
   explicit `--ignore-vuln <ID>` list file `security/pip-audit-ignore.txt` with a justification comment per ID), and `npm audit --omit=dev
   --audit-level=high` for the frontend.
4. Document in `docs/SECURITY.md`: how dependencies are audited, the accepted-risk list, and that Aikido PR #12 was superseded by this change.
Acceptance (paste outputs in the verdict): `uvx pip-audit -r requirements-render.txt` → 0; `uvx pip-audit -r requirements-app.txt` → 0;
`uvx pip-audit -r requirements.txt` (exclude ibapi, not on PyPI) → 0 or only documented accepted risks; `python3 -m pytest -q -m "not spark and
not lakebase and not databricks"` green; a Render-style install `pip install -r requirements-render.txt` in a fresh venv + `python -c "import
api.main"` succeeds; `cd frontend && npm ci && npm run build`.
Verdict: .agents/mimo/VERDICT-security-deps.md.
