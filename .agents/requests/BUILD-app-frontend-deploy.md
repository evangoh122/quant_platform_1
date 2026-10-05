# BUILD app-frontend-deploy (builder: MiMo; checker: DeepSeek; reviewer: Codex; final + live deploy: Claude)

IMPLEMENT NOW. Do not ask "Shall I proceed?". Branch slice/app-frontend-deploy (off main). Commit after each item, descriptive messages. LF.
NEVER delete or weaken tests. You cannot reach Databricks; Claude deploys and smoke-tests live.

Problem: the Databricks App (resources/app.yml, `quant-platform-${bundle.target}`, uvicorn api.main:app) serves `frontend/dist` as a same-origin SPA
(api/main.py ~355) only if it exists, but frontend/dist is gitignored (.gitignore) and bundle sync respects .gitignore, so `databricks bundle deploy`
ships the API without the UI.

1. databricks.yml: add `sync.include: [frontend/dist/**]` (keep the existing excludes, incl. frontend/node_modules). Verify with the Databricks bundle docs
   semantics in a comment: include overrides gitignore for those paths.
2. A build step operators run before deploy: `scripts/build_frontend.sh` (npm ci && npm run build in frontend/, fails loudly) and document it in
   docs/DEPLOYMENT.md (“Deploying the Databricks App”: build frontend → bundle validate → bundle deploy → apps start → smoke test URLs). Also a Makefile
   target or note if a Makefile exists. Do NOT commit frontend/dist.
3. api/main.py: if FRONTEND_DIST is missing at startup in the app environment, log a clear WARNING ("frontend/dist not found — run scripts/build_frontend.sh
   before deploy") and keep the API working; GET / returns a small JSON/HTML hint instead of 404. Test both (dist present → index.html served; absent →
   hint + API routes still work) with FastAPI TestClient and a tmp dist dir.
4. Test that databricks.yml sync.include contains frontend/dist/** and the exclude list still has frontend/node_modules (parse YAML).
5. Smoke-test script scripts/smoke_app.py <base_url>: GET /api/health (or the existing health route — check api/main.py), GET / (expects index.html),
   and one read-only API per screen that has a backend route (list them); prints PASS/FAIL per check; no auth secrets in the script (use the
   Databricks CLI token from the environment only if the app requires auth — read DEPLOYMENT.md §9 auth notes).
Acceptance: python3 -m pytest -q (CI-equivalent: -m "not spark and not lakebase and not databricks") passes; `cd frontend && npm ci && npm run build` works.
.agents/mimo/VERDICT-app-frontend-deploy.md. Commit everything.
