# Mid-Frequency Quant Strategies, Indicators & ML Techniques

**Status:** residual mean-reversion is the primary built strategy. OLS
market/industry is the baseline factor model; PCA (Ledoit-Wolf shrinkage) is
the statistical-factor variant. Intraday pairs and daily alpha basket are
later/experimental. The industry-taxonomy caveat applies throughout (§1).
**Data checked:** 2026-10-02 against `bootcamp_students.evangoh_capstone` via
databricks-connect serverless. **Every feasibility verdict below is measured,
not assumed** — the queries are in §6.

---

## 0. Executive summary — what is actually buildable today

| # | Item | Verdict | Binding constraint |
| :- | :-- | :-- | :-- |
| 1 | **Cross-sectional stat arb (residual momentum)** | ✅ **Strongest** | 4,120 liquid names × 1,173 days available. No Value factor (needs book value). |
| 2 | **RSP/SPY breadth ratio** | ✅ Daily only | RSP minute history is a 22-day fragment; daily is complete (1,173 d). |
| 3 | **Sector / factor divergence** | ✅ Daily | Industry labels come from `config/tickers.yaml`, not a vendor classification. |
| 4 | **PEAD** | ⚠️ Reformulate | **No analyst estimates exist anywhere.** SUE as written is impossible. Universe is 18 names, ~all semis/mega-cap tech. |
| 5 | **SPY vs RSP implied-vol spread** | ❌ As specified | **`bronze_options_quotes` has 0 RSP rows.** Replace with implied correlation (§2.2) — a better metric for the same question. |
| 6 | **Index rebalancing arb** | ❌ Not yet | No S&P/Russell announcement data in the lakehouse. Needs new ingestion. |
| 7 | **TWAP/VWAP execution modelling** | ✅ | `bronze_ohlcv` carries `vwap` + minute bars. |
| 8 | **Short borrow / HTB costs** | ❌ No data | Must be an explicit modelled assumption, never silently zero. |

**Recommended build order:** §1 residual mean-reversion (✅ built, primary) →
§2 indicators → §3 PEAD (reformulated) → §4 ML discipline throughout → index
arb last, after ingestion.

Rationale: residual mean-reversion is the only strategy whose full data
requirement is already satisfied at scale, and it is the one the rubric's
research question ("do options/SEC/COT features beat OHLCV alone?") can
actually be tested on.

---

## 1. Cross-Sectional Statistical Arbitrage (Residual Mean-Reversion) — BUILT, PRIMARY

### Alpha
Regress each stock's return on systematic factors, isolate the idiosyncratic
residual, and trade its mean reversion. Unlike 1-to-1 pairs trading this does
not depend on a single cointegrating relationship surviving.

$$R_{i,t} = \alpha_i + \sum_k \beta_{i,k} F_{k,t} + \epsilon_{i,t}$$

Trade when the cumulative standardized residual (the *s-score*) breaches a
threshold:

$$s_{i,t} = \frac{\sum_{\tau=t-L}^{t}\epsilon_{i,\tau}}{\sigma(\epsilon_i)}$$

Enter short at $s \ge +2.5$, long at $s \le -2.5$, exit toward $|s| < 0.5$.
Expected reversion horizon 3–10 trading days.

### Factor set — what we can actually build

| Factor | Source | Status |
| :-- | :-- | :-- |
| Market | SPY daily return (1,173 d) | ✅ |
| Industry | `config/tickers.yaml` industry groups (12,400 tickers) | ✅ but see caveat |
| Size (proxy) | rank of ADV = `AVG(close*volume)`; true market cap unavailable | ⚠️ proxy |
| Short-term reversal | own lagged 1–5 d return | ✅ |
| Value | needs book value from XBRL — `silver_sec_entities` is empty | ❌ |
| Momentum | 12-1 month return | ✅ |

**Caveat on industry:** `tickers.yaml` groups are a hand-rolled industry list,
not GICS/SIC. Fine for neutralisation, but do not describe it as a vendor
classification in the write-up.

### Better alternative to raw OLS: statistical (PCA) factors
With 4,120 names, prefer **eigenportfolios** (Avellaneda–Lee): PCA the
correlation matrix of returns, keep the top 10–15 components as the factor set,
regress each stock on those. Advantages: no dependence on a possibly-wrong
industry taxonomy, and it adapts to regime. Use **Ledoit–Wolf shrinkage** on the
covariance before the eigendecomposition — with 4,120 names and ~1,173 days the
sample covariance is badly conditioned ($N$ close to $T$).

### Implementation notes
- Rolling window 60 days, re-estimate daily, **expanding-window only** (never
  fit on future data).
- Residual must be computed from betas estimated **strictly before** the trade
  timestamp → `information_available_ts` discipline (§4.1).
- Neutralise the book to beta ≈ 0 and industry ≈ 0 at the optimiser stage, not
  by hand-picking. A long-tech/short-utilities book is a macro bet, not alpha.

---

## 2. Indicators

### 2.1 RSP/SPY Breadth Ratio — ✅ daily

**Measured:** SPY, RSP, QQQ each have 1,173 daily bars, 2022-01-03 → 2026-09-04.
RSP *minute* data is only 8,695 bars across 22 days (2023-03-13 → 2023-04-12),
so **any intraday version of this signal is not supportable** — do not build it.

A daily cadence is correct anyway: this is a macro breadth regime signal, not a
mid-frequency trigger.

```
ratio_t      = close(RSP)_t / close(SPY)_t
ratio_ma50   = SMA(ratio, 50)
breadth_z    = (ratio_t - mean(ratio, 252)) / std(ratio, 252)
breadth_slope= ratio_t / ratio_{t-20} - 1
regime       = 'BROAD'  if ratio_t > ratio_ma50 and breadth_slope > 0
               'NARROW' if ratio_t < ratio_ma50 and breadth_slope < 0
               else 'MIXED'
```

**Interpretation.** Rising = broad participation, the average stock beating the
mega-caps, a more resilient tape. Falling = narrow leadership, index returns
carried by a handful of names, historically a more brittle, reversal-prone
configuration.

**Use it as a conditioning variable, not a trade signal.** Highest value as a
regime feature that gates the other strategies — e.g. residual-momentum mean
reversion behaves differently in NARROW regimes, where idiosyncratic dispersion
is higher. Add `breadth_regime` to `gold_model_features` and let the ablation
(§4.5) measure whether it earns its place.

### 2.2 Implied Volatility Spread — ❌ as specified; build implied correlation instead

**Measured:** `bronze_options_quotes` contains **0 rows for underlying `RSP`**.
There is no RSP options data, so the SPY-vs-RSP IV spread cannot be computed.

Available IV coverage (rows with non-null `implied_volatility`):

| Underlying | IV rows | Expiries |
| :-- | --: | --: |
| SPY | 12,632 | 33 |
| QQQ | 9,898 | 32 |
| META | 5,064 | 22 |
| AMD | 5,225 | 23 |
| TSLA | 4,407 | 22 |
| GOOGL | 3,872 | 22 |
| MSFT | 3,514 | 22 |
| NVDA | 3,212 | 22 |
| AAPL | 3,040 | 23 |
| AMZN | 2,310 | 24 |

**The substitute is strictly better for the question being asked.** What the
SPY/RSP IV spread is reaching for — "is fear concentrated in the mega-caps, or
systemic?" — is measured directly by **implied correlation** (the basis of
CBOE's COR3M). We have index IV *and* single-name IV for the dominant SPY
constituents, which is exactly what it needs:

$$\rho_{\text{implied}} \approx \frac{\sigma_{\text{SPY}}^2 - \sum_i w_i^2\sigma_i^2}{2\sum_{i<j} w_i w_j \sigma_i \sigma_j}$$

Using ATM IV at a matched expiry, $w_i$ = approximate SPY weights for the names
above (document the weights; they are approximations, not live index weights).

- **ρ rising** → index fear exceeds the sum of single-name fears: *systemic*
  risk, correlated selloff being priced.
- **ρ falling** → single names scary, index calm: *idiosyncratic/dispersion*
  regime, concentrated binary events (earnings, one-name blowups).

Secondary, cheaper signal available today: **SPY vs QQQ IV spread** — a clean
broad-vs-mega-cap-tech read, both well populated.

Also build the standard term-structure and skew features from the same table,
since `bronze_options_quotes` already carries `implied_volatility`, `delta`,
`gamma`, `theta`, `vega`, `open_interest`:
`iv_atm`, `iv_skew_25d` (25Δ put IV − 25Δ call IV), `iv_term_slope`
(near vs far expiry), `put_call_volume_ratio`, `oi_concentration`.

### 2.3 Sector & Factor Divergence — ✅ daily

```
cyclical_value_signal = return(RSP, 20d) - return(SPY, 20d)   # >0 → breadth/cyclicals leading
growth_momentum_signal= return(SPY, 20d) - return(RSP, 20d)   # >0 → mega-cap growth leading
tech_concentration    = return(QQQ, 20d) - return(SPY, 20d)
```

RSP's equal weighting structurally tilts it toward Industrials, Financials and
Materials relative to SPY's ~mega-cap-tech concentration, so the spread is a
usable proxy for cyclical-vs-growth rotation. **Caveat to state honestly:** this
is a *proxy* inferred from two ETFs, not a true factor decomposition — we have
no constituent weights or fundamental factor data. Treat it as a regime feature.

---

## 3. Post-Earnings Announcement Drift — ⚠️ requires reformulation

### The blocker
The specified formula needs $Expected(EPS_t)$ — analyst consensus. **We have no
analyst estimate data anywhere in the lakehouse, and none of the four ingestion
sources (Polygon/Massive, SEC EDGAR, CFTC, IBKR) provides it.** SUE as written
is not computable. Do not build a stub that pretends otherwise.

Second constraint: SEC filings cover **18 tickers only** — AAPL, AMAT, AMD,
AMZN, AVGO, GOOG, GOOGL, INTC, KLAC, LRCX, META, MRVL, MSFT, MU, NVDA, QCOM,
TSLA, TXN. That is almost entirely semiconductors and mega-cap tech. Two
consequences:
- A decile sort over 18 highly-correlated names is not a cross-sectional
  strategy; it is a leveraged semis bet.
- **Sector neutralisation is impossible inside a single-sector universe.**

### Two defensible reformulations

**(a) Seasonal-random-walk SUE** — the original academic construction
(Foster 1977; Bernard & Thomas 1989), which predates analyst-consensus datasets
and needs only reported EPS history:

$$E[EPS_t] = EPS_{t-4} + \delta, \qquad \delta = \text{mean 4-quarter drift}$$
$$SUE_t = \frac{EPS_t - E[EPS_t]}{\sigma(EPS_t - E[EPS_t])}$$

Requires actual quarterly EPS, which means **XBRL facts** — i.e.
`silver_sec_entities` must be populated first (currently empty; it is in the
Silver/Gold lane's scope). Parse `EarningsPerShareDiluted` from companyfacts.

**(b) Price-reaction surprise** — no fundamentals needed at all:

$$\text{surprise}_i = \text{CAR}_i[0,+1] = \sum_{t=0}^{+1}\left(r_{i,t} - \beta_i r_{\text{SPY},t}\right)$$

Rank the earnings-day abnormal return, then trade the continuation over
+2 … +20 days. This is well documented and is **executable today** from
`bronze_ohlcv_day` plus 8-K/10-Q filing dates, with no XBRL dependency.

**Recommendation:** build (b) first — it is achievable now and tests the drift
hypothesis directly. Add (a) once `silver_sec_entities` exists.

### Point-in-time hazard specific to PEAD
Use **`accepted_ts`, never `filing_date`.** A filing dated T may only become
public at T+1. `bronze_sec_filings` carries `accepted_ts` precisely for this.
Getting this wrong manufactures the entire anomaly.

---

## 4. Quant ML Techniques — what to adopt and why

The current ML lane uses a plain time-series split and a fixed 30-minute forward
return label. For multi-day holding periods that is not sufficient. These are
the techniques that matter here, in priority order.

### 4.1 Purged & embargoed walk-forward CV — **highest priority**
With 5–20 day holding periods, labels **overlap**: the label for day $t$ depends
on prices through $t+20$, which also appear in the features of days
$t+1 \dots t+20$. A naive split leaks. Required:
- **Purging** — drop training observations whose label window overlaps the
  validation window.
- **Embargo** — additionally drop a buffer after the validation window.

Without this, backtest Sharpe is inflated and the result is not real. This is
the single most important change to the existing ML lane.

### 4.2 Triple-barrier labelling + meta-labelling
Replace "sign of 30-minute forward return" with a path-dependent label: profit
target, stop loss, and time limit, whichever is hit first. Then **meta-label** —
a primary model picks direction, a secondary model predicts whether to *take*
the signal and at what size. Meta-labelling typically improves precision and is
how position sizing becomes learnable rather than hand-tuned.

### 4.3 Sample weighting by uniqueness
Overlapping labels break the IID assumption, so effective sample size is far
below row count. Weight each observation by its **average uniqueness** (inverse
of concurrent label overlap), and use sequential bootstrap when bagging.

### 4.4 Cross-sectional ranking, not per-name regression
For equity alpha, predict **relative** ordering. Train on a rank objective
(rank-IC / LambdaRank) over the daily cross-section rather than per-name
absolute returns. Evaluate with **rank information coefficient** (Spearman of
prediction vs forward return, per day) — the standard measure and far more
informative than ROC-AUC for a long/short book.

### 4.5 Factor-neutralised features and honest evaluation
- **Feature neutralisation:** residualise each feature against beta/industry
  before training, so the model cannot win by covertly loading on a known factor.
- **Deflated Sharpe Ratio** and **probability of backtest overfitting** to
  penalise the multiple testing implicit in trying four feature sets (A/B/C/D).
- **Combinatorial purged CV** for a distribution of out-of-sample paths rather
  than one number.
- Keep the A/B/C/D ablation, but report rank-IC and transaction-cost-adjusted
  return, not just ROC-AUC. With equal tuning per arm.

### 4.6 Models
Start with **regularised logistic/linear** on neutralised features — it is the
honest baseline. Challenger: **LightGBM** with monotonic constraints where sign
is known a priori (e.g. spread → worse fill). Avoid deep sequence models here;
with ~1,173 days of daily cross-section the sample does not support them, and
they would mostly fit noise.

### 4.7 Portfolio construction
- **Ledoit–Wolf shrinkage** covariance (sample covariance is ill-conditioned at
  $N \approx 4{,}120$, $T \approx 1{,}173$).
- Constrained mean-variance with beta/industry neutrality and position caps; or
  **hierarchical risk parity** as a shrinkage-free alternative.
- Turnover penalty in the objective — mid-frequency alpha dies on costs.

---

## 5. Execution mechanics

```
[Bronze 232M rows] -> [Silver] -> [Gold features + PIT join]
                                          |
                        +-----------------+------------------+
                        v                 v                  v
                 [Risk model: PCA/OLS]  [Alpha signals]  [Regime: breadth, ρ]
                        |                 |                  |
                        +--------> [Factor neutralisation] <--+
                                          |
                                   [Portfolio optimiser]
                                          |
                                  [TWAP/VWAP scheduler]
                                          |
                              [IBKR paper execution bridge]
```

**Slippage.** Do not model fills at the open. `bronze_ohlcv` has minute bars and
a `vwap` column, so TWAP/VWAP execution over a 2–4 hour window is **simulatable
with real data**. Reuse `strategies/cost_model.py`, which already exists.

**Short borrow.** No borrow-fee data exists in any source. Model it as an
explicit configured assumption (e.g. a bps/day haircut by liquidity decile) and
**report results both gross and net of it.** An unstated zero borrow cost is the
most common way a market-neutral backtest flatters itself.

**Capacity.** With ADV computable from `bronze_ohlcv_day`, cap position size at
a fraction of ADV (e.g. ≤1%) and report strategy capacity. Without this a
4,120-name book will show returns it could never realise.

---

## 6. Feasibility queries (reproduce the verdicts above)

```sql
-- RSP/SPY/QQQ daily coverage -> 1,173 bars each, 2022-01-03..2026-09-04
SELECT symbol, COUNT(*) n, MIN(event_date), MAX(event_date)
FROM bootcamp_students.evangoh_capstone.bronze_ohlcv_day
WHERE symbol IN ('SPY','RSP','QQQ') GROUP BY symbol;

-- RSP minute data is a 22-day fragment -> no intraday breadth signal
SELECT symbol, COUNT(*) n, COUNT(DISTINCT date(event_ts)) days
FROM bootcamp_students.evangoh_capstone.bronze_ohlcv
WHERE symbol IN ('SPY','RSP') GROUP BY symbol;

-- RSP options: 0 rows -> SPY/RSP IV spread not computable
SELECT COUNT(*) FROM bootcamp_students.evangoh_capstone.bronze_options_quotes
WHERE underlying = 'RSP';

-- Cross-sectional universe -> 20,241 symbols; 4,120 liquid (>=500d, ADV>$5M)
WITH c AS (
  SELECT symbol, COUNT(*) d, AVG(close*volume) adv
  FROM bootcamp_students.evangoh_capstone.bronze_ohlcv_day
  WHERE close IS NOT NULL AND volume IS NOT NULL GROUP BY symbol)
SELECT COUNT(*) total,
       SUM(CASE WHEN d>=500 AND adv>5e6 THEN 1 ELSE 0 END) liquid FROM c;

-- PEAD candidate set -> 18 tickers, almost all semis / mega-cap tech
SELECT DISTINCT ticker FROM bootcamp_students.evangoh_capstone.bronze_sec_filings
WHERE ticker IS NOT NULL ORDER BY ticker;
```

---

## 7. What is deliberately NOT claimed

- No analyst-estimate data exists, so classical consensus-based SUE is out.
- No index-rebalancing announcement data exists; index arb needs new ingestion
  from S&P DJI / FTSE Russell before it is more than a design note.
- No borrow-cost data; short-side economics are an assumption, not a measurement.
- No market cap or book value; Size is a liquidity proxy and Value is absent.
- Industry labels come from a repo YAML, not a vendor taxonomy.
- `silver_*` and `gold_*` are **currently empty (0 rows)**; everything here
  depends on the Silver/Gold lane landing first.
