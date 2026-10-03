# VERDICT: ml-hardening commit 84b2458 (pandas 3 cast) — Codex
## ITEM B — APPROVED

Commit `84b2458` is correct and behavior-preserving.

[ml/features.py:580](/home/jianj/code/qp1-ml/ml/features.py:580) converts only `residualise_cols` to numeric float before floating-point residuals are assigned at [line 603](/home/jianj/code/qp1-ml/ml/features.py:603). This makes pandas 3’s dtype requirements explicit while matching pandas 2’s previous implicit upcast. Market-wide and excluded nonnumeric columns remain untouched.

Targeted ML hardening tests: **21 passed**.

## ITEM B — APPROVED

Commit `84b2458` is correct and behavior-preserving.

[ml/features.py:580](/home/jianj/code/qp1-ml/ml/features.py:580) converts only `residualise_cols` to numeric float before floating-point residuals are assigned at [line 603](/home/jianj/code/qp1-ml/ml/features.py:603). This makes pandas 3’s dtype requirements explicit while matching pandas 2’s previous implicit upcast. Market-wide and excluded nonnumeric columns remain untouched.

Targeted ML hardening tests: **21 passed**.

