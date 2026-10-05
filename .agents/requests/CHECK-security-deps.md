# CHECK: security-deps (checker: DeepSeek) — FAST (submission in ~3 h; keep to ~25 min)

Read-only. Write .agents/deepseek/VERDICT-security-deps.md between ===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or
"Status: CHANGES_REQUESTED", with file:line evidence. Request: BUILD-security-deps.md; Aikido CVEs: .agents/claude/aikido-pr29-findings.md.
Claude: `uvx pip-audit -r requirements-render.txt` → 0; `-r requirements-app.txt` → 0; fresh venv `pip install -r requirements-render.txt`
(fastapi 0.142.2 / starlette 1.7.0) + clean-env `PUBLIC_DEMO=1 uvicorn api.main:app` → /api/health 200.
Verify: every Aikido PR #29 CVE (langchain, langchain-core, langsmith, langchain-community, lxml, requests) is excluded by the new lower bounds
(no downgrades, no exact pins in requirements.txt/app); oauthlib handled or justified; mlflow change does not break ml/ jobs (grep usage);
CI dependency-audit job is correct YAML and would fail on a vuln; SECURITY.md accurate. Run: python3 -m pytest -q tests/api tests/test_requirements_completeness.py --timeout 120.
