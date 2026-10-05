# BUILD: baseline-signals point-in-time label fix (findings 2+3 of the agy post-submission review)

You are MiMo. Branch `review/post-submission` (worktree qp1-postrev). Commit on THIS branch only; no new branches.
Never touch `.agents/dispatch.sh`. LF endings. Do NOT run anything against Databricks (no `--write`, no WorkspaceClient).
Findings: `.agents/reviewer/VERDICT-post-submission-agy.md` (items 2 and 3). Script: `scripts/publish_baseline_signals.py`.

## Problem
- `return_30m` at snapshot s is the TRAILING 30-minute return ending at s. The label is
  `groupby(symbol).return_30m.shift(-1)` = the next snapshot's trailing return. If the next snapshot is less than 30 minutes
  later, that window overlaps data already known at s. If it is the next trading day, the label spans the overnight gap.
- Train/test split: training rows are selected by `prediction_ts <= cut`, but a training row's label is only known at the
  NEXT snapshot's time. The last training row per symbol has a label observed after `cut` (in the test period).

## Required changes
1. Move the labelling and the split into pure, importable functions, e.g. `ml/baseline_labels.py`:
   - `forward_labels(df, horizon=pd.Timedelta("30min"), tol=pd.Timedelta("1min"))` → adds `label` and `label_ts`.
     For each row, the label comes from the same symbol's next snapshot s' only if `horizon - tol <= s' - s <= horizon + tol`
     AND s and s' fall on the same US/Eastern trading date. Otherwise `label` is NaN. `label_ts = s'`.
   - `purged_split(lab, frac=0.8)` → (train, test). `cut` = the frac quantile of `prediction_ts`.
     Train = rows with `label_ts <= cut`; test = rows with `prediction_ts > cut`. No row whose label is observed after `cut` is in train.
   - Final refit for scoring: only rows with `label_ts <=` the scoring snapshot time (document this; the latest snapshot itself is never labelled).
2. The script imports these functions; there is no other behaviour change. Update the module docstring to describe the label correctly.
3. Tests in `tests/ml/test_baseline_labels.py` (they must fail on the current logic; show the red phase):
   - next snapshot exactly 30 min later on the same day → labelled from it;
   - next snapshot 5 min later → NaN (overlap);
   - next snapshot on the next trading day → NaN (overnight);
   - last snapshot of a symbol → NaN; symbols never mix;
   - purged split: a row with `prediction_ts <= cut` but `label_ts > cut` is NOT in train; no train `label_ts` > cut;
     train and test are disjoint.
   - Mutations to report with FAILED output: replace the gap check with plain `shift(-1)`; drop the same-day check;
     split train on `prediction_ts <= cut` instead of `label_ts`.

## Acceptance
`python -m pytest tests/ml -q` green and the full offline suite not regressed
(`python -m pytest -q -m "not spark and not lakebase and not databricks"`). Verdict: `.agents/mimo/VERDICT-signals-pit.md`.
