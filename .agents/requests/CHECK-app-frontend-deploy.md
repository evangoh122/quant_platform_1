# CHECK: app frontend deploy (checker: DeepSeek)

Read-only. Mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>`. Write .agents/deepseek/VERDICT-app-frontend-deploy.md between
===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED". Request: .agents/requests/BUILD-app-frontend-deploy.md.
Verify the 5 items. Context: Claude already deployed main + a locally built dist with an equivalent `sync.include: frontend/dist/**` and
`databricks bundle deploy -t dev` uploaded it (343 files) — so the include approach works.
1. databricks.yml sync.include frontend/dist/**, excludes intact. 2. scripts/build_frontend.sh fails loudly; DEPLOYMENT.md runbook complete and correct.
3. api/main.py missing-dist warning + hint at GET /, API still works; dist present → index.html. Mutations: remove the fallback → test FAILS.
4. YAML test real. 5. scripts/smoke_app.py: no secrets; covers health, /, one read-only route per backed screen; handles Databricks App auth sensibly
(the app URL requires a Databricks login/OAuth token — check what it does).
Run: python3 -m pytest -q -m "not spark and not lakebase and not databricks"; cd frontend && npm ci && npm run build.
