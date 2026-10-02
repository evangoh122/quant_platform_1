# BUILD-REQUEST: ml-hardening — ROUND 6 (tests only)

**Branch:** `slice/ml-hardening` · **Builder:** MiMo · **Validators:** Claude, then Codex
Read `.agents/codex/VERDICT-ml-hardening-round5.md`.

**The production fixes from round 5 are correct — do not change them.** Codex verified
per-symbol beta shift, fold-local classification, and insufficient-coverage handling.
The defect is that the three regression tests do not test the defects.

## Rewrite these three tests

Each must **fail against the pre-fix commit `147c696` for the intended reason** — an
assertion about the behaviour — and pass on HEAD. Failing because a helper's return
signature changed does **not** count. If you need a stable call shape, call the public
entry points or write a small adapter that works on both revisions.

1. **Beta look-ahead** (`test_market_beta_shifted_one_bar_no_lookahead`). Build a matrix,
   then change **only the return at bar t** (via the close at t) for one symbol and
   rebuild. Assert `market_beta` at t is **unchanged** and at t+1 **changes**. On
   `147c696` beta at t changes → test fails.
2. **Sparse feature** (`test_sparse_cross_sectional_feature_is_neutralised`). The fixture
   must reproduce the old bug: a feature that varies across symbols wherever observed but
   is all-NaN on **> 90%** of timestamps. Assert it is **not** classified market-wide and
   **is** residualised. On `147c696` it is classified market-wide → test fails.
3. **Fold-local classification** (`test_fold_local_classification_unchanged_by_future_data`).
   Drive the real training/ablation path, not the helper alone. Create `matrix_alt` that
   changes only rows **after** fold k's training window so the full-sample classification
   flips. Assert fold k's classification (and its training-row features) are identical
   between `matrix` and `matrix_alt`. On `147c696` it differs → test fails.

## Small cleanups Codex noted

- `ml/features.py:563`: the log says insufficient-coverage columns are "not neutralised",
  but they are residualised. Fix the message.
- `ml/train.py:280`: `X_full` is unused. Remove it.

## Proof required in your verdict

For each of the three tests, paste the output of running it against `147c696`
(use a scratch worktree: `git worktree add /tmp/<scratch> 147c696`, copy only the test
file in, run it, then remove the worktree) showing an **assertion** failure, and then
the passing run on HEAD.

Do not touch `silver/`, `gold/`, `agent/`, `db/`, `api/`, `conftest.py`, `pytest.ini`,
`requirements*.txt`. **Commit your work.** Write `.agents/mimo/VERDICT-ml-hardening-round6.md`.
