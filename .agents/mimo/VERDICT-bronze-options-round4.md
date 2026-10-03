# VERDICT: bronze-options-round4 — MiMo
**Status:** APPROVED
**Round:** 4

## Changes made
- `_detect_s3` (line 397): logs `{type(exc).__name__}: {exc}` on each failed probe instead of bare `continue`.
- `_in_databricks()` helper (line 497): checks `DATABRICKS_RUNTIME_VERSION` env var; replaces unreliable `globals().get("dbutils")`.
- `_stage_file` (line 502): when not in Databricks, downloads to local tmpdir then uploads via `sdk_client.files.upload(path, fh, overwrite=True)` (BinaryIO, not the non-existent `upload_from`). Local file removed after upload.
- `_clear_staged` (line 530): uses `_in_databricks()` for local FS vs SDK `files.delete`.
- `trading_days()` (line 162): iterates NYSE trading days only (weekdays minus 2025-2026 US holidays). `_run_daily` now calls `trading_days()` instead of `date_window()`, so `failed` counts real failures — weekends/holidays are never iterated.
- Added `_NYSE_HOLIDAYS` frozenset covering 2025-2026 NYSE closures.

## Blocking findings
- None.

## Non-blocking notes
- The NYSE holiday list is static (2025-2026). Future years will need extension or a library like `exchange_calendars`.
- `_stage_file` outside Databricks still uses `sdk_client.files.create_directory` which may raise on existing dirs; the bare `except Exception: pass` is intentional idempotency handling.

## Checks run
- `python3 -m pytest tests/bronze/test_refresh_bronze_options.py -v` → 30/30 passed
- CRLF check: 0 carriage returns in both files (LF confirmed)
- No lint/typecheck config found in repo (pyproject.toml, ruff.toml, .flake8 all absent)