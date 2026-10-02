# VERDICT: ml-hardening after round 4 — Codex

CHANGES_REQUESTED

Blocking findings:

- `market_beta` is not strictly point-in-time. The return at timestamp `t` is calculated from the close at `t`, and the unshifted rolling covariance/variance includes that same return. The resulting beta is then joined directly onto the row at `t`: [ml/synthetic_data.py](/home/jianj/code/qp1-ml/ml/synthetic_data.py:176), [ml/synthetic_data.py](/home/jianj/code/qp1-ml/ml/synthetic_data.py:183), [ml/synthetic_data.py](/home/jianj/code/qp1-ml/ml/synthetic_data.py:197). To satisfy “strictly before,” returns or the computed beta must be shifted by one timestamp before joining.

- Market-wide detection is not robust for sparse cross-sectional features. The threshold is 90% of all timestamps, and `nunique(dropna=True) <= 1` counts an entirely missing timestamp as constant: [ml/features.py](/home/jianj/code/qp1-ml/ml/features.py:422), [ml/features.py](/home/jianj/code/qp1-ml/ml/features.py:437), [ml/features.py](/home/jianj/code/qp1-ml/ml/features.py:441). Thus a genuinely cross-sectional feature available at fewer than 10% of timestamps will automatically be classified as market-wide and bypass neutralisation, regardless of its variation when observed.

- Market-wide classification is fitted on the full matrix before walk-forward folds are applied. `neutralize_features()` examines every timestamp at [ml/features.py](/home/jianj/code/qp1-ml/ml/features.py:537), while the runner calls it on the complete matrix before iterating through splits at [ml/train.py](/home/jianj/code/qp1-ml/ml/train.py:252). Future validation timestamps can therefore determine whether historical observations are residualised. The individual beta/industry regressions are timestamp-local, but this global preprocessing decision is not training-fold-local.

Other checks:

- DSR uses timestamp-aggregated strategy returns: [ml/evaluate.py](/home/jianj/code/qp1-ml/ml/evaluate.py:236).
- Its default trial count is `feature sets × models`, so the optional challenger is included: [ml/train.py](/home/jianj/code/qp1-ml/ml/train.py:219). Each runner invocation executes exactly one selected label method, so its actually-run label-method multiplier is one. The `label_method` argument to `run_ablation()` itself does not affect the count.
- Purging still removes inclusive label-window overlaps, and embargo timestamps remain permanently excluded from subsequent training folds: [ml/train.py](/home/jianj/code/qp1-ml/ml/train.py:101), [ml/train.py](/home/jianj/code/qp1-ml/ml/train.py:106), [ml/train.py](/home/jianj/code/qp1-ml/ml/train.py:112). I found no regression there.
- Requested test suite: `33 passed, 17 warnings in 51.47s`.

