# BUILD: signals PIT round 3 (Codex sol CHANGES_REQUESTED)

You are MiMo. Branch `review/post-submission` (stay on it). Read `.agents/codex/VERDICT-signals-pit.md`. LF endings, never touch
`.agents/dispatch.sh`, no Databricks. COMMIT your work.

Finding: scripts/publish_baseline_signals.py:56 refits on ALL labelled rows, but each symbol's latest snapshot is scored at its own
timestamp; a symbol scored earlier can use other symbols' labels observed later.
1. Add `refit_rows(lab, scoring_ts)` to ml/baseline_labels.py: returns labelled rows with `label_ts <= scoring_ts.min()` (the earliest
   scored snapshot), so no scored row sees a label observed after its own time. Use it in the script: compute `latest` (the scoring rows)
   BEFORE the refit, then refit on `refit_rows(lab, latest.prediction_ts)`. Print the refit cutoff and row count. Fix the comments/docstring
   at the refit to match the code (remove the stale NOTE).
2. Test (staggered symbols): symbol A's latest snapshot at 10:00, symbol B's at 15:00, with B labels observed at 12:00 → the 12:00-label row
   is excluded from the refit set. Must FAIL if `refit_rows` returns all of `lab` (paste FAILED output in the verdict).
Acceptance: `python3 -m pytest tests/ml -q` green. Verdict `.agents/mimo/VERDICT-signals-pit-r3.md`.
