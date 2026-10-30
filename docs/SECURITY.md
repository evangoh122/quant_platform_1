# Security: Dependency Auditing

## Overview

Dependencies are audited for known vulnerabilities using:

- **pip-audit** (Python) — runs in CI on every PR and push to `main`
- **npm audit** (Node.js) — runs in CI on every PR and push to `main`
- **Aikido** — external monitoring (superseded by this in-repo audit)

## CI enforcement

The `security-audit` job in `.github/workflows/ci.yml` runs:

1. `uv export --frozen --no-dev --no-hashes | pip-audit -r /dev/stdin` — the locked runtime set (what Databricks Apps and the Docker image install)
2. `uv run pip-audit` — the environment uv built from the lock (runtime + dev)
3. `npm audit --omit=dev --audit-level=high` — frontend production dependencies

Both audit inputs are exports of the committed `uv.lock`, so the audited set is
exactly the resolved set — it cannot drift from `pyproject.toml`.

Any vulnerability without an accepted-risk entry in `security/pip-audit-ignore.txt`
will **fail the build**.

## Accepted risks

| ID | Package | Reason |
|----|---------|--------|
| PYSEC-2026-4114 (CVE-2026-49265) | oauthlib 3.x | PKCE timing side-channel; fix requires >=4.0.0 but `databricks-sql-connector` pins `oauthlib ^3.1.0` (<4). Exploitability limited: requires repeated authorization_code interception under controlled network conditions. |
| CVE-2026-49272 (GHSA-3jp2-3mrg-2vxc) | oauthlib 3.x | Device-code grant (RFC 8628) does not validate `device_code`; fix requires >=4.0.0 but this project pins `oauthlib>=3.1.0,<4` directly at `pyproject.toml:70` (`databricks-sql-connector` itself allows `<5.0.0`). Exploitability limited: needs a valid client ID enrolled in the device workflow, which the connector does not use. Upgrading to 4.0.0 requires lifting that pin and testing. |

To add a new accepted risk:

1. Add the vuln ID to `security/pip-audit-ignore.txt` with a justification comment.
2. Update the table above.
3. The CI ignore-args builder reads non-comment lines from that file.

## Supersedes

Aikido PR #12 ("Fix 1 critical issue in langchain and 26 other issues") was
rejected by all four reviewers because it exact-pinned blindly (downgraded
langchain to ==0.2.0, pinned starlette==1.0.1 independently of fastapi,
lxml==4.9.1). Aikido PR #29 was also unsatisfiable (langchain==0.2.0 needs
langsmith<0.2 but pins langsmith==0.10.9; lxml==4.9.1 fails to build on CI).

This change supersedes both PRs:

- **requirements-render.txt** (retired with Render): fastapi bumped to 0.142.2
  (pulls starlette 1.7.0), resolving all 14 starlette CVEs. That exact-pin
  deploy set is superseded by `uv.lock` + the generated `requirements.txt`.
- **requirements.txt**: lower bounds raised for all Aikido-flagged packages to
  first non-vulnerable versions (langchain>=1.0.0, langchain-core>=1.0.0,
  langchain-community>=0.3.0, langsmith>=0.2.0, lxml>=4.9.2, requests>=2.32.0,
  fastapi>=0.142.2, uvicorn>=0.54.0). These floors now live in
  `pyproject.toml`; `requirements.txt` is generated from `uv.lock`. Lower bounds
  do not force an upgrade, so the audit also runs against the resolved lock —
  `uv lock --upgrade-package <name>` is how a flagged floor is actually raised.
- **oauthlib**: documented as accepted risk (transitive via
  databricks-sql-connector).

## Manual audit

```bash
# Runtime set (what Databricks Apps / the Docker image install):
uv export --frozen --no-dev --no-hashes | pip-audit -r /dev/stdin

# Full CI set (the environment `uv sync --frozen --group dev` created):
uv run pip-audit
```

`pyproject.toml` carries one `[tool.uv].override-dependencies` entry:
`certifi>=2026.10.19`. `polygon-api-client` (dev-only) caps certifi at
`<2026.0.0`, which held the shared lock at 2025.11.12 (PYSEC-2026-4320). certifi
is a CA-data package with an unchanged API, so the runtime security floor
overrides that dev-tool cap; a pip re-resolution of the dev export would report
the conflict, which is why the CI job audits the uv-built environment instead
of re-resolving the export with pip.


`ibapi` is not on PyPI and never enters `uv.lock`, so no filtering is needed
anymore (CI still asserts it stays out).

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

## Other CVEs resolved by lower-bound raises

| CVE | Package | Description | New floor |
|-----|---------|-------------|-----------|
| CVE-2024-8309 | langchain | SQL injection via GraphCypherQAChain | >=1.0.0 |
| CVE-2025-68664 | langchain-core | Serialization injection in dumps()/dumpd() | >=1.2.22 |
| CVE-2026-34070 | langchain-core | Prompt loading path traversal | >=1.2.22 |
| GHSA-f4xh-w4cj-qxq8 | langsmith | Tracing header arbitrary file read | >=0.8.18 |
| AIKIDO-2026-944829 | langsmith | Signing key leak in trace metadata | >=0.8.18 |
| CVE-2025-6984 | langchain-community | XXE in EverNoteLoader | >=0.3.27 |
| CVE-2022-2309 | lxml | NULL ptr dereference in iterwalk | >=4.9.2 |
| AIKIDO-2026-106840 | requests | Proxy bypass via no_proxy matching | >=2.33.0 |
| CVE-2026-25645 | requests | Predictable filename in extract_zipped_paths | >=2.33.0 |