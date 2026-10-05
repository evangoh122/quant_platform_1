# CHECK: baseline signals 1-day horizon (checker: DeepSeek)

Read-only; mutations only in `git archive HEAD | tar -x -C /tmp/<dir>` copies. Write .agents/deepseek/VERDICT-signals-1d.md between
===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED", file:line.
Spec: .agents/requests/BUILD-signals-1d.md (owner chose a 1-day horizon). Commits 9488d19, c38bfd0, 7b2564a. MiMo's verdict is a self-report.
Claude: tests/ml → 64 passed. Claude read-only live run (no --write): 40,943/40,983 rows labelled; holdout AUC 0.533 (train 32,753 / test 8,189,
cutoff 2025-09-26); refit cutoff 2026-09-02 21:20 UTC, 40,943 rows; 35 signals, ALL UP (p 0.518–0.542). pandas FutureWarning at
ml/baseline_labels.py (`out.loc[..., "label_ts"] = label_ts_vals`: tz-aware values into a tz-naive NaT column).
1. Run the three named mutations against the SHIPPED `daily_close_labels` (close_ts<=prediction_ts → trade_date<=prediction_ts.date();
   drop the max_gap check; label from N+1) — each must fail a test. MiMo's "D6 mutation tests": if they only re-implement buggy logic inline,
   that is a blocking finding (same as signals-pit round 1 N1).
2. Look-ahead: can close_D ever be a close whose close_ts > prediction_ts? Check the D selection with ET dates around midnight UTC and DST.
3. The tz warning: label_ts must be created tz-aware (UTC) so no dtype coercion happens; is it a correctness risk today?
4. The script's warehouse SQL: constant table names, no user values, regular-session filter correct (`is_regular_session = true` and minute
   bars; the last regular-session minute ≈ 19:59/20:59 UTC depending on DST).
5. All-UP output: is that a bug (e.g. constant features, label imbalance, leakage) or the honest result of a weak model? Inspect label balance
   in the fixture logic and the script's printed diagnostics; report, do not over-claim.
