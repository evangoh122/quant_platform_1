# Execution Plan — Codex Independent Assessment

**Source:** Codex, dispatched to challenge the feasibility claims in
`QUANT_STRATEGIES.md` and produce a build plan. Codex had databricks-connect
and re-ran the checks itself.

> **Note on completeness:** Part 1 (the feasibility challenges) was lost from the
> capture because the dispatch piped output through `tail`. Part 2 below is
> intact. Codex's conclusions still reflect Part 1 — see "Where Codex corrected
> the spec" at the end.

---

- top 200–500 names;
- market/industry residual baseline;
- 3-, 5-, and 10-day horizons;
- fixed entry/exit parameters before broad tuning.

#### `strategies/portfolio.py`

Use the existing `strategies/neutralize.py`, extending it for:

- beta-neutral constraints;
- sector exposure constraints;
- per-name caps;
- ADV capacity;
- gross and turnover constraints;
- infeasibility diagnostics.

#### `strategies/cost_model.py`

Reuse and repair in place:

- name-level costs;
- reject/schedule orders exceeding ADV cap;
- calibrated spread where available;
- VWAP/impact path;
- explicit borrow haircut by liquidity bucket;
- gross, net, and stressed-cost outputs.

#### `strategies/backtest.py`

Responsibilities:

- consume dated target weights;
- enforce one-bar execution lag;
- apply costs and borrow;
- prevent trades outside the PIT universe;
- store fold, model, feature, and universe versions;
- output daily positions, trades, P&L and attribution.

Start gate:

- purged splitter complete;
- point-in-time universe complete;
- cost-model repairs complete.

### Phase 4: modelling

#### `ml/train_ranker.py`

First model:

- ridge/elastic-net cross-sectional forward-return or rank model;
- daily cross-sectional preprocessing fitted within each training fold;
- sample uniqueness weights;
- purged expanding folds.

Only add LightGBM after the linear model produces stable out-of-sample rank IC and net returns.

#### `ml/ablation.py`

Compare, with identical folds and tuning budgets:

```text
A: OHLCV/residual features
B: A + breadth/divergence
C: B + options, only if coverage gate passes
D: C + SEC/earnings, only on valid event rows
```

Report:

- daily rank IC;
- ICIR;
- gross and net Sharpe;
- turnover;
- cost drag;
- coverage;
- performance by fold and regime;
- sensitivity to doubled and tripled costs.

Do not compare arms over different date universes without also reporting their common-sample results.

## Dependency order

```text
ml/purged_cv.py + tests
        |
        +------------------------------+
        |                              |
Silver OHLCV lane               Silver options/SEC lanes
        |                              |
gold_tradable_universe          coverage/event validation
        |                              |
gold_regime_features            Gold optional features
gold_risk_factors                      |
        +---------------+--------------+
                        |
               gold_model_features
                        |
          residual_reversion baseline
                        |
        neutralization + cost-aware book
                        |
             purged walk-forward test
                        |
          ablations and challengers
```

## The one thing to build first

Build `ml/purged_cv.py` and its overlap-invariant test suite first.

Why:

- it does not depend on the currently empty Silver and Gold tables;
- it is reusable across every surviving strategy;
- it prevents false results rather than merely improving a feature;
- its correctness can be proven now with synthetic intervals;
- it forces the project to define prediction time, label end time, purge, embargo, and daily grouping before modelling begins.

Once the Silver OHLCV lane lands, the first strategy experiment should be a top-200-to-500 market/industry residual mean-reversion baseline, with RSP/SPY breadth as an ablation feature. PCA should be a challenger, not the starting point. Implied correlation and PEAD should remain gated research items until their date-level coverage and event-timestamp tests pass.

---

## Where Codex corrected the spec (coordinator notes)

1. **Universe: top 200–500 names, not 4,120.** My spec reported 4,120 liquid
   names (≥500 days, ADV > $5M). Codex scoped the first experiment to the top
   200–500. That is the prudent call — my filter did not test *recency*, so the
   4,120 likely includes delisted and stale tickers. Treat 4,120 as an upper
   bound on the screen, not a tradable universe.

2. **PCA is a challenger, not the starting point.** I recommended leading with
   Avellaneda–Lee eigenportfolios. Codex puts a plain market/industry residual
   baseline first and PCA second. Codex is right: establish the simple baseline
   before adding an estimated factor structure, or you cannot attribute the
   result.

3. **Implied correlation and PEAD are gated research items**, not build items,
   until date-level coverage and event-timestamp tests pass. This matches the
   concern I raised: per-underlying IV row counts do not prove that SPY *and*
   its constituents have matched-expiry ATM quotes on the *same dates*, which is
   what implied correlation actually requires.

4. **`strategies/cost_model.py` needs repair, not just reuse.** Codex says
   "reuse and repair in place" and lists missing pieces: ADV-cap rejection,
   calibrated spread, VWAP/impact path, explicit borrow haircut by liquidity
   bucket, and gross/net/stressed outputs.

5. **One-bar execution lag** must be enforced in the backtester, and trades
   outside the point-in-time universe must be prevented structurally rather
   than filtered afterwards.

## Agreement

Both of us independently concluded the first thing to build is the **purged and
embargoed splitter** — it is the only component that depends on none of the
currently-empty Silver/Gold tables, is reusable across every surviving strategy,
and prevents false results rather than improving a feature. That work is in
flight on `slice/ml-hardening`.
