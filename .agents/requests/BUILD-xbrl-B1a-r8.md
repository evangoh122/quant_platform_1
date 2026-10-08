# BUILD-xbrl-B1a round 8 — two more bugs from Claude's live run

You are MiMo. Branch `feat/xbrl-fundamentals` (stay on it). LF endings, never touch `.agents/dispatch.sh`, no Databricks.
Shell rule: if quoting is hard, write to `/home/jianj/code/qp1-xbrl/.agentlogs/<name>.sh` and run `wsl -d Ubuntu -- bash /home/jianj/code/qp1-xbrl/.agentlogs/<name>.sh`.
No .ps1/.bat, no PowerShell wrappers, nothing in C:\temp. Stage only files you changed (no `git add -A`). COMMIT; verdict `.agents/mimo/VERDICT-xbrl-B1a-r8.md`.
Live results (after round 7): NVDA+AAPL → mapped=2, fetched=2, facts=52,416; XOM → 20,909 facts from both CIKs. Remaining bugs:
1. Manifest `ALTER TABLE … ADD COLUMNS (http_status INT)` runs every time → `[FIELD_ALREADY_EXISTS]` logged as ERROR on every run once the column
   exists. Check the table's columns first (DESCRIBE / spark.table(t).columns) and only ALTER when missing. Test with a fake spark: column present →
   no ALTER issued; column missing → exactly one ALTER.
2. Test pollution of the real fallback cache: a test wrote a 1-entry company_tickers.json (only AAPL) into the production fallback path
   /tmp/sec_cache at 01:56; the next live run trusted it and reported "No CIK found for NVDA". (a) Every test that touches the CIK cache must use
   pytest's tmp_path / monkeypatch the cache dir — grep the tests for "sec_cache" and "/tmp"; add a conftest autouse fixture that points the cache
   dir at tmp_path so no test can write the real path. (b) Treat a company_tickers cache with fewer than 1,000 entries as invalid (re-fetch) — the
   real file has ~10,400. Tests for both (fixture cache with 1 entry → re-fetch is attempted).
