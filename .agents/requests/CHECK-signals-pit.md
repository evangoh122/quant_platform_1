# CHECK: baseline-signals PIT labels + purged split (checker: DeepSeek)

Read-only on the worktree. Mutation copies via `git archive HEAD | tar -x -C /tmp/<dir>`; never run git inside a copy.
Write .agents/deepseek/VERDICT-signals-pit.md between ===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or
"Status: CHANGES_REQUESTED", file:line for every finding.

Spec: .agents/requests/BUILD-signals-pit.md. Findings being fixed: items 2+3 of .agents/reviewer/VERDICT-post-submission-agy.md.
Commit 41b2455: ml/baseline_labels.py, tests/ml/test_baseline_labels.py, scripts/publish_baseline_signals.py.
MiMo built it (its verdict .agents/mimo/VERDICT-signals-pit.md is a self-report, not evidence). Claude tiny fix: the same-day check
now compares US/Eastern dates (`_eastern_date`); MiMo's version compared the UTC wall date for UTC input (new test
`test_same_day_uses_us_eastern_date_for_utc_input` fails on it — Claude verified). Claude: tests/ml → 48 passed.

Check:
1. Run the spec's three named mutations yourself (plain shift(-1); drop the same-day check; split train on prediction_ts) — each must fail a test.
2. MiMo's tests `test_plain_shift_labels_5min_gap` / `test_prediction_ts_split_leaks_label` — do they test the shipped code or only
   re-implement the old logic inline (vacuous)? Vacuous "mutation tests" are a finding.
3. Edge cases: duplicate prediction_ts for a symbol; unsorted input (the function says input must be sorted — is that enforced or tested?);
   tz-naive input; DST transition days.
4. The script: is the final refit still free of labels observed after the scoring snapshot? Is the printed `cut` the same cut used by purged_split?
5. `python3 -m pytest tests/ml -q` and report.
