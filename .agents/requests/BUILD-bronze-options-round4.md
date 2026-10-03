# BUILD-REQUEST: bronze-options — ROUND 4 (stage files without a local /Volumes mount)

**Branch:** `slice/bronze-options` · **Builder:** MiMo · **Checkers:** Claude, then DeepSeek

## Measured by the coordinator, running your round-3 code from WSL (where credentials work)
```
[err] 2026-09-26 probe: ClientError                       <- Saturday
[err] 2026-09-28: PermissionError: [Errno 13] Permission denied: '/Volumes'
... every trading day 2026-09-08 .. 2026-10-01 fails the same way
[gap] 2026-10-02, 2026-10-03 (403 / not entitled)          <- not yet published; fine
daily: appended=0 candidate=0 entitlement_gap=2 failed=27
```
S3 listing/credentials now work. Two code defects remain:

1. **Staging writes to `/Volumes/...` as a local path.** That path is a FUSE mount that exists only
   inside a Databricks runtime. When not running inside Databricks, upload the downloaded file to the
   UC Volume with the SDK Files API (`databricks.sdk.WorkspaceClient().files.upload(path, fileobj,
   overwrite=True)`), then read it server-side with `spark.read` from the Volume path. Keep the
   local-filesystem path only when running inside Databricks (detect it, e.g. `DATABRICKS_RUNTIME_VERSION`).
   Clean up staged files after a successful append.
2. **Weekends/holidays are counted as failures.** Iterate NYSE trading days only (weekday + US
   market holiday calendar), so `failed` counts real failures. A missing file for a real trading day
   is still a failure.

Also: `_detect_s3` swallows every exception and reports "403", which hid the real cause in
rounds 1–2. Log the exception type and message (never secrets) instead.

Do not run `--write`. The coordinator will run the dry-run and write from WSL.
Edit only `notebooks/refresh_bronze_options.py` and `tests/bronze/test_refresh_bronze_options.py`.
Add tests: staging uses the Files API when not inside Databricks (mock the client); a Saturday is
not iterated; a trading day with a missing file counts as failed. LF line endings.
**Commit your work.** Write `.agents/mimo/VERDICT-bronze-options-round4.md`.
