# MFT Strategy Research Plan

| | |
|---|---|
| **Date** | 2026-10-24 |
| **Status** | Proposal. Nothing described here is built, scheduled, deployed or traded |
| **Scope** | Retail mid-frequency research on the qp1 stack (Databricks, Unity Catalog, Lakebase, Polars) for a $200,000 paper account (raised from an initial $10,000 on 2026-10-24) |
| **Verification** | Data counts for held data are taken from repository docs dated 2026-10-04 and are unverified against live tables. Vendor facts are marked **[verified]** (checked against vendor documentation on 2026-10-24) or **[unverified]**. Fees and prices are planning assumptions until entered in the effective-dated fee configuration |

## Contents

- [0. Decisions of record and glossary](#0-decisions-of-record-2026-10-24-and-glossary)
- [1. Goals and non-goals](#1-goals-and-non-goals)
- [2. Data: what we hold and what Massive offers](#2-data-what-we-hold-and-what-massive-offers)
- [3. Strategy assessment at $200k](#3-strategy-assessment-at-200k-with-massive-data)
- [4. ML and statistical methodology](#4-ml-and-statistical-methodology-shared-harness)
- [5. Per-strategy specifications](#5-per-strategy-specs-shortlist-200k-sizing)
- [6. Backtest architecture](#6-backtest-architecture)
- [7. Transaction cost and slippage model](#7-transaction-cost-and-slippage-model)
- [8. Performance metrics and evaluation](#8-performance-metrics-and-evaluation)
- [9. Data and infrastructure](#9-data-and-infrastructure-massive-first)
- [10. Operationalisation (incl. 10.1a per-trade cap, 10.1b stop-losses)](#10-operationalisation-offline-first-every-live-step-needs-maintainer-approval)
- [11. Agent reliability and hallucination control](#11-agent-reliability-and-hallucination-control)
- [12. Regime detection and adaptation](#12-regime-detection-and-adaptation)
- [13. Phased roadmap, gates and kill criteria](#13-phased-roadmap-gates-and-kill-criteria)
- [14. Risk, delivery and work packages](#14-risk-delivery-and-work-packages)
- [15. Unit and execution testing strategy](#15-unit-and-execution-testing-strategy)
- [16. Open questions and decisions](#16-open-questions-and-decisions)
- [Appendix A. Design review log](#appendix-a-design-review-log)

---

## 0. Decisions of record (2026-10-24) and glossary

| Decision | Effect on the plan |
|---|---|
| **Paper account, $200,000** (raised from $10,000) | Everything is sized for $200k, with integer shares and 100x option multipliers. Fixed fees become negligible; the per-trade and aggregate risk caps bind (Sections 7.6, 10.1a) |
| **Data vendor: Massive** (S3 flat files at `files.massive.com`, bucket `flatfiles`, plus REST) | ORATS/ThetaData are dropped. **One-month bulk acquisition** (Stocks Advanced + Options Advanced + Indices Starter, $447 list, one-time), then cancel, with forward data from our own broker collection. Conditional on a mandatory licensing gate (Sections 9.2-9.3) |
| **Options in scope, defined-risk only** | Allowed: verticals, iron condors, credit iron butterflies, long (debit) butterflies. **Not allowed:** naked legs, short straddles/strangles, delta-hedged short straddles, 1x2 ratios, risk reversals. Long straddles are replaced by defined-risk debit structures. **Calendars and diagonals are excluded for now** (Section 3.1) |
| **Best-price execution** (replaces the earlier MOC decision) | Execution minimises implementation shortfall with limit, peg and midpoint-walking orders inside a window, falling back to a marketable limit at a deadline. Gates assume a conservative crossing policy (Section 6.3) |
| **Per-trade risk cap: 0.5% of portfolio equity** | No single trade's worst-case loss (option max loss + fees, or the stressed gap for equity legs) may exceed 0.5% of current equity (**$1,000 at $200k**). Defined-risk options spreads now fit. Sized on stressed lifecycle costs (stop exits add exit fees): e.g. 10-12 XSP $1-wide (11 at a $20 credit) or 2 XSP $5-wide. Options are **paper-eligible once their research gates pass**; they are no longer backtest-only. Section 10.1a governs every sizing statement in this plan |
| **Mandatory stop-loss on every trade** | The 0.5% cap is built in through stops: no order without a pre-defined stop. Sizing = 0.5% equity / (stop distance + slippage + gap allowance). Section 10.1b |
| **Paper host undecided (IBKR paper or Schwab paperMoney)** | Use a broker-adapter interface, and do not commit to either (Section 10.3) |
| **Tax** | Capital gains are 0%. Dividend withholding is **30%** (maintainer figure), modelled in every backtest as a ledger cost; shorts pay 100% in lieu (Section 7.7). No other tax work |

### Glossary: the two terms the maintainer asked about

**Holdout.** A holdout is a block of history (here **2016-01 to 2021-12**) that nobody looks at while designing
strategies.
- **Why it is needed:** 2022-26 has already been studied by earlier qp1 work, so a test on 2022-26 is biased.
  Each sleeve's frozen final rules are run on the holdout **exactly once** for a pass/fail. A failed holdout is
  used up and cannot be "fixed" by tweaking the strategy.
- **Data needed:** Massive stock/ETF daily history back to at least 2016-01, plus 2003-2015 for development.
  - Massive day-aggregate flat files start **2003-09-10 [verified]**.
  - Stocks **Developer ($79/mo) only gives a rolling 10 years [verified]**. On 2026-10-24 that reaches about
    2016-10, so it **misses Jan-Sep 2016**.
  - **Stocks Advanced ($199/mo, full history) [verified]** is required, bought for **one month** (Section 9.2).
    The 2016-2021 daily bars come in the same pull and are written to restricted storage and hashed at download.
- **How it is sealed:**
  1. A restricted ingest writes the window to a separate UC table or volume that research snapshots cannot
     read.
  2. A manifest (file list + SHA-256 + Delta version) is recorded in the run registry.
  3. The registry rejects any research run whose input manifest overlaps the window.
  4. Every access is logged.
  5. **All sleeve families are frozen jointly** before the first opening, so one sleeve's result cannot leak into
     another's design.
- **Who opens it:** a **restricted, deterministic evaluation job** that the maintainer authorises explicitly. The
  final-gate reviewer inspects the job's report.
  - Model identity is not a security boundary, so the opener is the job, not a model.

**`data_source` codes.** By maintainer rule, every row a qp1 table produces carries a provider code from
`config/data_sources.py`. The current set on main is `massive, sec_edgar, sec_companyfacts, hyperliquid,
binance_um, config, derived`.
- **Recommendation: add no new codes now.**
- **Granularity:** codes are provider-level. A provider gets a sub-code only when it has a distinct API, as
  with `sec_edgar` vs `sec_companyfacts`. Every Massive dataset stays `massive`.
- **Which dataset:** a new **`source_dataset`** column records it, e.g. `massive:us_stocks_sip/day_aggs_v1`,
  `massive:us_options_opra/quotes_v1` (path prefix *unverified*), `massive:rest/dividends`,
  `massive:us_indices/day_aggs_v1`.
- **Other lineage columns:** retrieval time, entitlement tier, object ETag/hash and transform version.
- **Simulated fills** are `derived`.
- **Codes to add later, each in its own vocabulary PR at the time its first rows are written:**
  - `ibkr` and/or `schwab`, when real broker fills or positions are ingested;
  - `fred`, when FRED-sourced rows (the financing benchmark) are first written under the rule.
  - No speculative codes.

---

## 1. Goals and non-goals

**Goals**
1. Falsify cheaply. A documented rejection is a deliverable.
2. Build one shared harness: contracts, registry, **metrics/tearsheet**, ledger, costs, daily engine and a small
   options event engine.
3. Statistics come first. ML is a challenger that must beat a frozen rule after costs.
4. Promote at most 2-3 sleeves into the $200k paper account, only through frozen gates (Sections 8 and 11).
5. Size for a real $200k account under the 0.5% per-trade cap. Paper results must be achievable at that size:
   integer shares and contracts, margin, borrow, assignment funding.

**Non-goals**
- No latency games (L2/OFI, 0DTE, intraday stat-arb).
- No undefined-risk options.
- No Kelly sizing.
- No broker connection, scheduling, live money, shared-signal writes or warehouse/app start without **separate
  maintainer approval** for each.
- No profitability claims from 2022-26 equity data.
- No pandas in new code. Perps are `instrument_type=perpetual_future`.

---

## 2. Data: what we hold and what Massive offers

### 2.1 Held today (per docs 2026-10-04, unverified live)
| Asset | What exists | Gaps |
|---|---|---|
| Equity/ETF bars | `bronze_ohlcv` minute + daily: ~232M rows (README 2026-10-05 says 73.3M in `bronze_ohlcv`, which conflicts, so audit it), 20,241 symbols, ~4,120 liquid, from **2022-01-03**. SPY/RSP/QQQ: 1,173 daily bars to 2026-09-04 | No pre-2022 data. RSP minute data covers 22 days only |
| Adjusted daily | `silver_ohlcv_day_adjusted` (splits applied, 174 masked breaks; 16:30 NY availability) | **No dividends**, so no total return |
| Universe | `gold_tradable_universe` (PIT top-N by ADV, 2022+) | No market cap, no GICS, no delisting returns |
| Options | Quotes/trades for **12 underlyings** (SPY QQQ META AMD TSLA GOOGL MSFT NVDA AAPL AMZN JPM XOM) over weeks of snapshots (22-33 expiries); `bronze_options_day` has 152M contract-day rows | No SPX/XSP. Not backtestable |
| SEC / other | EDGAR + submissions (mostly semis/mega-cap tech), XBRL facts, COT, FRED, splits, 10 commodity ETFs | No consensus estimates, index announcements, L2 or borrow fees |
| Code | pandas `strategies/backtest.py` (t+1 close fills), `cost_model.py`, `etl/slippage.py`, `gold/pit_guard.py`; `execution/bridge.py` is a stub | Synthetic-only ML ablation |

Measured hurdle: residual reversion gross Sharpe 0.68, **net 0.12**, -0.45 at 2x costs.

### 2.2 Massive plans and datasets (list prices per month; annual billing saves 20%)
| Dataset / plan | Fact | Status |
|---|---|---|
| Stocks Starter $29 / Developer $79 / Advanced $199 | 5y / 10y / 20+y history. All three include flat files. Developer adds trades; Advanced adds trades + quotes + real-time | [verified] |
| Stocks day aggregates (flat) | Records from **2003-09-10**. Depth by plan: Starter 5y, Developer 10y, Advanced full | [verified] |
| Stocks minute aggregates / trades / quotes (flat) | Exist (`us_stocks_sip/*`). Start dates not stated | [unverified] |
| Dividends REST | `cash_amount, ex_dividend_date, pay_date, record_date, declaration_date, distribution_type, frequency, historical_adjustment_factor, split_adjusted_cash_amount`, from **2000-01-15**, full history on every paid Stocks plan | [verified] |
| Splits REST | Already used by qp1 | held |
| Options Starter $29 / Developer $79 / Advanced $199 | 2y / 4y / "5+y". All include flat files. Developer adds trades; **Advanced adds trades + quotes** | [verified] |
| Options **quotes** (flat, top of book, nanosecond `sip_timestamp`, bid/ask price, size and exchange) | Records from **2022-03-07**. Advanced/Business only. **All US options**, not just our 12 | [verified] |
| Options trades / day aggregates (flat) | Records from **2014-06-02** (trades: Developer+; day aggregates: Starter+) | [verified] |
| Index options (SPX, XSP) | Covered by the Options subscription. Snapshot greeks need the `I:SPX` ticker | [verified] (FAQ) |
| Historical OI, IV, greeks as flat files | None listed. IV and greeks must be computed from quotes (rates, dividends, synchronised underlying). OI history is unavailable, so B2 stays dead | [unverified] |
| Indices Starter $49 / Advanced $99 | All index tickers incl. SPX/VIX (Basic excludes them), "1+ year" history, flat files (values, minute, day). Index flat-file start date not stated | [verified] tiers; depth [unverified] |
| Maintainer's current entitlement | Holding data from 2022 suggests a Starter-type tier | [unverified]. First check: list S3 prefixes for 2016 and for `us_options_opra/quotes_v1` (maintainer action) |

**Implications:**
- **Equity sleeves:** need **Stocks Advanced** for the 2003-2015 development data and the 2016-21 holdout.
  Dividends come from REST on any paid plan.
- **Options sleeves:** quotes exist only from **2022-03-07**, about 4.6 years or ~230 weekly cohorts. That span
  covers the 2022 bear market, 2024-08-05 and April 2025, but **not 2018 or 2020**.
  - Pre-2022 trades and day aggregates support **contract-availability checks and stress-scenario calibration
    only**. They cannot price executable packages: an absent trade is not an absent market, and day high/low
    across legs creates fictional fills.
- **Holdout status of options history:** 2022-26 options quotes have never been studied for options signals, so
  using them is a **retrospective options evaluation under a frozen protocol**. It is not a clean holdout, because
  the economic hypotheses were chosen after seeing 2022-26 equities. Forward paper observations supply the
  independent evidence.
- **Cost:** a **one-time** one-month purchase of Stocks Advanced + Options Advanced + Indices Starter is **$447 at
  list**. Storage, compute and broker data fees come on top. It is conditional on the licensing gate (Section 9.2).
  No continuous subscription is planned.

---
## 3. Strategy assessment at $200k with Massive data

Rank is for the $200,000 paper account. The per-trade worst-case-loss cap is 0.5% ($1,000), and the proposed
aggregate open-risk cap is 5% (Section 10.1a).
- **G** = GO research.
- **C** = conditional.
- **B** = backlog.
- **N** = NO-GO.

| Rank | # | Strategy | Data (Massive) | $200k feasibility | Stats vs ML | Main risk | Verdict |
|---|---|---|---|---|---|---|---|
| 1 | A6 | ETF relative strength, up to **6 pairs** from RSP/SPY-equivalent, IWM/SPY-eq, SPLV/SPHB, XLK/XLU, EFA/SPY-eq | Stocks Advanced (2003+) + dividends REST | **Feasible.** Each pair is one trade unit at WCL about $500 (legs about $3.3k at planning G = 15%). Fees are negligible. ETF ADV floor $20m | Frozen rule; ridge challenger | A factor tilt; pair stress definition | **G** |
| 2 | B1 | Defined-risk VRP on **XSP and SPX** (cash-settled European); SPY limited to 1 contract by the assignment rule | Options Advanced (quotes 2022-03+) + Indices Starter (SPX values) | **Contracts now fit** (stressed lifecycle costs): XSP $1-wide 10-12, $3-wide 3-4, $5-wide 2; SPX $5-wide about 2, $10-wide 1. Executable economics remain unproven (friction gate at 2x costs, quote trial) | HAR-RV + threshold rule | Tail-dominated; no 2018/2020 in the quotes | **C**, paper-eligible once gates pass |
| 3 | A1 | ETF pairs (KRE/XLF, XHB/ITB, GDX/GLD, XLY/XRT, XLE vs XOP; GLD/IAU control), **up to 2 pairs** at WCL about $1,000 | Same as A6 | **Feasible**: legs about $6.6k; borrow availability is checked daily | OLS z rule; Kalman challenger | Crowded; cointegration breaks; stop whipsaw | **C** |
| 4 | A4 | EAR drift, concentrated: **about 5 names at WCL about $400** (about $2k each, beta-hedged) | Stocks + EDGAR 8-K timestamps (SEC dependency) | **Feasible small book** (about $2k sleeve WCL). A new registration | Sorts / clustered regression; no ML | Timestamp audit; event/hedge clustering | **C** |
| 5 | B3 | Skew/term with **same-expiry defined-risk structures only** | Options Advanced quotes 2022-03+; IV computed from quotes | Contracts fit as for B1 | Linear signal + one structure | Synchronised surfaces; Reg-T structure recognition | **C**, after B1 |
| 6 | B4 | Earnings crush (iron condor / credit iron butterfly), **single names, 1 contract** | Options Advanced + EDGAR timing | **Limited pilot**: 1 contract per name under the assignment-notional rule, after broker assignment drills | Hierarchical shrinkage | Event timing; tails; assignment funding | **C, limited**, after A4 audit and B1 |
| 7 | A5a | TOM overlay | Stocks Advanced | **Trivial under the cap**: one long broad-ETF trade of about $5k (G = 20%) earns about $25-75/yr incrementally | Newey-West + block bootstrap | Weak, old effect | **Research only** |
| 8 | A2 | Option-flow imbalance | Options Advanced | -- | Feature research only | Noisy signing | **Research feature only** |
| 9 | -- | Residual-reversion rescue | Held | No longer size-blocked; its failure was **cost-driven** | Rule | Costs | Bounded falsification, then park |
| 10 | B5 | Dispersion (defined-risk version) | Data-feasible from 2022 | Basket granularity and stress capacity are still insufficient | -- | Many legs | **B, feasibility backlog** (was NO-GO for size) |
| 11 | B2 | GEX | No OI history; dealer sign unobservable | -- | -- | -- | **N** (data-driven, unchanged) |
| 12 | A3 | OFI / volume profile | Stock quotes need Advanced | -- | -- | Decays below retail latency | **N** (unchanged) |
| 13 | A5b | Index reconstitution | No announcement data | -- | -- | -- | **N** (unchanged) |

**What changed with size, and what did not:**
- **Size removes implementation barriers, never a failed edge, cost or data gate.**
- **Re-verdicted because they were size-driven:** B1/B3/B4 move from backtest-only to **paper-eligible after
  their gates**. B5 moves from NO-GO to feasibility backlog. Residual is no longer size-blocked but stays parked
  on cost.
- **Unchanged because they were data- or edge-driven:** A2 stays a research feature; A3, B2 and A5b stay NO-GO.
- **TOM** becomes research-only because the per-trade cap makes it economically trivial.

### 3.1 Defined-risk compliance check of the B-list (maintainer rule)
- **B1:** put credit spreads and iron condors are fine. **Delta-hedged short straddles/strangles are removed.**
  0DTE stays excluded (cost and latency).
- **B2:** "short gamma -> long straddles" would have to become debit spreads. The sleeve stays NO-GO anyway.
- **B3:**
  - Risk reversal -> **call-vertical-vs-put-vertical** with every leg, expiry and package max loss specified.
  - 1x2 put ratio -> **not allowed**. The substitute is a broken-wing butterfly with **1:2:1 quantities**, ordered
    strikes and an explicit unequal-wing max-loss calculation.
  - **Calendars and diagonals: excluded initially**. A later-expiring long leg does not cap the loss at
    the debit: short $100 call + long later $105 call can lose the $5 strike gap ($500) beyond the debit. American
    exercise and financing add further paths.
- **B4:** iron condor or **credit** iron butterfly (to be distinguished from a debit/reverse iron butterfly). On
  American single names, assignment handling is mandatory.
- **Replacing long straddles:** a debit vertical is directional and capped, so it does **not** reproduce a
  straddle's two-sided convexity. A two-sided substitute is a long call vertical + long put vertical (a defined
  "strangle-as-spreads"), registered as its own structure.
- **American legs (SPY, single names):**
  - Short calls risk assignment before ex-dividend when remaining extrinsic value < the dividend.
  - Deep-ITM short puts risk early assignment.
  - Assignment creates stock exposure, and the long leg does **not** auto-exercise to cover it.
  - Requirements:
    - assignment detection;
    - capital or margin to carry 100 shares overnight (about $65k per SPY contract). At $200k, the
      assignment-notional rule (Section 10.1a) limits SPY to one 1-contract vertical, and the broker may
      force-liquidate;
    - a deterministic liquidation policy;
    - **close any short leg whose extrinsic value is below its next dividend before the ex-date**;
    - close everything at T-1.
  - This is why **XSP (European, cash-settled) comes first.**

---
## 4. ML and statistical methodology (shared harness)

### 4.1 Model roles

| Role | Default | Challenger | Not now |
|---|---|---|---|
| Signal (A6, A1) | Frozen rule | Ridge/elastic net, <= 8 pre-registered features | Random forest. For importance, use grouped chronological ablation instead |
| Hedge ratio (A1) | Rolling OLS 120 (60/252 as robustness reports) | Kalman (process noise is a registered hyperparameter) | OU + hazard + Johansen stack. Use ADF only as a screen |
| Vol forecast (B1, sizing) | HAR-RV with an overnight term, QLIKE loss | GARCH(1,1)/GJR | Deep vol |
| Regime | Continuous 20d RV and 60d trend, or one frozen threshold | 2-3 state HMM, filtered, expanding fit (later) | HMM as the default |
| Events (A4, A5, B4) | Sorts, event study, calendar-time portfolio, clustered regression | Hierarchical shrinkage (B4) | Any per-name ML |
| Nonlinear | -- | LightGBM: depth <= 3, >= 200 rows per leaf, monotone constraints | Deep nets |
| Calibration | Platt, fitted out of sample | -- | Isotonic |

**No ML for:**
- A4 (1-2 variables; events cluster by date and sector);
- A5 (~240 months);
- B4 (12-16 events per name);
- any sleeve with fewer than 1,000 independent episodes.

**Meta-labeling** is deferred until a sleeve has **>= 1,000 non-overlapping entries including >= 200 losses**. It
then predicts E[net P&L] and is used only for abstention or sizing.

### 4.2 Labels and purging
- **Label:** the net P&L of the **registered position policy** for that variant. The same policy drives the
  backtest, so convergence exits and time stops are included.
- **Purge interval:** [decision time, latest possible exit]. Train rows whose interval overlaps the test block are
  dropped, and so are labels not yet observable at the cutoff.
- **Triple-barrier** is not the default. Stops and targets go to the event engine, which resolves a simultaneous
  touch as the stop.

### 4.3 Data periods and holdouts
qp1 has studied 2022-26, so that period is **consumed**. Pre-2022 history has never been loaded and is therefore
unseen.

| Sleeves | Development | Frozen holdout (opened once, ledger-logged) | Fresh evidence after that |
|---|---|---|---|
| Daily ETF sleeves | Inception (or 2003) to 2015 | 2016-2021 | 2022-26 is a sign check only; then prospective shadow data |
| TOM | 2003-2015 (Massive day aggregates start 2003-09-10) | 2016-2021 | Prospective shadow data |

- An **access audit** before each sleeve starts reclassifies any period already viewed for that signal as
  development.
- Sleeves with no unseen history (A4, B1) use prospective shadow data as the holdout. The 2022-26 options quotes are a retrospective evaluation under a frozen protocol (Section 2.2).
- **"3 of 4 blocks":** after a 2-year warm-up the development period is split into 4 equal contiguous blocks.
  Retraining is every 63 sessions on an expanding window. Both are frozen in the family YAML.

### 4.4 Inference: one primary test per question
- **(a) Absolute:** a family-simultaneous one-sided 95% lower bound on net Sharpe. It uses a max-statistic
  (Romano-Wolf) stationary block bootstrap on calendar-time daily portfolio P&L, with 5,000 resamples. This also
  covers the frozen rule.
- **(b) Relative:** Hansen SPA of each challenger against the frozen rule, on net P&L differentials.
- **Bootstrap block length** = max(10, 2 x the maximum holding period) sessions, with sensitivity at 0.5x and 2x.
- **Diagnostics only:** DSR (raw N and an effective-N range), PBO (CSCV) and BH-FDR across sleeves.
- **CPCV** (N=6, k=2) is sensitivity analysis and never counts as evidence.
- **Pseudo-replication:** all inference runs on aggregated calendar-time P&L. Event sleeves cluster by issuer and
  date.

### 4.5 Power
With IID-normal returns, `T ~ 6.18 / S^2` years are needed:

| Net Sharpe | Years needed |
|---|---|
| 0.5 | 24.7 |
| 0.75 | 11.0 |
| 1.0 | 6.2 |

For episodes, `n ~ 6.18 / d^2` (d=0.10 needs 620 independent episodes). Shadow and live trading therefore test
the implementation, not the alpha.

### 4.6 Trial ledger
- At most 12 configurations per family. The YAML is committed before the first run and registers the **full
  selection tree**: universe/pairs, rule parameters, construction, the cost scenario used for selection, and each
  challenger.
- The residual rescue gets 4 incremental runs, but its multiplicity N is >= 14 because r1-r10 count.
- A 13th run needs a new family and unseen data.

### 4.7 Sizing
- **Vol targeting** with sigma = max(EWMA lambda=0.94, EWMA lambda=0.985, 1y 90th-percentile floor), reusing
  the `risk/` estimators.
- **Initial budgets are standalone per sleeve**, as set in Section 5 for the $200k account.
- **Portfolio check:** a Ledoit-Wolf constant-correlation covariance, with stress replays.
- **No Kelly.**

---

## 5. Per-strategy specs (shortlist, $200k sizing)

**Common to all sleeves:**
- The decision is made at bar close t; daily data is available at 16:30 NY. **Execution is best-price on
  t+1** (Section 6.3): registered schedules S-open / S-close / S-part, gated on the conservative crossing scenario.
  A signal that uses day t's close can never fill at day t's close.
- **Sizing at E = $200,000 (paper):** the binding limits are the **0.5% per-trade WCL cap ($1,000)**, enforced by
  mandatory stops, and the **5% aggregate open-WCL cap ($10k, proposal)**. Both are in Section 10.1a.
  - **Aggregate WCL budget by sleeve (proposal):**

| Sleeve | Share of NAV | Dollars | Allocation |
|---|---|---|---|
| A6 | 1.5% | $3k | 6 pairs x $500 |
| A1 | 1.0% | $2k | 2 pairs x $1,000 |
| A4 | 1.0% | $2k | 5 names x $400 |
| Options (B1/B3/B4) | 1.5% | $3k | 3 trades x <= $1,000 |
| TOM | 0 | $0 | Research only |

  - A **joint stress-scenario loss limit** also applies (Section 10.1a). The portfolio vol ceiling stays 5%
    ($10k/yr). The caps bind well before it: expected portfolio vol is about 1-2% of NAV.
  - **Joint sizing, deterministic:**
    1. Options max loss is reserved first (Reg-T margin, Section 10.1a).
    2. Each trade is sized by `q = floor(min(budgeted WCL, 0.005 x E) / WCL_unit, ...)`.
    3. If targets exceed a sleeve's WCL budget, scale in reverse priority (A4, then A1, then A6).
    4. Re-apply the lot preference (`price <= leg/20`, a granularity preference, not a risk rule), hedge ratios,
       margin, borrow and stress checks after scaling.
  - Short legs are held in a margin account.
- Costs per Section 7; metrics per Section 8; results go to `strategies/results/<sleeve>_rN.md` plus registry
  rows.

**5.0 Residual rescue (bounded falsification)**
- 4 runs: baseline, hysteresis 2.5/1.0, 2-day rebalance, combined.
- The pass is turnover <= 14%/day with >= 75% of gross retained and net > 0 at 2x variable costs.
- No longer size-blocked at $200k, but its failure was cost-driven: it stays parked unless the 4-run rescue passes.

**5.1 A6 relative strength**
- **Universe:** up to 6 pairs live, each one trade unit with WCL <= $500 (its share of the sleeve budget).
  - **Pair unit and stress:** the unit is the complete hedge bundle. G_rel is the **adverse relative return of the
    bundle** (long-leg return minus beta x short-leg return) over the stress window. Planning G_rel = 15% of
    long-leg notional gives about $3.3k legs. An empirical worst observed x 1.25 (e.g. 7% x 1.25 = 8.75%) gives
    about $5.7k legs, to calibrate in WP9.
  - A stress is never changed to accommodate a lot size.
  - Lot preference `price <= leg/20` is a granularity preference. SPY at about $650 needs a lower-priced
    equivalent or a fractional/smaller share count where permitted. Any substitute ETF needs its own liquidity,
    tracking, borrow and history checks.
  - ETF ADV floor: $20m.
  - SMH/SOXX is a diagnostic.
- **Signal:** 60d/120d log-ratio TSMOM or the 100d MA on the ratio, rebalanced weekly at Friday 16:30 and
  executed on Monday (Section 6.3).
  - s in {-1, 0, +1}; dead zone |signal| < 0.25 x sigma_ratio x sqrt(L).
  - s = +1 is long A and short beta x B. Beta is the 252d OLS at t-1. |net SPY beta| <= 0.1 x sleeve gross.
- **No-trade band:** 10% of the sleeve target gross. With weekly decisions, expect about 10-20 orders per pair per
  year.
- **Family:** 8 of 12 slots:
  - 3 rules x 2 decision frequencies (weekly Friday; daily);
  - a long-only tilt;
  - ridge on exactly 8 features: 20/60/120d ratio returns, distance from the 60d mean, ratio RV 20d, leg beta
    252d, beta gap 60d-252d, relative dollar volume.
- **Benchmarks:** always long the ratio, 12-1 momentum, and SPY.
- **Execution schedule is frozen independently, not inside the family.** The cost-based execution study
  (WP14, on 2022+ minute data, measuring execution cost only, not alpha) picks one of S-open, S-close or S-part
  before any strategy run. The historical gate then uses that schedule's daily proxy (Section 6.3).

**5.2 A1 ETF pairs**
- **Screen:** ADF p < 0.10 on the training window.
- **Signal:** z(60) enters at |z| >= 2 and exits at |z| <= 0.5.
- **Time stop:** 2x the training-fold median convergence time, capped at 10 sessions.
- **CUSUM guard:** a 5% boundary closes the trade and suspends the pair; re-entry needs a passing 63-session
  refit.
- **Family:** 6 pairs x {OLS-120, Kalman} = 12, with the schedule frozen as in A6. Live: up to 2 pairs at WCL about
  $1,000 (legs about $6.6k at planning G_rel), chosen by a frozen priority order.
- **Stops:** whichever triggers first of the z-stop (abs(z) >= 3.5), the $700 pair dollar stop and the 10-session
  time stop. The remaining $300 covers gap overshoot and costs; stress sizing still governs.
- **Execution:** synchronised two-leg best-price working with the imbalance bound B and the cancel-both rule
  (Section 6.3).
- **PDT:** at $200k equity the PDT limit no longer binds (*verify* the broker rule). Hourly variants remain
  registered research options only.

**5.3 TOM overlay**
- **Research only at $200k:** the per-trade cap limits a single long broad-ETF trade to about $5k (G = 20%), or
  about $7.7k at an empirical 13%. The incremental edge is about $25-75/yr, so TOM is kept as a research
  hypothesis, not a paper sleeve.
- **Rule (research):** a base holding, raised so that the position is held through the closes of sessions **D-1,
  D+1, D+2 and D+3**, where D+1 is the first trading day of the month.
- **Timing:**
  - The add decision is at 16:30 on D-3, and the order fills in the **S-close window of D-2**, so the position is
    held from roughly the D-2 close.
  - The reduce decision is at 16:30 on D+3, and the order fills in the S-close window of D+4.
  - TOM always uses S-close. Holidays follow the NYSE calendar.
- **Test:** incremental return vs the same average exposure, including financing and cash yield.
- **Allowed interaction:** one, trailing RV above or below its median.

**5.4 A4 EAR (new concentrated policy)**
- **Event timing:** release time = the earliest verified public time; pre-09:30 releases map to the same session.
  EAR = the [0, +1] abnormal return. **Entry is in the session +2 execution window.**
- **Admission:** an event is admitted at its session +2 decision if
  |EAR| >= a **frozen threshold**. The threshold is the trailing-252-session 90th percentile of |EAR| over events
  whose EAR completed before the decision. Capacity is at most 5 open positions at WCL about $400 each (about $2k notional at G = 20%; sleeve WCL budget
  $2k), first come
  first served; events arriving while capacity is full are skipped and logged. Positions are held 20 sessions in
  the PIT top-1,000 liquid names. Longs and shorts each have their own registered variant; short availability and borrow are modelled.
  A beta hedge uses the S&P 500 ETF.
- **Dependency:** Massive covers prices. The **EDGAR ingest is a declared non-Massive dependency** (`sec_edgar`).
- **Gate 0:** a 100-event audit with zero entries before the verified release.
- **Holdout:** prospective collection (Section 10.5).

**5.5 B1 defined-risk VRP**
- **Instrument order:**
  1. **XSP** quote trial first (European, cash-settled; liquidity and spreads *verify*).
  2. **SPX** (same $100 multiplier; wider strikes): $5-wide about 2 contracts, $10-wide 1 contract under the
     $1,000 cap. XSP and SPX are compared on **matched exposure under the 2x variable-cost crossing scenario**,
     not on width.
  3. **SPY: limited to 1 contract** by the assignment-notional rule (aggregate assignable notional <= 50% of
     equity = $100k; one SPY contract is about $65k). The ex-dividend and T-1 controls also apply.
- **Contract counts under the $1,000 cap** (WCL with stressed lifecycle costs of about $8 per 2-leg spread):
  XSP $1-wide 10-12 (11 at a $20 credit), $3-wide 3-4, $5-wide 2; SPX $5-wide about 2, $10-wide 1 (Section 10.1a).
- **Status:** paper-eligible once the research gates, the friction gate and the quote trial pass.
- **Cohorts:** enter in the **Monday 15:00-15:40 ET** window into **that week's
  Friday** expiry (4 DTE). Exit at XSP Friday cash settlement or the SPY Thursday 15:30 close. The next entry is
  the following Monday.
- **Signal warm-up:** the percentile uses an expanding window, with a 63-session minimum and 252 sessions once
  available (registered).
- **Eligible cohorts:** quotes from 2022-03-07 minus the 63-session warm-up (to about 2022-06) give about **229 raw
  weekly cohorts** to 2026-10. After quote failures and holiday weeks, expect about 200-220.
- The cohort count is a **disclosure** (Section 8.5) and drives the power statement. It is not an eligibility
  gate.
- **Exit variants:**
  - **(a) Hold to cash settlement (XSP/SPX):** saves the closing fees and crossing; it does not remove the entry
    costs or contingent liquidation costs.
  - **(b) T-1 15:30 close:** mandatory for SPY.
  - **(c) Close at 50% of max profit.**
- **Signal:** IV^2 (computed from quotes) minus the HAR forecast of matched-horizon variance including overnight,
  above its trailing-252d 60th percentile. Events are a registered feature, with no blanket exclusion.
- **Stress (not backtest):** reprice open packages under **parametric** shocks (spot gap, vol jump, impaired exits)
  calibrated only from data up to 2015-12 and from 2022-03-07 onward. The 2018-02 and 2020-03 episodes lie in the
  sealed 2016-2021 holdout and enter only as parametric shocks until the single opening.
- **Holdout:** the 2022-26 quotes are a retrospective frozen-protocol evaluation, followed by prospective
  collection of >= 52 cohorts.

---
## 6. Backtest architecture

### 6.1 Engines
| Engine | Use | Basis |
|---|---|---|
| **Daily engine (Polars, vectorised)** | Residual, A6, A1, TOM, A4 | New `strategies/mft/daily_engine.py`: target positions -> orders -> fills -> ledger |
| **Event engine (small, per-order state machine)** | Options packages; intraday stops and targets; limit-order brackets | New `strategies/mft/event_engine.py`. Order states: submitted, partial, filled, cancelled, rejected. Events: expiry, settlement, assignment |
| **Legacy pandas engine** | Reproducing residual r10 only | Kept unchanged. `legacy_adapter.py` must produce identical orders and ledger events, with returns at abs tol 1e-10 |

- The engines share **one accounting ledger, calendar, instrument specification and fee library**.
- v2 economics (dividends, effective-dated fees) are a separate mode, not a parity target.
- No general execution platform is built before the daily research path works.

### 6.2 Correctness rules
- **PIT:** every input row carries `information_available_ts`. `pit_guard` covers universe selection, feature
  vintages and corporate actions, not just final joins. Daily bars become usable at 16:30 NY, minute bars one bar
  later. Bars are grouped by NY date.
- **Prices:**
  - Raw executable prices + an explicit corporate-action ledger. Splits change quantity.
  - **Dividends:** on the ex-date, accrue a **receivable** (longs) or a **payment-in-lieu liability**
    (shorts) on the quantity entitled at the prior close. The accrual settles to cash on the pay date. Closing the
    position between the ex-date and the pay date does not cancel the accrual.
  - Signals use causal total returns, never back-adjusted levels.
- **Financing:** effective-dated rates in `fee_schedules.yaml`.
  - Cash credit = benchmark - 0.5% on the balance above the broker threshold.
  - Debit = benchmark + 1.5%.
  - Short proceeds are credited at benchmark - 0.25% (all are planning defaults).
  - Benchmark = the FRED effective fed funds rate. The `fred` code is added **before** any FRED row is
    ingested; `derived` is reserved for transformations. The TOM matched-exposure benchmark includes the same cash yield.
- **Survivorship:** the universe is rebuilt per date from `gold_tradable_universe`, including delisted names.
  - **Hindsight bias:** the candidate ETF lists for A6 and A1 were chosen with 2026 knowledge of which ETFs survived
    and stayed liquid. Results are also reported on a PIT-eligible ETF universe at each date (inception, ADV floor),
    and the bias is disclosed.
  - **Terminal events:** reconcile the cash consideration, merger conversion or recovery.
  - **Unresolved longs:** a scenario set including **-100%**, and shorts get no symmetric windfall.
  - Results that depend on terminal marks are excluded from promotion.
- **Calendar:** NYSE sessions, DST, holidays and early closes, all effective-dated.

### 6.3 Fill models: best-price execution (maintainer change; replaces MOC)

**Objective.** The maintainer's "best price" means minimising implementation shortfall against the *signal* price,
subject to a completion deadline. It never means the best price observed after the fact.

Two benchmarks are always recorded (Section 7.1):
- `IS_total = s*Q*(P_fill - P_signal) + fees`
- `IS_exec = s*Q*(P_fill - M_arrival) + fees`

Their difference is the delay cost.

**Execution schedules.** Three candidates are compared once, on identical target orders, in the WP14 execution
study (cost only). That study sits **outside the strategy families**; one schedule is frozen before any strategy
run:

| Schedule | Window |
|---|---|
| **S-open** | 09:35-10:30 ET on t+1, after the opening auction |
| **S-close** | 15:00-15:50 ET on t+1 |
| **S-part** | A fixed participation schedule across the session |

The signal is frozen at 16:30 on day t.

**Order mechanics (operational policy):**
1. **Start:** a midpoint peg, or a limit at the near touch where pegging is unavailable. Prices are always set
   relative to the **current** NBBO.
2. **Repricing:** every 5 minutes, move toward the far touch by **max(1 tick, 25% of the current spread)**, inside
   an absolute collar of +/- max(5 bps, 2 ticks) around the arrival mid.
3. **Deadline (window end):**
   - **Required reductions and exits** become marketable limits (far touch + collar), with up to 3 one-minute
     retries. After that, an UNRESOLVED-position alert fires and the position is recorded.
   - **Entries** expire under an explicit target-state rule.
   - An A6 sign reversal is split into "close existing" (required) and "open new" (entry).
4. **Time in force:** DAY, with an explicit cancel 2 minutes before the close, then reconciliation.

**What the gate assumes.** The **gate scenario is a reproducible crossing policy**: a
marketable limit at the window start, at the modelled half-spread + impact, with the 2x stress. Passive price
improvement is **sensitivity only** until execution evidence exists.

**Which policy may run:**
- The paper account may run the maintainer's passive best-price policy, because that is how fill evidence is collected.
- **Small live may run a passive policy only if its own full-path backtest (scenario P1, including missed entries,
  partial legs and deadline crossings) also passes gates 2-3.** Otherwise small live runs the evaluated crossing
  policy G.
- Passive gains beyond P1 need live-order evidence (below).
- Failure tests run for every policy: missed deadline, partial leg, rejected order, halt.

**Historical execution data.**
- Massive minute and quote coverage for 2003-2021 is *unverified*, and Massive day aggregates carry **no VWAP**.
- The development and holdout gate therefore uses a **frozen daily proxy** of the chosen schedule:
  - S-open: next-session open;
  - S-close: next-session close;
  - S-part: the next-session (O+H+L+C)/4.
  - Each proxy adds half-spread + impact + a 3 bps timing-uncertainty stress, and the 2x stress applies.
- Minute-bar G/P1/P2 simulation runs only where minute coverage exists (2022+ held). It is used to choose the
  schedule in the execution study (cost only) and to bound the proxy's error.
- No schedule may be selected using intraday paths that are unavailable for the gated period.

**Backtest scenarios:**

| Scenario | Fill rule (minute bars; quotes where available) | Role |
|---|---|---|
| **G: crossing** | Window start: minute-open price proxy + half-spread + impact + timing-uncertainty stress | **Gate** |
| P1: passive, conservative | Submit or reprice only at minute boundaries, and evaluate only *subsequent complete* minutes. A buy at L fills only on a **trade-through** (low <= L - 1 tick). Fill quantity <= q x minute volume, with q = 5% registered (sensitivity 1% and 10%; at $1k orders the cap rarely binds, so it is not evidence of queue access). Partials and cancels are tracked. The remainder at the deadline crosses as in G | Sensitivity |
| P2: passive, optimistic | Touch fills; midpoint fills at mid | Upper bound only |

- The **2x stress** applies to **all** variable costs: passive fills' modelled costs, hedges, flattening and
  deadline crossings.
- "Everything crosses immediately" is a different policy, not a pessimistic bound, because waiting can be better or
  worse.

**Selection bias.** Non-fills are biased toward winners, because the price ran away. Every policy is therefore gated
on the **complete portfolio path**: residual holdings, partial trades, aborted-entry round trips, financing and
borrow.
- Fill rates are reported **conditional on** direction, signal strength, volatility and the subsequent return.
- The hypothetical P&L of missed trades is a **diagnostic**. It is never used to chase trades selectively, and there
  is no fixed "missed-trade %" threshold.

**What minute bars cannot prove:**
- queue position;
- hidden or midpoint liquidity;
- whether the order was resting before the low printed;
- cancel/fill races;
- broker routing quality;
- that the minute close was executable.

Massive stock **quote** flat files (Stocks Advanced; start date *unverified*) improve the NBBO reconstruction but
still cannot show queue priority.

**Calibration (paper, then small live):**
- **Log per order:** signal price, arrival NBBO, every reprice, acknowledgement, fill, cancel, the minute path, and
  contemporaneous quotes.
- **Paper fills** validate plumbing only.
- **Passive fill assumptions may enter a gate only with:**
  1. actual small live orders;
  2. a pre-specified fill model with untouched chronological validation;
  3. coverage of every enabled bucket;
  4. a gate that still holds under the conservative bounds.
- **Precision needs:** estimating a 50% fill rate to +/-5pp takes about **385 independent orders per bucket**.
  200 orders is a pilot (+/-7pp).

**A1 pairs (synchronised legs):**
- **Imbalance:** both legs are worked simultaneously, sized in beta-dollars. Monitor
  `B = |beta_L * P_L * q_L - beta_S * P_S * q_S|` continuously.
- **Bounds:** B <= 20% of pair gross (with a one-share minimum granularity), and **<= 2 minutes from the first
  fill**. On a breach, the lagging leg crosses immediately.
- **Cancel-both** cancels *working orders*, not inventory: send cancels, await acknowledgements, reconcile late
  fills, then **complete or flatten deterministically**. Entries are worked as 3 paired slices of about 1/3 each.
- **PDT:** at $200k equity the pattern-day-trader restriction (which applies below $25k in a margin account;
  *verify* the current FINRA and broker rule) does not bind. An aborted entry flattened the same day is still
  logged as a day trade.
- **Backtest:** per-leg P1/G rules, with the legging hedge charged as crossing.

**B1 options (atomic combo orders):**
- **Conventions:** credit per spread. Natural credit `C_nat = bid_short - ask_long`, summed across both sides for a
  condor. The order fills when `C_nat >= C_L`, the limit credit.
- **Operational window:** Monday 15:00-15:40 ET into that week's Friday expiry. **Friday is not an entry window**
  (no 0DTE entries).
  - Start at package mid and concede one valid tick every 2 minutes, never below the c = 1 price.
  - If the entry is unfilled, **skip the cohort**, logged as missed.
  - SPY risk-reducing exits escalate to marketable combos, then legging-out as a last resort with assignment
    checks.
  - Deadlines are expiry-relative, and holiday weeks are handled.
- **Backtest:**
  - Each leg's **prevailing valid quote is reconstructed as of the decision**: never future quotes, quote age <=
    1 s (registered), displayed size >= order size, regular session, valid contract.
  - Conservative fill = a marketable combo at C_nat after a registered latency. Mid fills are optimistic only.
  - A fleeting synthetic natural does not prove a resting complex order filled.

**Other registered policies:** next-session open and MOC remain registered variants for comparison.

**Limit orders elsewhere:** the P1/P2 brackets apply. There is no adverse-selection fee on top: the realised path
already carries it.

**Options packages generally:** see Section 7.3.

### 6.4 Validation harness
Chronological expanding windows with purging, the frozen holdout, simultaneous inference and diagnostics
(Section 4). CPCV is a sensitivity option.

### 6.5 Run registry and result schema
- **Delta table `research_runs`:**
  - Identity: `run_id`, `family_id`, `config_hash`, `policy_spec`, `git_sha`, `engine`, `mode` (legacy/v2).
  - Data and environment: `input_manifest` (Delta table versions + file content hashes), `calendar_version`,
    `ca_version`, `fee_schedule_version`, `seed`, `deps_lock_hash`.
  - Results: `period`, `status` (exploratory/confirmatory), `trial_index`, `metrics` (struct), `artifacts_path`,
    `created_at`, `data_source='derived'`.
- **Result markdown sections:** configuration; data periods (with the access audit); gross / net / 2x-variable /
  cost grid; inference block; trial count; known limitations.
- **Reproducibility:** cash and positions reproduce **exactly** to their accounting precision. Statistics may use
  a tolerance.

### 6.6 Validator invariants (each is a test)
1. Changing future data cannot change earlier signals, orders or universe membership.
2. A 16:30 daily input cannot fill the same session. Minute inputs obey the one-bar delay.
3. Sessions, DST, holidays and early closes are correct.
4. Splits preserve wealth. Dividends and payments-in-lieu reconcile to cash.
5. Every position or cash change maps to a fill, fee or corporate action.
6. Zero turnover means zero trading fees. Order minimums apply per actual order.
7. A higher cost multiplier never improves net P&L when fills are held fixed.
8. Capacity caps create partial or unfilled orders, and no residual quantity silently disappears.
9. A universe exit keeps the liability and runs an explicit liquidation.
10. A stale or missing quote blocks the fill, with no interpolation.
11. Options respect multipliers, settlement, assignment and package maximum loss.
12. An immutable rerun reproduces the ledger.

**Production-mutant checks.** Each mutant applied to the *new* code must fail a named, substantive
assertion:

| Mutant | Assertion that must fail |
|---|---|
| Remove the execution lag | Invariant 2 |
| Allow future inputs | Invariant 1 |
| Disable purging | The purge-interval known-answer test |
| Zero the costs | The hand-computed cost-per-order test |
| Allow same-bar fills | Invariant 2 |
| Drop delisted names | Invariant 9 |
| Reverse the short dividend sign | The payment-in-lieu cash test |
| Skip the split quantity adjustment | Invariant 4 |
| Drop a partial-fill remainder | Invariant 8 |
| Duplicate an intent | The OMS idempotency test |

**Regression proofs** are separate. They apply only where a PR changes existing behaviour (e.g. the legacy cost
form), and the parent revision must fail **for the intended behavioural reason**, not because a module or import
is missing. The final gate runs both in isolated `/tmp` copies made with `git archive`.

---

## 7. Transaction cost and slippage model

### 7.1 Accounting identity
Implementation shortfall in dollars, with s = +1 for a buy and -1 for a sell:

`IS$ = s * Q * (P_fill - P_decision) + fees`
`    = s*Q*(P_arrival - P_decision)   [delay]`
`    + s*Q*(P_fill - P_arrival)       [execution: spread + impact]`
`    + fees`

When actual fills are replayed, modelled impact is **not** charged again.

### 7.2 Equities and ETFs: modelled one-way cost (bps of notional)
`c = fees_bps + h * M_stress + I * M_stress + borrow_bps * calendar_days (shorts)`

| Component | Formula / default | Notes |
|---|---|---|
| Commission | IBKR tiered $0.0035/sh (<= 300k sh/mo), min $0.35, max 1% of value | Effective-dated `fee_schedules.yaml` |
| Exchange/clearing pass-through | Scenario $0.000 / $0.001 / $0.003 per share | Routing can earn rebates, so zero must be representable |
| SEC Section 31 | Sell side: `rate_t * notional`, with the rate effective-dated per fiscal period | The legacy $0.000008/sh is **wrong in form** |
| FINRA TAF | Sell side: per-share rate_t with a per-trade cap, effective-dated | Equities only. Do not apply it to options by default |
| Half-spread h | ETFs: **full-spread scenarios 1 / 2 / 5 bps**. Single stocks by ADV bucket: full spread 4 / 10 / 30 bps. `h_bps = max(full_spread_bps / 2, 1e4 * 0.5 * tick / price)` | Tick-aware: at $500 the 1-cent floor is h = 0.1 bps; at $50 it is h = 1 bp (hand-tested in WP3). Abdi-Ranaldo/Corwin-Schultz are **diagnostics only**, unreliable at sub-bp spreads. Quotes are used where held |
| Impact I | `I = 1e4 * Y * sigma_d * sqrt(Q / V_est)`, with **Y in {0, 0.5, 1}**, base 0.5 | **Sizing uses only information known at decision time**. For MOC, closing-auction volume is not held, so the registered proxy is V_est = 5% x trailing 20d median dollar ADV; otherwise the trailing median volume of the window. Orders are capped at 1% of V_est; realised-volume caps apply only inside the fill simulation. **Worked examples (Y=0.5):** SPY (sigma_d=1%, ADV $30bn, V_est $1.5bn): $10k gives 0.13 bps, $100k gives 0.41 bps. A $20m-ADV ETF (sigma_d=1.5%, V_est $1m): the order is capped at $10k, giving 7.5 bps. The legacy Almgren term is **not** added on top |
| Delay | Simulated by filling at the registered delayed price; uncertainty stress adds **0 / 1 / 3 bps** | No automatic sigma*sqrt(h) charge, because unconditional drift is zero |
| Stress M_stress | First 15 min x2; last 10 min (non-auction) x1.5; earnings/FOMC/CPI days x1.5; 20d SPY RV > 2x its 1y median x2 | Overlapping stresses take the **max**, not the product. They apply only to modelled spread and impact, never to observed quotes |
| Borrow | Bucket bps/day {0.25, 0.75, 2.0}, accrued per **calendar** day; ETFs at 0.25 | 0.25 bps/day ~ 0.9%/yr calendar. Hard-to-borrow names are excluded. Availability and recall are a separate flag |
| Financing | Cash, debit and short-proceeds rates (Section 6.2), effective-dated | A fixed cost, reported separately from variable costs |
| Dividend withholding | 30% of ordinary dividends received (maintainer figure); shorts pay 100% payment-in-lieu (Section 7.7) | A fixed cost line, effective-dated |

### 7.3 Options
- **Fees:** $0.65/contract (IBKR) + exchange, ORF, OCC and product fees, effective-dated. **Index options are
  stressed at $1.50/contract/side all-in** until product-specific fees are confirmed.
- **Package fill:**
  - Credit: `mid_pkg - c * sum(leg half-spreads)`. Debit: `mid_pkg + c * sum(leg half-spreads)`.
  - Base **c = 1** (cross every leg's half-spread), optimistic c = 0.5, stress c = 1.5. The leg spread and the
    package concession are never both charged.
- **Quote rules:**
  - Legs must be synchronised with the underlying at the feed's actual timestamp resolution.
  - No fill on a crossed, zero-bid or wide quote (full spread > 10% of mid).
  - Leg size must be >= the order size. Aggregate leg size does not prove a complex order is fillable.
  - Failed entries, failed exits and legging are explicit scenarios.
- **Spread priors** (half-spread as % of premium by delta bucket {5-15, 15-30, 30-50} x DTE bucket {0-7, 8-30,
  31-60}) are estimated from held SPY/QQQ snapshots **as weak descriptive priors only**. They are filtered for
  crossed or stale quotes and replaced by vendor data for SPX/XSP.

### 7.4 Gates and the cost-sensitivity report
- **Rule:** net Sharpe > 0 at **2x variable execution costs** (spread, impact, delay stress). Fixed fees and
  borrow are reported separately. A whole-cost 2x stress is also reported. This sits alongside the simultaneous
  statistical gate.
- **Report format (one per run):**

| Multiplier on variable cost | 0 | 0.5 | 1 | 1.5 | 2 | 3 |
|---|---|---|---|---|---|---|
| Net ann. return / Sharpe / max DD / turnover | ... | ... | ... | ... | ... | ... |

  The report also includes:
  - **Cost by component** as a share of gross P&L: commission, exchange, regulatory, spread, impact, delay
    stress, borrow, dividends-in-lieu.
  - **Break-even multiplier**, as the distance to failure.
  - Capacity at the 1% participation cap.

### 7.5 Calibration loop (shadow, paper and live fills)
- **Fill log:** decision price, arrival mid, quoted spread at arrival, fill price and size, window volume,
  sigma_d, fees, order type and policy.
- **IS decomposition** (Section 7.1) per fill, clustered by decision day.
- **Monthly shrinkage update:** `theta_post = (n0 * theta_prior + n * theta_hat) / (n0 + n)` with n0 = 100 fills,
  covering the spread scenario level and Y.
  - Slippage is fitted only on **>= 200 fills** spread across symbols, sizes and regimes. Below that, priors are
    kept.
- **Alerts:**
  - Alert when realised/modelled IS > 1.25 over a rolling 20 fills, with a floor of 0.5 bps or $1 per fill so
    near-zero models do not explode the ratio.
  - **Hard pause** only when cumulative excess IS exceeds the sleeve's registered dollar slippage budget (default
    25% of the backtest's expected monthly net P&L for that allocation).

### 7.6 Cost drag at $200k

These are planning numbers. Every fee is *unverified* until it is in `fee_schedules.yaml`.

**Equities.** Fixed fees are now negligible; spread, impact and borrow dominate.

| Sleeve (sizing) | Orders/yr | Commission/yr (IBKR tiered, $0.35 min) | % NAV | Variable costs | Notes |
|---|---|---|---|---|---|
| A6: 6 pairs, legs about $3.3k | about 180 | about $63 | 0.03% | Spread 1-2 bps; impact per Section 7.2 | A $3.3k order of a $60 ETF is about 55 shares, so the $0.35 minimum (about 1 bp) applies |
| A1: 2 pairs, legs about $6.6k | about 80 | about $32 | 0.02% | As above | -- |
| A4: 5 names about $2k + hedge | about 150 | about $55 | 0.03% | Single-name spreads 4-10 bps | -- |

**Impact convention** (corrected): `I = 1e4 * Y * sigma_d * sqrt(Q / V_window)`, with V_window = the trailing
median volume of the execution window. Where minute data is missing, the registered proxy is 15% of 20-day
median ADV for a 50-minute window.

| Order | ETF ADV | Impact (Y = 0.5, sigma_d = 1.5%) |
|---|---|---|
| $6.6k | $5m (window 15% = $0.75m); **below the $20m floor, shown only to illustrate why it is excluded** | **about 7.0 bps** |
| $3.3k | $20m (window about $3m) | **about 2.5 bps** |
| $3.3k | SPY-class | < 0.1 bps |

**Rules:**
- ADV floor $20m.
- Participation <= 1% of window volume.
- Impact is **charged**, never assumed negligible.

**Borrow on the short leg:**
- A daily broker snapshot of shortable shares and borrow fee.
- Skip the pair if the name is hard to borrow (fee > 1%/yr) or unavailable.
- Borrow accrues per calendar day (Section 7.2).

**Options (B1). Friction = round-trip fees + c=1 crossing, against credit.**
- Fees use a base all-in of $0.70/contract (SPY) or $0.85 (XSP), with SPX product fees *verify*.
- The stress is $1.50/contract/side: **$3 to enter a 2-leg spread, $6 for a round trip** per spread.
- Friction/credit does **not** depend on the contract count. The count only scales dollars.

| Structure | Credit (illustrative, *verify*) | WCL/contract | Contracts at $1,000 | Friction/credit | Verdict |
|---|---|---|---|---|---|
| SPY $1-wide put spread, T-1 close | $15-20 | $80-85 + costs | **1** (assignment rule) | **24-45%** | Fails the 20% gate |
| XSP $1-wide put spread, held to settlement | $15-25 | $83-93 (stressed lifecycle) | **10-12** | Needs h <= $0.0065 (on a $15 credit) to $0.0165 (on $25) | Conditional on the quote trial |
| XSP $1-wide iron condor | $30-40 | $76-86 (stressed lifecycle) | 11-13 | Similar ratios | Conditional |
| XSP $3-wide put spread | $45-75 | $233-263 | **3-4** | About 7-15% if h <= $0.01 | Conditional |
| XSP $5-wide put spread | $60-100 | $408-448 | **2** | About 5-12% if h <= $0.01 | Conditional |
| SPX $5-wide put spread | $60-100 | $400-440 + SPX fees | **about 2** | Depends on SPX fees and dollar spreads | Conditional, compared at matched exposure |
| SPX $10-wide put spread | $150-200 | about $800-850 | **1** | As above | Conditional |

**Conclusion:**
- At $200k the **contract counts fit**.
- Whether options pass depends on measured leg spreads and product fees in the quote trial, under the 2x
  variable-cost gate.
- The friction gate (<= 20%) is necessary, not sufficient.

**Data subscriptions** are research overhead, reported separately from trading P&L (Section 9.2).

### 7.7 Dividend withholding (30%, maintainer figure; capital gains 0%)
- **Ledger lines:** `dividend_gross`, `withholding_tax` (30%, effective-dated config), `dividend_net`,
  `payment_in_lieu_paid` (shorts pay 100%), `substitute_payment_received` (70%, an assumption pending broker
  evidence).
  - Entitlement is fixed at the ex-date; cash posts on the pay date, including receivables across exits.
- **Carry, equal notionals:** `carry = 0.7*y_L - y_S`, so withholding adds `-0.3*y_L` vs the gross total-return
  ratio.
- **Carry, unequal notionals:** `Pi_div = 0.7*N_L*y_L - N_S*y_S`.
  - Example: a $1,500 long at 3% yield loses **$13.50/yr** to withholding. That is 45 bps of $3k pair gross, or
    0.675 bps of the $200k NAV.
  - Actual cash follows ex-dates, not smooth accrual.
- **Signals:**
  - Signals and hedge ratios use **gross total returns**, because the market relationship is not account-specific.
  - Withholding enters **portfolio P&L** only.
  - A net-return signal is a separate registered variant.
- **Ex-date avoidance** (delaying a new long entry when the leg's ex-date is within 2 sessions) is a
  **dividend-timing strategy**. It is a registered configuration tested on its full delayed-entry path, not a free
  fix.
- **Pair viability.** Yields are *unverified* and get pulled from Massive dividends. Yield alone does not decide
  viability.

| Pair | Withholding effect | Other issues | Status |
|---|---|---|---|
| XLK/XLU, SPLV/SPHB | Direction-dependent drag of about 0.3 x 2.5-3% = **0.75-0.9%/yr of long notional** when long the high-yield leg | Factor differences dominate | Keep in research; report carry by direction |
| EFA vs S&P 500 | Fund-level foreign tax is already in EFA's NAV, so do **not** subtract it twice; only the 30% on EFA's distributions applies | Currency and region factor | Research |
| KRE/XLF | Quantify actual distributions and borrow | Banks are event-prone | Research |
| GDX/GLD | GDX distributes cash, GLD does not, so the effect is asymmetric | Miners carry equity and operating risk | Research |
| GLD/IAU | About zero dividend effect | Tiny spread; borrow and fees likely dominate | Control/diagnostic only |

- **Dollar terms at $200k (planning; the ledger computes actual holding-period exposure):**
  - A6 longs of about $20k at about 2% yield give about $400 in dividends, so about $120/yr is withheld.
  - A1 longs of about $13k give about $24/yr withheld.
  - A4 longs of about $10k give about $9/yr withheld.
  - Total: about **$150/yr (about 0.08% NAV)**.
  - Short-leg payments-in-lieu and financing are booked separately in pair economics.
- **TOM:** the effect is computed from **actual holdings across ex-dates** (S&P 500 ETFs go ex quarterly). It is
  reported, not assumed negligible.
- **Distribution classes:** ordinary dividends, capital-gain distributions, return of capital and later
  reclassifications are recorded separately. The default is 30% on ordinary dividends. Other classes follow the
  broker's 1042-S treatment (*verify*).
  - Paperwork assumed: a W-8BEN on file and Chapter 3/Section 1541 withholding by the broker.
  - "Qualified" status does not remove non-resident withholding.
- **Options:** spreads receive no dividends, but **assignment** creates stock positions that do. A short ITM call
  with extrinsic value below the dividend is closed before the ex-date (Section 3.1). Assignment and exercise are
  booked in the ledger.

---

## 8. Performance metrics and evaluation

### 8.1 Two metric families, one NAV convention
- **Continuous sleeves** (A6, A1, TOM, portfolio): **trading-session NAV returns**.
  - Zero-position sessions are included. Weekends are not inserted.
  - Returns include cash interest, dividends and payments-in-lieu, financing, fees, and marked open positions.
  - All sleeves use one account-capital convention ($200k NAV, with the sleeve's allocated capital stated).
- **Event and options sleeves** (B1, A4, later B3/B4): **per-trade/package metrics** *plus* the same daily
  marked-to-market NAV series, so drawdown and Sharpe compare across sleeves.

### 8.2 Definitions
Notation: x_t = r_t - rf_t; S_d = mean(x) / sd(x); A = 252.

| Metric | Definition | Notes |
|---|---|---|
| Sharpe (annualised) | sqrt(A) x S_d | Conventional. Inference uses the dependence-aware bootstrap (Section 4.4) |
| Autocorrelation-aware Sharpe (Lo) | S_A = sqrt(A) S_d / sqrt(1 + 2 sum_{k=1..A-1} (1 - k/A) rho_k) | Diagnostic. Reporting q = 10 truncation assumes the omitted rho are zero, so the bandwidth and its sensitivity are documented |
| PSR(S*) | Phi[(S_d - S*) sqrt(T-1) / sqrt(1 - g3 S_d + (g4-1)/4 S_d^2)] | Per-session units; g4 is ordinary (non-excess) kurtosis; IID approximation. Diagnostic |
| MinTRL | 1 + [1 - g3 S_d + (g4-1)/4 S_d^2] z_{1-a}^2 / (S_d - S*)^2 | Only defined when S_d > S*. A planning number, not a gate |
| DSR | PSR against S* ~ mu_S + sigma_S [(1-gamma_E) Phi^-1(1 - 1/N) + gamma_E Phi^-1(1 - 1/(eN))], gamma_E ~ 0.5772 | The trial universe and N (raw, plus a documented effective range) come from the registry. Diagnostic |
| Sortino | sqrt(A) x mean(r - m) / DD, where DD = sqrt(mean over **all** t of min(r_t - m_t, 0)^2) | MAR m_t = the daily T-bill rate (time-varying). If DD = 0, the value is UNDEFINED, not a pass. Per-trade Sortino is not used |
| Max drawdown | d_t = V_t / max_{u<=t} V_u - 1; MDD = -min d_t | Reported in % of the sleeve's capital and in % of NAV |
| Time under water | Peak-to-trough, trough-to-recovery and total underwater sessions | An unrecovered final drawdown is **CENSORED** and gives a lower bound only |
| Ulcer index | sqrt(mean d_t^2) | Units labelled (fraction) |
| Calmar | CAGR / MDD, over the same window | UNDEFINED if MDD = 0. Rolling 36m is a diagnostic only |
| ES / CVaR 95 / 99 | Mean daily **loss** beyond the 95/99% loss quantile (positive = loss); interpolation method stated | Descriptive. About 12 observations sit beyond the 99% quantile in 4.6y, so it cannot certify a tail |
| Worst day / worst trade | Min daily return; min trade P&L (in $, % NAV and % of package max loss) | -- |
| Skew, kurtosis | Of daily returns and of trade P&L | -- |
| Tail ratio | Q.95(r) / abs(Q.05(r)) | **Only when Q.95 > 0 > Q.05**; otherwise both quantiles are reported and the ratio is marked N/A |
| Turnover, capacity | One-way annualised turnover; capacity from the auction proxy or quoted depth, not "1% ADV" | Options capacity comes from quoted size |
| Cost drag | Gross minus net (bps/yr and $), split by component (Section 7.4) | Ratios to gross are reported only when gross > 0 |
| Regime and fold stability | Metric per walk-forward block, per vol tercile and per trend sign | "3 of 4 blocks positive" is descriptive |
| PBO | CSCV over the registered family | Diagnostic |

### 8.3 Per-trade metrics (event and options sleeves)
**Win rate is never shown alone.** It always appears with payoff ratio and expectancy.

| Metric | Definition |
|---|---|
| N | Trades, non-overlapping cohorts, distinct event dates, distinct issuers |
| Win rate p; avg win W; avg loss L | Net of all costs |
| Payoff ratio | W / abs(L) |
| Expectancy | E = p W - (1-p) abs(L), in $ and per $100 of max loss |
| Profit factor | sum(wins) / abs(sum(losses)). UNDEFINED with no losses; flagged INSUFFICIENT with fewer than 20 losses |
| Trade P5 and median, worst trade | Also the average of the worst 5% of trades (trade-level ES) |
| Hold time | Mean and median sessions; days in trade for options |
| MAE / MFE | Per trade, from the event engine |
| Clustering | Every trade statistic's bootstrap is clustered by entry week (B1) or event date + issuer (A4) |

### 8.4 Options-specific metrics (B1, B3, B4)
- **Risk/reward:** max loss / credit; **return on risk** = net P&L / max loss; return on broker margin
  requirement.
- **Credit capture** = realised P&L / initial credit.
- **Event frequencies:**
  - breach frequency (short strike touched intraday; closed ITM);
  - **max-loss frequency** vs its binary break-even `p_loss < credit / width`. This holds only in a binary
    no-cost model, so real exits are judged on net expectancy, not on this ratio.
- **Friction:** friction / credit (a gate for credit structures). For debit structures it is measured against
  premium and expected gross edge.
- **Operational events:** early-assignment, pin (underlying within 0.5% of a short strike at the T-1 decision),
  ex-dividend and forced-liquidation events.
- **Concurrent exposure:** concurrent open max loss ($, % NAV), the per-expiry cluster, and stress losses (gap, vol
  jump, impaired exit).
- **"Winners erased by one max loss"** = max loss / average win. A diagnostic only.

### 8.5 Gates (8) vs diagnostics (everything else)
Each gate has a status of **PASS / FAIL / PENDING / NOT_APPLICABLE**. A pending maintainer decision can never show as a
pass.

1. **Data and accounting validity:** NAV reconciles; signals are causal; timestamps are executable; marking is
   documented.
2. **Primary inference:** the family-simultaneous block-bootstrap **lower bound on net Sharpe > 0** at 1x costs
   (one-sided 95%). Cross-sleeve dependence is preserved by bootstrapping joint daily sleeve vectors.
3. **Cost robustness:** point net Sharpe > 0 at **2x variable costs**, with fixed fees at their actual $200k values. (Economic gates are not fully size-invariant: minimum
   commissions, integer contracts and fixed data costs change realised returns.)
4. **Challenger control:** a pre-specified SPA requirement before any challenger replaces the rule.
5. **Approved risk limits:**
   - Every trade's worst-case loss (stressed gap for equities, contractual max loss + fees for options) is <= 0.5%
     of E_t (Section 10.1a).
   - Aggregate open WCL <= 5%, a crash cluster <= 3%, a joint stress-scenario loss <= 5%, and assignable
     notional <= 50% (proposals).
   - A trade that would exceed a cap is **skipped**, never resized upward.
6. **Options economics:** base friction / credit <= 20% for credit structures.
7. **Operational readiness (paper):**
   - >= 60 sessions.
   - Every applicable workflow observed at least once: window fill, deadline crossing, partial fill, reject, missed deadline, expiry
     or settlement, assignment drill (simulated if not seen), kill switch.
   - Fills, cash, fees, positions and marks reconcile to the cent, with cumulative paper-vs-simulator P&L
     divergence attributed.
   - Sparse workflows are reported as UNTESTED, not passed.
8. **Evaluation integrity:** frozen spec, complete trial ledger, an untouched evaluation window (or a declared
   retrospective/prospective status), and stated power limits.

**Removed as gates**: Sortino > 0.5, profit factor >= 1.2, cost drag <= 50% of gross, largest loss / avg
win <= 8, a trade-expectancy bootstrap lower bound (it would duplicate inference without a multiplicity plan), and
an "18 months under water" limit.

**Evidence counts are disclosures, not eligibility:** about 52 decisions/yr for weekly A6, about 12 windows/yr for
TOM, >= 3.85 years for 200 B1 cohorts. A 1-year window cannot hold 100 weekly episodes.

### 8.6 Tearsheet schema (Polars, long format; authoritative tables)
```text
research_runs:    [all Section 6.5 fields: input_manifest, policy_spec, calendar/ca/fee versions, seed,
                  deps_lock_hash, artifacts_path] + run_id Utf8, strategy_version Utf8, family_id Utf8, data_snapshot_id Utf8,
                  config_hash Utf8, git_sha Utf8, trial_registry_id Utf8, engine Utf8,
                  mode Utf8, evaluation_status Enum[EXPLORATORY,RETROSPECTIVE,HOLDOUT,PROSPECTIVE],
                  created_at Datetime[UTC], data_source Utf8 ('derived')
research_metrics: run_id Utf8, sleeve Utf8, family_id Utf8, cost_mult Float64,
                  evaluation_split Utf8, period_start Date, period_end Date, metric Utf8,
                  value Float64?, unit Utf8, n_sessions UInt32, n_trades UInt32?, n_cohorts UInt32?,
                  ci_lo Float64?, ci_hi Float64?, confidence_level Float64?,
                  inference_method_id Utf8?, definition_version Utf8,
                  status Enum[VALID,UNDEFINED,INSUFFICIENT,CENSORED], notes Utf8?
research_gates:   run_id Utf8, sleeve Utf8, gate_id Utf8, policy_version Utf8,
                  status Enum[PASS,FAIL,PENDING,NOT_APPLICABLE], evidence_ref Utf8
inference_methods: inference_method_id Utf8, seed Int64, n_resamples UInt32, block_spec Utf8,
                  family_members List[Utf8], multiplicity_method Utf8
(all tables carry data_source Utf8 = 'derived' plus lineage to research_runs.input_manifest; this is the single
 authoritative schema, superseding Section 6.5's list)
trades:           run_id, sleeve, trade_id, entry_ts, exit_ts, legs (struct list), credit_debit,
                  max_loss, fees, slippage, pnl, mae, mfe, events (assignment/pin/ex-div) List[Utf8]
```
- **Bootstrap intervals** come from the stationary block bootstrap with block length chosen from observed
  dependence (start at max(10, 2 x hold), with 0.5x/2x sensitivity). Monthly sleeves use month blocks.
- Intervals are **not** attached automatically to path extrema or sparse tails. These get status INSUFFICIENT.
- **Report layout:** a header (status, gates); a cost grid (Section 7.4); the daily metric table; trade/options
  tables; drawdown episodes; regime and fold tables; stresses; limitations.

---
## 9. Data and infrastructure (Massive-first)

### 9.1 Datasets and lineage
| Need | Massive source | `data_source` / `source_dataset` | WP |
|---|---|---|---|
| Daily ETF/stock history 2003+ (development + sealed 2016-21 holdout) | `us_stocks_sip/day_aggs_v1` (Stocks Advanced, one-month bulk pull) | `massive` / `massive:us_stocks_sip/day_aggs_v1` | WP-D1, WP9 |
| Dividends (ex, pay, amount, type) | REST dividends (2000+) | `massive` / `massive:rest/dividends` | WP8 |
| Splits | REST splits (already used) | `massive` | held |
| Minute bars / stock quotes (execution study) | `minute_aggs_v1`, `quotes_v1` (start dates *unverified*) | `massive` | WP14 |
| Options quotes / trades / day aggregates + historical contract reference | `us_options_opra/*` (quotes 2022-03-07+, trades and day 2014-06-02+; prefix *unverified*), one-month bulk pull | `massive` / `massive:us_options_opra/quotes_v1` | WP-D1, WP-D2, WP15 |
| SPX values (XSP settlement, IV underlying) | Indices Starter (`us_indices/*`; depth *unverified*) | `massive` / `massive:us_indices/values_v1` | WP15 |
| 8-K timing | EDGAR submissions (**non-Massive dependency**) | `sec_edgar` | WP12 |
| Broker forward quotes, orders and fills (Section 9.3) | IBKR / Schwab | `ibkr` / `schwab` (vocabulary PR at first ingest) | WP-D3, WP-D4, WP19 |

- **Storage:** UC bronze/silver/gold. The sealed holdout lives in a restricted schema or volume.
- **Research:** runs locally in Polars on manifest-pinned snapshots.
- **Not adopted:** QuestDB, TimescaleDB, VectorBT.

### 9.2 One-time bulk acquisition, then broker overlay (decision of record, 2026-10-24)

**Decision.** There is no continuous premium subscription. The plan buys the minimum tiers for **one month**,
downloads the required history, verifies it before the month ends, and cancels. Forward data comes from our own
broker collection (Section 9.3).

This design is **conditional on the licensing gate** (Step 0b) and on a measured feasibility pilot.

#### Sequence (each step is a maintainer decision)
| Step | Action | Cost (list) | Gate to proceed |
|---|---|---|---|
| 0a | **Entitlement and feasibility check** (WP-D0): list the accessible S3 prefixes and dates under the current account; confirm that dataset start dates are actually *entitled* (stocks to 2003-09-10, options quotes from 2022-03-07, options day aggregates from 2014-06-02, index depth); confirm expired-contract and delisted-symbol reference access | $0 | Entitlement confirmed in writing or by listing |
| 0b | **Licensing gate, mandatory, *unverified*.** Written answers from Massive (terms + support) covering: retention and use of downloaded data **after cancellation**; derived outputs; redistribution; personal vs business use for the actual account/entity; cloud processing, storage, backups and service providers; paper and possible live use; whether S3 flat-file downloads fall under the same terms. Broker-data storage rights are checked the same way (Section 9.3) | $0 | **If retention after cancellation is not permitted, this design stops.** Any fallback (e.g. a continuous cheaper tier) needs its own confirmed permissions and coverage, and a separately approved scope and budget. Options Starter cannot replace quote access |
| 0c | **Start the broker forward collection** (Section 9.3) **at least 5 weeks before** the purchase date, so the fixed cutoff includes **>= 20 completed broker sessions** | Broker data fees (Section 9.3) | Collector running and reconciled daily; >= 20 sessions before the cutoff |
| 1 | **One month:** Stocks Advanced ($199) + Options Advanced ($199) + Indices Starter ($49), all started on the same day. Renewal is switched off at purchase, and a calendar alert is set 7 days before the renewal date | **$447** | Pilot passes (below) |
| 2 | Acquisition by priority, with incremental audits (below) | -- | Completeness sign-off >= 5 business days before the renewal date |
| 3 | Cancel all three tiers. Keep the manifests and the licensing correspondence | -- | Cancellation confirmed in writing |
| 4 (optional) | A second burst 12-18 months later (Options Advanced, $199) to extend options history | $199 | Only for data still entitled and licensed then. It cannot repair older gaps |

#### Feasibility pilot (first days of the month, or earlier if access allows)
- **Problem:** without server-side predicate filtering (none is documented), filtering OPRA quote files locally
  still means **downloading the full compressed daily objects**. Filtering cuts retained storage, not inbound
  bytes.
- **Measure** on several representative sessions, including a busy expiry or event day:
  - compressed bytes per day;
  - download throughput;
  - decompress and filter time;
  - peak disk and RAM;
  - output size;
  - failure and retry cost.
- **Extrapolate** to the full requested period against the remaining days, with 50% headroom.
- **Stop or re-scope rule:** if the projection exceeds about 60% of the month, drop or reduce scope in this order
  before starting the bulk pull: **P6, then P5, then P4, then P3, then P2**. P1 is never reduced. Mandatory
  dependencies are preserved, and any strategy left short is declared incomplete. All sizes are *unverified* until measured.

#### Pull manifest (priority order if the month is cut short)
| Priority | Dataset | Range | Scope | Retention |
|---|---|---|---|---|
| P1 | Stocks day aggregates (full market, incl. delisted) | 2003-09-10 -> **fixed cutoff** (the last complete session before the pull starts; it must include >= 20 completed broker sessions) | All symbols | Raw files kept (small). 2016-2021 objects go **straight to restricted storage** |
| P1 | Dividends, splits, ticker reference (type, list/delist dates, CIK) | 2000+ | ETF universe + A4 candidate universe | Raw JSON kept |
| P2 | Options **quotes** for B1: XSP, SPX/SPXW | 2022-03-07 -> cutoff | Contracts selected **causally**: expiries <= 45 DTE, strikes within +/-15% of the **prior-session** close of the underlying (no intraday look-ahead), plus every contract an open position or exit would need | Filtered Parquet (a bounded research archive) |
| P2 | **Historical contract reference** (expired contracts, roots, AM/PM settlement, adjustments) for **every** underlying whose quotes are retained (P2, P4, P5). It is a **mandatory dependency** of each quote pull and is checked in the completeness audit | 2022-03-07 -> cutoff | All retained contracts | Raw kept |
| P3 | Index values/day aggregates: SPX, VIX, VIX3M (as deep as entitled) | Max available | -- | Raw kept |
| P4 | Options quotes for SPY (1-contract verticals) and QQQ | 2022-03-07 -> cutoff | As P2 | Filtered |
| P4 | Options day aggregates for the P2/P4 underlyings | 2014-06-02 -> cutoff | -- | Raw. **2016-2021 to restricted storage** |
| P5 | Options quotes for about 50 B4 single names | 2022-03-07 -> cutoff | As P2 | Filtered |
| P6 | Stock minute aggregates, only for ETFs with missing minute coverage in held bronze (e.g. RSP) | 2022+ | Execution study only | Raw |

**A4 inputs not covered by Massive:**
- EDGAR 8-K timing comes from the existing SEC pipeline (`sec_edgar`).
- A historical liquid-universe membership is rebuilt from P1.
- If either is incomplete when the month ends, A4's data requirements are recorded as incomplete.

#### Integrity, lineage and holdout isolation
- **Per downloaded object**, a row in an **append-only** bronze manifest table (`bronze_massive_pull_manifest`,
  `data_source='massive'`):
  - S3 key and ETag (the ETag is an identifier, not a content hash);
  - size;
  - **SHA-256 of the source compressed bytes**;
  - pull timestamp;
  - the fixed cutoff;
  - entitlement tier.
- **Per retained output**, a SHA-256 of the output plus:
  - filter/code version, schema and contract-mapping version;
  - source, output and **rejected** row counts;
  - timestamp conventions.
- **Codes:**
  - Raw rows: `data_source='massive'` with a `source_dataset` (e.g. `massive:us_options_opra/quotes_v1`).
  - Filtered or derived tables: `derived`, with lineage to manifest rows.
- **Filtered-only retention** is a deliberately bounded research archive, not a reproducible full OPRA archive.
  Discarded contracts and fields cannot be recovered after cancellation; source hashes cannot reconstruct them.
- **Holdout isolation:**
  - All 2016-2021 raw objects, volumes and derived copies (stocks day aggregates and options day aggregates) are
    written **at download** into restricted storage.
  - Research service identities have **no read grant** on them.
  - Only development partitions (2003-2015, 2022+) are exported to research.
  - Hashes prove that bytes did not change, not that nobody read them. Access logs plus the grant configuration
    are the evidence.
  - Holdout validation during acquisition is **mechanical only** (row counts, hashes). No strategy outcome is
    inspected.

#### Completeness audit (incremental during the pull, final before the lapse; gaps cannot be re-pulled later)
- **Stocks:**
  - per-symbol per-session row presence vs the **date-specific** NYSE calendar (holidays, early closes) between
    listing and delisting dates;
  - classified exceptions (no-trade days, halts, suspensions, listing-date semantics);
  - duplicate and key checks;
  - corporate-action consistency (split and dividend vs price jumps);
  - sampled comparison against independent sources (held bronze 2022+, FRED SP500).
  - **Economic checks** (price-jump vs corporate-action reconciliation, independent price comparisons) that a
    researcher can see run **only on development partitions** (2003-2015, 2022+). For 2016-2021 the audit is
    mechanical only (row presence, keys, hashes). Its economic validation is deferred to the authorised holdout
    process.
- **Options**, for the contracts the strategies actually need (both legs, entry, holding period and exit
  observations):
  - quote-row counts, quote age, two-sided markets, sizes;
  - crossed or locked quotes; timestamp ordering;
  - expected expiries from the **historical product calendar** (no hard-coded weekdays);
  - session hours per product and date;
  - an explicit stale-quote rule (Section 6.3).
- **Indices:** per-session presence for the required series.
- **Acceptance:** strategy-level criteria are defined **before** the pull, e.g. at most 1% of B1 cohort decisions
  missing a usable entry quote. Missingness is reported by period, so stressed sessions are not silently excluded.
- **Sign-off:** >= 5 business days before the renewal date, with time reserved for repair.

#### Costs and break-even
| Item | Cost |
|---|---|
| Subscriptions, one month, list | **$447** (one-time) |
| Optional second burst | $199 |
| Storage, compute and transfer | Measured in the pilot; ceiling set in Section 16 |
| Broker market data for the forward collection | Section 9.3; *verify* |
| Tax | If applicable |

- **Against the edge:** $447 once is about 22-45% of one year's expected edge ($1-2k), and about 0.075% of NAV per
  year amortised over three years. That assumes three years of permitted, useful retention.
- The amortisation measures cost spread, not recovery of the expense.
- **The continuous-subscription cost model is retired.**

### 9.3 Broker forward collection and overlay
**Purpose:**
1. Calibrate fills and slippage on our own orders.
2. Extend history **forward** from the bulk cutoff.

It **cannot replace the bulk pull**: brokers generally do not serve historical quotes for expired option contracts
*[unverified]*.

**Route:**
- Choose **one** broker (IBKR or Schwab) and verify before collecting:
  - real-time OPRA and index entitlements on the account (a paper account does not establish them);
  - retention rights;
  - snapshot throughput and pacing limits *[unverified]*;
  - whether quotes are fresh updates or cached or delayed values.
- Market-data fees are counted in the budget.

**Collection scope:**
- **Contracts:** the same causal selection rule as P2, plus every contract held or needed to exit. The chain size
  is measured before the cadence is fixed.
- **Cadence:**
  - every 1 minute in the Monday 14:55-15:45 ET entry window;
  - every 1 minute in scheduled exit windows;
  - stop triggers come from the **independent live stop monitor** (Section 10.1b: a 60-second regular-hours loop
    for open packages), whose observations are retained. Stop-related conclusions are limited to what that cadence
    can observe;
  - every 15 minutes during the rest of regular hours across the **whole holding period**;
  - settlement values and exercise/assignment events, recorded separately.
- **Fields:**
  - bid/ask and sizes, last;
  - broker IV/greeks, labelled as **broker-model outputs**;
  - underlying bid/ask;
  - OCC symbol + broker contract id;
  - exchange timestamp (where provided) and local receive timestamp;
  - request id and a fresh-vs-cached flag;
  - our own orders, acknowledgements and fills.
- **Storage:** its own bronze tables with `data_source='ibkr'` or `'schwab'` (vocabulary PR at first ingest), and
  append-only.
- **What paper fills show:** paper-execution diagnostics only, not live slippage. Independent leg quotes do not
  prove an executable complex-order price.

**Reconciliation and join:**
- **Overlap:** >= 20 completed sessions before the fixed cutoff (Step 0c) as a minimum, plus minimum matched-observation counts per product, expiry/DTE, moneyness
  and liquidity bucket. Thresholds are set **before** the overlap is evaluated.
  If the matched-count thresholds are not met, the join stays **unapproved**.
- **Matching:**
  - canonical OCC identifiers;
  - exchange-event timestamps where available;
  - quote ages and clock diagnostics;
  - asynchronous-sampling analysis (a fixed 1-second match is not assumed);
  - unmatched observations reported, never counted as agreement.
- **Diagnostics:** stratified distributions of mid differences and spread widths in **product-specific ticks**,
  and their **economic impact** on the selected spreads and on entry decisions.
  - Comparisons of IV across sources use **our own** model on both feeds' quotes, never broker-model IV against
    vendor data.
  - A structural-break check at the join (CUSUM on the matched daily statistic) needs a baseline from the overlap.
    It is reported, not trusted, while observations are few.
- **Hard rule:** vendor (backtest) and broker (forward) series are **never silently mixed**. Every row carries
  `data_source`. A joined series exists only as an explicit, **versioned join view** recording the join date,
  diagnostics and thresholds.
- Passing diagnostics does not make the sources interchangeable. Analyses state which source they use.


---

## 10. Operationalisation (offline first; every live step needs maintainer approval)

### 10.1 Signal to portfolio
- **Sleeve output:** desired positions with attribution: sleeve, `instrument_id`, `instrument_type`, `decision_ts`,
  `information_available_ts`, `valid_until`, `run_id`.
- **Allocator:**
  - Nets positions per instrument while keeping sleeve allocations.
  - Applies standalone sleeve vol budgets (Section 5), a 5% portfolio-vol ceiling and aggregate gross <= 100% NAV.
  - Enforces the lot rule (`price <= leg/20`) and per-sleeve no-trade bands in exposure units.
- **Per-trade cap:** every trade's worst-case loss <= 0.5% of E_t (Section 10.1a). The aggregate open risk is <= 5%,
  a crash cluster <= 3%, and assignable notional <= 50% of equity (proposals).
- **Options limits:**
  - |net delta| <= 10% NAV equivalent. The sum of absolute package vegas <= 0.1% NAV per vol point.
  - Stress loss (spot +/-10%, vol +/-10pt) <= 3% NAV.
- **No Kelly.**


### 10.1a Per-trade risk cap: 0.5% of equity (decision of record, 2026-10-24)

**Rule.** The **worst-case loss (WCL) of any single trade must not exceed 0.5% of current portfolio equity**
E_t, which is **$1,000 at $200,000**.
- E_t is the marked NAV at the decision time, recomputed every decision. After losses the cap shrinks; it is never
  measured from the high-water mark.
- The cap is enforced deterministically in order generation and through **mandatory stops** (Section 10.1b).
  Agents cannot override it.
- **It is a modelled loss budget, not a guaranteed realised-loss ceiling.** Gaps, halts and liquidity failures can
  exceed it. Any exceedance is a registered event (Section 10.1b, item 4).

**Worst-case loss per unit:**

| Position type | WCL per unit |
|---|---|
| Defined-risk credit vertical | `100 x width - credit + stressed lifecycle costs` (entry fees and crossing; exit costs unless held to cash settlement; contingent liquidation) |
| Same-expiry iron condor | Larger wing width x 100 - net credit + costs (only one side can finish in the money) |
| Debit vertical | Net debit + costs |
| Butterfly / broken-wing butterfly / any other package | **Max loss = -(minimum expiry payoff over every strike breakpoint and both tails) + net debit (or - net credit) + costs.** A broken-wing butterfly can lose more than its debit: long 100C, short 2x 105C, long 115C pays -$500 above 115 before premium |
| Equity/ETF position | `notional_unit x max(stop distance, G) + stressed slippage + fees` |
| ETF pair (one unit = the complete hedge bundle) | `long-leg notional x G_rel + slippage + fees`, where G_rel is the adverse relative return of the bundle |

These option bounds hold **only for intact packages** held through cash settlement or closed as packages. American legs (SPY,
single names) also need assignment, gap, dividend and forced-liquidation scenarios, sized under the
assignment-notional rule below.

**Stress values G** (planning values. Before the holdout opening, WP9 calibrates the empirical value as the worst
observed x 1.25 using **only 2003-2015 and 2022-onward data**; 2016-2021 is sealed. A stress is never changed to fit
a lot size):

| Position | G planning | Empirical **[unverified]** |
|---|---|---|
| Broad-index ETF long | 20% | about 13% [unverified] |
| Sector/style ETF long-only | 25% | -- |
| ETF pair bundle (G_rel) | 15% | e.g. 7% x 1.25 = 8.75% [unverified] |
| Single stock after the event (A4) | 20% | about 15% [unverified] |

**Sizing formula:**

```text
q = floor( min( budgeted_WCL_for_trade, 0.005 * E_t ) / WCL_unit , other limits )
if q < 1: skip the trade   # never round up past the cap, never alter a structure to fit
```

#### Fit at E = $200,000 (cap $1,000)
| Position | WCL per unit | Units at the cap | Planned size |
|---|---|---|---|
| A6 pair (WCL budget $500) | 0.15 x leg + costs | Legs about $3.3k | 6 pairs |
| A1 pair (WCL $1,000) | 0.15 x leg + costs | Legs about $6.6k | 2 pairs |
| A4 name (WCL $400) | 0.20 x notional + costs | About $2k each | 5 names |
| TOM long broad ETF | 0.20 x notional + costs | About $5k (about $7.7k at G = 13%) | Research only |
| XSP $1-wide put spread | $83-93 (stressed lifecycle) | 10-12 | B1 |
| XSP $3-wide / $5-wide | $233-263 / $408-448 | 3-4 / 2 | B1 |
| SPX $5-wide / $10-wide | about $408-448 / about $808-858 | about 2 / 1 | B1 alternative |
| SPY **vertical only** | -- | **1 contract** (assignment rule below; a condor's two short legs breach it) | Limited |
| Single-name B4 condor | Width-dependent | 1 contract per name, **share price <= $100** (two short legs x 100 x price <= $20k) | Limited pilot |

#### Aggregate risk (proposals; the decision of record sets only the per-trade cap)
1. **Aggregate open WCL <= 5% of E_t** ($10k), budgeted by sleeve as in Section 5: A6 1.5%, A1 1%, A4 1%,
   options 1.5%. A 10% aggregate is **not** adopted without portfolio stress evidence.
2. **Joint stress-scenario loss limit:** registered scenarios (2008-10, 2022 H1, 2024-08-05, 2025-04 replayed;
   **2018-02 and 2020-03 as parametric shocks only** until the holdout opening, because they fall in the sealed
   2016-2021 window; a 10% gap; a vol jump; failed hedges and pair dislocations) must each lose <= 5% of E_t. Hedges get
   conservative recognition.
3. **Crash cluster** (long ETF legs, short puts, A4 longs, failed pair hedges) <= 3% of E_t.

**Assignment-notional rule (American options):**
- The sum over all short American option positions of contracts x 100 x underlying price must be <= **50% of E_t**
  ($100k). One SPY contract is about $65k, so **SPY is limited to 1 contract**.
- A single name is limited to <= 10% of E_t ($20k) per name. **Every short leg counts**: a condor has two short legs,
  so a 1-contract single-name condor needs share price <= $100 (2 x 100 x $100 = $20k). For SPY, a condor's two
  short legs (about $130k) breach the $100k aggregate, so **SPY trades verticals only**.
- This is an operational policy, not proof of carryability. Settled cash, margin, simultaneous assignments and
  hedge-exercise timing are checked in the broker assignment drills before SPY or B4 trade on paper.

**Reg-T margin:**
- A defined-risk vertical's requirement is about its max loss.
- A qualifying same-expiry iron condor uses the larger wing width less net credit.
- Broker recognition, house rules and expiration handling are *verified* in the paper drills.
- Different expiries invalidate condor treatment.

**Ruin arithmetic.** With 0.5% per trade, k consecutive max losses leave 0.995^k: 95.1% at k = 10 and 90.5% at
k = 20. The binding scenario is a clustered event at the aggregate cap (-5%).

### 10.1b Mandatory stop-losses (decision of record: the 0.5% cap is built in through stops)

#### 1. Every trade carries a stop at entry
- **No stop, no order:** an order intent without a pre-defined stop is **rejected by code**. This is enforced in
  the guardrails and the OMS, and agents cannot override it.
- **Stop fields** are fixed at entry and stored with the intent: stop level or trigger, stop type, time stop,
  modelled stop slippage, gap allowance, and the resulting WCL.
- **Sizing:**

```text
q = floor( 0.005 * E_t / WCL_unit )   (and the other limits in Section 10.1a)
WCL_unit = stop_distance + modelled_stop_slippage + gap_allowance + fees
gap_allowance = max(0, G - stop_distance)        # so WCL_unit = max(stop_distance, G) + slippage + fees
```

  For any position held overnight, a stop **cannot** lower the WCL below the gap stress G. Stops cut typical and
  intraday losses; **G sets the size**.
- **Stops move only in the protective direction** (tighten, never loosen). Every change is an audited event.

#### 2. Stop types by strategy
| Sleeve | Stop design | Execution |
|---|---|---|
| A6 ETF relative strength (pairs) | **Pair-level hard dollar stop** at 70% of the trade's WCL budget ($350 for an A6 pair at a $500 budget), leaving 30% for slippage and gap. Plus a ratio stop at 2 x ATR(14) of the ratio against the position, and a time review at each weekly decision | Software-monitored on combined pair P&L. **Both legs exit together** (cancel-both, then complete or flatten). A broker-native catastrophe stop on each leg sits at the level where pair loss equals the cap; if one fires, software closes the other leg immediately |
| A1 ETF pairs | Spread **z-score stop at abs(z) >= 3.5**, plus the hard dollar stop ($700 at a $1,000 budget), plus a time stop of 10 sessions; whichever comes first | Same as A6: pair-level, both legs together |
| TOM overlay (long broad ETF) | Price stop at 2 x ATR(14) below entry, plus the window-end time exit | **Broker-native** stop (survives process death): a marketable stop-limit with the limit 1% beyond the trigger, plus an emergency market fallback after 60 s unfilled during regular hours |
| A4 EAR (single names) | Price stop at 2.5 x ATR(14), plus the 20-session time stop. Entry is after the event, so G = 20% (outside earnings windows, *verify*) | Broker-native stop-limit as for TOM |
| Options spreads (B1/B3/B4, when enabled) | Exit triggers, first hit: (a) spread value >= 2 x the entry credit (a marked loss of 1.0 x credit); (b) the underlying trades through the short strike. **The defined-risk max loss is the backstop and the sizing basis**, because spread stops gap and illiquid combos may not fill | **Software-monitored**: a regular-hours loop (60 s), marketable combo exit at the c = 1.5 stress price, escalation after 3 tries; a fail-safe alert if the loop dies. |

#### 3. Honest limits of stops
- **Gaps:** an overnight or event gap fills at the open or worse, not at the stop. That is why sizing uses G.
- **Limit-based stops may not fill.** Stop-limits get a marketable offset, plus an emergency market fallback with a
  modelled slippage allowance.
- **Broker-native vs software stops:**
  - ETF and stock legs use broker-held stops, so protection survives process death.
  - Pair-level and options-spread stops need software. They depend on the monitor being alive, so the
    heartbeat, kill switch and broker catastrophe stops are mandatory backstops.
- **Whipsaw:** stops sell into noise and, for mean-reversion sleeves (A1), often exit just before the reversion.
  - Backtests report results **with and without stops** as a diagnostic.
  - Stop parameters are registered family dimensions that count toward the 12-configuration cap.
  - Stops are expected to **lower Sharpe and win rate** for A1 and to cut tail loss.

#### 4. Backtest realism for stops
- **Trigger:** for a long position, the stop triggers when the bar's low <= the stop.
- **Fill:** if the bar opens through the stop (a gap), the fill is the **open**; otherwise it is the stop price.
  Either way, subtract stressed slippage: the spread at the 2x stress multiplier plus impact.
- **Intrabar ordering:** if the stop and the target both fall in one bar, **the stop comes first**.
- **Daily bars only (2003-2021):** the same rules apply on daily OHLC, and there is no assumption about intraday
  path.
- **Pairs:** the stop is evaluated on pair P&L at each bar close, with a both-legs exit at the next bar's
  conservative fill. The intrabar pair path is unknown, so this adds one bar of delay.
- **Reported per run:**
  - stop-out rate;
  - average and worst loss on stopped trades vs the cap;
  - the distribution of (realised loss / cap);
  - **the number of cap breaches, which must be 0 in the 2x-stress backtest**.
  - **In development only:** a breach means G was too low. G is raised as a registered change counted in the
    trial ledger, and the run repeats.
  - **At the holdout opening:** a breach **fails the policy**. G cannot be changed and re-run on the holdout.

#### 5. Viability at $1,000 per trade with stops (E = $200,000)
| Position | Stop (typical) | G planning / empirical [unverified] | Max notional per trade | Commission per round trip | Commission as % of notional |
|---|---|---|---|---|---|
| A6 pair, $500 budget | $350 pair stop | 15% / 8.75% | **about $3.3k / $5.7k per leg** | about $1.40 (4 orders) | < 2 bps of pair gross |
| A1 pair, $1,000 budget | $700 pair stop + z-stop | 15% / 8.75% | **about $6.6k / $11.4k per leg** | about $1.40-2.00 | < 1.5 bps |
| A4 name, $400 budget | 2.5 x ATR | 20% / 15% | **about $2k / $2.7k** | $0.70 | about 3.5 bps |
| TOM broad ETF | 2 x ATR | 20% / 13% | about $5k / $7.7k | $0.70 | about 1.4 bps |

- The gap stress, not the stop distance, sets the size.
- **At $200k, fixed fees no longer decide viability.** Spread, impact, borrow and the signal itself do.

#### 6. Stop monitoring and the kill switch
- **Missed stop:** a stop condition was detected but there is no exit fill within 2 minutes (regular hours), or a
  broker-native stop is missing at reconciliation.
  - Action: **block new risk**, escalate, and attempt the emergency exit.
  - Two missed stops in a session trip the kill switch (reduce-only).
- **After a restart:** stops are persisted with the intent and reconciled against broker-held orders **before**
  any new order is allowed.

### 10.2 Order management (offline first, with a simulated broker)
- **Intents:** a stable intent ID; each broker attempt gets its own attempt ID. The intent is persisted before
  submission.
- **Unknown state:** a timeout becomes UNKNOWN and is resolved by reconciliation. **Never an automatic resend.**
- **State machine:** NEW -> SUBMITTED -> PARTIAL -> FILLED / CANCEL_PENDING -> CANCELLED / REJECTED / UNKNOWN.
- **Positions** = broker executions + broker-confirmed adjustments (splits, assignments, transfers).
- **Pre-trade checks** extend `agent/guardrails.py`. They are deterministic, and agents cannot override them:
  - instrument and session collars;
  - max notional;
  - package max loss;
  - greek limits;
  - duplicate intent;
  - stale data;
  - market hours;
  - paper mode;
  - kill switch.
- **Event store:** append-only tables for decision, target, intent, order-event, fill, allocation and cash.

### 10.3 Broker adapter (IBKR vs Schwab swappable; no commitment)
**Interface** (`execution/adapters/base.py`):
- `capabilities()`: paper API reachable, order types (limit, peg-mid, MOC/LOC), combo or complex orders and
  whether they are atomic, fractional and short rules, exercise/assignment feed, partial-fill reporting, cancel
  semantics, rate limits.
- `submit(intent)`, `cancel(attempt)`, `executions(since)`, `positions()`, `account()`, `heartbeat()`.
- Strategies **query capabilities and fail closed** when a required capability is missing.

| Capability | IBKR (`ib_async` + IB Gateway) | Schwab Trader API |
|---|---|---|
| Paper via API | **Yes** (paper ports 4002/7497) | thinkorswim **paperMoney does not appear reachable via the Trader API** (*unverified*; no evidence of a paper mode) |
| Midpoint peg / MIDPRICE | Yes (*verify per venue*) | Limited (*unverified*) |
| MOC / LOC | Yes | In the live API schema (*unverified*); a weak source says paperMoney lacks MOC/MOO |
| Multi-leg options | BAG combos | Complex order strategies (verticals, condors) in the live API (*unverified*) |
| API access | Account + market-data subscriptions | Developer-portal app approval (*verify*) |
| Commissions | Pro tiered $0.0035/sh, $0.35 minimum; options $0.65 (*verify*) | $0 stocks/ETFs online; options ~$0.65 (*verify*; availability to Singapore residents *verify*) |

- **If paperMoney is not API-reachable,** "paper" means one of:
  - **(a) IBKR paper**, if the maintainer opens it;
  - **(b) the internal simulator**, with manual mirroring into paperMoney and **reconciliation**, clearly labelled.
- Paper is **never** routed through a live endpoint.

### 10.4 Runtime, monitoring, kill switch, audit
- **Runtime:** research is local; ingest stays on the existing Databricks jobs. The pilot runs on one supervised
  Linux host with no Databricks/Lakebase dependency in the execution path.
- **Daily cycle:**
  - 16:30: data arrives.
  - 17:00: freshness check.
  - 17:30: targets are written.
  - t+1: the execution windows (Section 6.3).
  - After the close: reconciliation.
- **Breakers:**

| Trigger | Action |
|---|---|
| Sleeve loss > its budget | Block new risk |
| Portfolio daily loss > 1.5% NAV | Block new risk |
| Portfolio drawdown from the high-water mark: **proposed** >= 4% blocks new risk; >= 6% mandatory reduction of open WCL to <= 2.5%; >= 8% liquidates and stops pending re-validation (open decision, Section 16 item 2) | As listed |
| Integrity breach (reconciliation, stale input, duplicate, exposure) | Block new risk **and cancel working entries**; resume only after full reconciliation |

- **Kill switch:** a Lakebase flag **or** a local file, failing closed. A tested `halt --all` / `reduce-only` CLI
  handles cancellation and reduction.
- **Audit:** immutable linked records (decision -> target -> intent -> order events -> fills -> allocation ->
  cash), carrying input hashes and versions. A daily broker-vs-ledger-vs-sleeve reconciliation report.

### 10.5 Promotion ladder ($200k paper)
| Stage | Gate |
|---|---|
| Research | Section 8.5 gates 1-6 and 8 |
| Shadow (internal simulator on live data) | >= 60 sessions; every workflow observed or drilled; reconciliation clean |
| Paper (IBKR paper or labelled simulator + paperMoney mirror; maintainer approval) | Gate 7; plumbing only, **not** execution-quality evidence |
| Small live (separate maintainer approval) | Maintainer-set caps; this is where passive-fill evidence is collected |
| Scale | Fresh approval |

**A4 and B1** use prospective collection as their holdout.
- **A4:** 2 earnings seasons and >= 500 **eligible events scored**: admission decisions logged, whether traded or
  skipped for capacity. At 5 positions held 20 sessions, only about 30 of them are traded, so all admitted trades
  must also have closed.
- **B1:** >= 52 cohorts.

---

## 11. Agent reliability and hallucination control

**Goal:** not "agents never hallucinate". The goal is that **agent errors cannot silently become trusted
evidence, promoted strategies or executable instructions.** The largest risk is plausible code that implements the
wrong financial meaning while every test passes.

### 11.1 Hard architecture rule
- **Runtime trading authority belongs only to approved, deterministic, versioned, tested services:** the plan's
  rules and classical models (ridge, LightGBM, HAR), frozen per registered family, with hashed artifacts.
- No LLM or SLM produces or modifies a signal, size, order, cancel or risk limit at runtime.
- **Any learned text feature that changes targets is part of the trading model** and inherits every validation
  requirement (Section 11.3).
- **Permitted LLM roles:**
  - research assistance;
  - code authoring through the coder -> validator -> final-gate chain;
  - drafting reports from verified artifacts;
  - read-only anomaly triage.
- Research, triage and reporting go through typed, **read-only** tools.
- **Code authoring** writes only inside a **sandboxed build worktree** with no production, UC-write or
  broker credentials. Its output reaches production only through the reviewed PR chain.
- **Process separation:**
  - **research** (read-only UC credentials, no broker keys);
  - **signal service** (writes target files only);
  - **execution service** (the only holder of broker credentials; accepts only signed targets that pass
    guardrails, building on `agent/confirmation.py` HMAC tokens).
- **Signing:**
  - The signing key lives in an **isolated signer** that research and agent processes cannot reach. The signer
    signs only targets produced by the approved signal-service build (its hash is checked).
  - Every target carries an **expiry**, an account and environment binding (paper or live), a nonce and its
    run_id.
  - The execution side **rejects replays**, expired or wrong-environment targets, and **re-runs every risk check
    independently**. A signature proves origin, not safety.
- **Two-key rule:** the maintainer approves every promotion and every credential that can place orders.

### 11.2 Where errors still enter, and the control for each
| Entry point | Control |
|---|---|
| BUILD requests invent or change assumptions | An **maintainer-approved sleeve contract** (information timing, universe, corporate actions, execution, sizing, failure behaviour). Every change gets a semantic diff against it. Contract changes need maintainer sign-off |
| Agents weaken tests to pass | **Protected acceptance fixtures** (expected results, tolerances, gate scripts) in a CODEOWNERS-style path. Changes there need explicit review. A builder-rewritten green suite counts as weak evidence |
| Wrong financial meaning in code | Financial-invariant tests (future perturbation, unavailable prices, duplicate events), hand-worked sleeve examples, and production mutants (Section 6.6) |
| Shared blind spots between models | Different **evidence**, not just different models: external reconciliation, hand-worked cases, adversarial fixtures, alternative calculations of timestamps, joins, corporate actions, multipliers and costs |
| Stale or detached evidence | Validation records are bound to commit SHA + data snapshot + config + commands + exit status. Missing or stale evidence fails closed |
| Fabricated citations | A mechanical check that file:line resolves at the cited commit and that query and run IDs exist. A reviewer still checks that the citation supports the claim |
| Mislabelled provenance | Connectors stamp provider, retrieval time, object identity and payload hash, and keep the raw payload. An agent-typed `data_source` is an assertion, not provenance |
| Report narration | Factual tables render from artifacts. Measurement is separated from interpretation. Failed runs, exclusions and uncertainty are shown |

**Numbers in reports.** A universal numeric-literal lint is **rejected**: it flags dates and section numbers while
missing cherry-picked sourced numbers.
- Material financial claims instead use **typed report fields**: metric definition, units, universe, period,
  `run_id`, artifact hash and query parameters. These fields are rendered automatically.
- Illustrative numbers are labelled as such.

**Recompute rule.** A universal 1e-6 tolerance is **rejected**.
- Identifiers, event ordering and discrete decisions must match **exactly**.
- Each metric has its own numerical tolerance.
- An **independent ledger reconciliation** covers positions, cash, fees and P&L.
- A second Sharpe implementation over an already-contaminated return series proves little.

**Red-team suite (CI):**
- stale data, NaN/inf, duplicated bars, x100 poisoned prices;
- **instruction-only perturbations** in filings (prompt injection), which must not change authority or unrelated
  fields; ambiguous cases are quarantined;
- schema-valid but semantically corrupt extractor outputs;
- forged or altered signed targets.

### 11.3 LLM, SLM or classical in the decision path?
**Model size is the wrong boundary.** The questions that matter are:
1. Does the output change exposure?
2. Can its historical information set be reconstructed (PIT)?
3. Does it improve portfolio outcomes after costs and selection?
4. Is its failure behaviour acceptable?

**Extractor protocol (A4 only, after the timing audit):**
- **Timestamps come from source metadata** (EDGAR acceptance, wire time), never from model prose.
- Models extract only *interpretive* fields: guidance direction, event type, and GAAP/non-GAAP EPS with units and
  period.
- **Two clocks:** information-available time and feature-available time (including retrieval, extraction and
  validation latency). A replay with a later-built model is labelled *retrospective*.
- **Cache key:** raw input hash + parser/chunking version + model identity + prompt hash + schema + decoding
  config. Raw responses and validated outputs are immutable. Failures and abstentions are cached too.
  - Caching proves replayability, not correctness. A frozen canary set detects changes in hosted models.
- **Gold set:** sized from field-level error bounds and rare classes (no fixed "300").
  - Stratified by issuer, format, amendments and hard timing cases.
  - Separate development, locked evaluation and later temporal evaluation sets, with no issuer near-duplicates
    across splits.
  - A written rubric with evidence spans.
  - Report: disagreement before adjudication, prevalence, field precision/recall, numeric tolerances, and the
    accepted-output error vs coverage curve. (Kappa alone is insufficient; self-reported confidence is not
    assumed calibrated.)
- **Isolation:** the extractor has **no tools, credentials, network authority or downstream instruction channel**.
  Evidence spans are validated against the original document offsets.
- **Drift:** fresh production documents are sampled for adjudication. Shadow-model agreement is a diagnostic only.
- **Comparison:**
  - Baselines must match the task: XBRL/regex for numbers; LM dictionary and TF-IDF+GBM for tone/direction.
  - Cost, latency and accuracy for SLM vs LLM are **measured on the actual corpus before any claim**.
  - The comparison is pre-declared and every trial is counted.

**Risk veto.** An LLM or SLM "risk veto" **is a trading decision**: removing a hedge leg or blocking an exit can
*raise* risk, and a malicious document can trigger systematic abstention.
- Only a **shadow veto** (logged, with no effect on orders) is permitted.
- Promotion would require evaluating the combined policy, including false-veto cost, outages and adversarial
  triggers.
- Protective exits never consult a language model.

**Verdict: NO SLM or LLM in trading decisions now.**
- SLM deployment is deferred.
- LLMs may serve as an offline A4 extractor only after the timing audit, through the protocol above. Shadow use
  comes first; promotion is via the walk-forward gates.
- The near-term investment goes into trustworthy data, immutable evidence and constrained authority. A smaller
  model provides none of these by itself.

**Unclear maintainer term "jev".** It is not interpreted here. Possible readings:
1. a typo for "dev" (development agents);
2. "eval" or an evaluation harness;
3. a specific tool or model name;
4. an acronym such as "judge/evaluator" (LLM-as-judge).

This is an **open question** for the maintainer (Section 16).

---

## 12. Regime detection and adaptation

**Stance.** A detector can be strictly past-only and still produce an overfit trading policy. With the history
available, there is **no evidence yet that regime gating adds value**. Reducing exposure can remove winners and
concentrate the remaining trades.

The program therefore builds regime detection in three layers:

| Layer | Status at launch |
|---|---|
| **(1) Telemetry** | Describes conditions |
| **(2) Mechanical data and execution safeguards** | **Active** |
| **(3) Market-regime gates** | **Shadow only** until one pre-registered exposure reduction per sleeve earns evidence through the normal gates |

Regime states never switch alpha models or allocate toward "favourable" states. **No LLM or SLM makes regime
calls** (Section 11).

### 12.1 What "regime" means per sleeve (hypotheses, not facts)
| Sleeve | Conditions that plausibly hurt it | Sleeve-specific diagnostic (preferred over broad market states) |
|---|---|---|
| A6 relative strength | Trend reversals after high-vol drawdowns (momentum crashes) | Per-pair signal decay; ratio drawdown vs causal OOS distribution |
| A1 ETF pairs | Relationship breaks, persistent residual trends | Causal residual forecast errors, residual persistence, hedge-ratio uncertainty (Kalman variance as a model diagnostic only), recursive CUSUM (Section 5.2) |
| A4 EAR | High-vol earnings seasons, crowded reactions | Event-date clustering, hedge basis, admission rate |
| B1 credit spreads | Vol expansion, gap risk, wide or illiquid options markets | Executable quote width and size at the decision. At entry: implied variance from timestamped quotes vs a **past-only HAR forecast** for the forward horizon. Realised-vs-implied is published only **after** the horizon completes, as an ex-post diagnostic |
| All sleeves | Liquidity crunches, stale or broken data | Field-specific data freshness, quote validity, spread blowouts, fill-rate drift |

**Broad market features are telemetry only:**
- the existing EWMA vol-percentile labels (`risk/regimes.py`: low/mid/high/unknown, past-only);
- RSP/SPY breadth (`gold_regime_features`);
- VIX level (FRED `VIXCLS`, used **from the next session**);
- VIX/VIX3M term structure: VIX3M history, timing and availability are *unverified*. Indices Starter covers VIX
  and VIX3M tickers (*verify*).
- They are not gates. VIX is SPX implied volatility: high VIX or backwardation does not establish that B1 loses,
  because premiums may compensate.

**Feature contract.** Every feature has a stated universe, timestamp, estimator, warm-up and missing-data
behaviour before it is used.
- Revised macro series (FRED) need vintage data (ALFRED) or are excluded.
- Closing-value features take effect at the **next** eligible session.

### 12.2 Detection methods: what each is for
| Method | Use | Parameters | Status |
|---|---|---|---|
| Rule-based vol state (existing EWMA percentile) | Telemetry; candidate exposure ceiling | One frozen convention (current `risk/config.yaml` thresholds and window). Percentile vs **prior** observations with explicit tie handling. **No threshold optimisation** | Active telemetry |
| Absolute stress safeguard | Catches prolonged stress that a rolling percentile would normalise | One registered absolute level per feature, justified separately | Shadow |
| Data/execution health checks | Block new entries on broken inputs | Field-specific freshness: prior-close features 1 session; live quotes seconds. Quote-width and size limits per instrument | **Active** |
| Strategy decay CUSUM (Section 12.4) | Detects deterioration of a sleeve's own edge | Calibrated by dependent null simulation | **Active, advisory** |
| Pair relationship monitor | A1/A6 pair-break evidence | Causal residual forecast-error CUSUM + residual persistence + hedge-ratio uncertainty. Calibrated by replaying the full fitting procedure. Rolling ADF non-rejection and the "half-life > 2x" rule are **not** used as break evidence | Shadow, then registered |
| Markov-switching / HMM (2-3 states) | Research challenger only | Training-only transforms; fixed refit dates; multiple starts; stable state mapping; filtered (causal) probabilities; past published states kept on refit | Optional research; not a delivery dependency |
| BOCPD | -- | The hazard and likelihood choices dominate the result | **Deferred** |
| Gaussian mixture | -- | No temporal structure | Not used |
| Structural-break tests (Chow, Bai-Perron) | Offline diagnosis of past failures | Full-sample by construction | Research diagnostics only, never online |
| Supervised "strategy works" classifier | -- | Most overfit-prone: labels come from the same P&L, episodes are few, and the regime-definition search is large | **Not used** |

**Decision theory.** Thresholds are set by a **system-level false-intervention budget**, not per-stream ARL0
targets.
- **Definition:** under the dependent null, the **expected** number of advisory alarms across all sleeves is <= 2
  per 252 sessions, with P(>= 5 alarms in 252 sessions) <= 5%.
- After an alarm, that monitor resets and has a **20-session refractory period**.
- Calibration uses >= 2,000 dependent simulations, and the 95% Monte Carlo interval of the expected count must lie
  at or below 2.
- **Power targets** are pre-registered before calibration, e.g. detect a deterioration of delta within 60 trades
  with probability >= 0.5, with tolerances.
- Nothing here guarantees a pathwise maximum.
- Detection delay is reported as a power curve against specified alternatives (e.g. sleeve expectancy drops by
  delta standardised units). It is not promised as a fixed number.
- Missed-trade, idle-capital, whipsaw and restoration costs are part of every evaluation.

### 12.3 Hard problems and how they are handled
- **Look-ahead:**
  - only filtered, one-sided states;
  - train-only normalisation;
  - historical published states are immutable across refits;
  - historical universe membership;
  - PIT joins on publication time, including revisions.
- **Power:**
  - 2022-26 holds roughly three stress episodes (2022 bear, 2024-08-05, 2025-04), and that data is already
    consumed.
  - Daily observations are not independent regime episodes. Weekly B1 cohorts and clustered A4 events carry even
    less information.
  - Any gate test is therefore a long-history (2003-2015 development) exercise for the equity sleeves only. B1
    gates cannot be validated historically before 2022.
- **Multiple testing:** every feature, estimator, threshold, action and refit choice counts toward the trial ledger
  (Section 4.6), discarded variants included. Regime gating is pre-registered in the family YAML as **one**
  candidate exposure-reduction policy per sleeve.
- **Evaluation of a gate:**
  - **Primary endpoint (pre-registered):** the difference in annualised net mean daily P&L, gated minus
    benchmark, per unit of average gross exposure, over development data. The gate passes only if:
    - the one-sided 95% paired stationary block bootstrap lower bound (block = max(10, 2 x hold) sessions, 5,000
      draws) is > 0; **and**
    - the 99% daily ES is not worse; **and**
    - the aggregate caps and stress limits still hold at the portfolio level.
  - **Benchmarks:**
    - the ungated sleeve;
    - a **causal matched-exposure** benchmark that scales the ungated sleeve by the gate's ex-ante average
      ceiling from the *previous* development block, never from realised future gate activity.
  - Portfolio interactions with binding aggregate caps are included.
  - DSR is a diagnostic only; it does not repair an incomplete ledger or missing crises.
- **Holdout discipline:**
  - Detector, policy table and stress assertions are frozen **before** the 2016-2021 holdout is opened.
  - **No holdout-dependent replay** (including 2018-02 and 2020-03) runs before the single authorised opening.
  - Changes after opening need fresh confirmation elsewhere (prospective data).

### 12.4 Strategy decay monitors (active, advisory)
- **Observation unit (cohort contract):**
  - One observation per **cohort**: all trades of a sleeve opened in the same decision window (weekly for A6 and
    B1; per session for A1 and A4).
  - A cohort is published when its **last** member closes, or at the sleeve's maximum holding period, whichever
    is first. Open members are then marked to market.
  - `x_c = (sum of net P&L, realised + marked) / (sum of entry-approved WCL budgets)`. The denominator is frozen at
    entry, and partial exits stay inside their cohort.
  - The baseline and calibration use the **same cohort units**.
  - Losses beyond the budget are flagged separately (Section 10.1a).
  - **Independent mark-to-market monitoring** of open positions (breakers, stops) runs regardless, because a
    completed-cohort monitor misses unrealised losses.
- **Baseline:** the mean mu_0 and scale s_0 (with a pre-defined positive floor) of `x` from the **causal
  out-of-sample development trades** of the frozen strategy and execution model. Optimised in-sample backtests are
  never the baseline. Overlapping trades are handled at the cohort level.
- **Lower CUSUM** (one observation per cohort c):

```text
z_c = (x_c - mu_0) / s_0
C_c = max(0, C_{c-1} - z_c - k),  with k = delta / 2
alarm when C_i > h
```

  - delta is the minimum economically meaningful deterioration, set per sleeve by the maintainer.
  - h is calibrated by dependent null simulation and block replay, **including normal losing streaks**, baseline
    uncertainty, clustering, simultaneous monitors and resets, to meet the system false-intervention budget.
  - No universal h exists.
- **Separate monitors:**
  - **execution decay:** realised/modelled cost (with floors), fill-rate drift and quote-width drift;
  - **edge decay:** the CUSUM above.
- **Actions:**
  - An alarm triggers **review only** at launch.
  - An alarm-triggered exposure ceiling would be a registered trading policy. It needs the same evidence
    (Section 12.3) and promotion gates as any other exposure reduction; maintainer approval alone is not enough.
  - There is **no automatic retirement after N trades**. Retirement follows Section 13.2 kill criteria and
    maintainer review.
  - A second alarm is not independent confirmation.
  - An expectancy *upper* confidence bound below zero, under sequential calibration, is the strong evidence for
    retirement. A lower bound below zero is not.

### 12.5 Regime service and policy table
- **Regime state record** (typed, versioned, immutable):

```text
sleeve, feature_set_version, detector_version, decision_ts, effective_ts,
source_timestamps (per field), states (per field), health (per field: OK/STALE/MISSING/INVALID),
policy_version, reason_codes, data_source='derived'
```

- **Policy table:** each row maps sleeve x explicit condition to:
  - effective time;
  - entry permission;
  - **exposure ceiling (<= 1.0)**;
  - pending-order action;
  - existing-position action;
  - **recovery condition**;
  - reason code;
  - status (ACTIVE / SHADOW).

  Priorities are frozen. Correlated cuts **do not multiply** into an accidental shutdown: the minimum ceiling
  applies, not the product.
- **Active rows at launch** (mechanical only):
  - required input STALE, MISSING or INVALID for that sleeve -> no new entries for **that sleeve only** (unless a
    portfolio dependency fails); existing stops and exits stay active;
  - quote width or size outside limits -> no new entries in that instrument;
  - decay-CUSUM alarm -> review flag only.
- **Shadow rows:**
  - one pre-registered market-regime exposure reduction per sleeve (e.g. a vol-state "high" ceiling);
  - logged with their counterfactual effect;
  - promoted to ACTIVE only after passing the Section 12.3 evaluation and maintainer approval.
- **Invariants:**
  - The regime layer can only **reduce** risk or halt. Ceilings are <= 1.0, applied **after** the 0.5%
    per-trade cap and the aggregate caps, and enforced after quantity rounding (q = 0 means skip).
  - **Raising risk requires maintainer approval** and is outside the regime service.
  - Account drawdown breakers (4/6/8%) and mandatory stops are independent and take precedence.
- **Anti-chatter and recovery:**
  - **Mechanical health blocks act immediately**, with no hysteresis or dwell.
    - Pending entry orders in the affected sleeve are **cancelled**.
    - Stops, exits and breaker actions are never delayed by the regime layer.
  - **Hysteresis and minimum dwell** (one frozen band, the existing `risk/config.yaml` convention, not optimised)
    apply only to *market-state* transitions of shadow or approved gates.
  - **Recovery** means restoring exposure **up to a previously approved ceiling**, never above it. It is
    automatic, gradual (at most one ceiling step per week) and always intersected with the current health,
    breaker and risk-limit state. It persists across restarts.
  - Raising any approved ceiling or cap still requires maintainer approval.
- **Health monitoring:**
  - feature drift (PSI as an alert);
  - state-duration and state-frequency statistics vs development (live vs backtest);
  - HMM calibration (only if the challenger exists);
  - detector computation failures;
  - all routed through the Section 10.4 alerting path.

### 12.6 Stress replays and synthetic generators
**Events, assertions frozen in advance:**

| Event | Inside held data (2022+)? |
|---|---|
| 2008-09/10 | No: needs Massive 2003+ |
| 2011-08 | No: needs Massive 2003+ |
| 2015-08-24 | No: needs Massive 2003+ |
| 2018-02-05 | No: needs Massive 2003+. **Inside the sealed holdout:** replayed only at the single opening |
| 2020-03 | No: needs Massive 2003+. **Inside the sealed holdout:** replayed only at the single opening |
| 2022 rates | Yes (options replay from 2022-03-07) |
| 2024-08-05 | Yes |
| 2025-04 | Yes |

**Four separate replay types:**
1. underlying-data replay;
2. detector replay;
3. portfolio-accounting replay;
4. executable-options replay, **only on or after 2022-03-07** with valid contemporaneous quotes. Earlier B1
   replays are rejected, and B1 fills are never fabricated from daily underlying bars.

**What the replays assert is required behaviour, not P&L:**
- **entry** WCL <= 0.5% of equity and aggregate **approved** risk <= 5% at every decision;
- the prescribed 4/6/8% breaker actions fire;
- realised overshoots (gaps, unavailable quotes, failed stops, liquidation costs) are **recorded and reported, not
  asserted away**, because stops do not guarantee loss bounds;
- no regime-driven risk increase;
- stale-feed and exchange-interruption handling;
- false alarms and rapid recoveries handled without chatter.

**Synthetic generators** cover:
- heavy-tailed returns with clustered volatility (GARCH-t);
- abrupt and gradual vol shifts;
- temporary shocks;
- correlation breaks;
- cointegration breaks (an AR(1) spread turning into a random walk);
- **misspecified generators**, not only switches drawn from the detector's own model.

---

## 13. Phased roadmap, gates and kill criteria

### 13.1 Timeline
| Weeks | Work | Exit |
|---|---|---|
| 1-4 | WP1 contracts/registry; **WP2 metrics/tearsheet**; WP3 ledger + dividends/withholding/financing; WP4 costs v2 + $200k cost drag; WP5 daily engine + best-execution simulator (G/P1/P2) + legacy parity; WP6 statistics harness | CI green; mutation proofs; final gate |
| 2-5 | **WP-AG1** spec contracts + protected fixtures; **WP-AG2** decision-path firewall design (no broker code) | Approved sleeve contracts |
| 4-5 | WP7 residual falsification (4 runs) | Pass/park; not deployable |
| 1-3 | **WP-D0** entitlement + feasibility + **licensing gate**; **WP-D3** broker forward collection starts (>= 5 weeks before the purchase) | Written licensing answers; collector running |
| 5-9 | **One purchase month:** WP-D1 bulk pull + manifest + completeness audit; WP-D2 contract reference; WP8 dividends; WP9 history + sealed holdout | Audit sign-off >= 5 business days before renewal; cancellation confirmed |
| 7-11 | WP10 A6, WP11 A1 + TOM | Gate decisions, then shadow |
| 9-13 | WP12 EDGAR timing audit -> WP13 A4 (concentrated) | Audit pass/fail |
| 10-14 | WP14 execution study (minute bars/quotes) | Fill-scenario report |
| 10-15 | WP-D4 reconciliation/join; WP15 event engine + B1 on the pulled quotes | B1 gate decision at $200k |
| 13-17 | WP16 allocator + OMS + monitoring; WP17 evidence-backed reporting; WP18 red-team suite | Fault injection passes |
| >= 17 | WP19 broker adapters (approval) -> paper | Section 10.5 |
| 6-10 | **WP-RG1** regime telemetry + data-health service; **WP-RG3** policy-table engine (mechanical rows active, regime rows shadow) | Health rows active; telemetry published |
| After the first sleeve passes research gates | **WP-RG2** decay monitors (advisory CUSUM, execution-decay monitors) | Null calibration meets the false-intervention budget |
| With the 2003+ data | **WP-RG4** stress-replay and synthetic-generator suite | Frozen assertions pass |
| Later, optional | WP-RG5 one pre-registered exposure gate per equity sleeve (evaluation); HMM challenger research | Section 12.3 evaluation |
| Later, conditional | WP20 A4 text-extractor experiment (shadow) | Section 11.3 |

### 13.2 Kill criteria
- **Research:** a failed gate parks the sleeve. Revival needs a new hypothesis family and unseen data.
- **Live:** the Section 10.4 breakers.
- **Program:**
  - If none of A6, A1 or TOM passes on long history, stop the equity sleeves.
  - If the XSP and SPX quote trials fail the friction/credit gate at 2x variable costs, **stop the options
    sleeves**.
  - If the licensing gate fails, the one-month design stops. Any continuous tier needs a new approval.
  - If the completeness audit fails a sleeve's acceptance criteria, that sleeve's data is declared incomplete.
    It cannot be repaired after the lapse.

---

## 14. Risk, delivery and work packages

### 14.1 Portfolio risk
- **Stress tests:** 2022 H1, 2024-08-05 and 2025-04 replayed; 2018-02 and 2020-03 as parametric shocks until the
  holdout opening. The limits are those of Section 10.1a: each joint scenario <= 5% of E_t, crash cluster <= 3%, and
  entry WCL and aggregate approved risk within caps.
- **ETF gaps:** a 10% SPY gap must stay <= 1% NAV per sleeve.
- **Perps:** `perpetual_future` if ever used.
- **Data lapse risk:** after cancellation, nothing can be re-pulled.
  - **Mitigations:** the pilot, priority order, incremental audits, sign-off >= 5 business days before renewal,
    renewal switched off, an owner-visible daily progress and budget report, resumable checkpointed downloads with
    retry limits, and disk-capacity alerts.
  - **Residual risks:** credentials expiring mid-pull, partial or corrupt objects, rate limiting, vendor
    corrections published after the pull, schema changes, and accidental renewal.

### 14.2 Delivery (per repo `AGENTS.md`)
- **Chain:** coder (MiMo or DeepSeek by the peak rule) -> the other model validates -> **Codex Sol final gate**
  (Opus only on a Sol usage-limit fallback) -> draft PR -> CodeRabbit.
- Every PR updates README.md.
- Gate runs exclude spark/lakebase/databricks markers.
- BUILD requests forbid pandas and specify test shapes and mutations.

### 14.3 Work packages

Tests, oracles and the required mutants for each work package are specified in Section 15.9.
| WP | Scope | Key files | Tests / mutation proofs | Acceptance |
|---|---|---|---|---|
| **WP1** | Contracts + immutable run registry + family registry | `strategies/mft/contracts.py`, `registry.py`, `families/*.yaml` | Invalid `data_source`/instrument_type rejected; duplicate runs rejected; future inputs rejected; cap of 12; consumed-period flag. **Mutations:** availability check, cap | Offline; 2022-26 cannot be marked unseen |
| **WP2** | **Metrics + tearsheet library** (Section 8): daily and per-trade metrics, options metrics, gate statuses, Polars schemas | `strategies/mft/metrics.py`, `tearsheet.py`, `tests/mft/test_metrics.py` | Hand-computed fixtures (Sharpe, Sortino with all-period DD, MDD/TUW with censoring, ES, tail-ratio N/A, PSR/MinTRL, profit factor UNDEFINED); status enums. **Mutations:** downside deviation over negatives only; tail ratio with abs on both sides; Calmar window mismatch | Matches hand values; UNDEFINED/CENSORED/INSUFFICIENT emitted correctly; PENDING never renders as PASS |
| **WP3** | Ledger: ex-date dividends, **30% withholding**, payments-in-lieu, financing, calendar, assignment booking | `ledger.py`, `corporate_actions.py`, `calendar.py` | Ex/pay settlement across an exit; withholding lines; short payment-in-lieu at 100%; split wealth; DST/early close. **Mutations:** withholding off; short dividend sign; split quantity | Exact reconciliation |
| **WP4** | Costs v2: effective-dated fees, per-order minimums, $200k cost-drag and impact report, options friction/credit | `costs.py`, `fees.py`, `config/fee_schedules.yaml` | $50/$500 tick cases; $0.35 minimum on small orders; friction/credit for $1 and $3 spreads. **Mutations:** full spread per side; minimum ignored | Section 7.6 tables reproducible from config |
| **WP5** | Polars daily engine + **best-execution simulator** (G/P1/P2 on minute bars) + legacy parity | `daily_engine.py`, `exec_sim.py`, `legacy_adapter.py` | Trade-through only on subsequent complete minutes; deadline crossing; A1 imbalance B bound and cancel-both; legacy parity. **Mutations:** touch counted as fill; same-minute fill; skip deadline crossing | Invariants pass; gate uses G |
| **WP6** | Statistics harness (purging, simultaneous bound, SPA, sealed `open_holdout`) | `ml/harness/*` | Noise families reject at <= 5% + MC error; one-time open | As v2 |
| WP7 | Residual falsification | `families/residual.yaml` | N >= 14 | Pass/park |
| WP8-9 | Massive dividends; 2003+ history; sealed holdout | `etl/`, restricted schema | Manifest overlap rejection | Holdout sealed |
| WP10-11 | A6; A1 + TOM | `a6_*.py`, `a1_*.py`, `a5_tom.py` | Lot rule; withholding by direction; frozen WP14 schedule | Gate report |
| WP12-13 | EDGAR timing audit; A4 concentrated | `etl/`, `a4_ear.py` | Session mapping | 100-event audit |
| WP14 | Execution study (minute bars/quotes) | `research/exec_study.py` | Scenario brackets | Report only |
| WP15 | Options: quote reconstruction, event engine, B1 | `event_engine.py`, `b1_vrp.py` | As-of quote reconstruction (no future quotes); C_nat convention; settlement; assignment drill | Friction/credit at the approved cap |
| WP16 | Allocator, OMS, **mandatory stop manager** (Section 10.1b), monitoring, kill switch (simulated broker) | `portfolio.py`, `oms.py`, `monitor.py` | Fault injection; integrity breach cancels entries | No broker code |
| **WP-AG1** | Sleeve contracts + protected acceptance fixtures + evidence binding | `strategies/mft/contracts/*.yaml`, CODEOWNERS, `scripts/evidence_bind.py` | A test-weakening diff is flagged; missing evidence blocks | Contracts approved |
| **WP-AG2** | Decision-path firewall: process separation, signed targets, read-only research credentials, guardrail extensions | `execution/firewall.py`, `agent/guardrails.py` | Altered, stale, expired, replayed or wrong-environment targets rejected; execution re-runs risk checks; agents cannot change limits or reach the signer | No order path without a valid signature |
| WP17 | Evidence-backed reporting (typed fields, citation resolver) | `strategies/mft/report_fields.py` | Fabricated `run_id` or file:line fails | Material numbers render from artifacts |
| WP18 | Red-team suite | `tests/redteam/` | Poisoned data; instruction-only perturbations; forged targets | All blocked or quarantined |
| WP19 | Broker adapters (IBKR, Schwab) behind `capabilities()` (**approval**) | `execution/adapters/*` | Capability fail-closed; paper never routed live | Maintainer sign-off |
| WP20 | A4 text-extractor experiment (conditional, shadow) | `research/extract/*` | Section 11.3 protocol | Shadow-only results |
| **WP-RG1** | Regime telemetry + field-specific data health: EWMA vol labels (reuse `risk/regimes.py`), breadth, VIX next-session, quote health | `strategies/mft/regime/telemetry.py`, `health.py` | PIT joins on publication time; next-session effect; revision handling; warm-up -> `unknown`; restart persistence | Immutable versioned states; no gate effect |
| **WP-RG2** | Strategy decay monitors: per-trade lower CUSUM on `x_i`, execution-decay monitors | `strategies/mft/regime/decay.py` | Cohort contract (asynchronous closures, partial exits, marked open members); dependent-null calibration to the defined budget; pre-registered power targets | **Review-only** alarms; no order effect |
| **WP-RG3** | Policy-table engine: rows, priorities, min-ceiling (not product), ACTIVE/SHADOW, recovery, counterfactual logging | `strategies/mft/regime/policy.py`, `config/regime_policy.yaml` | Ceilings <= 1.0; applied after caps and rounding; stale input -> immediate block + pending-entry cancel for that sleeve only; recovery only up to an approved ceiling | Cannot raise risk; shadow rows have no order effect |
| **WP-RG4** | Stress-replay + synthetic regime generators | `tests/regime/`, `research/regime_replay.py` | Four replay types; options replays rejected before 2022-03-07; holdout-dated replays locked until the single opening; misspecified generators | Frozen assertions pass; overshoots reported |
| **WP-D0** | Entitlement, feasibility pilot and **licensing gate** (maintainer action plus tooling) | `research/data_pilot.py`, `docs/data/LICENSING.md` | Pilot measurements; projection vs the month | Written licensing answers; pilot projection <= 60% of the month or re-scoped; all-in budget approved |
| **WP-D1** | One-month bulk pull: resumable downloader, append-only manifest, causal contract filter, restricted holdout routing, incremental completeness audit | `etl/massive_bulk.py`, `etl/massive_manifest.py`, `etl/completeness_audit.py` | Calendar fixtures; resume after partial object; holdout routing; filter no-lookahead | Sign-off >= 5 business days before renewal; manifest complete |
| **WP-D2** | Historical options contract reference (expired contracts, roots, settlement style, adjustments) | `etl/massive_contracts.py` | Reference-vs-quote coverage | Mandatory dependency of every retained quote pull |
| **WP-D3** | Broker forward collection (one verified broker): chains, underlying, our orders and fills | `execution/collect_quotes.py` | Cadence, fresh-vs-cached flag, append-only, source flag | >= 20 completed sessions before the bulk cutoff |
| **WP-D4** | Vendor-broker reconciliation and versioned join view | `research/overlay_reconcile.py`, `gold/overlay_join.sql` | Stratified diagnostics; pre-set thresholds | Join approved only if thresholds pass; no unflagged mixing |
| WP-RG5 | (Optional) evaluate one pre-registered exposure gate per equity sleeve; HMM challenger research | `research/regime_gate_eval.py` | Paired block bootstrap vs ungated and matched-exposure | Promotion only via Section 12.3 + maintainer approval |

---

## 15. Unit and execution testing strategy

**Principle.** Every acceptance test must be **contract-bound and non-vacuous**:
- the conventions are stated;
- the expected result is established independently;
- the test provably reaches the intended branch;
- the test kills at least one relevant production mutation.

Green coverage alone is never acceptance evidence.

### 15.1 Pure-function unit tests with independent oracles
- **Oracle specification file.** Each fixture has an entry in `tests/mft/oracles/*.yaml`:

| Field | Content |
|---|---|
| Convention | Formula and convention |
| Derivation | Source or derivation (hand calculation, spreadsheet, or a published worked example whose assumptions match) |
| Units | Units and rounding |
| Reviewer | Independent reviewer |

  Expected values are **literals**. A test that calls the function under test (or a shared helper) to compute its
  own expected value is **rejected in review**. This is the known failure mode where builder tests copy production
  logic.
- **Metrics (WP2):**
  - Sharpe (excess returns, sample sd, sqrt(252), zero-variance -> UNDEFINED).
  - Sortino (stated MAR; all-period downside denominator).
  - Win rate, payoff, expectancy, profit factor (UNDEFINED with no losses; INSUFFICIENT under 20 losses).
  - PSR/MinTRL/DSR (skew and kurtosis conventions, trial count and sample size stated; a "golden" value only
    where a reproducible derivation exists).
  - MDD, time under water and Ulcer (initial NAV included, ties, recovery convention, terminal censoring).
  - Tail ratio (N/A when the quantiles do not straddle zero).
  - Values on **either side of every gate threshold**.
- **Costs (WP4):**
  - $0.35 minimum on small orders.
  - Tick floor at $50 and $500 (h = 1 bp and 0.1 bp).
  - Square-root impact for the worked examples in Section 7.2.
  - Fee effective-date boundaries, weekend borrow accrual, the financing rate switch.
- **Options math (WP15):**
  - Vertical and **asymmetric-wing** condor payoff on a strike grid, with multiplier and quantity explicit.
  - Gross vs net premium; max loss = width x 100 x qty - credit; friction/credit.
  - Net results may exceed gross payoff bounds only by fees, which is asserted, **for intact packages**. Broken-wing
    butterfly fixture: long 100C / short 2x 105C / long 115C has payoff -$500 above 115.
  - American legs (SPY, single names): assignment, gap, dividend and forced-liquidation fixtures.
- **Risk sizer (WP16)**, cap 0.5%, E = $200,000 (cap $1,000):
  - XSP $1-wide spread, $20 credit, **stressed lifecycle costs $6** (entry and stop-exit fees at $1.50/contract/side;
    mandatory stops add exit fees): WCL $86 -> q = **11** ($946). After equity falls to $180,000 (cap $900):
    q = **10**.
  - **0DTE rejection:** an XSP entry whose expiry is the same session (e.g. a Friday entry into that Friday's
    expiry) is rejected.
  - **Assignment notional with two short legs:** a 1-contract condor on a $101 stock (2 x $10,100 = $20,200 >
    $20k) is rejected; on a $100 stock it is allowed. A SPY condor is rejected; a SPY vertical (1 contract) is
    allowed.
  - **Floor boundary:** WCL exactly $100.00 -> q = 10; WCL $100.01 -> q = **9**. The sizer never rounds up past the
    cap.
  - SPX $10-wide, WCL $858 (stressed lifecycle) -> q = 1. At E = $170,000 (cap $850) -> q = **0**, so the trade is skipped.
  - TOM broad ETF at G = 20% with $0.35 fees, priced $100: q = floor(999.65 / 20) = **49 shares** ($4,900).
    Notional $4,995 -> WCL $999.35, allowed; $5,000 -> $1,000.35, rejected.
  - A1 pair bundle at G_rel = 15% with $1.40 fees: $6,600 long leg -> $991.40, allowed; $6,700 -> $1,006.40,
    rejected.
  - **Aggregate:** with $9,500 of open WCL, a new $1,000-WCL trade is rejected under the 5% cap ($10,000); a
    $500 trade is allowed.
  - **Assignment notional:** an open SPY short contract ($65k) plus a second one ($130k > $100k) -> the second is
    rejected.
- **Ledger (WP3):**
  - Explicit ex-date entitlements and pay-date postings. Example: a $45 gross distribution -> $13.50 withheld at
    30% -> $31.50 net.
  - A short pays 100% payment-in-lieu.
  - An exit between the ex-date and the pay date keeps the receivable.
  - Split and reverse split preserve wealth, with fractional-share cash.

### 15.2 Property-based tests (Hypothesis)
| Property | Domain qualification |
|---|---|
| Cost monotone in the variable-cost multiplier and in order size | Only over the feasible domain: same rounding bucket, no minimum-fee kink, no rejection |
| NAV conservation: `dNAV = trading P&L + income - fees - financing + external flows` | Sign conventions explicit; sleeve P&L composition defined |
| Position and cash identities | Every change maps to a fill, fee or corporate-action event |
| **No look-ahead** | Appending or perturbing data after t (by publication timestamp, including **revisions**) leaves signals and orders <= t unchanged |
| Idempotent reruns | Same config, event order, injected clock, random stream and schema version -> identical canonical economic-state hash (incidental timestamps excluded) |
| Options package P&L within [-(structure max loss) - costs, (structure max gain) - costs] | Per **intact** package at expiry; max loss/gain computed per structure from every strike breakpoint and both tails (not width - credit for butterflies); American-leg packages are tested separately under assignment, gap, dividend and liquidation scenarios |
| Netting preserves sleeve attribution | Sum of sleeve allocations = net position |
| **Per-trade cap: no generated order has WCL > 0.5% of E_t** | For random equity ($1k-$10M), prices, widths, credits, fees and gap stresses: WCL(order) <= 0.005 x E_t (+0 tolerance after contractual rounding); q < 1 means no order; q is the floor of the minimum over all limits; q+1 would violate at least one binding limit, which need not be the per-trade cap |
| **Cap tracks equity** | After a simulated loss sequence, the next permitted size is non-increasing as E_t falls; sizing never uses the high-water mark |
| **No stop, no order** | Any generated intent without a valid stop (or with a stop on the wrong side) is rejected |
| **Loss on stop <= 0.5% of E_t under the modelled gap** | For random gaps up to G and the stressed slippage, the realised stop-out loss including fees <= 0.005 x E_t |
| **Stops only tighten** | Any sequence of stop updates is monotone in the protective direction |
| **Aggregate, cluster and assignment caps** | Sum of open WCL <= 5% of E_t; crash cluster <= 3%; assignable notional <= 50% of E_t; a new order that would breach any of them is rejected |

**Hypothesis settings:**
- `derandomize=True` in the CI gate, plus explicit `@example` boundary cases.
- 200 examples is a starting budget, not adequacy evidence.
- No wall-clock `deadline` for stateful tests; suite-level timeouts instead.
- The example database is kept locally and failing examples are published as CI artefacts.
- A scheduled nightly job runs with a rotating seed (outside the gate).

### 15.3 Leakage/PIT tests and mutation proofs
- Each work package lists **at least five curated, non-equivalent semantic mutants** covering every critical
  invariant (Section 15.9). The gate requires **100% of curated mutants killed**. Broad automated mutation scores
  are supplementary.
- **Evidence per mutant:** baseline pass, exact commit, patch, command, the **named failing assertion**, and
  output.
- **What is not a kill:** import errors, collection failures, timeouts or unrelated failures.
- **Who reproduces it:** the validator records the evidence. The final gate reproduces it independently in an
  isolated `/tmp` copy made with `git archive`.
- **Regression proofs** for changed behaviour must fail on the parent revision for the intended reason.
- **Leakage fixtures:**
  - a future-return feature;
  - a backdated XBRL revision;
  - overlapping labels across a split;
  - same-bar and same-minute execution;
  - a publication-time vs event-time swap;
  - a month-end look-ahead selection, which must be **rejected** (A4 uses the causal admission threshold).

### 15.4 Golden, regression and differential tests
- **Policy:** fixtures committed to the repository are **synthetic only**. No vendor data (Massive or otherwise) is
  committed, because of the licensing terms.
- **Frozen synthetic datasets** (Parquet + JSON expected outputs; regeneration requires explicit review):
  - 20 sessions x 4 symbols with one split, one dividend and one delisting;
  - an AR(1) pair with a known half-life;
  - an options chain of 2 expiries x 9 strikes with a settlement and an assignment.
- **Edge inputs:** empty, singleton, null, duplicate, shuffled, timezone-aware and partition-boundary inputs.
  Intermediate decisions are compared, not only final NAV.
- **Legacy parity:** the pandas engine vs the Polars engine on the residual synthetic inputs. Orders, ledger
  events and integer quantities must match exactly; returns use per-field tolerances. This is supporting evidence
  only, since two engines can share a bug.
- **Metamorphic tests:**
  - symbol relabelling and permutation of independent assets leave results unchanged;
  - splits preserve wealth;
  - scaling claims are tested only where fees, lots, liquidity and impact allow.

### 15.5 Execution-path tests (FakeBroker, stateful)
- **Driver:** a deterministic `FakeBroker` plus a Hypothesis stateful model of the broker and OMS. Events may be
  duplicated, reordered, delayed, dropped, contradictory or corrected. Disconnects and durable-write failures are
  injected.
- **Crash matrix:** restart at every persistence, send and acknowledgement boundary. Recovery must neither
  duplicate an order nor strand valid work.
- **Stop scenarios:**
  - a gap through the stop fills at the open;
  - a stop-limit not filled -> emergency market fallback;
  - pair stop -> both legs close (cancel-both, complete or flatten);
  - a broker catastrophe stop on one leg -> the other leg closes immediately;
  - restart -> stops reconciled before new orders;
  - broker stop missing at reconciliation -> block new risk;
  - two missed stops -> kill switch (reduce-only);
  - options spread stop loop death -> fail-safe alert.
- **Scenarios:**
  - partial fills;
  - rejects;
  - cancel/replace races;
  - late fills after restart;
  - timeout -> UNKNOWN -> reconciliation (including a broker-proven absence), with no automatic resend;
  - duplicate-intent guard;
  - stale-data halt;
  - fat-finger and session collars;
  - market hours, holidays and early closes;
  - kill switch fail-closed;
  - **A1:** the imbalance bound B, the duration limit and cancel-both -> complete or flatten;
  - **B1:** combo concession floor (C_nat >= C_L), skip-on-unfilled entry, XSP cash settlement vs SPY physical
    delivery, partial assignment -> stock position event, deliverable changes, restart replay.
- **Clock injection** (wall and monotonic) for every deadline. Tests never sleep.

### 15.6 Adapter contract tests (IBKR / Schwab)
- **One shared suite** runs parameterised over `FakeBroker`, recorded-IBKR cassettes and recorded-Schwab cassettes.
  It covers:
  - `capabilities()` fail-closed (an unsupported capability defaults to false);
  - order-type mapping;
  - combos;
  - partial-fill reporting;
  - malformed and documented error responses;
  - unknown fields.
- **Cassette metadata:** adapter, API and schema version, capture date, account-capability context and a
  sanitisation check. Stale cassettes do not prove current compatibility and are re-recorded after broker
  changes.
- **No secrets** in fixtures.
- **Live and paper integration tests are manual and require explicit maintainer approval.** They are never part of
  CI.

### 15.7 Statistical-procedure and security tests
- **Statistics (WP6):**
  - purging by actual label intervals;
  - overlapping observations;
  - trial-count accounting;
  - single holdout opening, with the access audit;
  - constant and short samples;
  - simulation checks with pre-declared Monte Carlo tolerances (noise families reject at <= 5% + 2 MC s.e.).
- **Security (WP-AG2, WP18):**
  - real process/IPC permission tests;
  - forged, expired, replayed, wrong-account, wrong-environment, wrong-instrument or altered signed intents are
    rejected;
  - signer isolation;
  - fail-closed behaviour during dependency failures;
  - poisoned and instruction-bearing text stays data (the red-team suite, Section 11.2).

### 15.8 CI parity
- **Gate command:** `pytest -m "not spark and not lakebase and not databricks"`, run identically locally and in
  CI.
- **Collection integrity:** a test asserts that the marker expression collects every required critical test, so
  no critical test is lost to an inherited marker or an unconditional skip.
- **No network:** sockets are blocked by a fixture. Cassettes and fakes only.
- **Determinism:** pinned dependencies, derandomized Hypothesis, fixed numpy seeds, an injected clock, and a UTC
  plus NY calendar fixture.
- **Runtime:** benchmark first, then set a ratcheted budget (target <= 5 minutes for the gate suite). Exploratory
  property runs execute nightly outside the gate.
- **Coverage:** line and branch coverage are diagnostics with a **ratchet** (they never decrease). For
  risk-critical modules (guardrails, firewall/signer, OMS, ledger, costs, fill simulator, metric gates) **every
  safety branch and every state transition must be covered**, and any uncovered critical path needs a written
  justification. These modules turn errors into money or false evidence, so per-branch evidence matters more than
  a percentage. There is no universal 95% target.
- **Numerical policy:**
  - Exact equality for integer quantities, IDs, event order, and decimal money after contractual rounding.
  - Declared per-field absolute and relative tolerances for floating analytics.
  - NaN, inf and UNDEFINED are handled explicitly.
  - A tolerance must never change gate eligibility.

### 15.8a Regime-layer tests
- **Known-answer detection on synthetic planted breaks:**
  - abrupt and gradual vol shifts, correlation breaks, cointegration breaks, GARCH-t clustering, and misspecified
    generators;
  - report the expected alarm count per 252 sessions, P(>= 5 alarms), and the detection-delay distribution, with
    Monte Carlo intervals;
  - assert the budget definition in Section 12.2 and the pre-registered power targets.
- **No look-ahead (property):**
  - appending or perturbing future data never changes past published states;
  - **revisions** take effect only from their publication time;
  - refits never alter historical published states;
  - normalisation uses training data only.
- **Discriminating fixture for smoothing:** a series where smoothed and filtered HMM probabilities differ at a
  known date (only if the HMM challenger exists).
- **Hysteresis and dwell:** a frozen anti-chatter requirement (at most N state flips on a scripted oscillating
  series) and exact threshold boundaries.
- **Recovery:**
  - a gradual restoration schedule;
  - persistence across restart.
- **Policy table (property):**
  - for any states and positions, effective size <= the size without the regime layer;
  - ceilings <= 1.0, with the minimum (not the product) applied;
  - enforcement happens after rounding.
- **Fail-safe:**
  - a STALE, MISSING or INVALID required field blocks new entries for the affected sleeve only, and never
    permissively;
  - stops and exits continue.
- **Decay CUSUM:**
  - sign, reset, refractory period and threshold logic against hand-computed sequences;
  - cohort publication under asynchronous closures;
  - the alarm frequency on baseline-drawn paths (including losing streaks) is within the budget's Monte Carlo
    interval;
  - an alarm never changes orders at launch.
- **Mechanical blocks:** take effect in the same cycle (no dwell); cancel pending entries; never delay stops or
  breaker actions.
- **Holdout lock:** any replay dated 2016-2021 fails before `open_holdout`.
- **B1 entry features:** future realised returns cannot change entry-time features.

### 15.8b Data acquisition and overlay tests
- **Completeness audit known-answer fixtures:**
  - a synthetic calendar with a holiday, an early close, a listing mid-period, a delisting, a halt and a
    no-trade day must classify each exception correctly;
  - a missing session must be flagged;
  - an options fixture with a missing expiry, a crossed quote, a stale quote and a missing exit-window observation
    must each be flagged.
- **Integrity:**
  - a truncated or corrupt object fails its SHA-256 check and is re-queued;
  - resume after an interruption produces no duplicate manifest rows;
  - manifest rows are append-only (an update or delete is rejected).
- **Holdout routing:**
  - any 2016-2021 object lands only in restricted storage;
  - a research identity's read of it is **denied** (access test, not just a manifest check);
  - development exports contain no 2016-2021 rows.
- **Causal filter:**
  - contract selection uses only the prior-session close;
  - an intraday spike cannot change which contracts were kept that day;
  - every contract needed for an exit is retained.
- **Overlay:**
  - every broker and vendor row carries `data_source`;
  - an analysis reading a series without a declared source fails;
  - a join view without an approved diagnostics record cannot be built;
  - unmatched observations are counted, never treated as agreement.

### 15.9 Work package -> tests -> required mutants (minimum five per WP)
| WP | Test classes | Curated mutants that must be killed |
|---|---|---|
| WP1 contracts/registry | Unit, property (idempotent identity), PIT | Drop availability check; allow 13th config; mark 2022-26 unseen; accept unknown `data_source`; hash ignores config change |
| WP2 metrics/tearsheet | Oracle units, threshold-edge, status enums | Downside deviation over negatives only; Calmar window mismatch; tail ratio with abs on both sides; omit initial NAV in MDD; PENDING rendered as PASS |
| WP3 ledger | Oracle units, conservation property, metamorphic splits | Entitle at pay date; reverse short payment sign; disable withholding; split changes quantity only; drop receivable on exit |
| WP4 costs | Oracle units, domain-qualified monotonicity | Remove $0.35 minimum; full spread per side; wrong tick floor; shift fee effective date; skip weekend borrow |
| WP5 engine + fill simulator | Golden datasets, legacy parity, no-look-ahead property, scenario G/P1/P2 fixtures | Remove lag; same-minute fill; touch counts as fill; reuse consumed volume; skip deadline crossing; drop A1 imbalance bound |
| WP6 statistics harness | Procedure tests, MC calibration | Disable purge; per-variant instead of max-stat bound; undercount trials; allow second `open_holdout`; ignore label overlap |
| WP15 options engine | Payoff grid, lifecycle, settlement | Wrong multiplier; cash-settle SPY; ignore assigned stock; credit inequality reversed; future quote used for synchronisation |
| Stop manager (WP5 backtest stop rules; WP16 live stop manager) | Stop oracle fixtures (gap-through fill at open, stop-first intrabar, pair delay), stateful stop lifecycle, broker reconciliation | Accept an order without a stop; fill a gapped stop at the stop price; target-first intrabar ordering; loosen a stop; close only one pair leg; skip stop reconciliation after restart |
| Risk sizer (WP16, `portfolio.py`) | Oracle units (Section 10.1a fit table), cap properties, gap-vs-stop fixture | Size on the stop instead of the stressed gap; round q up; size from the high-water mark; omit fees from WCL; use 5% instead of 0.5% (a unit or percent slip); round q instead of floor; ignore the assignment-notional cap; condor WCL summed over both wings or computed from credit only |
| WP16 OMS/monitoring | Stateful FakeBroker, crash matrix, clock injection | Resend on UNKNOWN; lose late fill; kill switch fails open; integrity breach does not cancel entries; stale-data halt bypassed |
| WP-AG2 firewall/signer | Security boundary tests | Skip signature check; omit account/environment binding; accept a reused nonce; accept an expired target; execution skips its own risk re-check |
| WP19 adapters | Shared contract suite | Unsupported capability defaults to true; wrong order-type mapping; partial fill reported as full; paper routed to a live endpoint; unknown field crashes instead of failing closed |
| WP7 residual falsification | Registry count, frozen family | Run a 5th variant; reset N to 4 instead of >= 14; change costs after seeing results; skip the 2x-variable-cost check; mark the period unseen |
| WP8-9 data + **holdout seal** | Manifest overlap, restricted-schema access, one-time open | Research snapshot reads 2016-2021; **calibrate G using 2016-2021 data before opening**; allow a second `open_holdout`; manifest hash ignores Delta version; dividends posted at pay date without ex-date entitlement |
| WP10-11 A6 / A1 / TOM | Signal oracles, lot rule, withholding, frozen schedule | Use same-day close in the signal; size on the stop instead of G_rel; select the schedule inside the family; drop the withholding line; close only one pair leg on a stop |
| WP12-13 **timing audit** + A4 | Session-mapping table, 100-event audit tool, causal admission | Map a post-16:00 release to the same session; enter before EAR completes; use month-end top-N selection; use acceptance time when an earlier wire time exists; count a skipped-for-capacity event as traded |
| WP14 execution study | Scenario brackets, cost-only comparison | Use future minute bars to pick the schedule; count touch as fill; evaluate alpha instead of cost; select on the holdout window; omit the deadline crossing |
| WP17 reporting | Typed report fields, citation resolver | Accept a fabricated `run_id`; render a number without an artifact hash; resolve file:line against the wrong commit; drop failed runs from the report; mark an illustrative number as measured |
| WP18 red-team | Poisoned data, injection, forged targets | Accept x100 price; let instruction text change a field; accept a forged target; treat NaN as zero; skip quarantine |
| WP20 extractor (shadow) | Locked temporal evaluation, cache key | Cache keyed by document hash only; timestamps taken from model prose; shadow output reaches orders; evaluate on the development split; omit abstentions |
| WP-AG1 contracts/fixtures | Protected paths, evidence binding | Allow a test-weakening diff without review; accept stale evidence; skip the semantic diff; let a builder edit expected values; accept evidence from another commit |
| WP-RG5 gate evaluation | Paired bootstrap, causal matched exposure | Use realised gate activity for the matched benchmark; evaluate on the holdout before freezing; ignore aggregate-cap interactions; drop missed-trade costs; per-variant instead of pre-registered endpoint |
| WP-RG1 telemetry/health | PIT, revision, warm-up, restart tests | Use same-day unavailable VIX; full-sample scaling; permissive default on missing input; ignore revision timestamp; recompute past states on refit |
| WP-RG2 decay monitors | CUSUM oracles, dependent-null calibration | Flip the CUSUM sign; drop the reset or refractory period; use in-sample backtest as baseline; omit the scale floor; per-trade instead of cohort observations; alarm changes orders |
| WP-RG3 policy engine | Policy properties, fail-safe, recovery | Ceiling > 1 accepted; product instead of minimum; regime applied before caps/rounding; stale input treated as normal; dwell applied to a mechanical block; recovery above the approved ceiling; shadow row affects orders |
| WP-RG4 replays/generators | Frozen behaviour assertions | Fabricate B1 fills from daily bars; accept a B1 replay before 2022-03-07; run a holdout-dated replay before opening; assert realised loss <= cap instead of recording overshoot; allow regime-driven risk increase |
| WP-D1 bulk pull + audit | Calendar/exception fixtures, integrity, resume, holdout routing | Treat a missing session as OK; accept a truncated object (skip SHA-256); write a 2016-2021 object to research storage; allow a manifest update; use same-day close in the contract filter |
| WP-D2 contract reference | Reference-vs-quote coverage | Pull quotes without reference; infer expiries from today's product list; drop expired contracts; ignore adjustments; skip P4/P5 underlyings |
| WP-D3/D4 broker overlay + join | Source flags, fresh-vs-cached, join approval | Drop the `data_source` flag; mix broker rows into a vendor series silently; build the join without approved diagnostics; count unmatched as agreement; compare broker-model IV with vendor quotes |

The test shape is specified in every BUILD request: literal oracles, named assertions and the mutant list.

---
## 16. Open questions and decisions

**Resolved and removed:** account size ($200,000 paper) and the options cap (0.5% per trade applies to options
too).

1. **Aggregate open-risk cap.** Recommended: sum of open WCL <= **5%** of equity ($10k), budgeted A6 1.5%,
   A1 1%, A4 1%, options 1.5%. A joint stress-scenario loss limit <= 5% and a crash cluster <= 3% also apply. A
   10% aggregate is not recommended without portfolio stress evidence.
2. **Portfolio drawdown circuit breaker.** Recommended, from the high-water mark of marked daily NAV, with every
   action mandatory:
   - **4%**: block new risk.
   - **6%**: reduce open WCL to <= 2.5% (half).
   - **8%**: liquidate and stop pending re-validation.

   With open WCL <= 5%, a full simultaneous max loss from just under 4% could reach about 9%. That residual
   exceedance is accepted and stress-tested.
3. **Gap stress G for sizing:** keep the planning values (20% broad ETF, 15% pair bundle, 20% single name) or adopt
   the WP9 empirical worst x 1.25. This changes sizes about 1.3-1.7x (Section 10.1b).
4. **Data acquisition** (Section 9.2):
   - **(a)** do the licensing check in writing **before** purchase (retention after cancellation, derived outputs,
     redistribution, personal vs business use, S3 coverage, cloud storage). **Status: not verified.**
   - **(b)** which month to buy: after the broker collector has >= 20 sessions, and with no conflicting travel or
     other commitments.
   - **(c)** tiers: Stocks Advanced + Options Advanced + Indices Starter, $447 list, one-time.
   - **(d)** the all-in budget ceiling (subscriptions + storage/compute + broker data).
   - **(e)** the retained options quote universe (P2-P5) and the broker route (IBKR or Schwab) with verified
     entitlements.
5. **Commission plan:** IBKR Pro tiered vs a $0-commission venue. This matters little at $200k sizes.
6. **Paper venue:** IBKR paper (API-verified), or the internal simulator + paperMoney mirror if paperMoney has no
   API (*verify*). A margin account is needed for shorts and Reg-T spreads; options approval level for spreads.
7. **SPY and single-name options:** approve the assignment-notional rule (<= 50% of equity in aggregate; <= 10%
   per name) and the broker assignment drills that unlock them.
8. **Execution schedule preference** among S-open, S-close and S-part.
9. **Holdout:** approve 2016-2021 (needs Stocks Advanced) or shrink it to 2017-2021. Authorise the restricted
   `open_holdout` job.
10. **Withholding details:** confirm 30% on ordinary dividends, capital-gain distributions, return of capital,
    and substitute payments (W-8BEN on file?).
11. **A4 book:** confirm the concentrated 5-name design at about $400 WCL each.
12. **Agent policy:** approve the Section 11 verdict (no SLM/LLM in decisions; shadow-only extractor later).
13. **Regime stance:** approve "telemetry + mechanical safeguards active, market-regime gates shadow-only until
    one pre-registered exposure reduction per sleeve earns evidence" (Section 12).
14. **System false-intervention budget** for advisory alarms (proposed: expected <= 2 per 252 sessions across all
    sleeves, P(>= 5) <= 5%), the per-sleeve minimum deterioration delta, and the power targets for the decay
    CUSUM.
15. **VIX3M / term-structure data:** confirm availability and timing (Indices Starter, *verify*) before any
    term-structure feature is built. It stays telemetry.
16. **"jev":** what did the maintainer mean (Section 11.3)?

---

## Appendix A. Design review log

The plan was produced through a 13-round structured review between Claude Opus 5.5 (author) and Codex Sol
(`gpt-6.1-sol`, reviewer) on 2026-10-24. The table records each point of disagreement and how it was resolved.
"Owner" means the project maintainer. Round R13 (testing strategy) produced Section 15; its WP mapping was
re-keyed to this plan's work-package numbers.

| # | Topic | Opus | Sol | Resolution |
|---|---|---|---|---|
| 1 | Ranking basis | Ease of testing | Independent observations and implementable edge | **Sol** |
| 2 | Options data cost | EOD at about $100-300/mo is enough | DataShop is per-dataset; EOD cannot validate intraday | **Sol**: one trial, coverage first |
| 3 | Triple-barrier | Default | Barrier hyperparameters; ambiguous on daily bars | **Sol**: policy P&L label |
| 4 | Meta-labeling | Use now | Too few episodes | **Sol**: >= 1,000 / 200 losses |
| 5 | Kalman + OU + hazard + Johansen | All | Too many stacked choices | **Sol**: OLS default, Kalman challenger |
| 6 | HMM | Default regime | Overfit bait | **Sol**: later challenger |
| 7 | CPCV | Evidence | No new information on about 1,000 days | **Sol**: sensitivity only |
| 8 | Stacked DSR/PBO/SPA/BH | Require all | Not independent | **Sol + R4 fix**: an absolute simultaneous bound + SPA for challengers; the rest are diagnostics |
| 9 | Kelly | 0.25x cap | Not even as a cap | **Sol** |
| 10 | Vol target | 10% per sleeve | Too much in aggregate | **Sol**: 5% portfolio ceiling, standalone sleeve budgets |
| 11 | Literature haircut | 50% prior rung | Motivation, not observations | **Compromise**: literature chooses hypotheses; unseen pre-2022 data decides |
| 12 | Residual rescue | 6 weeks | 1 week, 4 runs | **Sol** |
| 13 | PEAD timing | Entry at acceptance + 1 session | EAR leaks; XBRL arrives later | **Sol (R4)**: entry at session +2; SUE only after the 10-Q |
| 14 | Holdout | Final 5y | 2022-26 already consumed | **Sol (R4)**: pre-2022 holdout + prospective shadow |
| 15 | B1 cohorts and events | 7-45 DTE, exclude macro | 200 cohorts infeasible; the exclusion kills the sleeve | **Sol (R4)**: weekly 7-10 DTE primary; event feature, no blanket exclusion **Superseded** by the Monday-entry 4-DTE schedule (Section 5.5) |
| 16 | SPY options | Allowed | Assignment and pin risk | **Sol (R4)**: SPX/XSP only **Superseded** at $200k by the assignment-notional rule (SPY 1-contract verticals; Section 10.1a) |
| 17 | Spread estimator for ETFs | Abdi-Ranaldo + floor | Unusable at sub-bp; tick-aware scenarios | **Sol (R5)** |
| 18 | Delay cost | 0.25 sigma sqrt(h) adverse | Zero unconditional drift; simulate delayed fills | **Sol (R5)**: simulation + 0/1/3 bps stress |
| 19 | Options package fill | c = 0.35 base | c = 1 base | **Sol (R5)**: c = 1 base, 0.5 optimistic, 1.5 stress. Opus notes that SPX complex orders often fill inside the summed spreads; to be revisited only with real fills |
| 20 | Default fill | First-30-min VWAP | Next-session close baseline | **Compromise (R5/R6)**: MOC baseline; open and VWAP registered. **Superseded by row 37** (best-price execution) |
| 21 | Limit fill probability model | p(touch) + adverse haircut | Minute bars give touch, not queue | **Sol (R5)**: bracket no-touch vs touch, no haircut |
| 22 | Delisting | -30% default | Terminal reconciliation; -100% scenario | **Sol (R5)** |
| 23 | ETF pair BAG orders | Use combos | Not assumed atomic | **Sol (R6)**: coordinated legs, verify combos |
| 24 | No-trade band | 0.5% NAV | Enormous vs a 5% sleeve | **Sol (R6)**: per-sleeve exposure units |
| 25 | Breakers | 3% sleeve DD pause | Separate block / cancel / liquidate; budget-based | **Sol (R6)** |
| 26 | IBKR paper value | Plumbing only | Plumbing yes; no fill evidence | **Agreed** |
| 27 | Workflow chain | Coder -> validator -> Codex Sol (per `AGENTS.md`) | R3/R4/R6 asserted "MiMo -> Kimi -> Codex" | **Opus held.** Checked `AGENTS.md` on origin/main: Kimi is not in the chain, and Opus is only the Sol usage-limit fallback. Sol was working from the prompt summary, not the file |
| 28 | R7 gap review | v2 judged near-final | 12 issues, including: dividend ex-date accrual; A1 MOC vs legging conflict; spread unit error; MOC auction-volume proxy; circular holdout for A4/B1; no stats-harness WP; financing missing; integrity breaches not cancelling orders; B1 cohort overlap; mutant vs regression conflation; aggregate gross/vega definitions; incomplete A6 rule | **All accepted and fixed in v2** (sections tagged "R7 fix"). No new disagreement |
| 29 | Scope of options data held | -- | The 12-underlying snapshots are descriptive spread priors only | **Agreed**: no options backtest on held data |
| 30 | Options caps at $10k | $300/package, $1,000 aggregate | $100/package, $300 aggregate; never raise risk to fit a contract | **Superseded by the decision of record (2026-10-24):** 0.5% of equity per trade; at $10k no planned options structure fits; the aggregate cap remains a proposal |
| 31 | Calendars/diagonals | Defined-risk if the long leg expires later | A diagonal can lose the strike gap beyond the debit; American legs | **Sol**: excluded initially |
| 32 | Options 2022-26 quotes as a holdout | Unseen, so clean | Hypotheses were chosen after studying 2022-26 equities | **Sol**: a retrospective frozen-protocol evaluation + prospective collection |
| 33 | data_source codes | Provider-level + `fred`/`cftc`/`sim_broker` | Provider-level; no speculative codes; simulated fills are `derived` | **Sol**: add `ibkr`/`schwab`/`fred` only at first ingest; `source_dataset` column |
| 34 | Holdout opener | The final-gate model | A model is not a security boundary | **Sol**: a restricted deterministic job authorised by the owner; Sol reviews the report |
| 35 | Metric gates | Sortino > 0.5, PF >= 1.2, cost drag <= 50%, etc. | A second selection system; duplicates inference | **Sol**: 8 gates; the rest are diagnostics |
| 36 | Lo Sharpe with q = 10 | The "Lo adjustment" | Truncation hides the omitted-rho assumption | **Sol**: a diagnostic with bandwidth sensitivity |
| 37 | Best-price execution gate | Passive trade-through fills (conservative) as the gate | Minute bars cannot prove passive fills | **Compromise**: the owner's best-price policy runs operationally; **the gate uses the crossing scenario G**; passive gains enter only with live-order evidence |
| 38 | Missed-trade threshold | <= 30% missed entries | No economic basis; selection-biased | **Sol**: removed; the full-path gate plus conditional fill-rate reporting replace it |
| 39 | A1 legging trigger | 50%/20% fill trigger | Contradicts the 20% gross cap | **Sol**: a continuous B bound + duration + deterministic complete/flatten |
| 40 | Options crossing inequality | limit >= natural | Reversed for credits | **Sol**: C_nat = bid_short - ask_long >= C_L |
| 41 | Signals on net-of-withholding returns | Yes | Account taxes distort market relationships | **Sol**: gross total-return signals; after-tax P&L |
| 42 | Ex-date avoidance | A cheap fix | It is a dividend-timing strategy | **Sol**: a registered variant |
| 43 | GDX/GLD and EFA withholding | GDX/GLD unaffected; EFA double withholding | GDX distributes; EFA's fund tax is already in NAV | **Sol** |
| 44 | Numeric lint / 1e-6 recompute | Universal | False positives; misses cherry-picking | **Sol**: typed report fields; per-metric tolerances; independent ledger |
| 45 | Extractor protocol | >= 300 gold docs, kappa, Platt, doc-hash cache | Insufficient on each count | **Sol**: Section 11.3 protocol |
| 46 | LLM risk veto that only reduces risk | -- | A veto is a trading decision and can raise risk | **Agreed**: shadow-only |
| 47 | SLM in decisions | No | "Too broad scientifically, sensible operationally"; size is the wrong boundary | **Agreed**: no SLM/LLM in decisions now |
| 48 | R12 final review of v3 | v3 judged near-final | 12 issues: A4 month-end look-ahead; B1 cohort overlap and warm-up count; crossing-gate vs passive operational policy; SPY/single-name assignment admission; no historical minute data for schedules; joint sizing over 100% NAV; TOM timing; family cap vs schedules; XSP friction arithmetic ($0.0065, not $0.01-0.015); TOM variable cost; FRED/`derived` and split registry schema; agent signing/replay and read-only vs code authoring | **All accepted and fixed** (text tagged "R12 fix"). No open disagreement; the options caps remain an owner decision |
| 49 | R13 testing strategy | 95% coverage target; literal oracles; fixed seeds | Coverage percentages invite denominator games; oracles need a versioned derivation; at least five curated mutants per WP, 100% killed | **Reviewer**: per-branch coverage of safety paths with a ratchet; oracle spec files; at least five mutants per WP (Section 15) |
| 50 | Per-trade cap (0.5% of equity) | -- | -- | A decision of record added after R13 (an earlier 5% figure was corrected to 0.5%). It was not separately reviewed by Codex Sol. Section 10.1a and its tests follow the reviewed sizing and stress principles (size on stressed loss, skip instead of resize) |
| 51 | Mandatory stop-losses | -- | -- | A decision of record added after R13. Section 10.1b was not separately reviewed by Codex Sol; it applies the reviewed principles (conservative fills, stop-first intrabar, size on gap, fail-closed) |
| 52 | Account raised to $200k (R14) | 10% aggregate open WCL with sleeve budgets; "15% per leg" pair stress; impact about 0.6 bps for a thin ETF; SPX fee advantage about 8x | Keep 5% aggregate plus a joint stress-scenario limit; define the pair unit and G_rel explicitly (empirical 7% x 1.25 = 8.75%); impact is 6.1 bps at window volume (later corrected to about 7.0 bps with the 15% window proxy); no width-based fee claim; Reg-T condor = larger wing; breaker levels must mandate actions | **Reviewer accepted on all points.** 5% aggregate, joint scenario limit, pair-bundle stress, corrected impact, matched-exposure SPX/XSP comparison, breaker 4/6/8% with mandatory actions |
| 53 | Size-driven vs data-driven verdicts | -- | Size removes implementation barriers, never a failed edge, cost or data gate | **Agreed.** B1/B3/B4 become paper-eligible after gates; B5 moves to backlog; residual stays parked on cost; A2/A3/B2/A5b unchanged; TOM research-only |
| 54 | Regime detection (R15) | Rule-based multi-dimension gates active; BOCPD alarm; HMM challenger; ARL0 >= 250; example multipliers per sleeve | Detector can be past-only yet the policy overfit; no evidence that gating helps; telemetry + mechanical safeguards first; gates shadow-only; system false-intervention budget; cohort CUSUM from causal OOS baseline; no automatic retirement | **Reviewer accepted.** Section 12 adopts the telemetry-first, shadow-gate design |
| 55 | R16 review of Section 12 | -- | Holdout-dated replays, 2022-03-07 cutoff, advisory vs ceiling, cohort contract, mechanical blocks immediate, replay assertions vs realised losses, utility endpoint, budget definition, B1 variance causality | **All 9 fixed** |
| 56 | One-month bulk acquisition (R17) | One-month Stocks Adv + Options Adv + Indices Starter; quotes "filtered at download"; 20-session overlap with 1-s matching and fixed tolerances | Filtering does not cut inbound bytes, so a feasibility pilot is needed; causal contract selection; restrict all holdout-bearing objects; product-calendar audits; licensing covers the actual use; verify the broker route; stratified, timestamp-aware reconciliation; resumability and renewal controls | **Agreed** (all nine amendments adopted). Sections 9.2-9.3 |
| 57 | R18 agreement check | -- | Scope-reduction order; stop-trigger observation; calendar gate for >= 20 overlap sessions; contract reference for every retained underlying; economic audit checks only on development partitions | **Agreed with fixes; all 5 applied** |
