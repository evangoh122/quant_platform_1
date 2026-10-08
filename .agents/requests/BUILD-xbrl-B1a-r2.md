# BUILD-xbrl-B1a round 2 (DeepSeek CHANGES_REQUESTED)

You are MiMo. Branch `feat/xbrl-fundamentals` (stay on it). Read `.agents/deepseek/VERDICT-xbrl-B1a.md`. LF endings, never touch
`.agents/dispatch.sh`, no Databricks, no network in tests. Run WSL commands directly (`wsl -d Ubuntu -- bash -lc '<cmd>'`); never wrap wsl.exe
in PowerShell and never write scripts to C:\temp. COMMIT per item and write the verdict.
1. Blocking: the append mode is untested. Test `SparkCompanyFactsWriter` (and the manifest writer) with a fake Spark/DataFrame that records
   `.write.mode(...)` and `.saveAsTable(...)`: assert mode "append" for both, and that no `overwrite`/`insertInto(..., overwrite=True)` is used.
   Paste FAILED output with `mode("append")` → `mode("overwrite")`.
2. Blocking: replace the no-op `test_same_payload_skipped_within_run` with a real test — inject a cik map / fake client so two identical
   payloads for the same CIK are fetched in one run; assert the second is NOT written (rows written once) and the manifest records it as
   skipped. Paste FAILED output with the skip logic removed.
3. Non-blocking (do it): bounded concurrency with a ThreadPoolExecutor (max_workers ≤ 4) sharing the process-wide limiter; manifest
   `attempt_count` = the real attempt count from SecClient for that CIK. Tests for both (fake client counting calls; ≤10 req/s still holds).
Acceptance: `python3 -m pytest tests/bronze/test_sec_companyfacts.py -q` and the offline suite green. Verdict `.agents/mimo/VERDICT-xbrl-B1a-r2.md`.
