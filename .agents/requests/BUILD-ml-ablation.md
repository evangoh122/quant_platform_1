# BUILD-REQUEST: ml-ablation

**Round:** 1
**Branch:** `slice/ml-ablation`
**Lane:** B (coordinated by Codex; built by DeepSeek then MiMo)
**Rubric requirements covered:** Machine Learning & Quantitative Research Design
(rubric §6: prediction task, feature families + ablation, evaluation), the
point-in-time join and no-look-ahead rule (§4.5), the PIT data-quality test
(§4.6), and `gold_trading_signals` population.

---

## Context

This is a Databricks capstone: a mid-frequency quant trading research platform.
The research question the whole project exists to answer is:

> Can short-horizon equity returns be predicted more effectively by combining
> price dynamics, options-derived features, SEC event features, and market
> positioning than by using OHLCV alone?

`ml/` currently contains **only `__init__.py`**. Nothing in this lane exists yet.

### Live data you build on (already populated — do not re-ingest)

Unity Catalog schema **`bootcamp_students.evangoh_capstone`** holds 27 Delta
tables. The ones you need:

| Table | Cols | Role |
| :-- | :-- | :-- |
| `gold_model_features` | 27 | PIT-joined feature matrix, keyed by symbol + prediction_ts |
| `gold_ohlcv_features` | 19 | returns, realized vol, ATR, momentum, RSI, VWAP dev, rel volume |
| `gold_options_features` | 16 | put/call, IV level/skew/term, spread, volume anomaly, OI |
| `gold_sec_features` | 13 | tone, risk-factor change, filing similarity, event flags |
| `gold_cot_features` | 12 | net positioning, weekly change, percentile, z-score |
| `gold_trading_signals` | 10 | **your output target** |
| `silver_ohlcv` | 15 | source for labels |

**Introspect the real columns yourself** before writing code — do not assume
names from this table. Use the Databricks CLI:
```
databricks tables get bootcamp_students.evangoh_capstone.gold_model_features --output json
```
A SQL warehouse exists (`Serverless Starter Warehouse`, id `b15d3d6f837ba428`)
but is STOPPED; start it if you need to run queries, and say so in your report.

---

## Scope — what to build

### 1. Point-in-time feature assembly with a real leakage test

`ml/features.py`:
- AS-OF join: for prediction timestamp `t`, select only records whose
  `information_available_ts <= t`. Never backward-fill future observations.
- SEC features use filing acceptance/availability time; COT uses the official
  release timestamp (forward-filled only until the next release); market
  features use event/window close.
- Labels computed **after** feature assembly and **not** persisted into serving
  tables.

`tests/ml/test_pit_no_lookahead.py` — this is the single most important test in
the lane. It must **fail the build** if any assembled training row contains a
feature whose `information_available_ts > prediction_ts`. Construct a fixture
that deliberately injects a leaking row and assert the guard catches it. A test
that only checks the happy path is a blocking defect.

### 2. Prediction task

`ml/train.py`:
- Primary target: **P(30-minute forward return > 0)** per eligible underlying.
- Baseline: **logistic regression**.
- Challenger: **XGBoost** (or LightGBM/RandomForest) to test nonlinear
  interactions.
- **Walk-forward / time-series split only.** Randomized k-fold across time is a
  blocking defect — it leaks future information.

### 3. Ablation study — the point of the lane

Four feature sets, trained and evaluated identically:

| Model | Feature set | Question |
| :-- | :-- | :-- |
| A | OHLCV only | baseline price/volume signal |
| B | OHLCV + options | incremental derivatives information |
| C | OHLCV + options + SEC | event/fundamental text contribution |
| D | OHLCV + options + SEC + COT | does positioning/regime help |

Produce a comparison table of A/B/C/D. This is the deliverable that answers the
research question — report it honestly even if adding features does **not** help.
A negative result, clearly shown, is a valid and valuable outcome. Do not tune
one arm harder than the others.

### 4. Evaluation

`ml/evaluate.py`:
- Predictive: ROC-AUC, precision/recall, directional accuracy, Brier
  score/calibration, information coefficient.
- Economic: transaction-cost-adjusted return, Sharpe, max drawdown, hit rate,
  turnover, average holding period. `strategies/cost_model.py` already exists —
  reuse it, do not reimplement.
- Operational: p50/p95 inference latency.

### 5. MLflow tracking

`ml/registry.py`: log runs, params, **feature-set version (A/B/C/D)**, metrics,
and artifacts; register the promoted model version. Runs must be reproducible —
log the random seed and the data window.

### 6. Scoring path

`ml/score.py`: load the promoted model, score the latest feature rows, and write
`gold_trading_signals` with the columns that table actually has — introspect it.
Expected semantics: `prediction_ts`, `symbol`, `horizon`, `probability`,
`direction`, `model_version`, `feature_snapshot_id`, `status`.

### 7. Tests

Under `tests/ml/`. Mark Spark-dependent tests `@pytest.mark.spark` and
Databricks-dependent ones `@pytest.mark.databricks` so they can be deselected.
Beyond the PIT test: assert the walk-forward splitter never lets a training
index exceed a validation index, and assert the ablation runner actually varies
the feature set between arms (a bug that silently trains the same features four
times would otherwise look like a clean null result).

---

## Non-goals — do not build

- Lakebase schema, agent tools, the risk service. **Lane A owns `db/` and
  `agent/` right now — do not touch those paths, you will cause conflicts.**
- CDF consumer or `analytics_*` tables.
- React frontend, FastAPI routes, Databricks App packaging.
- Structured Streaming pipelines.
- Re-ingesting raw data. Bronze/Silver/Gold are already populated.

## Shared files you must NOT edit

`conftest.py`, `pytest.ini`, `requirements.txt`, `requirements-dev.txt`,
`.agents/PROTOCOL.md`, `.agents/dispatch.sh`. A concurrent lane (`fix/test-harness`)
is repairing the test harness right now. If you need a dependency added, state
it in your verdict; do not edit those files.

## Acceptance criteria

1. The PIT leakage test exists, and **demonstrably fails** when fed a leaking
   row. Show that — paste the failing output from the deliberate-leak fixture,
   then the passing run.
2. Walk-forward validation only. No randomized CV anywhere.
3. The A/B/C/D ablation table is produced and committed as a result artifact
   with the metrics from §4.
4. MLflow runs logged with feature-set version and seed.
5. `python3 -m pytest tests/ml -q -m "not spark and not databricks"` passes —
   paste the real command and real output.
6. No secrets committed.
7. Branch `slice/ml-ablation` only. `main` untouched.

## Install note for this machine

Plain `pip install` fails with PEP 668 and `python3 -m venv` has no `ensurepip`.
Use `pip install --user --break-system-packages <pkg>`. `pyspark`, `mlflow`,
`scikit-learn`, `xgboost`, `pandas` and `pyarrow` are being installed centrally;
verify before assuming absence.

## When finished

DeepSeek → `.agents/deepseek/VERDICT-ml-ablation.md`
MiMo → `.agents/mimo/VERDICT-ml-ablation.md`
Codex → `.agents/codex/VERDICT-ml-ablation.md`
Per `.agents/PROTOCOL.md`.
