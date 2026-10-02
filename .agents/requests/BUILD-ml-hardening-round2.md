# BUILD-REQUEST: ml-hardening — ROUND 2

**Branch:** `slice/ml-hardening` · **Builder:** MiMo · **Validators:** Claude, then Codex
**Gate:** PR #9 BLOCKED. Read `.agents/codex/VERDICT-silver-gold-and-ml.md` (PR #9 section).

Codex confirmed purging, embargo, and trailing-only barrier volatility are
correct. **Do not change those.** Three defects:

## 1. Neutralisation silently does nothing (critical)

`ml/features.py:431` returns the input unchanged when `market_beta` or
`industry` is absent, and the runner path never provides them. Meanwhile
`ml/train.py:248` reports neutralisation as enabled. A reported-but-skipped step
is worse than a missing one.

- Compute `market_beta` as a **trailing** rolling beta to the market (SPY on
  real data; the synthetic market factor in `ml/synthetic_data.py`), using only
  data before each row's timestamp.
- Supply `industry` from `config/tickers.yaml` groups (real) or a synthetic
  assignment (synthetic).
- If neutralisation is requested and either input is missing, **raise**. Never
  no-op.
- Report the cross-sectional correlation of each feature with beta, before and
  after neutralisation, so it is visibly doing something.

## 2. Make triple-barrier selectable

`ml/run_ablation.py:47` has no label option and `ml/synthetic_data.py:70`
always uses fixed-horizon labels. Add `--label-method {fixed,triple_barrier}`
(default `fixed`), thread it through, and record it in MLflow params and the
results artifact.

## 3. Honest deflated Sharpe

`ml/evaluate.py:233` hard-codes 4 trials and computes DSR over individual
cross-sectional rows.
- Trial count = the actual number of configurations evaluated in the run
  (arms × models × label methods), passed in, not hard-coded.
- Compute DSR on a **timestamp-aggregated** strategy return series (one return
  per date), with matching sample size and annualisation.

## Tests

- Neutralisation raises when inputs are missing; with inputs, post-neutralisation
  beta correlation ≈ 0.
- Ablation actually changes labels when `--label-method triple_barrier` is used.
- DSR decreases as the trial count increases, holding returns fixed.

## Constraints

Do not touch `silver/`, `gold/`, `agent/`, `db/`, `api/`, `conftest.py`,
`pytest.ini`, `requirements*.txt`.
`python3 -m pytest tests/ml -q -m "not spark and not databricks"` must pass. Paste it.
**Commit your work.** Write `.agents/mimo/VERDICT-ml-hardening-round2.md`.
