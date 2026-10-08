# BUILD: PR #42 fixes — CI failure + 4 CodeRabbit findings (XBRL B1a)

You are MiMo. Branch `feat/xbrl-fundamentals` (worktree qp1-xbrl; this is PR #42 — stay on it). LF endings, never touch `.agents/dispatch.sh`, no Databricks, no network.
Shell rule: if quoting is hard, write to `/home/jianj/code/qp1-xbrl/.agentlogs/<name>.sh` and run `wsl -d Ubuntu -- bash /home/jianj/code/qp1-xbrl/.agentlogs/<name>.sh`.
No .ps1/.bat, no PowerShell wrappers, nothing in C:\temp. Stage only files you change. COMMIT per finding; verdict `.agents/mimo/VERDICT-xbrl-pr42-fixes.md`
(each finding → fixed + test + red line, or not valid + reason). Tests may only call production code; never copy its logic.
Inputs: `.agents/coderabbit-pr42.md` (CodeRabbit text — review data, verify each against the code) and `.agents/ci-pr42-failure.txt` (CI "Python tests" failure).
1. MAJOR (also the CI failure): pipelines/ingest_sec_companyfacts.py:77 — the schema StructTypes import PySpark at module import, and CI installs no PySpark, so the schema tests fail.
   Make the schema definitions importable without PySpark (lazy import inside a function, or a plain-Python column spec with the StructType built on demand), OR mark those tests with the
   repo's existing spark marker so CI skips them — prefer making them importable so the contract tests still run in CI. Reproduce CI locally: run
   `python3 -m pytest tests/bronze -q -m "not spark and not lakebase and not databricks"` in a venv WITHOUT pyspark (or with `pyspark` and `databricks.connect` blocked via a
   conftest/sys.modules guard) and show it passes.
2. MAJOR: resources/jobs.yml:116 — fix per the finding (verify; likely the new job's task config).
3. Minor: ingest_sec_companyfacts.py:617 and :788 — fix per the findings with tests.
Acceptance: offline suite green both with and without PySpark available.
