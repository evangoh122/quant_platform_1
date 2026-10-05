# Security: Dependency Auditing

## Overview

Dependencies are audited for known vulnerabilities using:

- **pip-audit** (Python) — runs in CI on every PR and push to `main`
- **npm audit** (Node.js) — runs in CI on every PR and push to `main`
- **Aikido** — external monitoring (superseded by this in-repo audit)

## CI enforcement

The `security-audit` job in `.github/workflows/ci.yml` runs:

1. `pip-audit -r requirements-render.txt` — the Render deploy lockfile (exact pins)
2. `pip-audit -r requirements-app.txt` — the app runtime dependencies
3. `npm audit --omit=dev --audit-level=high` — frontend production dependencies

Any vulnerability without an accepted-risk entry in `security/pip-audit-ignore.txt`
will **fail the build**.

## Accepted risks

| ID | Package | Reason |
|----|---------|--------|
| PYSEC-2026-4114 (CVE-2026-49265) | oauthlib 3.x | PKCE timing side-channel; fix requires >=4.0.0 but `databricks-sql-connector` pins `oauthlib ^3.1.0` (<4). Exploitability limited: requires repeated authorization_code interception under controlled network conditions. |

To add a new accepted risk:

1. Add the vuln ID to `security/pip-audit-ignore.txt` with a justification comment.
2. Update the table above.
3. The CI ignore-args builder reads non-comment lines from that file.

## Supersedes

Aikido PR #12 ("Fix 1 critical issue in langchain and 26 other issues") was
rejected by all four reviewers because it exact-pinned blindly (downgraded
langchain to ==0.2.0, pinned starlette==1.0.1 independently of fastapi,
lxml==4.9.1). This change supersedes that PR:

- **requirements-render.txt**: fastapi bumped to 0.142.2 (pulls starlette 1.7.0),
  resolving all 14 starlette CVEs. Exact pins retained as the deploy lockfile.
- **requirements.txt**: lower bounds raised for fastapi/uvicorn to match the
  render lockfile. All other packages (langchain, mlflow, gunicorn, websockets,
  protobuf, lxml) resolve clean per pip-audit; lower bounds unchanged.
- **oauthlib**: documented as accepted risk (transitive via
  databricks-sql-connector).

## Manual audit

```bash
pip-audit -r requirements-render.txt
pip-audit -r requirements-app.txt
# exclude ibapi (not on PyPI):
grep -viE '^[[:space:]]*ibapi([<=>~!]|$)' requirements.txt | pip-audit -r /dev/stdin
```

## Starlette CVEs resolved by this change

| CVE | Description | Fix version |
|-----|-------------|-------------|
| CVE-2025-54121 | Multipart form DoS | >=0.47.2 |
| CVE-2025-62727 | Range header DoS | >=0.49.1 |
| CVE-2026-48710 | Host header validation bypass | >=1.0.1 |
| CVE-2026-48818 | Windows StaticFiles SSRF | >=1.1.0 |
| CVE-2026-48817 | HTTPEndpoint method dispatch | >=1.1.0 |
| CVE-2026-54283 | urlencoded form limit bypass | >=1.3.1 |
| CVE-2026-54282 | request URL path injection | >=1.3.0 |