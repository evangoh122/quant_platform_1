# VERDICT: ml-hardening round 5 — Codex

CHANGES_REQUESTED

Production fixes appear correct, but the three claimed regression tests do not genuinely cover the prior defects:

- `test_market_beta_shifted_one_bar_no_lookahead` passes against `147c696`. It mutates `forward_return` after beta generation ([test_hardening.py:350](/home/jianj/code/qp1-ml/tests/ml/test_hardening.py:350)) and only checks the first beta is NaN ([test_hardening.py:359](/home/jianj/code/qp1-ml/tests/ml/test_hardening.py:359)); rolling `min_periods=5` already made that true before the shift.
- The sparse test fails against the old revision only because `_detect_market_wide_columns` previously returned one list while the test unpacks two values ([test_hardening.py:396](/home/jianj/code/qp1-ml/tests/ml/test_hardening.py:396)). Semantically, its two all-NaN timestamps produce only `2/3` constant timestamps, below the `0.9` threshold, so the old implementation would not misclassify this fixture.
- The fold-local test likewise fails against the old revision only from tuple unpacking. More importantly, the second classification still uses the original `train_rows_0`, not `matrix_alt` ([test_hardening.py:460](/home/jianj/code/qp1-ml/tests/ml/test_hardening.py:460)), so it compares identical inputs and does not exercise `run_ablation`.

Independent production-code findings:

- Beta shifting is correctly per symbol: each symbol is processed separately at [synthetic_data.py:182](/home/jianj/code/qp1-ml/ml/synthetic_data.py:182), with `shift(1)` applied inside that loop at [synthetic_data.py:193](/home/jianj/code/qp1-ml/ml/synthetic_data.py:193).
- Columns with no decidable timestamps are returned in `insufficient_coverage` and logged at warning level ([features.py:455](/home/jianj/code/qp1-ml/ml/features.py:455)). They are not market-wide and are consequently residualized. Note that the message saying “not neutralised” at [features.py:563](/home/jianj/code/qp1-ml/ml/features.py:563) contradicts the actual behavior.
- Fold classification uses only `matrix.iloc[train_idx]` ([train.py:263](/home/jianj/code/qp1-ml/ml/train.py:263)). Model fitting remains restricted to `train_idx` ([train.py:295](/home/jianj/code/qp1-ml/ml/train.py:295)).
- No new full-sample model fit was introduced. Purge/embargo and DSR implementations are unchanged in this diff. `X_full` at [train.py:280](/home/jianj/code/qp1-ml/ml/train.py:280) is unused dead code.
- Requested suite: `37 passed, 17 warnings`.

Required change: replace the three round-5 tests with behavioral tests that fail for the original implementation for the intended reason, not because of a changed helper return signature.

