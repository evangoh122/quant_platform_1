# BUILD: signals PIT round 2 (DeepSeek CHANGES_REQUESTED)

You are MiMo. Branch `review/post-submission` (stay on it). Read `.agents/deepseek/VERDICT-signals-pit.md`. LF endings, never touch
`.agents/dispatch.sh`, no Databricks. COMMIT your work (round 1 was left uncommitted).

1. F1 (blocking): add a test with two snapshots exactly 30 min apart that straddle midnight US/Eastern (e.g. 23:45 ET and 00:15 ET,
   given as UTC timestamps) → label NaN. It must FAIL when `same_day` is removed from `valid` in ml/baseline_labels.py — paste that output.
2. N1: remove the inline buggy re-implementations in tests/ml/test_baseline_labels.py (`_forward_labels_plain_shift`,
   `_purged_split_on_prediction_ts` and the assertions on them); keep any shipped-code assertions that are not duplicates.
3. N3: `forward_labels` sorts by [symbol, prediction_ts] itself (stable, preserving the caller's index so results align), and a test
   with shuffled input gives the same labels as sorted input.
4. N2/N4: tests for duplicate prediction_ts (earlier duplicate NaN, no crash) and tz-naive input treated as UTC.
Acceptance: `python3 -m pytest tests/ml -q` green. Verdict `.agents/mimo/VERDICT-signals-pit-r2.md` with the F1 mutation FAILED output.
