# REVIEW: baseline-signals PIT labels + purged split (reviewer: Codex)

Fixes items 2+3 of .agents/reviewer/VERDICT-post-submission-agy.md (label overlap/overnight; train/test boundary leak).
Commits 41b2455 (MiMo + Claude tiny fix: US/Eastern same-day), f013fe2 (round 2). Files: ml/baseline_labels.py,
tests/ml/test_baseline_labels.py, scripts/publish_baseline_signals.py. DeepSeek APPROVED round 2 (.agents/deepseek/VERDICT-signals-pit-r2.md;
3 named mutations each fail). Run `python3 -m pytest tests/ml -q` yourself; mutation proofs only in /tmp copies made with
`git archive HEAD | tar -x -C /tmp/<dir>`. Judge: is the label now strictly forward and non-overlapping; can any training row's label be
observed after the cut; is the scoring refit free of future labels; does the script still match its docstring. Do not run the script
(it talks to Databricks). Print the verdict to stdout between ===VERDICT START=== / ===VERDICT END=== with "Status: APPROVED" or
"Status: CHANGES_REQUESTED" and file:line. Do not edit files.
