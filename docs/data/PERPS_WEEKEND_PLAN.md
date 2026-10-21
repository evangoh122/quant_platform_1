# Perps weekend research plan (P0, v4)

**Status:** design + research scaffolding (P0, round 2). No ingestion job is
scheduled, no shared table is written and no signal is published. **Owner:**
decisions 2026-10-22.

**Instruments are derivatives.** Every row in the universe is a **perpetual
future** (`instrument_type: perpetual_future`) traded on a crypto venue. The
listed ticker, ETF or commodity is only the *underlying* it tracks through the
venue oracle: a perp is never the equity, never the ETF and never spot. Every
table, Unity Catalog comment/tag, knowledge-graph node and UI label must carry
that distinction, and perp columns in mixed feature tables use a `perp_` prefix.

**Question.** Do weekend moves in equity perpetuals improve predictions of the
Monday opening gap beyond (a) Friday equity/options signals and (b) broad crypto
weekend returns?

**Target.** `monday_gap = monday_open / friday_close - 1` for each US single stock
in the configured universe. The label is known at the Monday open; it is never a
feature.

**Hypotheses.**

- **H1 (incremental information):** weekend perp returns/volatility/funding add
  explanatory power for Monday gaps after controlling for Friday equity returns,
  options-implied volatility/skew, and BTC/ETH weekend returns.
- **H2 (crypto channel):** any apparent perp signal is explained by BTC/ETH
  weekend returns (equity perps trade 24/7 alongside crypto), so the perp block
  must be tested against those controls.
- **H0:** no incremental lift; the honest default.

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
| Flags | `new` = first bar after the window start; `sparse` = more than 25% of weekend hours with zero volume |

Tiers and flags are model inputs and filters, **not** ingestion filters: every
configured instrument is still ingested. They are re-measured with
[`scripts/perps/measure_closed_liquidity.py`](../../scripts/perps/measure_closed_liquidity.py),
which writes a proposal JSON and never edits the config; the owner applies
changes.

The round-1 ticker review in `scripts/perps/check_universe.py` is report-only.
It flags ETFs, funds, preferreds and tickers that are unmapped in the **offline**
SEC CIK files. The owner kept all 78 and set the underlying labels from that
check: `BOT → fund`, `STRC → preferred`, `KSTR → etf`. The checked-in offline map
is intentionally sparse (`config/sec_cik_overrides.yaml` plus
`tests/rag/fixtures/sec/company_tickers.json`), so "unmapped" is a prompt to run
the check with a full `company_tickers.json` snapshot, not proof that a company
lacks an SEC registration.

## 2. Sources, endpoints and limits

### 2.1 Hyperliquid info API (equity perps)

`POST https://api.hyperliquid.xyz/info`, JSON body, no API key.

| Request | Body (abridged) | Use | Limits / notes |
|---|---|---|---|
| `candleSnapshot` | `{"type":"candleSnapshot","req":{"coin":"xyz:NVDA","interval":"1h","startTime":<ms>,"endTime":<ms>}}` | 1h/15m bars for history and measurement; 1m for forward capture | Public API returns at most 5,000 candles per response; page by `startTime`. `endTime` bounds the page. **1m retention is only ~3.5 days** (see below). |
| `fundingHistory` | `{"type":"fundingHistory","coin":"xyz:NVDA","startTime":<ms>,"endTime":<ms>}` | funding records | Public API caps a page (order of 500 records); page by `startTime`. Interval is recorded per row, not assumed. |
| `metaAndAssetCtxs` | `{"type":"metaAndAssetCtxs"}` | **current** open interest / mark / oracle | Current snapshot only; there is **no historical OI** in the public info API. |
| `clearinghouseState` | `{"type":"clearinghouseState","user":...}` | user positions | Not used by this track. |

Operational rules:

- **Minute bars are a forward-capture stream.** The public API serves only
  roughly the last **3.5 days** of `1m` candles, so a backfill cannot recover
  older minute data. P2 therefore runs a **daily 1m forward-capture job** for
  every configured instrument (deduplicated by natural key). `15m` and `1h`
  candles are retained far enough back to establish history and measure the
  weekend window; `1d` is used for history checks only. Binance Vision archives
  for the controls carry full `1m` history (see §2.2).
- The probe is dry-run by default. `--live` is required to send requests.
- Polite rate limit: **≤ 2 requests/second**, exponential backoff with jitter on
  network errors/429/5xx and `Retry-After` support. 401/403 fail immediately.
- Empty windows are skipped in `--coarse-days` steps. The first non-empty window
  gives the earliest record; the report records the probe floor and `truncated`
  so a missing result is never presented as proof of no history.
- The API is undocumented/unofficial; treat schema changes as a monitored risk
  and fail closed on missing fields.

### 2.2 Binance Vision (controls only)

`https://data.binance.vision` S3-style archive listing. Files are downloaded by
the P2 job (not by the P0 probe):

| Dataset | Path template |
|---|---|
| USD-M 1h klines | `data/futures/um/monthly/klines/{SYMBOL}/1h/{SYMBOL}-1h-YYYY-MM.zip` (daily under `.../daily/...`) |
| USD-M 1m klines | `data/futures/um/monthly/klines/{SYMBOL}/1m/{SYMBOL}-1m-YYYY-MM.zip` — **full 1m history** for the controls |
| Funding rate | `data/futures/um/monthly/fundingRate/{SYMBOL}/{SYMBOL}-fundingRate-YYYY-MM.zip` |
| Metrics (OI, long/short ratios) | `data/futures/um/monthly/metrics/{SYMBOL}/{SYMBOL}-metrics-YYYY-MM.zip` |

The probe lists monthly archives, then refines the first month to the first
available **daily** archive. It records the archive key, month and day. Rate
limit and retries are the same as Hyperliquid; archive downloads in P2 must be
bounded and checksummed.

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

### 2.4 What is not available

- Historical Hyperliquid open interest (current only). See §8 for options.
- A canonical perp listing timestamp; the first candle/funding record is used as
  a lower bound.
- A stable funding interval across venues; store `funding_interval_hours` per row.
- Corporate-action semantics for HIP-3 perps (splits, index changes). Treat a
  discontinuity as a data-quality event until verified; never silently adjust.

### 2.5 Measured history (probe, 2026-10-21)

The live probe recorded the following lower bounds. They are **first
observations**, not listing dates, and `n/a` would mean "not found within the
probe budget", never "no history".

| Stream | Earliest measured | What it means for the design |
|---|---|---|
| Hyperliquid `1d` candles (company perps) | NVDA 2025-11-12; latest instrument 2026-10-06 | Per-instrument start differs. NVDA has ~49 weekends through 2026-10-16; 23 instruments have a first `1d` candle on or after 2026-07-20 (at most 13 weekends). |
| Hyperliquid funding | NVDA 2025-11-12 21:00 UTC | Funding starts with the listing; no deeper backfill exists. |
| Hyperliquid `1h` candles | 2026-03-27 09:00 UTC for the oldest instruments | The public API returns at most 5,000 candles per interval (~208 days of `1h`), so `1h` history is a recent window only. |
| Binance USD-M `1h` klines (controls) | 2020-01 monthly archive | Full control history; archive existence verified 2026-10-21 (the probe records the first month/day once the S3 listing is fixed). |
| Binance USD-M funding (controls) | 2020-01 monthly archive | Same. |
| Binance USD-M metrics (controls) | 2021-12 monthly archive | OI / long-short metrics are later than klines and funding. |
| Hyperliquid `1m` candles | ~3.5 days rolling | Forward capture only; never a backfill source. |

The commodity perps are part of the same probe run and are reported in their
own section; the 2026-10-21 measurement above covers the company perps because
that run predates the commodity section.

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
are listed separately with citations; they are not rule-derived.

**PIT convention.** Perp bars are 24/7 UTC. A 1h bar is available at its
`bar_end_ts`. For a weekend `[start, end)`, the feature `prediction_ts` is
`end - 1 microsecond`, so only bars with `bar_end_ts <= prediction_ts` may be
used. The partial 09:00-09:30 ET bar on Monday is therefore excluded; the last
complete bar ends at 09:00 ET. The label is known at `end`.

## 4. Architecture

The diagram is [`docs/data/perps_architecture.html`](perps_architecture.html)
(self-contained HTML + inline SVG, planned components dashed). The flow:

```text
Hyperliquid info API (15m/1h; daily 1m forward capture) ─┐
Binance Vision (full 1m history for controls) ──────────┼─> Bronze append-only ─> Silver canonical ─> Gold PIT features ─> Research eval
Existing equity/options + Massive ETF wrappers ─────────┘                                     ▲
NYSE calendar + perp universe config (78 + 8 + 2) ───────────────────────────────────────────┘
```

### 4.1 Bronze schemas (append-only)

All timestamps UTC. Every row carries `ingest_ts`, `run_id`, `payload_hash`; a
changed payload for an existing natural key is appended as a correction
observation (never updated in place). Partition by `ingest_date` (and `interval`
where noted).

#### `bronze_perp_candles`

| Column | Type | Notes |
|---|---|---|
| `ingest_ts` | TIMESTAMP | ingestion time |
| `run_id` | STRING | manifest run id |
| `venue` | STRING | `hyperliquid` |
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
| `open`,`high`,`low`,`close` | DECIMAL(28,10) | provider values |
| `volume` | DECIMAL(28,10) | base units |
| `trade_count` | BIGINT | provider `n` |
| `request_start_ts` | TIMESTAMP | paging cursor used for the request |
| `payload_hash` | STRING | sha256 of the raw record |

Natural key: `(venue, symbol, interval, candle_start_ts)`. Partition:
`interval, ingest_date`. `1m` rows exist only from the daily forward-capture
job onward (API retention ~3.5 days); `15m`/`1h` carry history.

#### `bronze_perp_funding`

| Column | Type | Notes |
|---|---|---|
| `ingest_ts` | TIMESTAMP | |
| `run_id` | STRING | |
| `venue` | STRING | `hyperliquid` |
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
| `payload_hash` | STRING | |

Natural key: `(venue, symbol, funding_time)`. Partition: `ingest_date`.

#### `bronze_perp_oi_snapshots`

| Column | Type | Notes |
|---|---|---|
| `ingest_ts` | TIMESTAMP | |
| `observed_at` | TIMESTAMP | snapshot time (UTC) |
| `venue` | STRING | |
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
| `source` | STRING | `forward_snapshot` / `s3_backfill` |
| `payload_hash` | STRING | |

Natural key: `(venue, symbol, observed_at, source)`. Partition: `ingest_date`.
This table starts empty; P4 populates it.

#### `bronze_binance_um_klines`

| Column | Type | Notes |
|---|---|---|
| `ingest_ts`, `run_id` | TIMESTAMP, STRING | |
| `symbol` | STRING | `BTCUSDT` / `ETHUSDT` |
| `interval` | STRING | `1h` |
| `open_time`, `close_time` | TIMESTAMP | archive fields (UTC) |
| `open`,`high`,`low`,`close` | DECIMAL(28,10) | |
| `volume`, `quote_volume` | DECIMAL(28,10) | |
| `trade_count` | BIGINT | |
| `taker_buy_base`, `taker_buy_quote` | DECIMAL(28,10) | |
| `archive_key` | STRING | source zip key |
| `payload_hash` | STRING | |

Natural key: `(symbol, interval, open_time)`.

#### `bronze_binance_um_funding`

`ingest_ts`, `run_id`, `symbol`, `calc_time`, `funding_interval_hours`,
`last_funding_rate`, `archive_key`, `payload_hash`.
Natural key: `(symbol, calc_time)`.

#### `bronze_binance_um_metrics`

`ingest_ts`, `run_id`, `symbol`, `create_time`, `sum_open_interest`,
`sum_open_interest_value`, `count_toptrader_long_short_ratio`,
`sum_toptrader_long_short_ratio`, `count_long_short_ratio`,
`sum_taker_long_short_vol_ratio`, `archive_key`, `payload_hash`.
Natural key: `(symbol, create_time)`.

### 4.2 Silver schemas (canonical, deduplicated)

#### `silver_perp_bars_1h`

| Column | Type | Notes |
|---|---|---|
| `venue`, `dex`, `symbol`, `ticker` | STRING | |
| `instrument_type`, `underlying_type`, `underlying_symbol`, `contract_symbol` | STRING | NOT NULL; `instrument_type = perpetual_future`; `contract_symbol = symbol` |
| `bar_start_ts`, `bar_end_ts` | TIMESTAMP | UTC |
| `open`,`high`,`low`,`close` | DECIMAL(28,10) | perp mark/trade price, **not** the stock price |
| `volume` | DECIMAL(28,10) | |
| `trade_count` | BIGINT | |
| `information_available_ts` | TIMESTAMP | `bar_end_ts` (conservative) |
| `source` | STRING | `hyperliquid` |
| `ingest_ts` | TIMESTAMP | latest selected observation |
| `quality_flags` | ARRAY<STRING> | `gap`, `stale`, `duplicate`, `split_suspect` |

Natural key: `(venue, symbol, bar_start_ts)`. Partition: `date(bar_start_ts)`.
Select the latest valid Bronze observation per key; keep flags rather than
dropping rows.

#### `silver_perp_funding`

`venue`, `dex`, `symbol`, `ticker`, `instrument_type`, `underlying_type`,
`underlying_symbol`, `contract_symbol`, `funding_time`, `funding_rate`,
`funding_interval_hours`, `information_available_ts` (= `funding_time`),
`source`, `ingest_ts`, `quality_flags`.
Natural key: `(venue, symbol, funding_time)`.

### 4.3 Gold schema

#### `gold_weekend_perp_features`

One row per `(weekend_id, security_id)`.

| Group | Columns |
|---|---|
| Keys | `weekend_id` (Friday date), `security_id`, `ticker`, `perp_symbol`, `venue`, `dex` |
| Window | `window_start_ts`, `window_end_ts`, `prediction_ts` (= `window_end_ts - 1µs`) |
| Perp price | `perp_first_px`, `perp_last_px`, `perp_ret_weekend`, `perp_ret_fri_close_to_sat`, `perp_ret_sun_to_mon`, `perp_high`, `perp_low`, `perp_range`, `perp_max_drawdown` |
| Perp risk | `perp_realized_vol_1h`, `perp_volume_base`, `perp_trade_count`, `perp_bar_count`, `perp_gap_count` |
| Funding | `funding_sum`, `funding_mean`, `funding_last`, `funding_count`, `funding_interval_hours` |
| OI (P4, nullable) | `oi_start`, `oi_end`, `oi_change_pct` |
| Controls | `btc_ret_weekend`, `eth_ret_weekend`, `btc_realized_vol_1h`, `eth_realized_vol_1h` |
| Equity baselines (PIT) | `friday_adj_close`, `friday_ret_1d`, `friday_ret_5d`, `friday_iv_atm`, `friday_iv_skew`, `friday_options_volume_z`, `equity_features_available_ts` |
| Label | `monday_open`, `monday_gap`, `label_available_ts` (= `window_end_ts`) |
| Governance | `instrument_type` (NOT NULL `perpetual_future`), `underlying_type`, `underlying_symbol`, `contract_symbol`, `venue`, `mapping_status` (`verified` / `unverified`), `information_available_ts`, `feature_version`, `ingest_ts` |

Natural key: `(weekend_id, security_id)`. Partition: `weekend_id`.
`information_available_ts` is the maximum of the component availability
timestamps and must satisfy `information_available_ts <= prediction_ts`; the
loader rejects rows that violate it. All perp-derived columns use the `perp_`
prefix, and the table comment starts with "Perpetual futures (derivatives), not
equities:" with tags `instrument_type=perpetual_future`,
`asset_class=derivative`; price columns are commented "perp mark/trade price,
not the stock price".

Feature definitions (all computed from rows with `bar_end_ts <=
prediction_ts`):

- `perp_ret_weekend = last_close / first_open - 1` over the window.
- `perp_ret_fri_close_to_sat`: first close at/after the window start divided by
  the first open, minus 1; `perp_ret_sun_to_mon` is the analogous tail return.
- `perp_realized_vol_1h = stdev(log returns of 1h closes)` (sample, requires at
  least 12 bars; otherwise null + flag).
- `perp_max_drawdown = min(close / running_max - 1)`.
- `funding_sum/mean/last` over funding records in `[start, end)`.
- `oi_change_pct = oi_end / oi_start - 1` only when both endpoints exist.
- Controls are the same calculations on `BTCUSDT`/`ETHUSDT` (Binance 1h bars,
  filtered to the same UTC window).
- Cross-sectional z-scores (by `weekend_id`) are derived in the research layer,
  not stored as raw features.

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
   `information_available_ts <= prediction_ts`. No forward fill of missing bars;
   a missing bar is a flag, not an interpolation.
2. **Friday equity/options features:** join as-of the Friday session close using
   the existing `information_available_ts`; require it to be `<= prediction_ts`.
   Do not use Monday data in a Friday feature.
3. **Label:** `monday_gap` is computed from the Monday open and is available only
   at `window_end_ts`. It must never appear in a feature column or a model input.
4. **Mapping:** use the bridge row valid at `prediction_ts`
   (`valid_from <= prediction_ts < valid_to`).
5. **Evaluation:** out-of-time split by `weekend_id`; no random shuffling.
6. **Controls:** BTC/ETH features use the same UTC window, so any perp signal
   must beat the crypto-only baseline, not just the equity-only baseline.

### 6.1 Statistical power (measured 2026-10-21)

History limits the claim the study can support. Pooled across the 78 company
perps the measured window gives roughly **1.9k company-weekends** through the
2026-10-16 weekend (NVDA has at most ~49; 23 instruments have at most 13).
After requiring a complete Friday equity/options baseline, a verified mapping,
non-sparse weekend bars and the BTC/ETH controls, the effective sample is closer
to **1.5–2k company-weekends**, and most individual instruments have too few
weekends for instrument-level inference.

The panel is therefore unbalanced and clustered by weekend (common market and
crypto shocks). P6 must evaluate with weekend-blocked/out-of-time splits, report
the effective sample and uncertainty per model, and treat a null or unstable
result as the likely outcome. This is a power caveat, not an invitation to pool
instruments without clustering: the design cannot detect a small incremental
`R²` from weekend perp features with this history, so pre-register what effect
size would be meaningful and report an honest negative result.

## 7. PR slices

| Slice | Scope | Acceptance |
|---|---|---|
| **P0 (this round)** | `config/perp_universe.yaml` v4 + typed loader (instrument_type, underlying_type, commodities, tiers A-D, flags); static NYSE calendar; `scripts/perps/check_universe.py`; `scripts/perps/probe_history.py`; `scripts/perps/measure_closed_liquidity.py`; this plan; architecture diagram; ontology terms; tests. | `pytest -q -m "not spark and not lakebase and not databricks"` (plain and with pyspark blocked); probe/measure `--dry-run`; no pandas/duckdb imports; calendar `--check`; loader loads 78 companies + 8 commodities + 2 controls; ontology test green. |
| **P2** | Bronze ingestion jobs for Hyperliquid 15m/1h candles and funding, **daily 1m forward capture** (API retains only ~3.5 days), and Binance USD-M archives (full 1m history); manifest, idempotency, bounded backfill, archive checksums. No OI history. | Re-running a run id creates zero duplicate Bronze rows; rate limits respected; partial writes retryable; 1m capture gap alarms; DQ report on missing/duplicate bars. |
| **P3** | Silver normalization: 1h bars, funding, QA flags (gaps, DST, stale marks, split suspects), canonical dedupe. | Natural keys unique; `information_available_ts` equals bar close; QA counts match Bronze source counts; no forward fill. |
| **P4** | OI: forward `metaAndAssetCtxs` snapshots into `bronze_perp_oi_snapshots`; optional S3 archive backfill behind owner approval. | Snapshot cadence documented; no fabricated history; `oi_change_pct` null when endpoints missing. |
| **P5** | `gold_weekend_perp_features`: weekend windows, PIT joins, equity/options baselines, BTC/ETH controls, label; mapping bridge. | Window boundaries match `market_calendar` fixtures; every row passes `information_available_ts <= prediction_ts`; label never in feature columns; reconciliation counts. |
| **P6** | Research evaluation: baseline models (Friday equity/options; + crypto; + perps), out-of-time metrics, ablations, notebook, owner review. | Pre-registered metrics; no signal publication; reproducible notebook and data snapshot; honest negative result allowed. |

Dependencies: P2 → P3 → P4/P5 → P6. P0 is standalone. OI is optional for P5;
`oi_*` stays nullable until P4.

## 8. Open interest options (owner decision)

Hyperliquid's public info API exposes **current** OI only; there is no
historical OI series to backfill from the API, and P0 ships no OI data. Options:

1. **Forward snapshots (recommended default):** poll `metaAndAssetCtxs` on a
   schedule (e.g. every 5-15 minutes) into `bronze_perp_oi_snapshots`. No
   back-history; starts when the poller is deployed. Low cost, immutable.
2. **S3 archive backfill:** Hyperliquid publishes node data to S3; requester-pays
   access may include historical OI. Verify licence, retention, schema and egress
   cost before use. Backfilled rows are labelled `source='s3_backfill'`.
3. **Candle-derived proxy:** do not call it OI. If used, name it explicitly
   (`volume_imbalance_proxy`) and document that it is not open interest.

The probe records these options in `docs/data/perps_history_probe.json` and does
not attempt an OI history fetch.

## 9. Risks and limitations

- **Survivorship / selection:** the universe is the 2026-10-21 liquid subset;
  tier D / sparse perps may have wide spreads and stale marks. Report liquidity
  flags and run results with/without the illiquid names.
- **Short history:** HIP-3 equity perps are recent; the probe establishes the
  true per-instrument start. Do not assume a common start date.
- **24/7 microstructure:** weekend marks may be noisy or stale; measure bar
  coverage and gap counts, and exclude windows below a minimum bar count in
  sensitivity tests.
- **Crypto confounding:** equity perps trade alongside crypto; BTC/ETH controls
  are mandatory, not optional.
- **Corporate actions:** splits/index changes may create price jumps; flag and
  review rather than auto-adjust.
- **Provider instability:** unofficial APIs can change fields or limits; fail
  closed, monitor the probe and ingestion manifest.
- **Minute-bar retention:** the public API keeps only ~3.5 days of `1m`
  candles. Historical minute work is impossible without the daily forward
  capture (P2) or Binance archives (controls only); use `15m`/`1h` for history.
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
python -m config.market_calendar --check
# coordinator only, live network:
python scripts/perps/probe_history.py --live \
  --out-json docs/data/perps_history_probe.json \
  --out-md docs/data/perps_history_probe.md
python scripts/perps/measure_closed_liquidity.py --live \
  --out docs/data/perp_liquidity_tier_proposal.json
```

The probe is not run in tests. `--dry-run` is the default and makes zero network
calls; `--live` enforces ≤ 2 requests/second with retries/backoff. The liquidity
tool writes a proposal only (`docs/data/perp_liquidity_tier_proposal.json`);
applying it to `config/perp_universe.yaml` is an owner edit.
