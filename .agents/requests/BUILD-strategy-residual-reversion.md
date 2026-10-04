# BUILD-REQUEST: strategy-residual-reversion (round 1)

**Branch:** `slice/strategy-residual-reversion` (worktree `/home/jianj/code/qp1-strat2`;
contains `slice/ml-hardening` + `slice/silver-gold`)
**Builder:** DeepSeek · **Validators:** Claude, then Codex
**Spec:** `docs/QUANT_STRATEGIES.md` §1–2 and `docs/EXECUTION_PLAN.md`. Codex's plan names
this as the first strategy experiment: a market/industry **residual mean-reversion
baseline** on a top-N liquid universe, with RSP/SPY breadth as an ablation feature.
PCA eigenportfolios are a **challenger for a later round**, not this one.

## Execution environment

- Spark: `databricks-connect` serverless — `DatabricksSession.builder.serverless(True).getOrCreate()`.
- Catalog/schema `bootcamp_students.evangoh_capstone`. Lakebase is **stopped**; do not use it.
- Daily data: `bronze_ohlcv_day` — ~20k symbols, 1,173 trading days (2022-01-03 → 2026-09-04).
  The strategy horizon is 3–10 **days**, so daily bars are the right grain.
- **Daily bars are stamped at the start of the day.** A day's close is available only after
  the 16:00 New York close. Use the same rule as `gold/02_gold_options_features.sql`
  (16:00 America/New_York + 30 min buffer, DST-aware) for every daily-derived
  `information_available_ts`. This exact convention has caused two look-ahead leaks
  already; get it right first.

## Build, in order

### 1. `gold_tradable_universe` (new table)
Point-in-time daily universe: for each date, the top **N** (configurable; default 300)
symbols by trailing 60-day median dollar volume, computed **only from data before that
date**, with a **recency filter** (traded on each of the last 5 sessions) and minimum
history (≥ 252 sessions). Codex flagged that a naive screen counts delisted/stale names —
the recency filter is what prevents that. Report universe size per date (min/median/max).

### 2. `gold_regime_features` (new table) — your RSP/SPY breadth signal
Daily, market-wide: `rsp_spy_ratio`, its 50-day SMA, 252-day z-score, 20-day slope,
`breadth_regime` ∈ {BROAD, NARROW, MIXED} per `QUANT_STRATEGIES.md` §2.1; plus
`qqq_spy_20d` and `rsp_spy_20d` relative returns (§2.3). All trailing; availability at
session close.

### 3. Residual signal — `strategies/residual_reversion.py`
- Daily returns; regress each stock on **market (SPY) + its industry** factor (equal-weight
  industry return excluding the stock itself) over a rolling **60-day** window that ends
  **strictly before** day t.
- Industry labels: `config/tickers.py` loaders (they now reject non-string tickers). Note
  in code that this is a repo taxonomy, not GICS.
- s-score = cumulative residual over a lookback L (default 5) / residual σ.
- Enter long at s ≤ −2.5, short at s ≥ +2.5, exit when |s| < 0.5 or after max hold
  (test 3, 5, 10 days).

### 4. Backtest — `strategies/backtest.py`
- **One-bar execution lag**: a signal from day t's close trades at day t+1. Enforce
  structurally (the backtester cannot be given same-bar fills).
- Trades only inside that date's `gold_tradable_universe`.
- Beta- and industry-neutral book using `strategies/neutralize.py` (extend it if needed).
- Costs via `strategies/cost_model.py` — **repair it in place** per `EXECUTION_PLAN.md`:
  ADV cap (reject/scale orders > 1% of ADV), spread/impact, and an explicit **borrow
  haircut** for shorts by liquidity bucket (there is no borrow data, so it is a stated
  assumption). Report results **gross, net, and net at 2× costs**.

### 5. Evaluation and the breadth ablation
- Walk-forward: choose any parameter (lookback, threshold, hold) **on training folds
  only**, evaluate out of sample. Reuse `ml/train.py`'s purged/embargoed splitter for the
  date splits (label horizon = max hold).
- Metrics: annualised return, Sharpe, max drawdown, hit rate, turnover, average hold,
  capacity, and **deflated Sharpe with the true number of configurations tried**.
- **Ablation:** strategy unconditioned vs gated by `breadth_regime`. Report both.
- Write results to `strategies/results/residual_reversion_r1.md`.

**An honest negative result is a valid outcome.** If the edge disappears net of costs,
say so plainly. Do not tune parameters on the full sample to rescue it.

## Tests (offline, `@pytest.mark.databricks` where Spark is needed)
- Universe: a symbol's membership on date t is unchanged when data after t is altered.
- Residual: perturbing day t's return does not change the beta used for day t's signal.
- Backtest: a signal on day t cannot produce a fill on day t (assert, with a fixture).
- Costs: an order above the ADV cap is scaled or rejected; shorts pay the borrow haircut.

## Constraints
Do not modify `ml/`, `silver/`, `gold/0*` existing transforms, `agent/`, `db/`, `api/`,
`frontend/`, `conftest.py`, `pytest.ini`, `.agents/dispatch.sh`. New gold tables: create
them and add their schemas to `docs/DATA_SCHEMAS.md`. Do not write `gold_trading_signals`.
**Commit your work.** Write `.agents/deepseek/VERDICT-strategy-residual-reversion.md`
leading with the results table and live row counts.
