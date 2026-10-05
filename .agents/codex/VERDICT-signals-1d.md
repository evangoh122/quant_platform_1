# Codex gpt-5.6-sol review — signals 1d (saved by Claude)

===VERDICT START===
# VERDICT: signals-1d — Codex

Status: CHANGES_REQUESTED

## Blocking findings

1. `scripts/publish_baseline_signals.py:70-71` does not print the number of labelled rows. It prints total rows before constructing `lab`, despite the build specification explicitly requiring “rows labelled.” Add `len(lab)` to the diagnostics after `lab` is created.

2. `scripts/publish_baseline_signals.py:24` states that the latest snapshot “is never labelled.” This is not guaranteed: `daily_close_labels` will label it whenever the independently queried close data contains a subsequent trading-day close. Reword this to say that scoring does not use the latest snapshot’s label.

## Validation

- DeepSeek prerequisite: APPROVED.
- `python3 -m pytest tests/ml -q`: 64 passed, 78 warnings.
- Isolated mutation proofs using `git archive HEAD` under `/tmp`:
  - Trade-date look-ahead mutation: 3 failed.
  - Removed maximum-gap guard: 2 failed.
  - N+1 labeling mutation: 7 failed, including the named mutation test.
- `ml/baseline_labels.py:150-159`: D selection correctly enforces `close_ts <= prediction_ts`.
- `ml/baseline_labels.py:208-210,238-239`: purged split and refit correctly use `label_ts` cutoffs.
- `scripts/publish_baseline_signals.py:53-64`: SQL interpolation is acceptable under the stated threat model because symbols originate from the warehouse, not user input. Parameterization or a join would still be safer.
- The all-UP output is consistent with a weak model whose probabilities are all slightly above 0.5; it is not evidence of leakage by itself.
- `ml/baseline_labels.py:121,183`: timezone-aware values assigned into a timezone-naive column produce a pandas `FutureWarning`; non-blocking today but should be corrected before a future pandas upgrade.

No repository files were edited.
===VERDICT END===
