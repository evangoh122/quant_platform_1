# REVIEW: baseline signals — 1-trading-day horizon (reviewer: Codex)

Owner decision 2026-10-05: switch the baseline to a 1-day horizon (gold_model_features has one snapshot/day, so 30-min labels gave 0 rows).
Commits 9488d19 (`daily_close_labels`), c38bfd0 (script: daily closes from silver_ohlcv, horizon "1d", model_version
baseline-logreg-v1-1d-2026-10-05), 7b2564a (tests). Spec .agents/requests/BUILD-signals-1d.md. DeepSeek APPROVED
(.agents/deepseek/VERDICT-signals-1d.md; 3 named mutations fail; DST/midnight probe clean). Your earlier approvals:
.agents/codex/VERDICT-signals-pit*.md. Claude read-only live run: 40,943 rows labelled; holdout AUC 0.533; 35 signals all UP (p 0.52–0.54).
Run `python3 -m pytest tests/ml -q`; mutation proofs only in /tmp via `git archive HEAD | tar -x -C /tmp/<dir>`. Do not run the script.
Judge: PIT correctness of close_D/close_N selection, purged split + refit cutoff with label_ts = close_N time, SQL safety
(DeepSeek noted an f-string symbol list at scripts/publish_baseline_signals.py:53 — symbols come from the warehouse, not user input; decide),
and whether docstring/printed diagnostics describe the model honestly. Print the verdict between ===VERDICT START=== / ===VERDICT END===
with "Status: APPROVED" or "Status: CHANGES_REQUESTED" and file:line. Do not edit files.
