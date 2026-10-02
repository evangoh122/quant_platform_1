# VERDICT: ml-ablation — DeepSeek

**Status:** APPROVED
**Round:** 1

Built the ML ablation lane (`ml/`) end-to-end on branch `slice/ml-ablation`:
point-in-time feature assembly with a hard no-lookahead guard, walk-forward-only
training, the A/B/C/D ablation runner, predictive/economic/operational
evaluation (reusing `strategies/cost_model.py`), MLflow tracking, and the
`gold_trading_signals` scoring path. All tests pass in lane isolation.

---

## Blocking findings

None within this lane's code.

**One cross-cutting blocker is outside this lane's ownership** and must be
resolved by the `fix/test-harness` lane (MiMo) before the final gate closes:

- The literal acceptance command `python3 -m pytest tests/ml -q -m "not spark
  and not databricks"` fails at **collection** because the shared root
  `conftest.py:48` does `import db.database as db_module`, and `db/database.py`
  does not exist (it was dropped in the DuckDB→Delta merge). This is the exact
  defect documented in `.agents/requests/BUILD-f0-test-harness.md`. The request
  explicitly forbids me from editing `conftest.py`/`pytest.ini` and from touching
  `db/` (Lane A), so I did not "fix" it — see **Checks run** for evidence that
  the lane's own tests pass once that shared harness issue is isolated.

## Non-blocking notes

- **Live data is empty.** The request assumed gold/silver were "already
  populated"; they are not. I probed `bootcamp_students.evangoh_capstone` via
  the Databricks CLI/SDK and every `gold_*`, `silver_*` table returned **0
  rows** (bronze has data: `bronze_ohlcv` 72.7M, `bronze_options_day` 146.1M,
  `bronze_sec_filings` 60.9K, `bronze_cftc_*` 15.4K). Re-ingesting raw data is
  an explicit non-goal, so the ablation result artifact is a **clearly-labelled
  synthetic demonstration** (`ml/results/ablation_abcd.md`) built from
  `ml/synthetic_data.py`, which mirrors the *real* schema. The pipeline is
  data-agnostic — point `ml/run_ablation.py` at the warehouse read path once
  gold lands.
- The A/B/C/D arms map one-to-one onto the 22 feature columns that
  `gold_model_features` actually carries (introspected, not assumed).
- `gold_trading_signals` schema introspected: `signal_id, symbol, prediction_ts,
  horizon, direction, probability, model_version, feature_snapshot_id, status,
  processed_ts` — `ml/score.py` writes exactly these (plus the NOT-NULL `signal_id`
  and `processed_ts` the request's "expected semantics" omitted).
- `cot_regime_label` (STRING) and `sec_material_event` (BOOLEAN) are encoded to
  numeric in `ml/train.prepare_features` before training; one-hot is fit on
  features only (no label leakage).
- No secrets committed; `mlruns/` and `.agentlogs/` are gitignored. Branch
  `slice/ml-ablation` only; `main` untouched.

## Acceptance criteria

1. **PIT leakage test** — exists (`tests/ml/test_pit_no_lookahead.py`) and
   demonstrably catches a leak (failing output below), plus the happy path.
2. **Walk-forward only** — `ml/train.walk_forward_splits`; no randomized CV
   anywhere in `ml/`.
3. **A/B/C/D table committed** — `ml/results/ablation_abcd.md` (synthetic, honest).
4. **MLflow runs with feature-set version + seed** — `ml/registry.build_run_tags`
   carries `feature_set` and `seed`; 8 runs logged to the `ml_ablation` experiment.
5. **`python3 -m pytest tests/ml -q -m "not spark and not databricks"`** — blocked
   by the shared harness (see Blocking findings); passes with lane isolation.
6. No secrets committed. ✓
7. Branch `slice/ml-ablation` only. ✓

## Checks run

**A. Deliberate-leak fixture — guard MUST fail, then the clean pass.**

```
$ PYTHONPATH=. python3 .agentlogs/demo_leak_guard.py
=== 1. Clean matrix: guard must NOT raise ===
OK: no lookahead on clean data

=== 2. Deliberately leaked row: guard MUST raise ===
LookaheadError raised as expected:
  lookahead detected: 1 row(s) have max_information_available_ts > prediction_ts.
  Example: symbol=AAPL max_information_available_ts=2026-01-05 09:44:00+00:00
  > prediction_ts=2026-01-05 09:39:00+00:00
```

**B. Lane test suite (isolated from the broken shared conftest).**

```
$ python3 -m pytest tests/ml -q -m "not spark and not databricks" --confcutdir=tests/ml
..............                                                           [100%]
14 passed in 2.34s
```

**C. The literal acceptance command — fails on the shared harness (not this lane).**

```
$ python3 -m pytest tests/ml -q -m "not spark and not databricks"
ImportError while loading conftest '/home/jianj/code/qp1-laneB/conftest.py'.
conftest.py:48: in <module>
    import db.database as db_module
E   ModuleNotFoundError: No module named 'db.database'
```

**D. Ablation run (synthetic) + MLflow + artifact.**

```
$ PYTHONPATH=. python3 -m ml.run_ablation --include-challenger --n-symbols 6 --n-bars 400 --n-splits 5 --min-train 60 --seed 42
Wrote ml/results/ablation_abcd.md
 arm       model  roc_auc  directional_accuracy  information_coefficient    sharpe  hit_rate
  A    baseline 0.493621              0.518919               -0.030645  1.431057  0.518919
  A  challenger 0.512251              0.509189                0.024556 -1.393186  0.509189
  B    baseline 0.501943              0.519459               -0.019528  0.593685  0.519459
  B  challenger 0.508131              0.512432                0.005790 -1.255780  0.512432
  C    baseline 0.560423              0.529730                0.135846  2.120284  0.529730
  C  challenger 0.567837              0.558919                0.160315  7.622132  0.558919
  D    baseline 0.561824              0.552973                0.122661  5.380740  0.552973
  D  challenger 0.557794              0.540000                0.145021  7.226488  0.540000
```

**E. Schema introspected (not assumed).** `databricks tables get
bootcamp_students.evangoh_capstone.gold_model_features --output json` → 27
columns (symbol, prediction_ts, feature_snapshot_id, 22 features, model_version,
processed_ts). `gold_trading_signals` → 10 columns as above.

**F. No secrets / clean branch.**

```
$ git status --short   # clean after commit
$ git log --oneline -3
581324c feat(ml): PIT feature assembly, walk-forward ablation, evaluation, MLflow, scoring
```
