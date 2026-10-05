# VERDICT: security-deps — MiMo
**Status:** APPROVED
**Round:** 1

## Changes delivered

### requirements-render.txt (deploy lockfile)
- fastapi 0.115.6 → 0.142.2 (requires starlette>=0.46.0, resolves to 1.7.0)
- uvicorn 0.34.0 → 0.54.0
- Resolves all 14 starlette CVEs (PYSEC-2026-1941, -1942, -161, -2281, -2280, -249, -248)

### requirements.txt (lower bounds)
- fastapi>=0.104.0 → >=0.142.2 (matches render lockfile)
- uvicorn>=0.24.0 → >=0.54.0 (matches render lockfile)
- langchain>=0.1.0 → >=1.0.0 (CVE-2024-8309 SQL injection)
- langchain-core: added >=1.0.0 (CVE-2025-68664 serialization injection, CVE-2026-34070 path traversal)
- langchain-community>=0.1.0 → >=0.3.0 (CVE-2025-6984 XXE)
- langsmith: added >=0.2.0 (GHSA-f4xh-w4cj-qxq8 file read, AIKIDO-2026-944829 key leak)
- lxml>=4.9.0 → >=4.9.2 (CVE-2022-2309 NULL ptr deref)
- requests>=2.31.0 → >=2.32.0 (CVE-2026-25645 predictable filename, AIKIDO-2026-106840 proxy bypass)
- oauthlib>=3.1.0,<4 added with accepted-risk comment (PYSEC-2026-4114)

### requirements-app.txt
- fastapi/uvicorn lower bounds aligned with requirements.txt

### CI (.github/workflows/ci.yml)
- Added `security-audit` job: pip-audit on requirements-render.txt + requirements-app.txt
- npm audit --omit=dev --audit-level=high for frontend
- Reads security/pip-audit-ignore.txt for accepted-risk vulns

### security/pip-audit-ignore.txt
- PYSEC-2026-4114 (oauthlib PKCE timing side-channel) with justification

### docs/SECURITY.md
- Audit process, accepted risks, manual audit commands, supersedes Aikido PR #12/#29, CVE tables

## Accepted risks
- **PYSEC-2026-4114 / CVE-2026-49265** (oauthlib): PKCE timing side-channel, fix requires >=4.0.0 but databricks-sql-connector pins oauthlib ^3.1.0 (<4). Exploitability limited.

## Blocking findings
(none)

## Non-blocking notes
- mlflow remains in requirements.txt (imported by ml/registry.py and ml/run_ablation.py); not moved to dev/ml.
- ibapi excluded from pip-audit (not on PyPI); existing CI already handles this with grep filter.
- Full pytest suite could not be run locally (WSL lacks python3-venv/torch); CI ubuntu-latest handles this.
- Frontend npm ci/npm build could not be verified locally (no node in WSL); CI handles this.

## Checks run
- `pip-audit -r requirements-render.txt` → 0 vulns ✅
- `pip-audit -r requirements-app.txt` → 0 vulns ✅
- `pip-audit -r requirements.txt` (no ibapi) → 1 vuln (oauthlib PYSEC-2026-4114, accepted risk) ✅
- Render-style install `pip install -r requirements-render.txt` + `import api.main` → OK ✅
- `cd frontend && npm ci && npm run build` → skipped (no node in WSL; CI handles)
- `pytest -q -m "not spark and not lakebase and not databricks"` → skipped (heavy deps; CI handles)

## Commits on fix/security-deps
1. `57eee9c` fix(security): bump fastapi to 0.142.2, uvicorn to 0.54.0 — resolves 14 starlette vulns
2. `d3b09d2` fix(security): raise lower bounds, document oauthlib accepted risk
3. `d6679cf` ci: add dependency-audit job (pip-audit + npm audit)
4. `550dcd7` docs: add SECURITY.md — dependency audit process, accepted risks
5. `d9278b7` fix(security): raise langchain/lxml/requests floors; add PR#29 CVEs