# VERDICT: signals-pit-r3 — MiMo
**Status:** APPROVED
**Round:** 3

## Blocking findings
- (none)

## Non-blocking notes
- `forward_labels` line 82 emits FutureWarning on `label_ts` dtype mismatch (pre-existing, not introduced by this change). Not blocking.

## Checks run
- `python3 -m pytest tests/ml -q` → 51 passed in 132.78s
- Mutation check: `refit_rows` returns 4 of 17 labelled rows with staggered A@10:00 / B@15:00 fixture → confirms the test FAILS if the function returns all of `lab`

## Changes made
1. `ml/baseline_labels.py`: added `refit_rows(lab, scoring_ts)` — returns `lab[lab.label_ts <= scoring_ts.min()]` so no scored row sees a label observed after its own time.
2. `scripts/publish_baseline_signals.py`: moved `latest` computation before refit, replaced `m.fit(...lab...)` with `m.fit(...refit_rows(lab, latest.prediction_ts)...)`, prints cutoff and row count, updated docstring.
3. `tests/ml/test_baseline_labels.py`: added `test_refit_rows_staggered_symbols` — symbol A scored at 10:00, symbol B scored at 15:00, B label at 12:00 excluded from refit set; fails if `refit_rows` returns all of `lab`.