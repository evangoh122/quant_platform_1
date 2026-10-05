===VERDICT START===
# VERDICT: security-deps — DeepSeek
**Status:** CHANGES_REQUESTED
**Round:** 1

## Scope of this check
Read-only review of `fix/security-deps` (10 commits ahead of origin/main). Verified
against `BUILD-security-deps.md`, `.agents/claude/aikido-pr29-findings.md`, and the
CHECK criteria: (a) `pip-audit` on the three requirements files, (b) every Aikido
PR #29 CVE is excluded by the new lower bounds, (c) oauthlib justified, (d) mlflow
keeps ml/ jobs working, (e) CI dependency-audit YAML correct and fails on a vuln,
(f) SECURITY.md accurate.

## Blocking findings

1. **[requirements.txt:7] `langchain-core>=1.0.0` does NOT exclude CVE-2025-68664.**
   OSV `GHSA-c67j-w6g6-q2cm` / `PYSEC-2026-373` ranges: `introduced 1.0.0 → fixed 1.2.5`
   (plus `introduced 0 → fixed 0.3.81`). The `>=1.0.0` floor permits
   langchain-core 1.0.0–1.2.4, all vulnerable to serialization injection
   (RCE via malicious `lc` keys). `pip-audit -r requirements.txt` does NOT catch this
   because it resolves the *latest* langchain-core, not every permitted version.

2. **[requirements.txt:7] `langchain-core>=1.0.0` does NOT exclude CVE-2026-34070.**
   OSV `GHSA-qh6h-p6c9-ff54` / `PYSEC-2026-2193`: `introduced 0 → fixed 1.2.22`.
   The `>=1.0.0` floor permits 1.0.0–1.2.21, all vulnerable to the `load_prompt`
   path-traversal/arbitrary-file-read. Verified: `langchain-core==1.2.21` still
   returns GHSA-qh6h-p6c9-ff54 from the OSV query API. Correct floor: `>=1.2.22`.

3. **[requirements.txt:8] `langchain-community>=0.3.0` does NOT exclude CVE-2025-6984.**
   OSV `GHSA-pc6w-59fv-rh23` / `PYSEC-2026-1515`: `introduced 0 → fixed 0.3.27`.
   `>=0.3.0` permits 0.3.0–0.3.26 (XXE in EverNoteLoader). Verified:
   `langchain-community==0.3.22` still returns the advisory. Correct floor: `>=0.3.27`.

4. **[requirements.txt:9] `langsmith>=0.2.0` does NOT exclude GHSA-f4xh-w4cj-qxq8 / CVE-2026-59152.**
   OSV: `introduced 0 → fixed 0.8.18`. `>=0.2.0` permits 0.2.0–0.8.17, all vulnerable
   to the TracingMiddleware arbitrary file read (HIGH, information disclosure).
   Verified: `langsmith==0.8.17` still returns GHSA-f4xh-w4cj-qxq8; `0.8.18` does not.
   Correct floor: `>=0.8.18`.

5. **[requirements.txt:14] `requests>=2.32.0` does NOT exclude CVE-2026-25645.**
   OSV `GHSA-gc5v-m9x4-r6x2` / `PYSEC-2026-2275`: `introduced 0 → fixed 2.33.0`.
   `>=2.32.0` permits 2.32.0–2.32.5 (predictable temp filename in
   `extract_zipped_paths()`, arbitrary code execution). Verified:
   `requests==2.32.5` still returns the advisory. Correct floor: `>=2.33.0`.

6. **[docs/SECURITY.md:78-86]** The "Other CVEs resolved by lower-bound raises" table
   is factually wrong for rows 79 (langchain-core → `>=1.0.0`), 83 (langsmith →
   `>=0.2.0`), 84 (langchain-community → `>=0.3.0`), and 86 (requests → `>=2.32.0`):
   those floors do NOT reach the fix versions. Once floors are corrected this table
   must be updated to match.

## Non-blocking notes

- **Not-in-PR-#29 but still below "first non-vulnerable":**
  - `langchain>=1.0.0` (requirements.txt:6) still permits CVE-2026-55443
    (path traversal + sandbox escape in file-search middleware/loaders,
    `GHSA-gr75-jv2w-4656`, fixed 1.3.9). CVE-2024-8309 itself *is* excluded (fixed 0.2.0). ✅
  - `lxml>=4.9.2` (requirements.txt:18) correctly excludes CVE-2022-2309 (fixed 4.9.1) ✅,
    but still permits CVE-2026-41066 (`GHSA-vfmq-68hx-4jfw`, XXE in iterparse, fixed 6.1.0).
- **CI coverage gap:** the `security-audit` job (.github/workflows/ci.yml:144-197) only
  audits requirements-render.txt and requirements-app.txt, never requirements.txt — which
  is exactly where the four insufficient floors above live. Per BUILD item 3 this is
  in-spec, but it means CI would *not* fail on the regressions this verdict flags.
- **mlflow** (requirements.txt:11, `>=2.10.0`) is correctly kept: imported by
  `ml/registry.py:50,78,84` and `ml/run_ablation.py:60`. No change → no ml/ breakage. ✅
- **`tests/test_requirements_completeness.py` does not exist** in the repo (the CHECK
  command references it). `tests/api` exists and was run instead.
- **`pytest tests/api` is not fully green** (see Checks run) — 1 failure, appears
  unrelated to this dependency slice (rate limiter, not touched by the diff).

## Checks run

- `uvx pip-audit -r requirements-render.txt` → **pass** — "No known vulnerabilities found"
- `uvx pip-audit -r requirements-app.txt` → **pass** — "No known vulnerabilities found"
- `uvx pip-audit -r requirements.txt` (ibapi stripped) → **pass** — exactly 1 vuln:
  `oauthlib 3.3.1 → PYSEC-2026-4114 (fix 4.0.0)`, which is the documented accepted risk
- oauthlib justification → **pass** — confirmed `databricks-sql-connector` metadata
  requires `oauthlib<4.0.0,>=3.1.0`, so the `<4` cap in requirements.txt:26 is real and
  the accepted-risk entry is accurate
- `ci.yml` YAML parse (`yaml.safe_load`) → **pass** — valid; pip-audit exits non-zero on
  any non-ignored vuln, so the job would fail a build
- `grep -rn "import mlflow\|from mlflow"` → ml/registry.py, ml/run_ablation.py (mlflow kept correctly)
- OSV query API version bisection → **fail** — four floors permit vulnerable versions (blocking 1-5)
- `python3 -m pytest -q tests/api --timeout 120` → **207 passed, 1 failed**:
  `tests/api/test_public_demo_security.py:337 test_rate_limit_61st_read_gives_429`
  (`assert 200 == 429`). Not in the security-deps diff; flagging for visibility only.

## Verdict
The Render lockfile and CI wiring are correct and `pip-audit` is green on the audited
files, but the **lower bounds for langchain-core, langchain-community, langsmith, and
requests do not actually exclude the Aikido PR #29 CVEs** they claim to fix. Raise the
four floors to `>=1.2.22` / `>=0.3.27` / `>=0.8.18` / `>=2.33.0` (respectively) and fix
the SECURITY.md table, then re-submit.
===VERDICT END===
