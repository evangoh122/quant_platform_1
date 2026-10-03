# BUILD-REQUEST: ml-hardening

**Branch:** `slice/ml-hardening` (based on `slice/ml-ablation`)
**Agent:** Codex — **BUILDER** for this request
**Rubric:** §6 ML & Quantitative Research Design, §4.5 PIT / no-look-ahead,
§4.6 data-quality tests.

## Read first: the ML already exists. Do not rebuild it.

`ml/` already contains ~1,073 lines built by DeepSeek:
`features.py` (323), `train.py` (200), `run_ablation.py` (185), `evaluate.py`
(181), `score.py` (128), `registry.py` (87), `synthetic_data.py` (169), plus 5
test files including `test_pit_no_lookahead.py` and `test_walk_forward.py`.

**Your job is to harden it, not replace it.** Rewriting working code is a
blocking failure for this request. Read `docs/QUANT_STRATEGIES.md` §4 — it
specifies the techniques below and why they matter here.

## Context you need

- The gold feature tables are **currently empty (0 rows)** — a separate lane is
  populating them from 232M bronze rows. That is why `run_ablation.py` falls
  back to `ml/synthetic_data.py`. **Keep that fallback**, keep it clearly
  labelled, and make the real path activate automatically once the tables fill.
- Real Spark is available: `databricks-connect` 19.2.0 with serverless.
  `DatabricksSession.builder.serverless(True).getOrCreate()`.
  Catalog/schema `bootcamp_students.evangoh_capstone`.
- Reuse `strategies/cost_model.py` — do not reimplement transaction costs.

## Gap 1 — Purged & embargoed walk-forward CV (HIGHEST PRIORITY)

`ml/` has walk-forward but **no purging and no embargo**. With multi-day holding
periods this leaks and inflates every metric.

The problem concretely: the label for day *t* depends on prices through *t+h*.
Those same prices are features for days *t+1 … t+h*. A plain time-series split
therefore trains on information that overlaps the validation labels.

Implement:
- **Purging** — drop training rows whose label window `[t, t+h]` overlaps the
  validation window.
- **Embargo** — additionally drop a buffer of `e` bars immediately after the
  validation window before training resumes.
- Both parameters configurable; document the defaults you choose and why.

**Required test:** construct a fixture where an un-purged split demonstrably
leaks (a feature that encodes the future label) and assert that the purged
splitter removes exactly the overlapping indices. Then assert that the naive
splitter would have retained them. A test that only checks the happy path is a
blocking defect — show the leak being caught.

Also report, honestly, how much usable sample survives purging. With ~1,173
trading days and a 20-day horizon the effective sample shrinks substantially; if
it collapses below a usable size, say so with numbers rather than proceeding
quietly.

## Gap 2 — Triple-barrier labelling

Replace the fixed-horizon forward-return sign label with a path-dependent label:
profit target, stop loss, and time limit, whichever is hit first. Keep the
existing label as a selectable option so the ablation can compare them.

Barriers should be volatility-scaled (e.g. target/stop as a multiple of rolling
realized vol), not fixed percentages.

## Gap 3 — Sample weighting by uniqueness

Overlapping labels break the IID assumption, so effective sample size is far
below row count. Implement **average uniqueness** weighting (inverse of
concurrent label overlap) and pass the weights to the estimators that accept
`sample_weight`. State the mean uniqueness you measure — it is a useful honesty
check on the whole setup.

## Gap 4 — Cross-sectional ranking metric

`evaluate.py` already computes rank IC — good. Extend it:
- rank IC **per day** across the cross-section, then report mean, std, and
  IC t-stat (not a single pooled number).
- **Deflated Sharpe Ratio** or probability of backtest overfitting, to penalise
  the multiple testing implicit in trying four feature sets A/B/C/D.

## Gap 5 — Feature neutralisation

Residualise features against market beta and industry before training so the
model cannot win by covertly loading on a known factor. Industry labels come
from `config/tickers.yaml` groups — note in the code that this is a repo YAML,
not a vendor taxonomy.

## Non-goals — do not build

- Do not implement the trading strategies themselves (residual momentum, PEAD,
  index arb). That is a later slice. This request is ML machinery only.
- Do not build a frontend, API routes, or streaming.
- Do not write `gold_*` tables — a concurrent lane owns those.
- Do not add deep sequence models. ~1,173 days of daily cross-section does not
  support them; LightGBM is the right challenger ceiling here.

## Paths you must NOT touch

`silver/`, `gold/` (live lane), `agent/`, `db/` (live lane), `api/`,
`conftest.py`, `pytest.ini`, `requirements*.txt`, `README.md`, `.agents/`.

## Acceptance criteria

1. Purged + embargoed CV implemented, with the leak-detection test passing and
   its output pasted.
2. Triple-barrier labelling available and selectable; old label retained.
3. Uniqueness weighting implemented; measured mean uniqueness reported.
4. Per-day rank IC with t-stat, plus a backtest-overfitting penalty.
5. Feature neutralisation implemented.
6. `python3 -m pytest tests/ml -q -m "not spark and not databricks"` passes.
   Paste the real command and output.
7. No existing `ml/` module rewritten wholesale. `git diff --stat` should read
   as additive plus targeted edits.
8. **Commit your work** to `slice/ml-hardening`. Never push, never touch `main`.

## Reporting

You cannot commit from a worktree (git metadata sits outside your sandbox) and
`.agents/` is read-only to you — so commit if you can, and either way print your
report to stdout starting with `===REPORT START===`, including the honest
surviving-sample numbers from Gap 1.
