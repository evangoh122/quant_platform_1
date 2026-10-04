# REVIEW: corporate actions lane, Massive-only (reviewer: Codex gpt-5.6-sol)

Independent REVIEWER after DeepSeek approved round 8 (.agents/deepseek/VERDICT-corporate-actions-round8.md). Do NOT edit repo files; no network,
no secrets; mutation proofs in /tmp copies. Print verdict between ===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or
"Status: CHANGES_REQUESTED", numbered findings with file:line, counts, mutation results. Your earlier review: .agents/codex/VERDICT-*corp* (check resolved).

Owner decision: Massive ONLY — splits from the Massive REST API (/v3/reference/splits, apiKey = the S3 secret key, which works) into
bronze_corporate_actions, applied in silver_ohlcv_day_adjusted. Live facts: bronze_ohlcv_day is UNADJUSTED (AMZN 2022-06-06 shows −95%);
Massive returned AMZN 2022-06-06 1→20, GOOGL 2022-07-18 1→20, TSLA 2022-08-25 1→3 / 2020-08-31 1→5, NVDA 2024-06-10 1→10 / 2021-07-20 1→4,
SQQQ reverse 5→1 ×8, META none (its 2022 jump is ticker reuse). Next step after merge: a live run over 557 symbols, then PR #16 (residual
reversion) is rerun on silver_ohlcv_day_adjusted.
Scope: branch slice/corporate-actions vs origin/main.
Review for:
1. Adjustment math: back-adjustment direction (prices before ex_date divided by cumulative ratio, volume multiplied), cumulative product
   across multiple splits (TSLA 5 then 3 → 15 before 2020-08-31), reverse splits, PIT (split availability 09:30 NY on ex_date; bar
   availability 16:30 NY) — can any adjusted value use a split that wasn't known at the bar's availability time? (Back-adjustment inherently
   rewrites history; check it is documented and that consumers use returns.)
2. Ticker reuse / delisting: META 2022 jump and similar — flagged by the price-jump breaks, not "fixed" by a bogus split?
3. Idempotency: rerunning the bronze refresh and silver MERGE doesn't duplicate or double-apply.
4. Secrets: API key never logged/persisted (bronze rows, checkpoints, errors).
5. Notebook/job wiring: dbutils widgets, jobs.yml notebook_task, secret scope evangoh_capstone / massive_s3_secret_key.
6. Run 3 mutations of your own.
Run: python3 -m pytest -q tests/bronze tests/silver tests/test_security.py
