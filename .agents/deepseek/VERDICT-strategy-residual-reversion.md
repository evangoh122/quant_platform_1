# VERDICT: strategy-residual-reversion — DeepSeek

**Status:** APPROVED
**Round:** 1

## Results (real data, `gold_tradable_universe` top-300, 2023-01-04 → 2026-09-04)

| metric | gross | net | net @ 2x costs |
|---|---:|---:|---:|
| annualised return | -0.0075 | -0.0442 | -0.0809 |
| Sharpe | -0.054 | -0.318 | -0.581 |
| max drawdown | -0.312 | -0.329 | -0.398 |
| hit rate (daily) | 0.394 | — | — |
| turnover (daily, one-way) | 0.329 | — | — |
| avg hold (days) | 3.84 | — | — |

Ablation (unconditioned vs gated by `breadth_regime == NARROW`): net Sharpe
**-0.318** vs **+0.073**; net@2x **-0.581** vs **-0.421**. Walk-forward
(max_hold ∈ {3,5,10} chosen on training folds only): out-of-sample net Sharpe
**-0.378**, **deflated Sharpe 0.000** (Bailey/LdP, n_trials=3).

**Conclusion — honest negative result.** The market/industry residual
mean-reversion baseline has **no net edge** on this universe. Gross Sharpe is
already ~0 (−0.05), so the failure is the signal, not just costs; costs turn it
decisively negative. No parameters were tuned on the full sample to rescue it.

## Live row counts

| table | rows | coverage |
|---|---:|---|
| `gold_tradable_universe` | **276,300** | 921 dates × 300 symbols; 554 distinct symbols; size/date min=300, median=300, max=300; 2023-01-04 → 2026-09-04 |
| `gold_regime_features` | **1,173** | one row per trading date, 2022-01-03 → 2026-09-04 |

Both tables are `MERGE`-idempotent; `information_available_ts` follows the
`gold/02_gold_options_features.sql` 16:00 America/New_York + 30 min DST-aware
convention (verified: regime rows stamp `20:30Z` summer, universe rows stamp the
prior session close).

## Blocking findings

None within this lane.

## Non-blocking notes

- **Universe screen admits ETFs** (SPY, QQQ, RSP, and other high-ADV funds
  appear in the top-300). `strategies/run_residual_reversion.py` excludes
  SPY/RSP/QQQ from the *tradeable* set (they are the factor/regime instruments);
  SPY's own residual is ~0 anyway, so this is conservative, not lossy. Worth a
  follow-up decision on excluding all ETFs.
- **Industry labels are the repo `config/tickers.yaml` taxonomy, not GICS** —
  stated in `residual_reversion.load_industry_map`, the runner, and the results.
- **Industry factor for a singleton industry is 0** (no "other" name), so those
  symbols collapse to a market-only regression. Documented in code.
- `strategies/neutralize.py` now projects onto the orthogonal complement of
  `[ones, beta, industry dummies]` *jointly* — sequential demean cannot satisfy
  all three constraints at once (a naive `[1,-1,1,-1]` book is pure systematic
  exposure and correctly neutralises to ~0).
- The runner pulls a ~550-symbol daily dataset through the SQL warehouse
  (databricks-sdk) and runs the regression on the driver — no Spark cluster is
  needed for a 300-name daily book. Warehouse id is a config default, overridable
  via `DATABRICKS_WAREHOUSE_ID`; credentials come from `~/.databrickscfg`.
- `gold_tradable_universe` starts 252 trading days after the data start
  (min-history gate), hence 921 (not 1,173) dates.

## Checks run

- `python -m pytest tests/strategies -q -m "not spark and not databricks"` →
  **21 passed** (universe PIT invariance, residual beta lag, no-same-bar-fill,
  ADV cap + borrow haircut, joint neutralisation).
- `python -m pytest tests/ml tests/gold -q -m "not spark and not databricks"` →
  **56 passed** (no regression from the `CostParams` ADV-cap default change).
- `python -m strategies.run_residual_reversion` → wrote
  `strategies/results/residual_reversion_r1.md` (numbers above).
- `DESCRIBE ...gold_tradable_universe` / `...gold_regime_features` → 6 / 10 cols
  match `docs/DATA_SCHEMAS.md` exactly.
- `git status` after commit → clean except the pre-existing
  `.agents/dispatch.sh` mode-only change (not mine, left unstaged). No secrets in
  the committed files (grep for `dapi`/`token`/`password`/`secret` → empty).
