===VERDICT START===

# VERDICT: corporate-actions

Status: CHANGES_REQUESTED

DeepSeek prerequisite: round 8 is APPROVED.

## Blocking findings

1. Massive-only job and runbook wiring still select yfinance.

   - [resources/jobs.yml:27](/home/jianj/code/qp1-corpact/resources/jobs.yml:27) passes `source: "yfinance"`, while [refresh_bronze_corporate_actions.py:87](/home/jianj/code/qp1-corpact/notebooks/refresh_bronze_corporate_actions.py:87) accepts only `massive`.
   - Reproducing the notebook task parameters raises `ValueError: source must be one of {'massive'}, got 'yfinance'` before Spark or ingestion starts.
   - The copy/paste commands at [CORPORATE_ACTIONS_RUNBOOK.md:44](/home/jianj/code/qp1-corpact/docs/CORPORATE_ACTIONS_RUNBOOK.md:44), lines 59, 66, and 78 have the same defect; the dry-run command exits 1.

2. Successful symbols are checkpointed before Bronze is written.

   [refresh_bronze_corporate_actions.py:417](/home/jianj/code/qp1-corpact/notebooks/refresh_bronze_corporate_actions.py:417) records `SUCCESS` inside the fetch loop, but the batch append does not occur until [line 438](/home/jianj/code/qp1-corpact/notebooks/refresh_bronze_corporate_actions.py:438). If execution stops between those points, resuming the same run ID loads that premature checkpoint and skips the symbol at lines 379–381, permanently omitting its rows. `SUCCESS` needs to follow append and post-append key verification.

3. Empty Massive responses bypass the configured rate limit.

   The overwhelmingly common no-split path executes `continue` at [refresh_bronze_corporate_actions.py:397](/home/jianj/code/qp1-corpact/notebooks/refresh_bronze_corporate_actions.py:397), skipping the only per-symbol sleep at line 430. The adapter stores `_delay` at [corporate_actions.py:143](/home/jianj/code/qp1-corpact/etl/corporate_actions.py:143) but never uses it. A 557-symbol run can therefore send consecutive empty-result requests without the promised minimum delay.

## Verification

- Required suite: `329 passed, 20 skipped, 0 failed` in 305.95 seconds.
- Adjustment direction, cumulative/reverse splits, volume inversion, Massive-only source filtering, break masking, PIT timestamps, explicit MERGE columns, and API-key redaction otherwise passed.
- Prior Codex findings concerning explicit Silver inserts and notebook `dbutils`/argv handling are resolved.

## Independent mutations

1. Reversed `s.ex_date > d.event_date` to `<`: `8 failed, 66 passed`.
2. Disabled Massive API-key redaction: `5 failed, 1 passed, 71 deselected`.
3. Changed split availability from 09:30 to 08:30 New York: `1 failed, 76 deselected`.

All mutations were confined to `/tmp`.

Repository status remained clean; no repository files were modified.

===VERDICT END===
