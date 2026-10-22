# Perps weekend research plan (P0, v5)

**Status:** design + research scaffolding (P0, round 7: history source changed to
flat-file backfill after the owner decision of 2026-10-22, "use flat file"). No
ingestion job is scheduled, no shared table is written and no signal is
published. The flat-file reader in `scripts/perps/hl_flat_files.py` is **design
only** in P0; no new code path touches the network. **Owner:** decisions
2026-10-22.

**Instruments are derivatives.** Every row in the universe is a **perpetual
future** (`instrument_type: perpetual_future`) traded on a crypto venue. The
listed ticker, ETF or commodity is only the *underlying* it tracks through the
venue oracle: a perp is never the equity, never the ETF and never spot. Every
table, Unity Catalog comment/tag, knowledge-graph node and UI label must carry
that distinction, and perp columns in mixed feature tables use a `perp_` prefix.

**Question.** Do weekend moves in perpetuals whose underlying is a listed equity
improve predictions of the next session's opening gap beyond (a) Friday
equity/options signals, (b) broad crypto weekend returns and (c) the
pre-market/overnight information that is already available at the same
prediction cutoff? The claim is therefore **"beyond the Friday close *and* the
information available at that cutoff"**, not "beyond everything the market
knows".

**Target (one definition).** For each underlying in the configured universe:

```text
open_gap = session_open / prev_session_close - 1
```

* `session_open` — the **official opening print** of the first regular session
  after the weekend break (the exchange opening auction/print), not the
  pre-market price and not the 09:30 quote.
* `prev_session_close` — the **official closing print** of the last regular
  session before the break. On a Friday-holiday weekend (Good Friday, July 4
  observed, Christmas observed) this is **Thursday's** close.
* Both prices are **raw** (unadjusted). The ratio is made split/dividend
  consistent by multiplying `prev_session_close` by the **explicit factor
  effective at that open**, taken from `bronze_corporate_actions` (splits,
  reverse splits and cash dividends between the close and the open); the factor
  is stored on the row so the label is reproducible. No implicit vendor
  back-adjustment is used.
* The label is known at the opening print and is never a feature. `label_available_ts`
  is that print time, and `information_available_ts <= prediction_ts < label_available_ts`.

**Hypotheses.**

- **H1 (primary, pre-registered — the only confirmatory test):** at the
  **Monday 09:00 ET cutoff**, adding the perp block
  (`perp_ret_weekend`, `perp_implied_gap`, `perp_friday_close_basis`,
  `funding_sum`, `perp_realized_vol_1h`) to the Friday equity/options + BTC/ETH
  control baseline raises the out-of-time partial R² for `open_gap` by more than
  zero. The exact comparison, metric, split and correction are fixed in §6.2
  before any result is inspected.
- **H2 (secondary, exploratory):** any apparent perp signal is explained by
  BTC/ETH weekend returns (equity perps trade 24/7 alongside crypto), so every
  secondary comparison must control for them.
- **H0:** no incremental lift; the honest default. A null result is reported as
  the result, not as a tuning problem.

H1's "beyond" clause includes the **pre-market/overnight baseline** at the same
cutoff (see §3.2): where the repository cannot yet observe that baseline
(pre-market equity bars and CME Globex futures are not ingested as of
2026-10-22), the claim is narrowed to "beyond Friday close and the observable
controls" and the unmodelled pre-market information is listed as a confounder.

The research claim is predictive lift in an out-of-time evaluation, not trading
profitability. No signal is published to `gold_trading_signals` by this track
without separate owner approval.

## 1. Scope and instrument universe

Perps are ingested **only** for the instruments in
[`config/perp_universe.yaml`](../../config/perp_universe.yaml) (version 4):
78 company perpetuals on Hyperliquid HIP-3, 8 commodity perpetuals paired with
Massive ETFs, plus Binance USD-M `BTCUSDT` and `ETHUSDT` as mandatory controls.
The file is the single source of truth; `config/perp_universe.py` validates it
(unique tickers/symbols, `symbol == "<dex>:<TICKER>"`, venue/dex allowlists,
controls present, version, `instrument_type`, `underlying_type`, tiers and
flags).

| Property | Value |
|---|---|
| Instrument type | `perpetual_future` (derivative; `is_equity: false`, `is_derivative: true`) |
| Company venue | Hyperliquid HIP-3 (sub-dexes `xyz`, `para`, `io`) |
| Companies | 78, selected 2026-10-21 (owner choice) |
| Commodities | 8 (WTI, Brent, silver, gold, natural gas, copper, platinum, palladium) |
| Commodity wrappers | `etfs: [USO]`, `[BNO]`, `[SLV, SIVR]`, `[GLD, IAU]`, `[UNG]`, `[CPER]`, `[PPLT]`, `[PALL]`; `etf_kind` physical or futures |
| Controls | Binance USD-M `BTCUSDT`, `ETHUSDT` (always, `underlying_type: crypto`) |
| Underlying types | company rows: `equity`, `etf`, `fund`, `preferred`; commodities: `commodity`; controls: `crypto` |
| Liquidity basis | measured **while the NYSE is closed**, from 1h candles (`volume × close`) |
| Measurement window | 2026-08-26 → 2026-10-21 (8 weeks) |
| Tiers (`weekend_usd_per_h`) | `A ≥ 250k`, `B ≥ 50k`, `C ≥ 10k`, `D < 10k` |
| Flags | `new` = first bar after the window start; `sparse` = more than 25% of **expected** weekend hours with zero volume |
| Tier use | **descriptive stratification only** — a model input/filter must use trailing point-in-time liquidity (§1.2) |
| Survivorship | universe selected 2026-10-21 from the names then listed and liquid; delisted/never-selected perps are a P1 audit, not a proven absence |
| Data source | one provider code per row from [`config/data_sources.py`](../../config/data_sources.py): `hyperliquid` for HIP-3 perps, `binance_um` for the Binance USD-M controls |

Tiers and flags are descriptive stratification, **never** ingestion filters:
every configured instrument is still ingested. They are re-measured with
[`scripts/perps/measure_closed_liquidity.py`](../../scripts/perps/measure_closed_liquidity.py),
which writes a proposal JSON (with `weekend_coverage`, `expected_hours` and
`tier_withheld_reason`, and no tier when coverage is below 80% of the expected
hours) and never edits the config; the owner applies changes.

### 1.2 Static tiers are look-ahead — use trailing liquidity instead

The tiers in the config were measured over **2026-08-26 → 2026-10-21**, i.e.
*after* almost every weekend in the study window. Using them as a model input
or a sample filter would leak future liquidity into the past. Therefore:

* the static tier/flag values are used only to **describe** the universe and to
  stratify reported results;
* every model input or filter uses **trailing point-in-time liquidity** computed
  only from data strictly before each `window_start` (for example the mean
  closed-market notional per hour over the previous N weekends, with a minimum
  observation count, and `null` + a flag when the history is too short);
* sensitivity tables may re-run the headline model on the static tier subsets
  (A/B only, excluding `sparse`), but those runs are descriptive, not the
  pre-registered test.

**Survivorship.** The universe is the 2026-10-21 liquid subset. Perps that were
delisted, never selected, or too thin to appear in that snapshot are missing by
construction, so any result is conditional on "still listed on 2026-10-21".
Listing the delisted/never-selected HIP-3 perps (and recording why each was
excluded) is a **P1** task; until it is done the plan must not claim the
universe is representative.

### 1.1 The `data_source` provider code

Owner rule (2026-10-22): every new table, view, config row, snapshot record and
knowledge-graph node/edge/evidence row produced by this track carries a
non-null `data_source` holding **one** code from
[`config/data_sources.py`](../../config/data_sources.py). The vocabulary is
defined once and reused by the loader, the probe and liquidity records, and the
schemas below:

| Code | Meaning |
|---|---|
| `massive` | Massive (Polygon) S3 flat files / REST (OHLCV, options, splits, dividends) |
| `sec_edgar` | SEC EDGAR filings and the submissions API (`data.sec.gov/submissions`) |
| `sec_companyfacts` | SEC XBRL Company-Facts API |
| `hyperliquid` | Hyperliquid venue data: requester-pays S3 flat files (fills, asset contexts, funding events, L2) and the info API (probe/measurement, current snapshots) |
| `binance_um` | Binance USD-M futures (`data.binance.vision` flat archives / API) |
| `config` | hand-maintained repository config (e.g. the universe YAML) |
| `derived` | computed in this project from other rows; a row that mixes sources is `derived` and records its input sources in lineage/docs |

SQL tables carry `data_source STRING NOT NULL` with a Unity Catalog column
comment naming the code and this vocabulary. YAML config rows carry
`data_source:` and `config/perp_universe.py` rejects a missing or unknown code,
and a code that contradicts the row's venue (`hyperliquid → hyperliquid`,
`binance_usdm → binance_um`). Python records (probe and liquidity outputs) carry
a required `data_source` validated against the same vocabulary.


The round-1 ticker review in `scripts/perps/check_universe.py` is report-only.
It flags ETFs, funds, preferreds and tickers that are unmapped in the **offline**
SEC CIK files. The owner kept all 78 and set the underlying labels from that
check: `BOT → fund`, `STRC → preferred`, `KSTR → etf`. The checked-in offline map
is intentionally sparse (`config/sec_cik_overrides.yaml` plus
`tests/rag/fixtures/sec/company_tickers.json`), so "unmapped" is a prompt to run
the check with a full `company_tickers.json` snapshot, not proof that a company
lacks an SEC registration.

## 2. Sources, endpoints and limits

### 2.1 Hyperliquid history: requester-pays flat files (P1)

Owner decision 2026-10-22 (**binding**): perp history comes from **flat files**,
not from the `candleSnapshot` API and not from an API forward-capture job. The
archive is the durable source; the info API stays a probe/measurement tool
(§2.1.1).

| Dataset | Object prefix | Use | Notes |
|---|---|---|---|
| Trades (fills) | `s3://hl-mainnet-node-data/node_fills_by_block` (older API-format `node_fills`; non-API `node_trades`) | **Primary trade history.** We aggregate fills into our own `1m`/`15m`/`1h` trade-price bars, so the 5,000-candle API window stops being a limit. | Requester-pays bucket. Block-partitioned objects; dedupe on fill id/hash. Field names must be verified on a sample object before the loader is written. |
| Asset contexts | `s3://hyperliquid-archive/asset_ctxs/<date>.csv.lz4` | Funding, open interest, mark and oracle history (`funding`, `openInterest`, `markPx`, `oraclePx`) — **field list TO VERIFY** on one sample file. | Requester-pays bucket. One object per date, `.csv.lz4`. |
| Funding events | `s3://hl-mainnet-node-data/misc_events_by_block` | Funding events (cross-check/fallback for `fundingHistory`) | Requester-pays bucket. Same block-object shape as fills. |
| L2 snapshots (optional) | `s3://hyperliquid-archive/market_data/<date>/<hour>/l2Book/<coin>.lz4` | Optional depth features (P4+); not needed for the weekend feature set. | Largest objects in the archive; bounded sample only. |

Documented caveats (quote them, do not soften them):

- The archive is uploaded **roughly monthly** and the provider states there is
  **"no guarantee of timely updates and data may be missing"**. A flat file is
  therefore *not* a real-time feed: recent weeks can be absent, and a missing
  object is a gap to record, never to interpolate or assume empty.
- **HIP-3 coverage (`xyz`/`para`/`io`) is UNVERIFIED.** The docs do not state
  whether the fills/asset-context archive includes HIP-3 sub-dex coins. One
  sample file must be inspected (owner-approved, requester-pays) and the coin
  list, date and byte count recorded before any history claim depends on it.
- **Requester-pays:** the requester pays S3 request and data-transfer charges.
  Every run is dry-run by default; it prints the object list, total bytes and an
  estimated transfer cost **before** the first `GET`, and refuses to download
  without `--live` (§4.4).
- No credentials are ever read, printed or persisted: the reader uses the
  standard AWS profile chain (environment/CLI profile name only, §4.4).

#### 2.1.1 Hyperliquid info API (probe, measurement and current snapshots)

`POST https://api.hyperliquid.xyz/info`, JSON body, no API key. This endpoint is
**not** a history source any more; it remains the probe and closed-market
liquidity measurement path (and an optional reconciliation sample).

| Request | Body (abridged) | Use | Limits / notes |
|---|---|---|---|
| `candleSnapshot` | `{"type":"candleSnapshot","req":{"coin":"xyz:NVDA","interval":"1h","startTime":<ms>,"endTime":<ms>}}` | 1h/15m bars for the liquidity measurement and the history probe | Public API returns at most 5,000 candles per response; page by `startTime`. `endTime` bounds the page. **1m retention is only ~3.5 days** (see below). |
| `fundingHistory` | `{"type":"fundingHistory","coin":"xyz:NVDA","startTime":<ms>,"endTime":<ms>}` | funding records (reconciliation against `misc_events_by_block`) | Public API caps a page (order of 500 records); page by `startTime`. Interval is recorded per row, not assumed. |
| `metaAndAssetCtxs` | `{"type":"metaAndAssetCtxs"}` | **current** open interest / mark / oracle | Current snapshot only; there is **no historical OI** in the public info API. |
| `clearinghouseState` | `{"type":"clearinghouseState","user":...}` | user positions | Not used by this track. |

Operational rules:

- **Candle prices are TRADE (last) prices.** Hyperliquid `candleSnapshot` OHLCV
  is the last traded price on that venue's perp order book, not the equity
  price, not the equity pre-market price, and not the venue mark or oracle
  (see §2.6). Every return computed from candles is a perp trade-price return.
- **The 5,000-candle window is a rolling floor, not a history source.** The
  public API returns at most 5,000 candles per interval: ~208 days of `1h` (the
  oldest instrument's window started 2026-03-27 on 2026-10-21) and ~52 days of
  `15m`, and the window moves forward every day. Because the flat-file fills
  archive is now the history source, that floor no longer defines what history
  exists: it only caps what the **API-only** probe can see. That is why the
  round-6 recount is an **API-only lower bound** (§2.5) and not the buildable
  panel.
- **Minute bars no longer depend on API retention.** The public API serves only
  roughly the last **3.5 days** of `1m` candles; the flat-file rebuild produces
  `1m` bars from fills for the whole covered period, and the Binance Vision
  archives carry full `1m` history for the controls (§2.2). `1d` remains a
  history check only.
- The probe is dry-run by default. `--live` is required to send requests.
- Polite rate limit: **≤ 2 requests/second**, exponential backoff with **jitter**
  on network errors/429/5xx and `Retry-After` support (both scripts accept an
  injectable RNG so the jitter is testable). 401/403 fail immediately.
- Empty windows are skipped in `--coarse-days` steps. The first non-empty window
  gives the earliest record; the report records the probe floor and `truncated`
  so a missing result is never presented as proof of no history.
- The API is undocumented/unofficial; treat schema changes as a monitored risk
  and fail closed on missing fields.

### 2.2 Binance Vision (controls only)

`https://data.binance.vision` S3-style archive listing. Binance USD-M is already
flat-file history, so the controls follow the same flat-file pattern as §2.1;
files are downloaded by the P1/P2 job (not by the P0 probe):

| Dataset | Path template |
|---|---|
| USD-M 1h klines | `data/futures/um/monthly/klines/{SYMBOL}/1h/{SYMBOL}-1h-YYYY-MM.zip` (daily under `.../daily/...`) |
| USD-M 1m klines | `data/futures/um/monthly/klines/{SYMBOL}/1m/{SYMBOL}-1m-YYYY-MM.zip` — **full 1m history** for the controls |
| Funding rate | `data/futures/um/monthly/fundingRate/{SYMBOL}/{SYMBOL}-fundingRate-YYYY-MM.zip` |
| Metrics (OI, long/short ratios) | `data/futures/um/monthly/metrics/{SYMBOL}/{SYMBOL}-metrics-YYYY-MM.zip` |

Caveats carried from the provider's docs:

- the monthly archives are uploaded **approximately monthly** (daily files more
  often), and Binance states **"no guarantee of timely updates and data may be
  missing"**;
- a missing month/day is a recorded gap; the control series is never
  forward-filled and a partial month is not treated as complete;
- downloads must be bounded, checksummed (the archive publishes `.CHECKSUM`
  files) and retried; a checksum mismatch fails the run.

The probe lists monthly archives, then refines the first month to the first
available **daily** archive. It records the archive key, month and day. Rate
limit and retries are the same as Hyperliquid.

The archive hostname serves the HTML download site, so the probe lists the
bucket through the S3 endpoint
`https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?delimiter=/&prefix=...`.
That response is a namespaced S3 `ListBucketResult`: `Contents` carries the
archive keys, `CommonPrefixes` the directory level, and `IsTruncated` /
`NextMarker` drive pagination. The probe parses by XML local name (so the S3
namespace cannot hide elements), follows every page, and fails closed on a
truncated page without `NextMarker` — a listing that silently stops after page
one would report a false "no archives". The first page pairing is covered by a
recorded two-page fixture in `tests/fixtures/perps/`.

### 2.3 Existing equity/options features

Friday equity daily bars and returns come from `silver_ohlcv_day_adjusted`
(`adj_close`, `return_1d`, `information_available_ts`); options features come
from `gold_options_features` (`iv_atm`, `iv_skew`, `volume_anomaly_zscore`,
`information_available_ts`). They are joined as-of the Friday close; this track
does not re-ingest them. The `friday_*` columns in §4.3 are the new gold output
names; the parenthesised source columns above are the existing schema.

The **baselines** are the back-adjusted features above, but the **label** is not:
`prev_session_close` and `session_open` are the raw official prints plus the
explicit factor effective at the open (§Target). Mixing the two bases (a
back-adjusted close over a raw open) is what produced the previous ambiguous
definition and is forbidden.

### 2.4 What is not available

- **Verified asset-context fields.** Historical open interest, mark and oracle
  may come from `asset_ctxs`, but the field list is **TO VERIFY** on a sample
  file; until it is verified, historical OI stays forward-only (§8).
- **Verified HIP-3 coverage of the flat-file archive.** The docs do not state
  whether fills/asset contexts include the `xyz`/`para`/`io` coins, so
  "history from listing" is an upper bound, not a fact (§2.5).
- A canonical perp listing timestamp; the first candle/fill/funding record is
  used as a lower bound.
- A stable funding interval across venues; store `funding_interval_hours` per
  row.
- Corporate-action semantics for HIP-3 perps (splits, index changes). Treat a
  discontinuity as a data-quality event until verified; never silently adjust.
- **Pre-market/overnight equity bars and CME Globex futures** (needed for the
  baseline at the `mon_0400`/`mon_0900` cutoffs). Not ingested as of 2026-10-22;
  see §3.2 and the P1 decision.
- **Per-dex HIP-3 oracle/mark documentation** (§2.6). Unknown, not unavailable:
  each deployer defines it and the public endpoints do not describe it.

### 2.5 Measured history and the buildable weekend panel (probe, 2026-10-21)

The live probe recorded the following lower bounds. They are **first
observations**, not listing dates, and `n/a` would mean "not found within the
probe budget", never "no history".

| Stream | Earliest measured | What it means for the design |
|---|---|---|
| Hyperliquid `1d` candles (company perps) | NVDA 2025-11-12; latest instrument 2026-10-06 | Per-instrument start differs. `1d` bars are for history checks only: weekend features need `1h` coverage (next row). |
| Hyperliquid `1h` candles (**API-only**) | 2026-03-27 09:00 UTC for the oldest instruments | The public API returns at most 5,000 candles per interval (~208 days of `1h`), so the oldest `1h` candle is a **rolling floor**. It bounds the *API-only* probe, not the flat-file rebuild: fills are expected to give `1h` history back to each listing, subject to HIP-3 coverage verification (§2.1). |
| Hyperliquid funding | NVDA 2025-11-12 21:00 UTC | Funding starts with the listing; the API has no deeper backfill. `misc_events_by_block` is the flat-file source to verify against it. |
| Binance USD-M `1h` klines (controls) | 2020-01 monthly archive | Full control history; archive existence verified 2026-10-21 (the probe records the first month/day once the S3 listing is fixed). |
| Binance USD-M funding (controls) | 2020-01 monthly archive | Same. |
| Binance USD-M metrics (controls) | 2021-12 monthly archive | OI / long-short metrics are later than klines and funding. |
| Hyperliquid `1m` candles (**API-only**) | ~3.5 days rolling | API retention only; the flat-file rebuild produces `1m` bars from fills, so minute history no longer depends on this window. |

**Buildable weekend panel — two bounds.** [`scripts/perps/recount_weekends.py`](../../scripts/perps/recount_weekends.py)
recounts the panel from the probe JSON with one rule (a weekend counts when its
Friday `weekend_id` is on or after the instrument's first candle date and on or
before the last Friday before the probe, 2026-10-16):

| Basis | Company-weekends | Distinct weekends | First weekend | Status |
|---|---|---|---|---|
| `1d` (history exists) | **1,871** | 49 | 2025-11-14 | **Upper bound**, only if fills cover HIP-3 from listing |
| `1h` (API-only) | **1,538** | **30** | 2026-03-27 | **Lower bound** measured on 2026-10-21 (the API window) |

The round-6 **API-only lower bound** stands: 1,538 company-weekends over 30
weekends (19 weekends / 333 company-weekends are `1d`-only), and that API window
loses about one weekend per instrument per week. Any pooled history figure that
is not bar-based overstates what can be built; §6.1 carries the power
consequence.

The **upper bound** applies only if the fills archive covers HIP-3
(`xyz`/`para`/`io`) from each instrument's listing: the panel then returns to
the daily-history count of **~1,871 company-weekends over 49 distinct
weekends**, still weekend-clustered. That is conditional, not a measurement:
HIP-3 flat-file coverage is unverified until a sample object is inspected
(owner-approved, requester-pays) and its coin list is recorded (§2.1). Until
then the plan quotes the upper bound as "at most 1,871 / 49 weekends" and the
API-only numbers as what the probe actually proves.

The commodity perps are part of the same probe run and are reported in their
own section; the 2026-10-21 measurement above covers the company perps because
that run predates the commodity section.

Every per-instrument record in `docs/data/perps_history_probe.json` /
`docs/data/perps_history_probe.md` and every row of the liquidity proposal
carries `data_source` (`hyperliquid` for HIP-3 perps, `binance_um` for the
Binance controls), validated against `config/data_sources.py` (§1.1).

### 2.6 Oracle, mark and funding prices while the underlying is closed

The weekend question is only answerable if we are explicit about *which* perp
price is observed and what the venue's reference is.

**Known** (what this repository queries and records):

- A perp's own **trade (last) price** is the only price series used by the
  return features. It comes from fills (`node_fills_by_block`) aggregated into
  our own trade-price bars (§4.1/§4.4), with the `candleSnapshot` API as the
  probe/measurement series (§2.1.1). Both are the venue's traded price, never
  the equity price, the pre-market price, the mark or the oracle.
- `metaAndAssetCtxs` exposes a **current** `markPx`, `oraclePx`, funding and
  open interest per asset. There is no historical series for mark, oracle,
  premium or OI in the public info API; the `asset_ctxs` flat file may carry
  them historically, but its **field list is TO VERIFY** before any of those
  columns is populated (§8).
- `fundingHistory` serves recorded funding rows (time, rate, premium); the
  funding interval is stored per row rather than assumed. `misc_events_by_block`
  is the flat-file funding-event source to reconcile it against.
- HIP-3 perps are listed on deployer-run sub-dexes (`xyz`, `para`, `io` in this
  universe), so the **deployer**, not this repository, defines the perp's
  oracle.

**Unknown — open questions, not assumptions** (no invented facts):

- What each deployer uses as the oracle/reference for an equity, ETF, fund,
  preferred or commodity underlying **while its cash market is closed**: the
  last Friday print held flat, a pre-market/after-hours feed, an index or CME
  Globex proxy, or a composite. Neither the public endpoints nor the probe
  document per-dex oracle inputs.
- Whether mark/oracle is frozen over the weekend and how the mark is formed
  (order-book median, oracle, or a blend).
- How funding accrues when the reference is stale, and whether `xyz`, `para`
  and `io` differ.
- Whether behaviour changes on holiday-extended weekends, early-close Fridays,
  or around index events and dividends.

**Design consequences:**

- Returns, volatility and the implied gap use **trade prices** only; a mark is
  never treated as an equity price.
- Mark/oracle stay P4 context: read them from `asset_ctxs` **after** the field
  list is verified, or from forward snapshots while it is not; measure the
  perp-vs-oracle basis and label each row's `source` (`s3_backfill` /
  `forward_snapshot`). A mark is never treated as an equity price.
- A weekend perp move is **not** an unbiased expectation of the opening print:
  the perp can carry a basis precisely because its reference may be stale. The
  plan therefore stores the basis (`perp_friday_close_basis`,
  `perp_implied_gap`, §4.3) instead of treating the perp level as fair value.
- Verifying the per-dex oracle behaviour — ideally with documentation from each
  deployer — is a **P1** open question requiring owner sign-off. Until it is
  verified, the plan states the uncertainty and does not claim a mechanism.

## 3. Weekend window definition

For a Friday date `F` (America/New_York):

```text
start_utc = last_close_before(Saturday 00:00 ET after F)
end_utc   = next_open_after(start_utc)
weekend   = [start_utc, end_utc)
```

`config/market_calendar.py` implements this from the static
[`config/xnys_holidays.yaml`](../../config/xnys_holidays.yaml), which covers
2000-01-01 through 2035-12-31. Sessions open 09:30 ET and close 16:00 ET, or
13:00 ET on recurring early closes. DST is handled by `zoneinfo`; all window
boundaries are returned as timezone-aware UTC datetimes.

Rules and edge cases:

| Case | Start | End |
|---|---|---|
| Normal week | Friday 16:00 ET | Monday 09:30 ET |
| Monday holiday (e.g. Labor Day 2026-09-07) | Friday 16:00 ET | Tuesday 09:30 ET |
| Friday holiday (e.g. Good Friday 2026-04-03) | Thursday 16:00 ET | Monday 09:30 ET |
| Day after Thanksgiving (2026-11-27) | Friday **13:00** ET | Monday 09:30 ET |
| Christmas Eve (2026-12-24) | Thursday **13:00** ET | Monday 2026-12-28 09:30 ET |
| July 3 early close (2025-07-03) | Thursday **13:00** ET | Monday 09:30 ET |
| July 4 observed Friday (2026-07-03) | Thursday 16:00 ET | Monday 09:30 ET |
| New Year's Day on Saturday (2022-01-01) | Friday 2021-12-31 16:00 ET | Monday 2022-01-03 09:30 ET |

The YAML is generated from NYSE Rule 7.2 and the NYSE trading-hours calendar
(`python -m config.market_calendar --write`) and drift-checked with
`--check`. Ad-hoc closures (9/11, Hurricane Sandy, national days of mourning)
are listed separately with citations; they are not rule-derived. Early-close
rules are asserted from 2013 onward; the pre-2013 July rule (a Thursday July 4
moves the 13:00 close to Friday July 5) is documented, and the pre-2013
December entries are flagged unverified in the module docstring and YAML.

**Atypical weekends are flagged, not dropped.** Each window carries
`weekend_flags` (§4.3): `holiday_extended` (Monday or Friday holiday),
`early_close_start` (13:00 Friday close), `good_friday`, `nfp_on_good_friday`
(when Good Friday is also the first Friday of the month, i.e. the US payrolls
release day — an information event on a closed equity session),
`month_end`, `quarter_end`. P6 reports the headline result with and without
these windows; they are also a pre-declared stratification of the secondary
family (§6.2), never a post-hoc exclusion.

### 3.1 Point-in-time convention

Perp bars are 24/7 UTC. A 1h bar is available at its `bar_end_ts`, so a feature
at cutoff `T` may use only bars with `bar_end_ts <= T`; `information_available_ts
= bar_end_ts` (conservative). No forward fill: a missing bar is a flag.

### 3.2 Prediction cutoffs, alignment and baselines

Instead of one implicit "end of the break" timestamp, the study defines four
cutoffs per weekend. Each cutoff is its own prediction row (same label, different
information set):

| Cutoff id | Wall time | What it can see | Label |
|---|---|---|---|
| `sun_1800` | Sunday 18:00 ET (the CME Globex futures week reopens around then) | perp + BTC/ETH bars with `bar_end_ts <= cutoff`; Friday equity/options features | `open_gap` at the next official open |
| `sun_2000` | Sunday 20:00 ET | same, one more evening of perp/crypto bars | same |
| `mon_0400` | Monday 04:00 ET (US pre-market opens) | same + any pre-market bars if ingested | same |
| `mon_0900` | Monday 09:00 ET (pre-market complete, last complete 1h bar) | same + pre-market/overnight information available at 09:00 | same |

Rules:

- `prediction_ts` is the cutoff itself; the label's `label_available_ts` is the
  official opening print, so `prediction_ts < label_available_ts` and the
  09:30-10:00 ET partial bar is never used.
- **Pre-market/overnight baseline.** At `mon_0400` and `mon_0900` the honest
  baseline includes what the market already knows: US pre-market equity prints
  (04:00-09:30 ET) and, for commodities, the CME Globex session. As of
  2026-10-22 this repository ingests neither pre-market equity bars nor CME
  Globex futures, so the usable baselines are Friday equity/options features +
  BTC/ETH controls. Until those inputs are ingested (P1), H1 is explicitly
  narrowed to "beyond Friday close **and the observable controls**", and the
  unmodelled pre-market information is a listed confounder (§9) — not a claim
  that perps beat the pre-market.
- Each cutoff is evaluated separately (no pooling of cutoffs into one test
  family; the pre-registered test in §6.2 is `mon_0900`).

## 4. Architecture

The diagram is [`docs/data/perps_architecture.html`](perps_architecture.html)
(self-contained HTML + inline SVG, planned components dashed). The flow:

```text
Hyperliquid requester-pays S3 (node_fills_by_block -> own 1m/15m/1h bars; asset_ctxs; misc_events_by_block; optional L2) ─┐
Hyperliquid info API (probe + closed-market liquidity measurement; 5k-candle window) ────────────────────────────────────┤
Binance Vision (flat archives: full 1m/1h history for the controls) ───────────────────┼─> Bronze append-only ─> Silver canonical ─> Gold PIT features ─> Research eval
Existing equity/options + Massive ETF wrappers ────────────────────────────────────────┘                                     ▲
NYSE calendar + perp universe config (78 + 8 + 2) ───────────────────────────────────────────────────────────────────────────┘
```

No API forward-capture job exists in this design: bars built from fills are the
history, the API only measures and probes.

### 4.1 Bronze schemas (append-only)

All timestamps UTC. Every row carries `ingest_ts`, `run_id`, `payload_hash` and a
`data_source STRING NOT NULL` provider code from `config/data_sources.py`
(§1.1); a changed payload for an existing natural key is appended as a
correction observation (never updated in place). The flat-file tables add
`source` (`flat_file_backfill` at first; `api_capture` only if a capture path is
ever approved) and `archive_key` so the object a row came from stays traceable.
Partition by `ingest_date` (and `interval` where noted).

#### `bronze_perp_fills`

Per-fill trade prints from the Hyperliquid archive — the raw input for the bar
rebuild. Provider field names are **TO VERIFY** on a sample object; the reader
maps them explicitly and fails closed on a missing field.

| Column | Type | Notes |
|---|---|---|
| `ingest_ts` | TIMESTAMP | ingestion time |
| `run_id` | STRING | manifest run id |
| `venue` | STRING | `hyperliquid` |
| `data_source` | STRING | NOT NULL; provider code from `config/data_sources.py` (`hyperliquid` here) |
| `dex` | STRING | `xyz` / `para` / `io` |
| `symbol` | STRING | provider symbol, e.g. `xyz:NVDA` |
| `ticker` | STRING | company ticker or commodity label |
| `instrument_type` | STRING | NOT NULL, always `perpetual_future` (derivative) |
| `underlying_type` | STRING | `equity` / `etf` / `fund` / `preferred` / `commodity` / `crypto` |
| `underlying_symbol` | STRING | tracked ticker/commodity |
| `contract_symbol` | STRING | venue contract symbol; same value as `symbol` |
| `trade_ts` | TIMESTAMP | fill/trade time (UTC), not the block time |
| `fill_id` | STRING | provider fill id (or `tid`); nullable when the archive has none |
| `fill_hash` | STRING | dedupe fallback: sha256 of the canonical fill tuple |
| `price` | DECIMAL(28,10) | traded price on the perp book |
| `size` | DECIMAL(28,10) | traded size in base units |
| `notional` | DECIMAL(28,10) | `price * size`, derived at ingest |
| `side` | STRING | provider side/direction, normalised |
| `block_time` | TIMESTAMP | provider block timestamp |
| `source` | STRING | NOT NULL; `flat_file_backfill` (planned) |
| `archive_key` | STRING | object key the fill came from |
| `payload_hash` | STRING | sha256 of the raw record |

Natural key: `(venue, symbol, trade_ts, fill_id)` when `fill_id` exists,
otherwise `(venue, symbol, trade_ts, fill_hash)`. Dedupe on fill id/hash is
mandatory: the same fill can appear in more than one block object or in both the
`node_fills_by_block` and `node_fills` formats.

#### `bronze_perp_candles`


| Column | Type | Notes |
|---|---|---|
| `ingest_ts` | TIMESTAMP | ingestion time |
| `run_id` | STRING | manifest run id |
| `venue` | STRING | `hyperliquid` |
| `data_source` | STRING | NOT NULL; provider code from `config/data_sources.py` (`hyperliquid` here), commented in Unity Catalog |
| `dex` | STRING | `xyz` / `para` / `io` |
| `symbol` | STRING | provider symbol, e.g. `xyz:NVDA` |
| `ticker` | STRING | company ticker or commodity label, e.g. `NVDA` |
| `instrument_type` | STRING | NOT NULL, always `perpetual_future` (derivative) |
| `underlying_type` | STRING | `equity` / `etf` / `fund` / `preferred` / `commodity` / `crypto` |
| `underlying_symbol` | STRING | tracked ticker/commodity (e.g. `NVDA`, `gold`) |
| `contract_symbol` | STRING | venue contract symbol; same value as `symbol` |
| `interval` | STRING | `1m` / `15m` / `1h` / `1d` |
| `candle_start_ts` | TIMESTAMP | bar open (UTC) |
| `candle_end_ts` | TIMESTAMP | bar close (UTC) |
| `open`,`high`,`low`,`close` | DECIMAL(28,10) | perp TRADE (last) prices on the perp book, built from fills |
| `volume` | DECIMAL(28,10) | base units |
| `trade_count` | BIGINT | number of fills in the bar (fill-derived) |
| `source` | STRING | NOT NULL; `flat_file_backfill` (planned) / `api_capture` (only if a capture path is ever approved) |
| `archive_key` | STRING | source object key(s) contributing fills |
| `request_start_ts` | TIMESTAMP | API paging cursor when the row came from the probe/capture path; null for flat files |
| `payload_hash` | STRING | sha256 of the raw record |

Natural key: `(venue, symbol, interval, candle_start_ts)`. Partition:
`interval, ingest_date`. `1m`/`15m`/`1h` rows are **built from fills** over the
whole covered period, so they are not limited by the API's rolling window;
`1d` is a history check only. A late fill re-emits its affected bar as an
append-only correction; bars are never interpolated and a missing bar stays a
gap.

#### `bronze_perp_asset_ctxs`

Per-(date, coin) asset-context rows from
`s3://hyperliquid-archive/asset_ctxs/<date>.csv.lz4`. Carries the same
derivative/`data_source` column set as the candles table, then the context
fields. **Field list TO VERIFY** on a sample file before the table is populated;
until then the columns below are the expected names and are nullable except the
`data_source`/`instrument_type` governance set.

| Column | Type | Notes |
|---|---|---|
| `ingest_ts`, `run_id` | TIMESTAMP, STRING | |
| `venue` | STRING | `hyperliquid` |
| `data_source` | STRING | NOT NULL; `hyperliquid` |
| `instrument_type` | STRING | NOT NULL, always `perpetual_future` |
| `underlying_type`, `underlying_symbol`, `contract_symbol`, `dex`, `symbol`, `ticker` | STRING | see §4.1 candles; `contract_symbol = symbol` |
| `observed_date` | DATE | archive date (UTC) |
| `observed_ts` | TIMESTAMP | sample timestamp when the file carries one; nullable |
| `funding_rate` | DECIMAL(18,10) | nullable until verified |
| `open_interest` | DECIMAL(28,10) | nullable until verified |
| `mark_px`, `oracle_px` | DECIMAL(28,10) | nullable until verified |
| `premium` | DECIMAL(18,10) | nullable until verified |
| `source` | STRING | NOT NULL; `flat_file_backfill` (planned) |
| `archive_key` | STRING | source object key |
| `payload_hash` | STRING | sha256 of the raw record |

Natural key: `(venue, symbol, observed_date)` (extended to `observed_ts` if the
verified file is intraday). Partition: `ingest_date`. A row with only the
governance columns and null context fields is rejected: the loader fails closed
on a missing expected field instead of writing half a row.

#### `bronze_perp_funding`

| Column | Type | Notes |
|---|---|---|
| `ingest_ts` | TIMESTAMP | |
| `run_id` | STRING | |
| `venue` | STRING | `hyperliquid` |
| `data_source` | STRING | NOT NULL; provider code from `config/data_sources.py` (`hyperliquid` here) |
| `dex` | STRING | |
| `symbol` | STRING | |
| `ticker` | STRING | |
| `instrument_type` | STRING | NOT NULL, always `perpetual_future` |
| `underlying_type` | STRING | see §4.1 candles |
| `underlying_symbol` | STRING | see §4.1 candles |
| `contract_symbol` | STRING | same value as `symbol` |
| `funding_time` | TIMESTAMP | provider `time` |
| `funding_rate` | DECIMAL(18,10) | decimal, not percent |
| `premium` | DECIMAL(18,10) | nullable |
| `funding_interval_hours` | INT | recorded, never assumed |
| `source` | STRING | NOT NULL; `flat_file_backfill` (`misc_events_by_block`) / `api_capture` (only if approved) |
| `archive_key` | STRING | source object key for flat-file rows |
| `payload_hash` | STRING | |

Natural key: `(venue, symbol, funding_time)`. Partition: `ingest_date`.

#### `bronze_perp_oi_snapshots`

| Column | Type | Notes |
|---|---|---|
| `ingest_ts` | TIMESTAMP | |
| `observed_at` | TIMESTAMP | snapshot time (UTC) |
| `venue` | STRING | |
| `data_source` | STRING | NOT NULL; provider code from `config/data_sources.py` (`hyperliquid` here) |
| `dex` | STRING | |
| `symbol` | STRING | |
| `ticker` | STRING | |
| `instrument_type` | STRING | NOT NULL, always `perpetual_future` |
| `underlying_type` | STRING | see §4.1 candles |
| `underlying_symbol` | STRING | see §4.1 candles |
| `contract_symbol` | STRING | same value as `symbol` |
| `open_interest` | DECIMAL(28,10) | base units |
| `mark_px` | DECIMAL(28,10) | nullable |
| `oracle_px` | DECIMAL(28,10) | nullable |
| `open_interest_usd` | DECIMAL(28,10) | nullable, derived at ingest |
| `source` | STRING | `s3_backfill` (from `asset_ctxs`) / `forward_snapshot` (P4 poller) |
| `payload_hash` | STRING | |

Natural key: `(venue, symbol, observed_at, source)`. Partition: `ingest_date`.
This table starts empty; P4 populates it. `s3_backfill` rows are written only
after the `asset_ctxs` field list is verified (§2.1); until then the table has no
historical rows and `oi_*` features stay null.

#### `bronze_binance_um_klines`

The Binance control tables inherit the **same derivative columns** as the HIP-3
tables: `instrument_type` (`perpetual_future`), `underlying_type` (`crypto`),
`underlying_symbol` (`BTC`/`ETH`), `venue` (`binance_usdm`) and
`contract_symbol` (same value as `symbol`), so no perps table can be mistaken
for an equity/spot table and every row names the perp contract it is.

| Column | Type | Notes |
|---|---|---|
| `ingest_ts`, `run_id` | TIMESTAMP, STRING | |
| `venue` | STRING | NOT NULL, `binance_usdm` |
| `instrument_type` | STRING | NOT NULL, always `perpetual_future` (derivative) |
| `underlying_type` | STRING | NOT NULL, `crypto` for the controls |
| `underlying_symbol` | STRING | NOT NULL, `BTC` / `ETH` |
| `contract_symbol` | STRING | NOT NULL, same value as `symbol` |
| `data_source` | STRING | NOT NULL; provider code from `config/data_sources.py` (`binance_um` here) |
| `symbol` | STRING | `BTCUSDT` / `ETHUSDT` |
| `interval` | STRING | `1h` |
| `open_time`, `close_time` | TIMESTAMP | archive fields (UTC) |
| `open`,`high`,`low`,`close` | DECIMAL(28,10) | archive TRADE (last) prices on the Binance USD-M perp book |
| `volume`, `quote_volume` | DECIMAL(28,10) | |
| `trade_count` | BIGINT | |
| `taker_buy_base`, `taker_buy_quote` | DECIMAL(28,10) | |
| `archive_key` | STRING | source zip key |
| `payload_hash` | STRING | |

Natural key: `(symbol, interval, open_time)`.

#### `bronze_binance_um_funding`

Same derivative columns (`venue`, `instrument_type`, `underlying_type`,
`underlying_symbol`, `contract_symbol`, `data_source STRING NOT NULL`
=`binance_um`), then `ingest_ts`, `run_id`, `symbol`, `calc_time`,
`funding_interval_hours`, `last_funding_rate`, `archive_key`, `payload_hash`.
Natural key: `(symbol, calc_time)`.

#### `bronze_binance_um_metrics`

Same derivative columns (`venue`, `instrument_type`, `underlying_type`,
`underlying_symbol`, `contract_symbol`, `data_source STRING NOT NULL`
=`binance_um`), then `ingest_ts`, `run_id`, `symbol`, `create_time`,
`sum_open_interest`, `sum_open_interest_value`,
`count_toptrader_long_short_ratio`, `sum_toptrader_long_short_ratio`,
`count_long_short_ratio`, `sum_taker_long_short_vol_ratio`, `archive_key`,
`payload_hash`. Natural key: `(symbol, create_time)`.

### 4.2 Silver schemas (canonical, deduplicated)

#### `silver_perp_bars_1h`

| Column | Type | Notes |
|---|---|---|
| `venue`, `dex`, `symbol`, `ticker` | STRING | |
| `data_source` | STRING | NOT NULL; provider code from `config/data_sources.py` (`hyperliquid` here) |
| `instrument_type`, `underlying_type`, `underlying_symbol`, `contract_symbol` | STRING | NOT NULL; `instrument_type = perpetual_future`; `contract_symbol = symbol` |
| `bar_start_ts`, `bar_end_ts` | TIMESTAMP | UTC |
| `open`,`high`,`low`,`close` | DECIMAL(28,10) | perp **trade (last)** price, **not** the stock price, mark or oracle |
| `volume` | DECIMAL(28,10) | |
| `trade_count` | BIGINT | |
| `information_available_ts` | TIMESTAMP | `bar_end_ts` (conservative) |
| `source` | STRING | `flat_file_backfill` (fills-built) / `api_capture` (only if approved) |
| `ingest_ts` | TIMESTAMP | latest selected observation |
| `quality_flags` | ARRAY<STRING> | `gap`, `stale`, `duplicate`, `split_suspect` |

Natural key: `(venue, symbol, bar_start_ts)`. Partition: `date(bar_start_ts)`.
Select the latest valid Bronze observation per key; keep flags rather than
dropping rows. `quality_flags` includes `duplicate` because a fill can appear in
two archive objects; the rebuilt bar counts each fill once (§4.4).

#### `silver_perp_funding`

`venue`, `dex`, `symbol`, `ticker`, `instrument_type`, `underlying_type`,
`underlying_symbol`, `contract_symbol`, `data_source STRING NOT NULL`
(`hyperliquid`; provider code from `config/data_sources.py`), `funding_time`,
`funding_rate`, `funding_interval_hours`, `information_available_ts`
(= `funding_time`), `source`, `ingest_ts`, `quality_flags`.
Natural key: `(venue, symbol, funding_time)`.

### 4.3 Gold schema

#### `gold_weekend_perp_features`

One row per `(weekend_id, security_id, prediction_cutoff)`.

| Group | Columns |
|---|---|
| Keys | `weekend_id` (Friday date), `security_id`, `ticker`, `perp_symbol`, `venue`, `dex`, `prediction_cutoff` (`sun_1800` / `sun_2000` / `mon_0400` / `mon_0900`) |
| Window | `window_start_ts`, `window_end_ts`, `prediction_ts` (= the cutoff instant, see §3.2) |
| Perp price | `perp_first_px`, `perp_last_px`, `perp_ret_weekend`, `perp_ret_fri_close_to_sat`, `perp_ret_sun_to_mon`, `perp_high`, `perp_low`, `perp_range`, `perp_max_drawdown` |
| Perp basis | `perp_friday_close_basis` (= perp trade price at the last Friday bar before the close / `prev_session_close` - 1), `perp_implied_gap` (= `perp_last_px / prev_session_close - 1`) |
| Perp risk | `perp_realized_vol_1h`, `perp_volume_base`, `perp_trade_count`, `perp_bar_count`, `perp_gap_count`, `perp_weekend_coverage` |
| PIT liquidity | `perp_trailing_closed_usd_per_h` (mean over the previous N weekends, strictly before `window_start`), `perp_trailing_weekends` |
| Funding | `funding_sum`, `funding_mean`, `funding_last`, `funding_count`, `funding_interval_hours` |
| OI (P4, nullable) | `oi_start`, `oi_end`, `oi_change_pct`, `mark_px_at_cutoff`, `oracle_px_at_cutoff` (nullable; `s3_backfill` from verified `asset_ctxs`, otherwise forward snapshots) |
| Controls | `btc_ret_weekend`, `eth_ret_weekend`, `btc_realized_vol_1h`, `eth_realized_vol_1h` |
| Equity baselines (PIT) | `friday_adj_close`, `friday_ret_1d`, `friday_ret_5d`, `friday_iv_atm`, `friday_iv_skew`, `friday_options_volume_z`, `equity_features_available_ts` |
| Label | `prev_session_close` (raw official close of the prior session; Thursday on Friday-holiday weekends), `session_open` (raw official opening print), `label_split_factor` (factor effective at that open from `bronze_corporate_actions`), `open_gap`, `label_available_ts` (= session open print time) |
| Weekend flags | `weekend_flags` (ARRAY<STRING>): `holiday_extended` (Monday/Friday holiday), `early_close_start` (13:00 Friday close), `good_friday`, `nfp_on_good_friday` (Good Friday that is also a US payrolls release), `month_end`, `quarter_end` |
| Governance | `instrument_type` (NOT NULL `perpetual_future`), `underlying_type`, `underlying_symbol`, `contract_symbol`, `venue`, `data_source` (NOT NULL; `derived` for this feature row — perp/funding inputs are `hyperliquid`, equity/options inputs are `massive`, recorded in lineage), `mapping_status` (`verified` / `unverified`), `information_available_ts`, `feature_version`, `ingest_ts` |

Natural key: `(weekend_id, security_id, prediction_cutoff)`. Partition:
`weekend_id`.
`information_available_ts` is the maximum of the component availability
timestamps and must satisfy `information_available_ts <= prediction_ts`; the
loader rejects rows that violate it. `open_gap` must never appear in a feature
column. All perp-derived columns use the `perp_` prefix, and the table comment
starts with "Perpetual futures (derivatives), not equities:" with tags
`instrument_type=perpetual_future`, `asset_class=derivative`; price columns are
commented "perp trade (last) price, not the stock price".

The label is one point-in-time-safe, same-basis definition:

```text
open_gap = session_open / prev_session_close - 1
```

* `session_open` — raw official opening print of the first session after the
  break (the opening auction/print, not the pre-market price).
* `prev_session_close` — raw official closing print of the last session before
  the break (Thursday when Friday is the observed holiday).
* `label_split_factor` — explicit split/dividend factor effective at that open
  from `bronze_corporate_actions`, applied to `prev_session_close` (raw prices
  on both sides, one explicit adjustment). The stored factor makes the row
  reproducible; vendor back-adjusted columns are not used.

Feature definitions (all computed from rows with `bar_end_ts <=
prediction_ts`):

- `perp_ret_weekend = last_close / first_open - 1` over the window.
- `perp_ret_fri_close_to_sat`: first close at/after the window start divided by
  the first open, minus 1; `perp_ret_sun_to_mon` is the analogous tail return.
- `perp_friday_close_basis`: the trade price of the last 1h bar whose
  `bar_end_ts` is at or before the Friday regular-session close, divided by
  `prev_session_close`, minus 1 — how far the perp traded from the equity's
  official close when the cash market shut.
- `perp_implied_gap = perp_last_px / prev_session_close - 1`: the gap the perp
  "implies" at the cutoff. It is a perp trade price, not a forecast (see §2.6),
  and it is the feature that most directly tests the weekend information channel.
- `perp_realized_vol_1h = stdev(log returns of 1h closes)` (sample, requires at
  least 12 bars; otherwise null + flag).
- `perp_max_drawdown = min(close / running_max - 1)`.
- `funding_sum/mean/last` over funding records in `[start, prediction_ts)`.
- `oi_change_pct = oi_end / oi_start - 1` only when both endpoints exist.
- `perp_trailing_closed_usd_per_h` uses only weekends whose end is strictly
  before `window_start` (PIT liquidity, §1.2); null + flag below the minimum
  observation count.
- Controls are the same calculations on `BTCUSDT`/`ETHUSDT` (Binance 1h bars,
  filtered to the same UTC window).
- Cross-sectional z-scores (by `weekend_id`) are derived in the research layer,
  not stored as raw features.

### 4.4 P1 flat-file ingestion (`scripts/perps/hl_flat_files.py`, design only)

**P0 ships the design and no code.** The module below is specified here so the
P1 implementation is a scoped build, not a redesign; nothing in P0 imports
`boto3`/`lz4` or touches the network.

**Purpose.** Read the Hyperliquid requester-pays archive and rebuild trade-price
bars + context history, with an explicit dry-run cost gate:

```text
fills (node_fills_by_block | node_fills | node_trades)
  -> dedupe (fill id / fill_hash) -> bucket by TRADE time (UTC) -> 1m/15m/1h bars
asset_ctxs/<date>.csv.lz4        -> funding / OI / mark / oracle rows (fields TO VERIFY)
misc_events_by_block             -> funding events
market_data/<date>/<hour>/l2Book/<coin>.lz4 -> optional L2 sample (P4+)
```

**CLI contract (design):**

| Flag | Behaviour |
|---|---|
| `--dataset {fills,asset_ctxs,funding_events,l2}` | Which prefix to read. Default `fills`. |
| `--start`, `--end` | UTC date range; required for `--live`, default = the last complete month for dry-run. |
| `--symbols` / `--all-configured` | Restrict to `config/perp_universe.yaml` symbols, or scan every coin found in the archive as a discovery run (listed in the manifest, no bars written). |
| `--profile NAME` / `AWS_PROFILE` env | AWS profile *name* only; credentials come from the standard chain and are never read, printed or persisted. |
| `--usd-per-gb`, `--max-cost-usd`, `--max-bytes`, `--max-objects` | Cost gate. Defaults documented in the module; a run aborts before downloading if the estimate exceeds the cap. |
| `--out-manifest PATH` | JSON manifest: object keys, bytes, ETags, estimated cost, rows read, bars written, gaps. |
| `--dry-run` (default) | List objects only; zero `GET`s. |
| `--live` | Required to download. Never implied by any other flag. |

**Dry-run cost print (before any download).** Paginate `ListObjectsV2` with
`RequestPayer='requester'`, sum `ContentLength`, and print:

```text
dataset=fills  prefix=s3://hl-mainnet-node-data/node_fills_by_block/2026-09/
objects=1,234  bytes=812.4 GB  est_transfer_usd=... (at --usd-per-gb)
action=DRY-RUN (no GET sent); pass --live to download
```

The rate is a CLI input with a documented default, not a hard-coded claim; the
operator confirms the bucket's requester-pays terms before `--live`. Listing
requests are themselves requester-pays and are counted in the estimate.

**Streaming decode, no full-file loads.** Each object is opened as a stream and
decoded with an lz4 frame reader (`lz4.frame.open` over the streaming body)
yielding one record at a time; the reader never calls `.read()` on the whole
object, never loads a file into memory, and never materialises a month of
records. Memory stays bounded by a per-bar accumulator (symbol × interval), and
a decompression/parse error fails that object closed (recorded in the manifest,
no partial bars published). Per-object checkpoints make re-runs resumable and
idempotent.

**Bar construction rules.**

- Bucket by **trade time in UTC**: `bar_start_ts = floor(trade_ts / interval)`,
  `bar_end_ts = bar_start_ts + interval`, `information_available_ts = bar_end_ts`
  (conservative). Block time is stored on the fill but is never the bucket key.
- `open` = first fill price, `high`/`low` = max/min, `close` = last fill price,
  `volume` = sum of sizes, `trade_count` = fill count; `notional` is summed from
  `price * size`.
- Dedupe on `(symbol, fill_id)` when the archive carries an id, else on
  `fill_hash = sha256(canonical fill tuple)`. A duplicate is counted in the
  manifest, not double-counted in the bar.
- Out-of-order or late fills re-emit the affected bar as an append-only
  correction in Bronze; Silver selects the latest valid observation.
- No interpolation, no forward fill: a bar with no fills does not exist and is a
  gap; `weekend_coverage`/`perp_gap_count` report it.
- Identity columns on every row: `data_source='hyperliquid'`,
  `instrument_type='perpetual_future'`, `venue='hyperliquid'`, `dex` parsed from
  the `dex:TICKER` symbol, and `underlying_type`/`underlying_symbol`/`ticker`
  from `config/perp_universe.yaml`. An unknown coin fails closed; only an
  explicit `--all-configured` discovery run may list it (in the manifest, with
  no bars written).

**Credentials and safety.** Only the profile name and the bucket/prefix are
logged; access keys, session tokens and signed URLs are never printed, stored or
committed. Errors are redacted before logging. No `.env` value is passed as a
CLI argument. `--live` refuses to run when the estimate exceeds the cap or the
range is unbounded.

**Dependencies (P1, not this round).** Add `lz4` (streaming frame decode) and
`boto3` (S3 + `RequestPayer`) to `pyproject.toml`, then `uv lock` and
`scripts/export_requirements.sh`; `requirements.txt` is generated and is never
hand-edited.

**Testability (P1).** The object store and the decoder are injected
(`ObjectStore.list/get_stream`, `Decoder.records`), so tests use a tiny recorded
fixture and a fake store: a dry-run test asserts zero `get` calls, a mutation
test asserts a whole-object `read()` or a missing `--live` gate fails, and
bucketing/dedupe are tested across a UTC midnight boundary and a late fill.

**Pre-implementation gate (P1, owner-approved, requester-pays).** Inspect one
`node_fills_by_block` object and one `asset_ctxs/<date>.csv.lz4` object: record
the coin list (does it include `xyz`/`para`/`io`?), the field list (does
`asset_ctxs` carry funding/OI/mark/oracle?), the bytes and the cost. Record the
result in the evidence file and update §2.5 before claiming the upper bound.

**Bronze targets:** `bronze_perp_fills`, `bronze_perp_candles` (fill-built),
`bronze_perp_asset_ctxs`, `bronze_perp_funding`, `bronze_perp_oi_snapshots`
(`source='s3_backfill'` once verified) — all with the
RULE-perps-are-derivatives column set (`instrument_type`,
`underlying_type`, `underlying_symbol`, `venue`, `contract_symbol`) and a
non-null `data_source`.

## 5. Instrument mapping to the KG security dimension

The provider-symbol bridge is a first-class PIT table (planned
`bridge_provider_symbol`):

| Column | Example | Notes |
|---|---|---|
| `provider` | `hyperliquid` | `hyperliquid` / `binance_usdm` |
| `provider_symbol` | `xyz:NVDA` | exact API symbol |
| `venue` | `hyperliquid_hip3` | |
| `dex` | `xyz` | null for Binance |
| `security_id` | `NVDA` | US single-stock/ETF/commodity id (repo `symbol` convention) |
| `asset_class` | `equity` / `etf` / `fund` / `preferred` / `commodity` / `crypto` | underlying class |
| `instrument_type` | `perpetual_future` | NOT NULL; the bridge maps a derivative, never the security itself |
| `company_cik` | `0001045810` | nullable; SEC bridge |
| `valid_from`, `valid_to` | TIMESTAMP | PIT validity |
| `information_available_ts` | TIMESTAMP | when the mapping was verified |
| `mapping_status` | `verified` / `unverified` | `unverified` rows are excluded from training |
| `source` | `config/perp_universe.yaml` + SEC snapshot | |

Examples:

```text
provider=hyperliquid, symbol=xyz:NVDA  -> security_id=NVDA, asset_class=equity
provider=hyperliquid, symbol=para:CIEN -> security_id=CIEN, asset_class=equity
provider=hyperliquid, symbol=xyz:GOLD  -> security_id=gold, asset_class=commodity, etfs=[GLD, IAU]
provider=binance_usdm, symbol=BTCUSDT  -> security_id=crypto:BTC, asset_class=crypto
provider=binance_usdm, symbol=ETHUSDT  -> security_id=crypto:ETH, asset_class=crypto
```

The KG `Company` node is keyed by CIK, not ticker. The bridge links
`security_id -> company_cik` using the SEC snapshot; a commodity perp links to
the ETF wrapper's `Security` node via `UNDERLIES` (never merged), and every
bridge row carries `instrument_type = perpetual_future`.
`config/sec_cik_overrides.yaml` remains authoritative for multi-CIK issuers. A
ticker with no verified bridge is **quarantined** in gold (`mapping_status =
unverified`), not silently dropped. `scripts/perps/check_universe.py` produces
the review list that drives this table.

## 6. Point-in-time rules

1. **Weekend features:** only perp/funding/control rows with
   `information_available_ts <= prediction_ts`, where `prediction_ts` is the
   chosen cutoff (§3.2). No forward fill of missing bars; a missing bar is a
   flag, not an interpolation.
2. **Friday equity/options features:** join as-of the Friday session close using
   the existing `information_available_ts`; require it to be `<= prediction_ts`.
   Do not use Monday data in a Friday feature.
3. **Label:** `open_gap = session_open / prev_session_close - 1` on the raw
   official prints with `label_split_factor` effective at that open. It is
   available only at the opening print (`label_available_ts`) and must never
   appear in a feature column or a model input.
4. **Mapping:** use the bridge row valid at `prediction_ts`
   (`valid_from <= prediction_ts < valid_to`).
5. **Evaluation:** out-of-time split by `weekend_id`; no random shuffling.
6. **Controls:** BTC/ETH features use the same UTC window, so any perp signal
   must beat the crypto-only baseline, not just the equity-only baseline.
7. **Liquidity:** model inputs/filters use `perp_trailing_closed_usd_per_h`
   computed only from weekends ending strictly before `window_start`. The static
   tier in the config is descriptive (§1.2) and is never a feature.

### 6.1 Statistical power (recounted 2026-10-21; upper bound added 2026-10-22)

[`scripts/perps/recount_weekends.py`](../../scripts/perps/recount_weekends.py)
reproduces the panel and its power consequence from the probe JSON:

| Basis | Company-weekends | Distinct weekends | First weekend | Role |
|---|---|---|---|---|
| `1d` (history exists) | 1,871 | 49 | 2025-11-14 | **Upper bound** if fills cover HIP-3 from listing (unverified) |
| `1h` (**API-only**) | 1,538 | **30** | 2026-03-27 | **Lower bound** (measured on the API window) |

The **API-only lower bound** stands: 1,538 company-weekends over 30 weekends,
and 19 weekends (333 company-weekends) are `1d`-only because the API's 5,000
candle `1h` window starts at 2026-03-27. That window loses about one weekend per
instrument per week; the API-only panel is a **ceiling that is falling**, not a
backlog.

The flat-file rebuild is not subject to that window. **If** the fills archive
covers HIP-3 (`xyz`/`para`/`io`) from each listing — unverified until a sample
object is inspected (§2.1, §4.4) — the buildable panel returns to the
daily-history count: **~1,871 company-weekends over 49 weekends**, still
weekend-clustered. Until that check is recorded, 1,871/49 is an upper bound and
the API-only 1,538/30 is what the probe proves.

The panel is clustered by weekend: rows in the same weekend share one macro/crypto
shock. The effective N is the **number of weekends**, not the row count:

| N_eff | Smallest detectable partial r (80% power, two-sided 5%) | ΔR² |
|---|---|---|
| 30 (API-only lower bound) | **0.54** | **0.29** |
| 49 (upper bound, if flat-file HIP-3 coverage is confirmed) | **0.41** | **0.17** |

Using the 1,538 pooled rows instead would suggest r ≈ 0.07 (ΔR² ≈ 0.005) — an
anticonservative illusion. Even at the upper bound, the design can only detect
a **large** incremental effect. A realistic weekend-perp increment is far
smaller, so P6 must report the effect size and confidence interval, must not
present a non-significant result as "no signal", and must treat a null as the
expected outcome. The pre-registered test in §6.2 is defined at this effect
scale; anything smaller is descriptive.

### 6.2 Pre-registration and multiple testing

Fixed **before** any P6 result is inspected, in the P6 kickoff note:

- **One primary hypothesis / comparison (confirmatory):** H1 at cutoff
  `mon_0900` — the perp block added to the baseline
  (Friday equity/options + BTC/ETH controls) improves the out-of-time partial
  R² for `open_gap`. Primary metric: out-of-time partial R² of the perp block
  (equivalently the t-statistic of the block), with the weekend-clustered
  standard error. Primary sample: the bar-buildable weekends (flat-file
  fill-built `1h` bars once the HIP-3 coverage check is recorded, otherwise the
  API-only lower bound) with a verified mapping and a complete baseline.
- **Secondary family:** all other comparisons (other cutoffs, per-instrument
  runs, single-feature ablations, commodity perps, static-tier subsets). They
  are reported with the family defined up front and corrected with **Holm**
  across the family (family-wise error control), or **Benjamini–Hochberg** when
  the family is explicitly declared exploratory with FDR reported. The plan
  names one correction per family; switching correction after seeing results is
  not allowed.
- **Model selection and tuning stay inside training folds:** all feature
  selection, hyper-parameters, thresholds and cutoff choices are fitted on
  training weekends only (walk-forward/nested by `weekend_id`). The final
  out-of-time block is evaluated **once**, after the model is frozen; touching
  it to re-tune converts the test into a validation set and must be reported as
  such.
- **Reporting:** every comparison reports N_eff (weekends), the estimate, its
  interval and the correction applied; the pre-registered comparison is reported
  first and unadjusted, then the corrected secondary family.

## 7. PR slices

| Slice | Scope | Acceptance |
|---|---|---|
| **P0 (this round)** | `config/perp_universe.yaml` v4 + typed loader (instrument_type, underlying_type, commodities, tiers A-D, flags); static NYSE calendar; `scripts/perps/check_universe.py`; `scripts/perps/probe_history.py`; `scripts/perps/measure_closed_liquidity.py`; `scripts/perps/recount_weekends.py`; this plan (including the §4.4 flat-file reader design); architecture diagram; ontology terms; tests. | `pytest -q -m "not spark and not lakebase and not databricks"` (plain and with pyspark blocked); probe/measure `--dry-run`; no pandas/duckdb imports; calendar `--check`; loader loads 78 companies + 8 commodities + 2 controls; every row/record carries a valid `data_source` from `config/data_sources.py`; recount reproduces 1,871/1,538 company-weekends; ontology test green; no code path in P0 touches the network. |
| **P1 (flat-file backfill)** | **`scripts/perps/hl_flat_files.py` as designed in §4.4**: Hyperliquid requester-pays S3 fills (`node_fills_by_block`, older `node_fills`/`node_trades`) rebuilt into our own `1m`/`15m`/`1h` trade-price bars; `asset_ctxs` for funding/OI/mark/oracle **after** its field list is verified; `misc_events_by_block` funding events; optional L2 sample; Binance Vision controls. Plus the HIP-3 coverage check on one sample object, the universe survivorship audit, the per-dex oracle open-question verification, and a decision + ingestion plan for the pre-market/overnight (US pre-market equity bars) and CME Globex baselines. **No API forward-capture job.** | Dry-run prints the object list + estimated requester-pays transfer cost and sends **zero** `GET`s; `--live` is required to download and honours `--max-cost-usd`/`--max-bytes`; bars bucket by trade time in UTC, dedupe on fill id/hash and pass the fixture tests (UTC-midnight boundary, duplicate fill, late fill); re-running a manifest is idempotent; HIP-3 coverage and the `asset_ctxs` field list are recorded from a sample object; the survivorship list is recorded with sources; each open question in §2.6 is either answered with a cited source or still marked open; the pre-market/Globex decision is recorded before P6 claims "beyond pre-market". |
| **P2** | Bronze loaders for the P1 reader (fills, fill-built candles, asset contexts if verified, funding, Binance USD-M archives), manifests, idempotency, bounded backfill, archive checksums; DQ report on missing months and duplicate fills. | Re-running a run id creates zero duplicate Bronze rows; requester-pays cost stays inside the approved cap; partial writes retryable; checksum mismatch fails the run; DQ report on missing/duplicate bars and archive gaps. |
| **P3** | Silver normalization: 1h bars, funding, QA flags (gaps, DST, stale marks, split suspects), canonical dedupe. | Natural keys unique; `information_available_ts` equals bar close; QA counts match Bronze source counts; no forward fill. |
| **P4** | OI: verified `asset_ctxs` backfill into `bronze_perp_oi_snapshots` (`source='s3_backfill'`), plus optional forward `metaAndAssetCtxs` snapshots (`source='forward_snapshot'`); optional L2 depth sample. | Field list verified before backfill; snapshot cadence documented; no fabricated history; `oi_change_pct` null when endpoints missing. |
| **P5** | `gold_weekend_perp_features`: weekend windows, four prediction cutoffs, PIT trailing liquidity, equity/options baselines, BTC/ETH controls, the `prev_session_close`/`session_open`/`label_split_factor` label; mapping bridge. | Window boundaries match `market_calendar` fixtures; every row passes `information_available_ts <= prediction_ts`; label never in feature columns; `open_gap` reproducible from the stored prints and factor; reconciliation counts. |
| **P6** | Research evaluation: baseline models (Friday equity/options; + crypto; + perps), the pre-registered primary comparison (§6.2), out-of-time metrics, ablations, notebook, owner review. | Pre-registered metrics and correction; N_eff reported; model selection inside training folds; final out-of-time block untouched until evaluation; no signal publication; reproducible notebook and data snapshot; honest negative result allowed. |

Dependencies: P1 → P2 → P3 → P4/P5 → P6. P0 is standalone. P1 is no longer
race-against-the-clock: the archive is durable, although it is uploaded roughly
monthly and the provider warns data may be missing, so a run must tolerate gaps
and be re-runnable rather than "capture or lose forever". The one irreversible
risk is the HIP-3 coverage check, which needs one owner-approved,
requester-pays sample. OI is optional for P5; `oi_*` stays nullable until P4.

## 8. Open interest options (owner decision)

Hyperliquid's public info API exposes **current** OI only; there is no
historical OI series to backfill from the API, and P0 ships no OI data. Options:

1. **`asset_ctxs` backfill (preferred once verified):** the
   `s3://hyperliquid-archive/asset_ctxs/<date>.csv.lz4` archive is the intended
   source for historical funding, OI, mark and oracle. Its **field list is TO
   VERIFY** on a sample object (owner-approved, requester-pays); verify the
   licence, retention, schema and transfer cost before writing any row.
   Backfilled rows are labelled `source='s3_backfill'`.
2. **Forward snapshots (fallback/default while (1) is unverified):** poll
   `metaAndAssetCtxs` on a schedule (e.g. every 5-15 minutes) into
   `bronze_perp_oi_snapshots` (`source='forward_snapshot'`). No back-history;
   starts when the poller is deployed. Low cost, immutable.
3. **Candle-derived proxy:** do not call it OI. If used, name it explicitly
   (`volume_imbalance_proxy`) and document that it is not open interest.

The probe records these options in `docs/data/perps_history_probe.json` and does
not attempt an OI history fetch.

## 9. Risks and limitations

- **Survivorship / selection:** the universe is the 2026-10-21 liquid subset, so
  delisted and never-selected perps are missing; results are conditional on
  "still listed on 2026-10-21" until the P1 survivorship audit lands. Tier D /
  sparse perps may also have wide spreads and stale marks; report liquidity and
  run results with/without the illiquid names.
- **Short history, two bounds:** the API window proves a **lower bound** of 30
  weekends (1,538 company-weekends) and shrinks by about one weekend per
  instrument per week (5,000-candle rolling cap); do not assume a common start
  date. The flat-file rebuild can restore history to each listing
  — **at most** 1,871 company-weekends over 49 weekends — but only if the fills
  archive covers HIP-3 from listing, which is unverified (§2.1, §2.5). Do not
  quote 1,871 as buildable until that check is recorded.
- **Flat-file archive risk:** the Hyperliquid archive is uploaded **roughly
  monthly** and the provider states **"no guarantee of timely updates and data
  may be missing"**. Recent weeks can be absent, a missing object is a gap (never
  an empty period), and every run must be re-runnable rather than assumed
  complete. **HIP-3 (`xyz`/`para`/`io`) coverage is unverified** until a sample
  object is inspected, and every inspection/download is **requester-pays**
  (owner-approved, dry-run cost print first, §4.4).
- **Stale reference price:** the perp's oracle may be frozen while the underlying
  is closed (§2.6), so a weekend perp move is not an unbiased expectation of the
  opening print and can carry a basis. Report the basis, never treat it as value.
- **Pre-market/overnight confounder:** US pre-market equity bars and CME Globex
  commodity futures are not ingested, so at the `mon_0400`/`mon_0900` cutoffs the
  baseline is incomplete. H1 is narrowed accordingly (§3.2); claiming a perp
  edge over the pre-market would require those inputs.
- **24/7 microstructure:** weekend marks may be noisy or stale; measure bar
  coverage and gap counts (`weekend_coverage`, `weekend_gap_hours`), and withhold
  liquidity tiers below 80% expected-hour coverage.
- **Crypto confounding:** perps trade alongside crypto; BTC/ETH controls are
  mandatory, not optional.
- **Clustered and unbalanced panel:** 30-49 weekend clusters, so only large
  effects are detectable (§6.1); report N_eff, not row counts.
- **Corporate actions:** splits/index changes may create price jumps; flag and
  review rather than auto-adjust. The label uses the explicit factor effective at
  the open, stored per row.
- **Provider instability:** unofficial APIs and archive layouts can change
  fields or limits; fail closed, monitor the probe and ingestion manifest.
- **Minute bars:** the API keeps only ~3.5 days of `1m` candles, so API-only
  minute work is impossible; the flat-file rebuild produces `1m` from fills for
  the covered period, and Binance archives cover the controls. Until the rebuild
  lands, use `15m`/`1h` for history.
- **Offline CIK map:** sparse; the ticker review must be rerun with a full SEC
  snapshot before treating "unmapped" as final.

## 10. Reproduction

```bash
uv venv
uv pip install -r requirements.txt -r requirements-dev.txt   # drop ibapi as CI does
pytest -q -m "not spark and not lakebase and not databricks"
python scripts/perps/probe_history.py --dry-run
python scripts/perps/measure_closed_liquidity.py --dry-run
python scripts/perps/check_universe.py
python scripts/perps/recount_weekends.py \
  --probe docs/data/perps_history_probe.json   # the 2026-10-21 run is also archived as the P0 facts JSON
python -m config.market_calendar --check
# coordinator only, live network:
python scripts/perps/probe_history.py --live \
  --out-json docs/data/perps_history_probe.json \
  --out-md docs/data/perps_history_probe.md
python scripts/perps/measure_closed_liquidity.py --live \
  --out docs/data/perp_liquidity_tier_proposal.json
```

`scripts/perps/hl_flat_files.py` does not exist in P0: §4.4 is its design and the
implementation lands in P1. No P0 command above downloads a flat file.

The probe is not run in tests. `--dry-run` is the default and makes zero network
calls; `--live` enforces ≤ 2 requests/second with retries/backoff/jitter. The
liquidity tool writes a proposal only (`docs/data/perp_liquidity_tier_proposal.json`);
applying it to `config/perp_universe.yaml` is an owner edit. The recount script
is offline and stdlib-only; it reproduces §2.5 and §6.1.
