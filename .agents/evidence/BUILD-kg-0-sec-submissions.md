# Evidence — BUILD-kg-0-sec-submissions (KG-0)

Branch: `feat/kg-0-sec-submissions`
Worktree: `/home/jianj/code/wt-kg-0`
Base tree: `0dc5b1c3e4598a6ea2c3b22f28cac7125da4b123` (branch point; no unrelated
changes were present)
Date: 2026-10-22
Commit: one commit, `feat(sec): SEC submissions ingestion for registrant names,
former names, SIC and tickers (KG-0)`. The exact commit SHA is the one in the
terminal `BUILD DONE` line; this evidence file is part of that same commit.

## 1. Deliverables

| # | File | Change |
|---|---|---|
| 1 | `pipelines/ingest_sec_submissions.py` | new — job entry: reads `gold_sec_coverage.cik`, fetches `data.sec.gov/submissions/CIK##########.json`, writes `bronze_sec_submissions`; `--dry-run` default, `--live` opt-in |
| 2 | `sec_kg/submissions.py` | new — pure parser (no Spark/network) for the registrant record and former-name intervals |
| 3 | `silver/09_silver_sec_registrant.sql` | new — `silver_sec_registrant` (one row per `(cik, payload_sha256)`) + exploded `silver_sec_registrant_former_names` |
| 3b | `pipelines/run_silver_gold.py` | registered `("silver_sec_registrant", "silver/09_silver_sec_registrant.sql", "sql")` |
| 4 | `resources/jobs.yml` | new `sec_submissions_ingest` job: no schedule, `max_concurrent_runs: 1`, serverless task |
| 5 | `docs/DATA_SCHEMAS.md` | sections for `bronze_sec_submissions`, `silver_sec_registrant`, `silver_sec_registrant_former_names` |
| 6 | `tests/fixtures/sec_submissions/*.json` | 3 recorded real-shaped payloads: former names, multi-ticker share class, no tickers |
| 7 | `tests/rag/test_sec_submissions_parser.py` | 16 parser tests |
| 8 | `tests/bronze/test_sec_submissions_ingest.py` | 32 ingestion / rate-limit / idempotency / SQL / job tests |

No pandas, DuckDB, pyspark or network is imported by the new production code at
module scope (`spark` is imported lazily inside the writer/reader, exactly like
`pipelines/ingest_sec_companyfacts.py`).

## 2. Implemented contracts

### Bronze `bronze_sec_submissions` (append-only)

Columns, in order: `cik STRING NOT NULL`, `payload STRING` (nullable),
`payload_sha256 STRING NOT NULL`, `http_status INT NOT NULL`,
`fetched_at TIMESTAMP NOT NULL`, `ingest_run_id STRING NOT NULL`.

* `payload` is the raw JSON text exactly as fetched; `payload_sha256` is
  `sha256(payload.encode("utf-8"))`, so the key identifies the exact stored
  bytes.
* Idempotency: `MERGE ... ON t.cik = s.cik AND t.payload_sha256 = s.payload_sha256
  WHEN NOT MATCHED THEN INSERT *` — no update/delete branch, so the table stays
  append-only and reruns of an unchanged payload insert nothing.
* 404 is a **recorded miss**, not a failure: `http_status = 404`,
  `payload = NULL`, `payload_sha256 = MISS_PAYLOAD_SHA256 =
  sha256("sec-submissions-missing")`. Repeated 404s collapse under the same
  key; a later real payload has a different SHA and becomes a new observation.
* Other non-200 outcomes (after the shared client's retry/backoff loop) are
  reported in `errors` and counted in `ciks_failed`; nothing is written.
* A successful payload whose embedded CIK differs from the requested CIK is
  rejected (never filed under the wrong key).
* `--dry-run` returns before resolving the User-Agent, constructing an HTTP
  client, or touching the writer. `--live` is required for any HTTP request or
  write; a live run without a writer raises.
* Fair access: reuses `SecClient` (User-Agent from
  `SEC_EDGAR_USER_AGENT` env / Databricks secret scope+key; retries with
  backoff; 429/503 Retry-After cooldown). The rate limiter is constructed with
  `clamp_requests_per_second(...)`, hard-capped at
  `MAX_SUBMISSIONS_RPS = 8` (a configured 12, 10, 0 or garbage value cannot
  exceed 8 or disable the limiter).

### Parser `sec_kg/submissions.py`

`parse_registrant(payload, observed_at)` → `RegistrantRecord` with
`cik10`, `name`, `former_names[{name, from_date, to_date}]`, `sic`,
`sic_description`, `tickers`, `exchanges`, `state_of_incorporation`,
`fiscal_year_end`, `entity_type`, `observed_at`. `from`/`to` are preserved
verbatim (inclusive; no `+/- 1 day` conversion). Missing list keys become `[]`;
missing scalars become `None`; a missing/non-numeric CIK raises `ValueError`.
`ein` is deliberately absent (design §A drops it). `payload_sha256` and
`MISS_PAYLOAD_SHA256` are pure helpers.

### Silver

`silver_sec_registrant`: 13 columns (`cik10`, `payload_sha256`, `name`, `sic`,
`sic_description`, `tickers ARRAY<STRING>`, `exchanges ARRAY<STRING>`,
`state_of_incorporation`, `fiscal_year_end`, `entity_type`, `observed_at`,
`ingest_run_id`, `processed_ts`). `QUALIFY ROW_NUMBER() OVER (PARTITION BY cik,
payload_sha256 ...)` enforces one row per key; 404 misses are excluded by
`WHERE payload IS NOT NULL`.

`silver_sec_registrant_former_names`: 8 columns, `LATERAL VIEW explode(...)` of
`formerNames`, `CAST(fn.\`from\` AS DATE)` / `CAST(fn.\`to\` AS DATE)` with no
date arithmetic.

## 3. Acceptance — exact CI parity

CI command: `pytest -q -m "not spark and not lakebase and not databricks"`.
Two runs were executed: (a) in the uv venv, which has **no pyspark installed**
(confirmed `ModuleNotFoundError: No module named 'pyspark'`), and (b) the same
command with a pyspark-blocking stub first on `PYTHONPATH`
(`/tmp/opencode/kg0-sec-proofs/pyspark-stub/pyspark.py`, temp dir outside the
repo, raises `ModuleNotFoundError("No module named 'pyspark'")`).

Environment: `uv venv` → `/tmp/opencode/kg0-sec-proofs/venv`, Python 3.12.13,
pytest 9.1.1. Installed exactly as CI does: `ibapi` lines dropped from
`requirements.txt` and `requirements-dev.txt`, the `-r requirements.txt` include
dropped from the dev file, then `pytest pytest-asyncio pytest-timeout httpx
numpy pandas polars duckdb scikit-learn pyyaml`.

Environment note (not a code issue): the uv-managed CPython in this WSL image
does not see the legacy `US/Eastern` key through pandas' tzdata lookup, which
made all 29 `tests/ml/test_baseline_labels.py` tests fail with
`ZoneInfoNotFoundError: 'No time zone found with key US/Eastern'`. Installing
`tzdata==2026.5` into the venv fixed them (29 passed); the system interpreter,
like the CI runner's OS tzdata, passes without it. All acceptance numbers below
are after that environment fix.

### Targeted

```
$ venv/bin/python -m pytest -q tests/rag/test_sec_submissions_parser.py \
      tests/bronze/test_sec_submissions_ingest.py
................................                                 [100%]
48 passed in 12.19s
```

```
$ PYTHONPATH=<pyspark-stub> venv/bin/python -m pytest -q \
      tests/rag/test_sec_submissions_parser.py tests/bronze/test_sec_submissions_ingest.py
................................                                 [100%]
48 passed in 10.87s
```

`tests/rag/test_sec_knowledge_graph.py` (must stay green): **172 passed**.

Combined targeted run (new 48 + SEC KG 172) in both modes: **220 passed**
(33.48s normal, 32.65s pyspark-blocked).

### Full suite

```
$ venv/bin/python -m pytest -q -m "not spark and not lakebase and not databricks"
2985 passed, 70 skipped, 24 deselected, 46 warnings in 422.22s (0:07:02)
```

```
$ PYTHONPATH=<pyspark-stub> venv/bin/python -m pytest -q \
      -m "not spark and not lakebase and not databricks"
2985 passed, 70 skipped, 24 deselected, 46 warnings in 393.89s (0:06:33)
```

An earlier pyspark-blocked attempt (before the re-run above) had one failure in
`tests/api/test_public_demo_security.py::test_cf_connecting_ip_mode_61st_gives_429`
(1 failed, 2984 passed). It is unrelated to this diff (no touched file is on
that path) and passed 3/3 in isolation plus 158/158 as a whole file, with and
without the stub; the immediately repeated full run was green.

## 4. Old-behavior and mutation proofs

Isolated `git archive HEAD` copies under `/tmp/opencode/kg0-sec-proofs/`
(`base-old`; `new-state`; two mutated copies). The worktree was never copied
recursively.

### Control

`new-state` (archive + the changed/new files): **48 passed**.

### Old behavior (committed tree + only the new tests/fixtures)

```
E   ModuleNotFoundError: No module named 'sec_kg.submissions'
E   ModuleNotFoundError: No module named 'pipelines.ingest_sec_submissions'
2 errors during collection
```
i.e. the new tests are red before the implementation.

### Mutation A — parser drops `formerNames`

`raw_former = payload.get("formerNames")` → `raw_former = None`:

```
FAILED tests/rag/test_sec_submissions_parser.py::test_former_names_are_parsed_in_order_with_inclusive_dates
E   AssertionError: assert [] == [FormerName(...), FormerName(...)]
1 failed, 15 passed
```

### Mutation B — idempotency ignores `payload_sha256`

MERGE `ON t.cik = s.cik AND t.payload_sha256 = s.payload_sha256` →
`ON t.cik = s.cik`:

```
FAILED tests/bronze/test_sec_submissions_ingest.py::test_merge_matches_on_both_key_columns
E   AssertionError: assert 'ON t.cik = s.cik AND t.payload_sha256 = s.payload_sha256' in
    '... ON t.cik = s.cik ...'
1 failed
```

The idempotency test also proves the positive direction: same payload twice →
one stored row; same CIK with changed payload (different SHA) → a second row
(`test_idempotency_key_is_cik_and_payload_sha256`).

## 5. Other static checks

* `python3 -m py_compile` on all new/modified Python: exit 0.
* `git diff --check`: exit 0 (no whitespace errors, no blank line at EOF).
* LF verified for every new/modified file (`grep $'\r'` → no matches).
* No hard-coded contact email in the production module; the User-Agent is
  resolved from env/secret and a test asserts the source contains no address.
  The only synthetic address in the tree is the test fixture UA.
* No hard-coded catalog/schema in the silver SQL; `{catalog}` / `{schema}`
  placeholders only.
* Job YAML parses; the job has no `schedule` key and `max_concurrent_runs: 1`.
* No live SEC request, no Databricks query, no shared-table write was performed.
  The job definition deliberately stays dry-run; a live run adds `--live`
  explicitly.

## 6. Host boundary

Repository commands (checks, tests, proofs, commit) were run through LF scripts
under `.agents/run-kg0-sec-<n>.sh`, each launched foreground exactly once as
`wsl.exe -d Ubuntu -- bash <absolute path>` with a log beside it. One initial
read-only `git status`/log inspection used an inline `bash -c` before the script
harness was in place, and one launch referenced a script path before it was
written (bash exit 127; no command inside it executed, no repo mutation). Both
are process-only; every check was re-run afterwards through the sanctioned
scripts.

## 7. Non-goals (verified)

No push, no PR, no merge, no deploy, no job run, no live ingestion, no shared
table rebuild, no schedule change, no requirement/dependency changes, no
`databricks.yml` change, no secret access. Only the files listed in §1 were
changed.
